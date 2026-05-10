"""Graphics view for symbol block editing (zoom / pan, cursor DXF coordinates)."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, Qt, Signal
from PySide6.QtGui import QContextMenuEvent, QKeyEvent, QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QLabel, QGraphicsScene, QGraphicsView

from logic_cad.ui.graphics_view_navigation import apply_wheel_pan_scroll_delta, wheel_zoom_multiplier
from logic_cad.ui.snap_utils import dxf_from_scene_pos
from logic_cad.ui.symbol_block_editor.scene import SymbolBlockEditScene


class SymbolBlockEditView(QGraphicsView):
    """Pan/zoom block canvas; reports cursor position in DXF mm like :class:`DiagramView`."""

    cursor_dxf_mm_changed = Signal(object)

    def __init__(self, scene: QGraphicsScene, parent=None) -> None:
        super().__init__(scene, parent)
        self.setObjectName("blockEditCanvasView")
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self._panning = False
        self._last_pan_pos = QPoint()
        self._last_scene_pos: QPointF | None = None
        self._escape_cb = None
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._len_hud = QLabel(self.viewport())
        self._len_hud.hide()
        self._len_hud.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._len_hud.setStyleSheet(
            "QLabel { background-color: #2b2d31; color: #e8eaed; padding: 4px 8px; "
            "border: 1px solid #3d4048; border-radius: 4px; font-size: 11px; }"
        )

    def _update_length_hud(self, cursor_viewport_pos: QPoint) -> None:
        sc = self.scene()
        if not isinstance(sc, SymbolBlockEditScene):
            self._len_hud.hide()
            return
        plen = sc.length_hud_mm()
        if plen is None or plen < 1e-6:
            self._len_hud.hide()
            return
        self._len_hud.setText(f"{plen:.1f} mm")
        self._len_hud.adjustSize()
        pad = 14
        x = int(cursor_viewport_pos.x() + pad)
        y = int(cursor_viewport_pos.y() + pad)
        vr = self.viewport().rect()
        w, h = self._len_hud.width(), self._len_hud.height()
        if x + w > vr.right():
            x = max(0, int(cursor_viewport_pos.x() - w - pad))
        if y + h > vr.bottom():
            y = max(0, int(cursor_viewport_pos.y() - h - pad))
        self._len_hud.move(x, y)
        self._len_hud.show()
        self._len_hud.raise_()

    def set_escape_callback(self, cb) -> None:
        """Register callback invoked on Escape (clears placement tools)."""
        self._escape_cb = cb

    def last_scene_pos_dxf(self) -> tuple[float, float]:
        """DXF mm for last mouse position, or viewport center mapped to scene."""
        if self._last_scene_pos is not None:
            return dxf_from_scene_pos(self._last_scene_pos)
        vc = self.viewport().rect().center()
        return dxf_from_scene_pos(self.mapToScene(vc))

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape and self._escape_cb is not None:
            self._escape_cb()
            event.accept()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            super().wheelEvent(event)
            return
        factor = wheel_zoom_multiplier(delta)
        self.scale(factor, factor)
        event.accept()

    def fit_initial_view(self) -> None:
        """Zoom so the insertion origin ± :data:`~logic_cad.core.model.constants.BLOCK_EDIT_INITIAL_VIEW_HALF_MM` mm fills the view."""
        sc = self.scene()
        if not isinstance(sc, SymbolBlockEditScene):
            return
        r = sc.initial_view_scene_rect()
        if not r.isValid() or r.isEmpty():
            return
        self.resetTransform()
        self.fitInView(r, Qt.AspectRatioMode.KeepAspectRatio)

    def leaveEvent(self, event) -> None:
        """Clear status-bar cursor coordinates when the pointer leaves the view."""
        self._len_hud.hide()
        self.cursor_dxf_mm_changed.emit(None)
        super().leaveEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        sc = self.scene()
        if isinstance(sc, SymbolBlockEditScene):
            gp = (
                event.globalPosition().toPoint()
                if hasattr(event, "globalPosition")
                else event.globalPos()
            )
            if sc.deliver_context_menu(
                self.mapToScene(event.pos()),
                gp,
                self.viewport(),
                self.viewportTransform(),
            ):
                event.accept()
                return
        super().contextMenuEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            sc = self.scene()
            if isinstance(sc, SymbolBlockEditScene):
                r = sc.extent_rect_for_view_fit()
                if r.isValid() and not r.isEmpty():
                    self.fitInView(r, Qt.AspectRatioMode.KeepAspectRatio)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._last_pan_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        self._last_scene_pos = self.mapToScene(event.pos())
        self.cursor_dxf_mm_changed.emit(dxf_from_scene_pos(self._last_scene_pos))
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._panning:
            delta = event.pos() - self._last_pan_pos
            self._last_pan_pos = event.pos()
            apply_wheel_pan_scroll_delta(self, delta)
            self._len_hud.hide()
            event.accept()
            return
        self._last_scene_pos = self.mapToScene(event.pos())
        self.cursor_dxf_mm_changed.emit(dxf_from_scene_pos(self._last_scene_pos))
        super().mouseMoveEvent(event)
        self._update_length_hud(event.pos())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton and self._panning:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)
