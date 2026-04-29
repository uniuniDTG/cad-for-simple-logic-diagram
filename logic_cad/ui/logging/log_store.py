"""UI log store and process stream capture utilities."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
import io
import logging
import sys
import threading
from typing import TextIO

LOG_LEVEL_ORDER: dict[str, int] = {
    "DEBUG": 10,
    "INFO": 20,
    "WARN": 30,
    "ERROR": 40,
}


def normalize_log_level(level: str) -> str:
    """Normalize a log level name.

    Args:
        level: Input level string.

    Returns:
        One of ``DEBUG``, ``INFO``, ``WARN``, ``ERROR``.
    """
    up = (level or "").strip().upper()
    if up == "WARNING":
        up = "WARN"
    if up in LOG_LEVEL_ORDER:
        return up
    return "INFO"


def includes_level(min_level: str, entry_level: str) -> bool:
    """Return whether ``entry_level`` passes ``min_level`` filter.

    Args:
        min_level: Threshold level.
        entry_level: Candidate entry level.

    Returns:
        True when the candidate level is at least the threshold.
    """
    min_norm = normalize_log_level(min_level)
    entry_norm = normalize_log_level(entry_level)
    return LOG_LEVEL_ORDER[entry_norm] >= LOG_LEVEL_ORDER[min_norm]


def _to_logging_level(level: str) -> int:
    norm = normalize_log_level(level)
    return {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARN": logging.WARNING,
        "ERROR": logging.ERROR,
    }[norm]


def _from_logging_level(level: int) -> str:
    if level <= logging.DEBUG:
        return "DEBUG"
    if level <= logging.INFO:
        return "INFO"
    if level <= logging.WARNING:
        return "WARN"
    return "ERROR"


def set_global_log_level(level: str) -> str:
    """Set root logger level and return normalized level."""
    norm = normalize_log_level(level)
    logging.getLogger().setLevel(_to_logging_level(norm))
    return norm


def get_global_log_level() -> str:
    """Return root logger level as ``DEBUG``/``INFO``/``WARN``/``ERROR``."""
    root = logging.getLogger()
    level = root.getEffectiveLevel()
    return _from_logging_level(level)


@dataclass(frozen=True, slots=True)
class UiLogEntry:
    """Single UI log record."""

    timestamp: str
    level: str
    source: str
    message: str


class UiLogStore:
    """Thread-safe ring buffer for UI-visible logs.

    New records are appended into both:
    - a full ring buffer for history/snapshot reads
    - a pending queue consumed by timer-driven UI refresh
    """

    def __init__(self, max_entries: int = 10_000) -> None:
        self._max_entries = max(1, int(max_entries))
        self._entries: deque[UiLogEntry] = deque(maxlen=self._max_entries)
        self._pending: deque[UiLogEntry] = deque()
        self._lock = threading.Lock()

    @property
    def max_entries(self) -> int:
        """Maximum number of rows retained in history."""
        return self._max_entries

    def append(self, level: str, source: str, message: str) -> None:
        """Append one or more log lines.

        Args:
            level: Log level.
            source: Log source label.
            message: Message text. Multi-line input is split into records.
        """
        level_norm = normalize_log_level(level)
        source_norm = (source or "app").strip() or "app"
        lines = str(message).splitlines()
        if not lines:
            lines = [str(message)]
        now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        with self._lock:
            for line in lines:
                if not line:
                    continue
                entry = UiLogEntry(
                    timestamp=now,
                    level=level_norm,
                    source=source_norm,
                    message=line,
                )
                self._entries.append(entry)
                self._pending.append(entry)

    def snapshot(self, min_level: str = "DEBUG") -> list[UiLogEntry]:
        """Read a filtered copy of retained entries."""
        min_norm = normalize_log_level(min_level)
        with self._lock:
            return [entry for entry in self._entries if includes_level(min_norm, entry.level)]

    def pop_pending(self, max_items: int = 400) -> list[UiLogEntry]:
        """Pop up to ``max_items`` newly appended entries."""
        limit = max(1, int(max_items))
        out: list[UiLogEntry] = []
        with self._lock:
            while self._pending and len(out) < limit:
                out.append(self._pending.popleft())
        return out

    def clear(self) -> None:
        """Clear retained and pending records."""
        with self._lock:
            self._entries.clear()
            self._pending.clear()


class _StreamRedirector(io.TextIOBase):
    """Text stream wrapper that forwards writes to ``UiLogStore`` line-by-line."""

    def __init__(
        self,
        store: UiLogStore,
        *,
        level: str,
        source: str,
        forward_stream: TextIO | None,
    ) -> None:
        super().__init__()
        self._store = store
        self._level = normalize_log_level(level)
        self._source = source
        self._forward_stream = forward_stream
        self._buffer = ""
        self._emit_lock = threading.Lock()

    @property
    def encoding(self) -> str:  # type: ignore[override]
        """Expose encoding of the wrapped stream when available."""
        if self._forward_stream is None:
            return "utf-8"
        return getattr(self._forward_stream, "encoding", "utf-8")

    def isatty(self) -> bool:
        if self._forward_stream is None:
            return False
        try:
            return bool(self._forward_stream.isatty())
        except Exception:
            return False

    def fileno(self) -> int:
        if self._forward_stream is None:
            raise OSError("No backing file descriptor")
        return self._forward_stream.fileno()

    def writable(self) -> bool:
        return True

    def write(self, s: str) -> int:
        """Write text into the log store and optional forward stream."""
        text = str(s)
        if self._forward_stream is not None:
            self._forward_stream.write(text)
        with self._emit_lock:
            self._buffer += text
            while "\n" in self._buffer:
                line, self._buffer = self._buffer.split("\n", 1)
                line = line.rstrip("\r")
                if line:
                    self._store.append(self._level, self._source, line)
        return len(text)

    def flush(self) -> None:
        """Flush wrapped stream and emit trailing partial line."""
        if self._forward_stream is not None:
            self._forward_stream.flush()
        with self._emit_lock:
            if self._buffer:
                line = self._buffer.rstrip("\r")
                self._buffer = ""
                if line:
                    self._store.append(self._level, self._source, line)


@dataclass(slots=True)
class StreamCaptureHandle:
    """Handle for installed process stream capture."""

    stdout_original: TextIO
    stderr_original: TextIO
    stdout_redirector: _StreamRedirector
    stderr_redirector: _StreamRedirector

    def uninstall(self) -> None:
        """Restore original ``sys.stdout`` and ``sys.stderr`` once."""
        global _STREAM_CAPTURE_HANDLE
        if sys.stdout is self.stdout_redirector:
            self.stdout_redirector.flush()
            sys.stdout = self.stdout_original
        if sys.stderr is self.stderr_redirector:
            self.stderr_redirector.flush()
            sys.stderr = self.stderr_original
        if _STREAM_CAPTURE_HANDLE is self:
            _STREAM_CAPTURE_HANDLE = None


_UI_LOG_STORE: UiLogStore | None = None
_STREAM_CAPTURE_HANDLE: StreamCaptureHandle | None = None
_LOGGING_HANDLER: logging.Handler | None = None


def get_ui_log_store() -> UiLogStore:
    """Return process-wide singleton log store."""
    global _UI_LOG_STORE
    if _UI_LOG_STORE is None:
        _UI_LOG_STORE = UiLogStore()
    return _UI_LOG_STORE


def install_process_stream_capture(*, forward_to_original: bool = True) -> StreamCaptureHandle:
    """Install global ``stdout``/``stderr`` capture once per process.

    Args:
        forward_to_original: If True, keep writing to original streams in addition
            to UI capture.

    Returns:
        Installed capture handle (existing handle if already installed).
    """
    global _STREAM_CAPTURE_HANDLE
    if _STREAM_CAPTURE_HANDLE is not None:
        return _STREAM_CAPTURE_HANDLE
    store = get_ui_log_store()
    stdout_original = sys.stdout
    stderr_original = sys.stderr
    stdout_redirector = _StreamRedirector(
        store,
        level="INFO",
        source="stdout",
        forward_stream=stdout_original if forward_to_original else None,
    )
    stderr_redirector = _StreamRedirector(
        store,
        level="ERROR",
        source="stderr",
        forward_stream=stderr_original if forward_to_original else None,
    )
    sys.stdout = stdout_redirector
    sys.stderr = stderr_redirector
    _STREAM_CAPTURE_HANDLE = StreamCaptureHandle(
        stdout_original=stdout_original,
        stderr_original=stderr_original,
        stdout_redirector=stdout_redirector,
        stderr_redirector=stderr_redirector,
    )
    return _STREAM_CAPTURE_HANDLE


class _UiLogHandler(logging.Handler):
    """Logging handler that forwards records into ``UiLogStore``."""

    def __init__(self, store: UiLogStore) -> None:
        super().__init__(level=logging.DEBUG)
        self._store = store

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = normalize_log_level(record.levelname)
            source = record.name or "logging"
            message = record.getMessage()
            if not message:
                return
            self._store.append(level, source, message)
        except Exception:
            self.handleError(record)


def install_python_logging_bridge(*, default_level: str = "INFO") -> logging.Handler:
    """Install root logging bridge to UI store (idempotent)."""
    global _LOGGING_HANDLER
    if _LOGGING_HANDLER is not None:
        return _LOGGING_HANDLER
    store = get_ui_log_store()
    handler = _UiLogHandler(store)
    root = logging.getLogger()
    root.addHandler(handler)
    set_global_log_level(default_level)
    _LOGGING_HANDLER = handler
    return handler
