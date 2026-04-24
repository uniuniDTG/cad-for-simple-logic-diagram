"""Stacked toast notifications (frameless, fade, parent window follow)."""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPoint,
    QPropertyAnimation,
    QTimer,
    Qt,
)
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

MARGIN = 20
GAP = 10

_active_toasts: list[Toast] = []


class Toast(QWidget):
    def __init__(
        self,
        message: str,
        parent_window: QWidget | None = None,
        duration: int = 3000,
    ) -> None:
        super().__init__(None)

        self._parent_window = parent_window
        self._anim: QPropertyAnimation | None = None
        self._pos_anim: QPropertyAnimation | None = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self.label = QLabel(message)
        app_font = QApplication.font()
        self.label.setFont(app_font)
        self.label.setStyleSheet(
            """
            QLabel {
                background-color: rgba(50, 53, 60, 230);
                color: #e0e0e8;
                padding: 12px 20px;
                border-radius: 8px;
            }
            """
        )
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.addWidget(self.label)
        layout.setContentsMargins(0, 0, 0, 0)

        self.adjustSize()

        if self._parent_window is not None:
            self._parent_window.installEventFilter(self)

        self._anim = QPropertyAnimation(self, b"windowOpacity")
        self._anim.setDuration(300)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()

        QTimer.singleShot(duration, self._fade_out)

    def _calc_pos(self) -> tuple[int, int]:
        if self._parent_window is not None:
            geo = self._parent_window.frameGeometry()
            base_x = geo.right() - self.width() - MARGIN
            base_y = geo.bottom() - self.height() - MARGIN
        else:
            screen = QApplication.primaryScreen()
            if screen is None:
                return 0, 0
            avail = screen.availableGeometry()
            base_x = avail.right() - self.width() - MARGIN
            base_y = avail.bottom() - self.height() - MARGIN

        idx = _active_toasts.index(self) if self in _active_toasts else len(_active_toasts)
        offset_y = sum(_active_toasts[i].height() + GAP for i in range(idx))

        return base_x, base_y - offset_y

    def move_to_position(self, animated: bool = False) -> None:
        x, y = self._calc_pos()
        if animated:
            self._pos_anim = QPropertyAnimation(self, b"pos")
            self._pos_anim.setDuration(200)
            self._pos_anim.setStartValue(self.pos())
            self._pos_anim.setEndValue(QPoint(x, y))
            self._pos_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._pos_anim.start()
        else:
            self.move(x, y)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if self._parent_window is not None and obj is self._parent_window:
            if event.type() in (QEvent.Type.Move, QEvent.Type.Resize):
                self.move_to_position(animated=False)
        return super().eventFilter(obj, event)

    def _fade_out(self) -> None:
        self._anim = QPropertyAnimation(self, b"windowOpacity")
        self._anim.setDuration(400)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._anim.finished.connect(self.close)
        self._anim.start()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._parent_window is not None:
            self._parent_window.removeEventFilter(self)
        if self in _active_toasts:
            _active_toasts.remove(self)
            for t in _active_toasts:
                t.move_to_position(animated=True)
        super().closeEvent(event)


def show_toast(
    message: str,
    parent_window: QWidget | None = None,
    duration: int = 3000,
) -> None:
    toast = Toast(message, parent_window=parent_window, duration=duration)
    _active_toasts.append(toast)
    toast.move_to_position(animated=False)
    toast.show()
