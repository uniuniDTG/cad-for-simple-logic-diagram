"""Modeless log viewer for captured stdout/stderr and app logs."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from logic_cad.ui.logging import (
    LOG_LEVEL_ORDER,
    UiLogEntry,
    UiLogStore,
    get_global_log_level,
    get_ui_log_store,
    set_global_log_level,
)


class LogWindowDialog(QDialog):
    """Display process logs and control root logger level."""

    def __init__(self, parent: QWidget | None = None, *, store: UiLogStore | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("ログ")
        self.setModal(False)
        self.resize(860, 520)

        self._store = store or get_ui_log_store()
        self._logger_level = get_global_log_level()

        root = QVBoxLayout(self)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("loggerレベル"))

        self._level_combo = QComboBox()
        for level in ("DEBUG", "INFO", "WARN", "ERROR"):
            self._level_combo.addItem(level)
        self._level_combo.setCurrentText(self._logger_level)
        self._level_combo.currentTextChanged.connect(self._on_level_changed)
        controls.addWidget(self._level_combo)

        self._follow_tail = QCheckBox("末尾追従")
        self._follow_tail.setChecked(True)
        controls.addWidget(self._follow_tail)

        clear_btn = QPushButton("クリア")
        clear_btn.clicked.connect(self._on_clear_clicked)
        controls.addWidget(clear_btn)
        controls.addStretch(1)
        root.addLayout(controls)

        self._hint = QLabel(
            f"stdout/stderr を含むログを表示します。現在の root logger レベル: {self._logger_level}"
        )
        self._hint.setWordWrap(True)
        root.addWidget(self._hint)

        self._view = QPlainTextEdit()
        self._view.setReadOnly(True)
        self._view.setMaximumBlockCount(min(self._store.max_entries, 20_000))
        root.addWidget(self._view, 1)

        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(80)
        self._flush_timer.timeout.connect(self._on_flush_timer)
        self._flush_timer.start()
        self._reload_all()

    def _format_entry(self, entry: UiLogEntry) -> str:
        return f"[{entry.timestamp}] [{entry.level}] [{entry.source}] {entry.message}"

    def _reload_all(self) -> None:
        rows = self._store.snapshot()
        text = "\n".join(self._format_entry(entry) for entry in rows)
        self._view.setPlainText(text)
        if self._follow_tail.isChecked():
            self._view.moveCursor(QTextCursor.MoveOperation.End)

    def _on_level_changed(self, text: str) -> None:
        level = text.strip().upper()
        if level not in LOG_LEVEL_ORDER:
            level = "INFO"
        self._logger_level = set_global_log_level(level)
        self._hint.setText(
            f"stdout/stderr を含むログを表示します。現在の root logger レベル: {self._logger_level}"
        )

    def _on_clear_clicked(self) -> None:
        self._store.clear()
        self._view.clear()

    def _on_flush_timer(self) -> None:
        pending = self._store.pop_pending(max_items=1200)
        if not pending:
            return
        lines = [self._format_entry(entry) for entry in pending]
        if not lines:
            return
        if self._view.document().blockCount() > 0:
            self._view.appendPlainText("\n".join(lines))
        else:
            self._view.setPlainText("\n".join(lines))
        if self._follow_tail.isChecked():
            self._view.moveCursor(QTextCursor.MoveOperation.End)
