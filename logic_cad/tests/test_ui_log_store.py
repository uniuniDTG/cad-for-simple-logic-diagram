"""Tests for UI log store and process stream capture."""

from __future__ import annotations

import io
import logging
import sys

from logic_cad.ui.logging import (
    UiLogStore,
    get_global_log_level,
    get_ui_log_store,
    includes_level,
    install_python_logging_bridge,
    install_process_stream_capture,
    set_global_log_level,
)


def test_ui_log_store_snapshot_and_pending() -> None:
    store = UiLogStore(max_entries=3)
    store.append("INFO", "app", "a1")
    store.append("WARN", "app", "w1\nw2")
    store.append("DEBUG", "app", "d1")

    rows = store.snapshot("DEBUG")
    assert [row.message for row in rows] == ["w1", "w2", "d1"]
    assert [row.level for row in store.snapshot("WARN")] == ["WARN", "WARN"]
    assert includes_level("WARN", "ERROR")
    assert not includes_level("ERROR", "INFO")

    pending = store.pop_pending(max_items=2)
    assert len(pending) == 2
    pending_rest = store.pop_pending(max_items=10)
    assert len(pending_rest) == 2
    assert store.pop_pending(max_items=1) == []


def test_stream_capture_collects_stdout_and_stderr(monkeypatch) -> None:
    fake_stdout = io.StringIO()
    fake_stderr = io.StringIO()
    monkeypatch.setattr(sys, "stdout", fake_stdout)
    monkeypatch.setattr(sys, "stderr", fake_stderr)

    store = get_ui_log_store()
    store.clear()
    handle = install_process_stream_capture(forward_to_original=True)
    try:
        print("hello-ui-log")
        sys.stderr.write("oops-ui-log\n")
        sys.stderr.flush()
    finally:
        handle.uninstall()

    rows = store.snapshot("DEBUG")
    messages = [row.message for row in rows]
    assert "hello-ui-log" in messages
    assert "oops-ui-log" in messages
    assert "hello-ui-log" in fake_stdout.getvalue()
    assert "oops-ui-log" in fake_stderr.getvalue()


def test_logging_bridge_respects_root_level() -> None:
    store = get_ui_log_store()
    store.clear()
    install_python_logging_bridge(default_level="INFO")
    set_global_log_level("WARN")
    logger = logging.getLogger("logic_cad.test.logging_bridge")
    logger.info("suppressed-info")
    logger.error("captured-error")

    rows = store.snapshot("DEBUG")
    messages = [row.message for row in rows]
    assert "captured-error" in messages
    assert "suppressed-info" not in messages
    assert get_global_log_level() == "WARN"

    set_global_log_level("DEBUG")
    logger.debug("captured-debug")
    rows2 = store.snapshot("DEBUG")
    assert any(row.message == "captured-debug" and row.level == "DEBUG" for row in rows2)
