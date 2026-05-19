"""Crosshair overlay visibility on DiagramView (regression for viewport-child bug)."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QGraphicsScene

from logic_cad.tests.support.qt_offscreen import ensure_qapplication_offscreen
from logic_cad.ui.app_user_settings import (
    AppUserSettings,
    CrosshairMode,
    DEFAULT_CROSSHAIR_LOCAL_HALF_EXTENT_PX,
)
from logic_cad.ui.views.diagram_view import DiagramView


def _image_has_nontransparent_pixels(img: QImage) -> bool:
    """Return True when *img* contains at least one non-transparent pixel."""
    if img.isNull():
        return False
    for y in range(img.height()):
        for x in range(img.width()):
            if img.pixelColor(x, y).alpha() > 0:
                return True
    return False


def test_crosshair_overlay_paints_after_apply_settings() -> None:
    """FULL crosshair draws ink on the overlay without opening the settings dialog."""
    ensure_qapplication_offscreen()
    view = DiagramView()
    view.setScene(QGraphicsScene())
    view.resize(320, 240)
    view.show()
    settings = AppUserSettings(
        crosshair_mode=CrosshairMode.FULL,
        crosshair_local_half_extent_px=DEFAULT_CROSSHAIR_LOCAL_HALF_EXTENT_PX,
        crosshair_center_box_side_px=0,
    )
    view.apply_user_settings(settings)
    center = view.viewport().rect().center()
    view._sync_crosshair_viewport_pos(center)  # noqa: SLF001
    view.repaint()
    overlay = view._crosshair_overlay  # noqa: SLF001
    assert overlay.isVisible()
    assert overlay.parent() is view
    assert overlay.parent() is not view.viewport()
    grabbed = overlay.grab()
    assert _image_has_nontransparent_pixels(grabbed.toImage()), "crosshair overlay produced no pixels"


def test_flush_pointer_feedback_uses_viewport_to_scene() -> None:
    """Timer flush paths must not call QWidget.mapToScene (AttributeError regression)."""
    ensure_qapplication_offscreen()
    view = DiagramView()
    view.setScene(QGraphicsScene())
    view.resize(200, 160)
    view.show()
    center = view.viewport().rect().center()
    view._pending_viewport_pos = center  # noqa: SLF001
    view._flush_pointer_feedback()
    view._flush_port_tooltip()
    assert view._last_scene_pos is not None  # noqa: SLF001
