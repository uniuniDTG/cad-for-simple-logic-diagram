"""Shared helpers for :class:`~PySide6.QtWidgets.QGraphicsView` wheel zoom and pan scrolling.

Editors keep their own event policies (transformation anchors, ``delta_y == 0``, cursors);
this module only holds duplicated numeric factors and scroll-bar math.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QGraphicsView

WHEEL_ZOOM_STEP: float = 1.15
"""Linear scale factor for zoom-in when ``QWheelEvent.angleDelta().y() > 0``; zoom-out uses its reciprocal."""


def wheel_zoom_multiplier(delta_y: int, *, step: float = WHEEL_ZOOM_STEP) -> float:
    """Return the uniform XY scale multiplier for one logical vertical wheel step.

    Args:
        delta_y: ``QWheelEvent.angleDelta().y()``.
        step: Zoom-in multiplier; zoom-out uses ``1.0 / step``.

    Returns:
        Factor suitable for ``QGraphicsView.scale(factor, factor)``.

    Note:
        Views that must *not* zoom when ``delta_y == 0`` should branch before calling this
        (e.g. delegate to ``super().wheelEvent``). Other views may pass ``0`` and receive zoom-out,
        matching a strict ``> 0`` vs else split.
    """

    return step if delta_y > 0 else (1.0 / step)


def apply_wheel_pan_scroll_delta(view: QGraphicsView, delta: QPoint) -> None:
    """Adjust scroll bars so the scene follows a middle-button drag by *delta* viewport pixels.

    Args:
        view: Graphics view whose scroll bars reflect panning.
        delta: Cursor movement in viewport coordinates since the previous sample.

    Returns:
        None
    """

    view.horizontalScrollBar().setValue(view.horizontalScrollBar().value() - delta.x())
    view.verticalScrollBar().setValue(view.verticalScrollBar().value() - delta.y())
