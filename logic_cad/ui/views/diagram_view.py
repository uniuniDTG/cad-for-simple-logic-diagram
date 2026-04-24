"""QGraphicsView with zoom / pan."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QKeyEvent,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPen,
    QTransform,
    QWheelEvent,
)
from PySide6.QtWidgets import QApplication, QGraphicsItem, QGraphicsView, QLabel
from shiboken6 import isValid as shiboken_is_valid

from logic_cad.core.model.constants import A4_LANDSCAPE_HEIGHT_MM, A4_LANDSCAPE_WIDTH_MM
from logic_cad.ui.app_user_settings import (
    AppUserSettings,
    CrosshairMode,
    DEFAULT_CROSSHAIR_LOCAL_HALF_EXTENT_PX,
)
from logic_cad.ui.scene import DiagramScene
from logic_cad.ui.snap_utils import dxf_from_scene_pos


class DiagramView(QGraphicsView):
    """Pan/zoom view; ``cursor_dxf_mm_changed`` emits DXF mm ``(x, y)``, or ``None`` when the cursor leaves."""

    cursor_dxf_mm_changed = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setRenderHints(
            QPainter.Antialiasing | QPainter.SmoothPixmapTransform,
        )
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self._pan_anchor: QPoint | None = None
        self._escape_clear_wire_tools_cb: Callable[[], None] | None = None
        self._escape_clear_sketch_tools_cb: Callable[[], None] | None = None
        self._wire_len_label = QLabel(self.viewport())
        self._wire_len_label.hide()
        self._wire_len_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._wire_len_label.setStyleSheet(
            "QLabel { background-color: #2b2d31; color: #e8eaed; padding: 4px 8px; "
            "border: 1px solid #3d4048; border-radius: 4px; font-size: 11px; }"
        )
        self._last_scene_pos: QPointF | None = None
        self._shift_rubber_merge_active = False
        self._shift_rubber_saved: list[QGraphicsItem] = []
        self._crosshair_mode: CrosshairMode = CrosshairMode.NONE
        self._crosshair_local_half_px: int = DEFAULT_CROSSHAIR_LOCAL_HALF_EXTENT_PX
        self._crosshair_center_box_side_px: int = 0
        self._crosshair_viewport_pos: QPoint | None = None

    def _clear_shift_rubber_merge(self) -> None:
        self._shift_rubber_merge_active = False
        self._shift_rubber_saved.clear()

    def _event_modifiers_include_shift(self, event: QMouseEvent) -> bool:
        """Some platforms omit Shift on QMouseEvent; also consult keyboard state."""
        em = event.modifiers()
        kb = QApplication.keyboardModifiers()
        return bool(
            (em & Qt.KeyboardModifier.ShiftModifier)
            or (kb & Qt.KeyboardModifier.ShiftModifier)
        )

    def _shift_extension_allowed(self, event: QMouseEvent) -> bool:
        """Shift+left: add selection, drag on selected items, or rubber-band merge; off during wire/sketch."""
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        kb = QApplication.keyboardModifiers()
        if kb & Qt.KeyboardModifier.ControlModifier:
            return False
        if not self._event_modifiers_include_shift(event):
            return False
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            return False
        sc = self.scene()
        if not isinstance(sc, DiagramScene):
            return False
        if sc.wire_mode() or sc.manual_wire_mode():
            return False
        if sc.user_sketch_tool() != "none":
            return False
        return True

    def _top_selectable_at_viewport_pos(self, pos: QPoint) -> QGraphicsItem | None:
        """Topmost item or ancestor with ItemIsSelectable."""
        it = self.itemAt(pos)
        while it is not None:
            if it.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable:
                return it
            it = it.parentItem()
        return None

    def _reapply_shift_rubber_saved_selection(self) -> None:
        alive_items: list[QGraphicsItem] = []
        for item in self._shift_rubber_saved:
            if self._safe_select_if_alive(item):
                alive_items.append(item)
        self._shift_rubber_saved = alive_items

    @staticmethod
    def _safe_select_if_alive(item: QGraphicsItem) -> bool:
        """Select item only when its C++ instance is still valid and attached.

        Args:
            item: Candidate graphics item from saved selection snapshots.

        Returns:
            ``True`` when the item was confirmed alive and selected.
        """

        if not shiboken_is_valid(item):
            return False
        try:
            if item.scene() is None:
                return False
            item.setSelected(True)
            return True
        except RuntimeError:
            return False

    def _strip_physical_ctrl_modifier(self, event: QMouseEvent) -> QMouseEvent:
        """Hide real Ctrl from Qt selection so PAGE_REF jump uses keyboard only."""
        if not (QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier):
            return event
        mods = event.modifiers()
        if not (mods & Qt.KeyboardModifier.ControlModifier):
            return event
        ev = QMouseEvent(event)
        ev.setModifiers(mods & ~Qt.KeyboardModifier.ControlModifier)
        return ev

    def _update_length_hud(self, cursor_viewport_pos: QPoint) -> None:
        sc = self.scene()
        if not isinstance(sc, DiagramScene):
            self._wire_len_label.hide()
            return
        plen = sc.length_hud_mm()
        if plen is None or plen < 1e-6:
            self._wire_len_label.hide()
            return
        self._wire_len_label.setText(f"{plen:.1f} mm")
        self._wire_len_label.adjustSize()
        pad = 14
        x = int(cursor_viewport_pos.x() + pad)
        y = int(cursor_viewport_pos.y() + pad)
        vr = self.viewport().rect()
        w, h = self._wire_len_label.width(), self._wire_len_label.height()
        if x + w > vr.right():
            x = max(0, int(cursor_viewport_pos.x() - w - pad))
        if y + h > vr.bottom():
            y = max(0, int(cursor_viewport_pos.y() - h - pad))
        self._wire_len_label.move(x, y)
        self._wire_len_label.show()
        self._wire_len_label.raise_()

    def _update_cursor_dxf_status(self, viewport_pos: QPoint) -> None:
        self._last_scene_pos = self.mapToScene(viewport_pos)
        xd, yd = dxf_from_scene_pos(self._last_scene_pos)
        self.cursor_dxf_mm_changed.emit((xd, yd))

    def _sync_crosshair_viewport_pos(self, viewport_pos: QPoint) -> None:
        """Store the cursor position for crosshair overlay painting.

        Args:
            viewport_pos: Cursor position in viewport coordinates.

        Returns:
            None
        """

        self._crosshair_viewport_pos = viewport_pos
        if self._crosshair_mode != CrosshairMode.NONE:
            self.viewport().update()
        self._update_crosshair_viewport_cursor()

    def _update_crosshair_viewport_cursor(self) -> None:
        """Use a blank viewport cursor while the crosshair is shown; restore during middle-button pan.

        The closed-hand cursor is set on the view during pan; the viewport cursor is cleared so it
        is visible.

        Returns:
            None
        """

        vp = self.viewport()
        if self._pan_anchor is not None:
            vp.unsetCursor()
            return
        if (
            self._crosshair_mode != CrosshairMode.NONE
            and self._crosshair_viewport_pos is not None
        ):
            vp.setCursor(Qt.CursorShape.BlankCursor)
        else:
            vp.unsetCursor()

    def last_scene_pos_dxf(self) -> tuple[float, float]:
        """DXF mm for last mouse position on the canvas, or viewport center if unknown."""
        if self._last_scene_pos is not None:
            return dxf_from_scene_pos(self._last_scene_pos)
        vc = self.viewport().rect().center()
        return dxf_from_scene_pos(self.mapToScene(vc))

    def set_escape_clear_wire_tools_callback(self, cb: Callable[[], None] | None) -> None:
        """When Esc and scene.escape_clears_wiring_tools(), call this (e.g. uncheck wire tool buttons)."""
        self._escape_clear_wire_tools_cb = cb

    def set_escape_clear_sketch_tools_callback(self, cb: Callable[[], None] | None) -> None:
        """Same condition as wire tools: Esc clears sketch palette when no SymbolItem is selected."""
        self._escape_clear_sketch_tools_cb = cb

    def apply_user_settings(self, settings: AppUserSettings) -> None:
        """Apply persisted user preferences that affect this view (crosshair overlay).

        Args:
            settings: Application user settings snapshot.

        Returns:
            None
        """

        self._crosshair_mode = settings.crosshair_mode
        self._crosshair_local_half_px = settings.crosshair_local_half_extent_px
        self._crosshair_center_box_side_px = settings.crosshair_center_box_side_px
        self.viewport().update()
        self._update_crosshair_viewport_cursor()

    def _paint_crosshair_full_with_optional_gap(
        self,
        painter: QPainter,
        cx: int,
        cy: int,
        vr: QRect,
        side: int,
    ) -> None:
        """Draw full-span crosshair; if *side* > 0, omit segments inside the center box."""

        if side <= 0:
            painter.drawLine(vr.left(), cy, vr.right(), cy)
            painter.drawLine(cx, vr.top(), cx, vr.bottom())
            return
        left = cx - side // 2
        top = cy - side // 2
        right_excl = left + side
        bottom_excl = top + side
        if left - 1 >= vr.left():
            painter.drawLine(vr.left(), cy, left - 1, cy)
        if right_excl <= vr.right():
            painter.drawLine(right_excl, cy, vr.right(), cy)
        if top - 1 >= vr.top():
            painter.drawLine(cx, vr.top(), cx, top - 1)
        if bottom_excl <= vr.bottom():
            painter.drawLine(cx, bottom_excl, cx, vr.bottom())

    def _paint_crosshair_local_with_optional_gap(
        self,
        painter: QPainter,
        cx: int,
        cy: int,
        h: int,
        side: int,
    ) -> None:
        """Draw short crosshair arms; if *side* > 0, omit segments inside the center box."""

        if side <= 0:
            painter.drawLine(cx - h, cy, cx + h, cy)
            painter.drawLine(cx, cy - h, cx, cy + h)
            return
        left = cx - side // 2
        top = cy - side // 2
        right_excl = left + side
        bottom_excl = top + side
        x_lo, x_hi = cx - h, cx + h
        x2 = min(x_hi, left - 1)
        if x_lo <= x2:
            painter.drawLine(x_lo, cy, x2, cy)
        x1 = max(x_lo, right_excl)
        if x1 <= x_hi:
            painter.drawLine(x1, cy, x_hi, cy)
        y_lo, y_hi = cy - h, cy + h
        y2 = min(y_hi, top - 1)
        if y_lo <= y2:
            painter.drawLine(cx, y_lo, cx, y2)
        y1 = max(y_lo, bottom_excl)
        if y1 <= y_hi:
            painter.drawLine(cx, y1, cx, y_hi)

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        if self._crosshair_mode == CrosshairMode.NONE:
            return
        if self._crosshair_viewport_pos is None:
            return
        vp = self.viewport()
        with QPainter(vp) as painter:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            pen = QPen(QColor(180, 180, 190, 210))
            pen.setWidth(1)
            pen.setCosmetic(True)
            painter.setPen(pen)
            cx = int(self._crosshair_viewport_pos.x())
            cy = int(self._crosshair_viewport_pos.y())
            vr = vp.rect()
            side = self._crosshair_center_box_side_px
            if self._crosshair_mode == CrosshairMode.FULL:
                self._paint_crosshair_full_with_optional_gap(painter, cx, cy, vr, side)
            elif self._crosshair_mode == CrosshairMode.LOCAL:
                h = max(1, self._crosshair_local_half_px)
                self._paint_crosshair_local_with_optional_gap(painter, cx, cy, h, side)
            if side > 0:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                left = cx - side // 2
                top = cy - side // 2
                painter.drawRect(left, top, side, side)

    def fit_a4_page(self) -> None:
        """Reset transform and fit roughly one A4 sheet (mm) in scene coordinates."""
        self.setTransform(QTransform())
        margin = 12.0
        # DXF y up → scene y down: A4 landscape sheet x∈[0,W], y_scene∈[-H,0]
        rect = QRectF(
            -margin,
            -A4_LANDSCAPE_HEIGHT_MM - margin,
            A4_LANDSCAPE_WIDTH_MM + 2 * margin,
            A4_LANDSCAPE_HEIGHT_MM + 2 * margin,
        )
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            sc = self.scene()
            had_sketch_in_progress = False
            if sc is not None and hasattr(sc, "user_sketch_has_in_progress_geometry"):
                had_sketch_in_progress = sc.user_sketch_has_in_progress_geometry()
            if sc is not None and hasattr(sc, "cancel_wire_rubber"):
                sc.cancel_wire_rubber()
            if sc is not None and hasattr(sc, "cancel_user_sketch"):
                sc.cancel_user_sketch()
            self._wire_len_label.hide()
            if sc is not None and getattr(sc, "escape_clears_wiring_tools", lambda: False)():
                if hasattr(sc, "deselect_user_sketch_items"):
                    sc.deselect_user_sketch_items()
                if self._escape_clear_wire_tools_cb is not None:
                    self._escape_clear_wire_tools_cb()
                if self._escape_clear_sketch_tools_cb is not None and not had_sketch_in_progress:
                    self._escape_clear_sketch_tools_cb()
            event.accept()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        anchor = self.transformationAnchor()
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.scale(factor, factor)
        self.setTransformationAnchor(anchor)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        sc = self.scene()
        if isinstance(sc, DiagramScene):
            # Qt6: globalPosition() -> QPointF; Qt5 / some PySide6 builds: globalPos() -> QPoint only.
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

    def mousePressEvent(self, event) -> None:
        self.setFocus()
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_anchor = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self._update_crosshair_viewport_cursor()
            event.accept()
            return
        if isinstance(event, QMouseEvent) and event.button() == Qt.MouseButton.LeftButton:
            if self._shift_extension_allowed(event):
                hit = self._top_selectable_at_viewport_pos(event.pos())
                sc = self.scene()
                if hit is not None:
                    self._clear_shift_rubber_merge()
                    if not isinstance(sc, DiagramScene):
                        super().mousePressEvent(self._strip_physical_ctrl_modifier(event))
                        return
                    if hit.isSelected():
                        saved = list(sc.selectedItems())
                        super().mousePressEvent(self._strip_physical_ctrl_modifier(event))
                        for it in saved:
                            self._safe_select_if_alive(it)
                        event.accept()
                        return
                    hit.setSelected(True)
                    event.accept()
                    return
                if isinstance(sc, DiagramScene):
                    self._shift_rubber_saved = list(sc.selectedItems())
                    self._shift_rubber_merge_active = True
                    super().mousePressEvent(self._strip_physical_ctrl_modifier(event))
                    event.accept()
                    return
            super().mousePressEvent(self._strip_physical_ctrl_modifier(event))
            return
        super().mousePressEvent(event)

    def leaveEvent(self, event) -> None:
        self._wire_len_label.hide()
        self._crosshair_viewport_pos = None
        if self._crosshair_mode != CrosshairMode.NONE:
            self.viewport().update()
        self._update_crosshair_viewport_cursor()
        self.cursor_dxf_mm_changed.emit(None)
        self._clear_shift_rubber_merge()
        super().leaveEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._pan_anchor is not None:
            self._wire_len_label.hide()
            delta = event.pos() - self._pan_anchor
            self._pan_anchor = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            self._update_cursor_dxf_status(event.pos())
            self._sync_crosshair_viewport_pos(event.pos())
            event.accept()
            return
        if isinstance(event, QMouseEvent):
            super().mouseMoveEvent(self._strip_physical_ctrl_modifier(event))
            if self._shift_rubber_merge_active and (
                event.buttons() & Qt.MouseButton.LeftButton
            ):
                self._reapply_shift_rubber_saved_selection()
        else:
            super().mouseMoveEvent(event)
        self._update_cursor_dxf_status(event.pos())
        sc = self.scene()
        if sc is not None and hasattr(sc, "hover_port_hint"):
            h = sc.hover_port_hint(self.mapToScene(event.pos()))
            self.setToolTip(h)
        self._update_length_hud(event.pos())
        self._sync_crosshair_viewport_pos(event.pos())

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_anchor = None
            self.unsetCursor()
            self._update_crosshair_viewport_cursor()
            event.accept()
            return
        if isinstance(event, QMouseEvent):
            super().mouseReleaseEvent(self._strip_physical_ctrl_modifier(event))
        else:
            super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton and self._shift_rubber_merge_active:
            self._reapply_shift_rubber_saved_selection()
            self._clear_shift_rubber_merge()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Middle-button double-click: reset pan/zoom to full A4 landscape frame."""
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_anchor = None
            self.unsetCursor()
            self._update_crosshair_viewport_cursor()
            self.fit_a4_page()
            event.accept()
            return
        super().mouseDoubleClickEvent(self._strip_physical_ctrl_modifier(event))
