"""QGraphicsView with zoom / pan."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QLineF, QPoint, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QKeyEvent,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPen,
    QResizeEvent,
    QTransform,
    QWheelEvent,
)
from PySide6.QtWidgets import QApplication, QGraphicsItem, QGraphicsScene, QGraphicsView, QLabel
from shiboken6 import isValid as shiboken_is_valid

from logic_cad.core.model.constants import A4_LANDSCAPE_HEIGHT_MM, A4_LANDSCAPE_WIDTH_MM
from logic_cad.ui.app_user_settings import (
    AppUserSettings,
    CrosshairMode,
    DEFAULT_CROSSHAIR_LOCAL_HALF_EXTENT_PX,
)
from logic_cad.ui.scene import DiagramScene
from logic_cad.ui.snap_utils import dxf_from_scene_pos

_CROSSHAIR_PEN_PAD_PX = 3


def _crosshair_paint_bounds(
    mode: CrosshairMode,
    cx: int,
    cy: int,
    vr: QRect,
    local_half_px: int,
    center_box_side_px: int,
    pen_pad: int = _CROSSHAIR_PEN_PAD_PX,
) -> QRect:
    """Return a viewport rectangle covering the crosshair and center box for one cursor position.

    Args:
        mode: Crosshair display mode.
        cx: Cursor x in viewport pixels.
        cy: Cursor y in viewport pixels.
        vr: Viewport rectangle.
        local_half_px: Half arm length for ``LOCAL`` mode (ignored for ``FULL``).
        center_box_side_px: Hollow square side at the intersection (0 = none).
        pen_pad: Extra margin around ink for dirty-region updates.

    Returns:
        Bounding rectangle clipped to the viewport; empty when ``mode`` is ``NONE``.
    """

    if mode == CrosshairMode.NONE:
        return QRect()
    box_r = QRect()
    if center_box_side_px > 0:
        left = cx - center_box_side_px // 2
        top = cy - center_box_side_px // 2
        box_r = QRect(
            left - pen_pad,
            top - pen_pad,
            center_box_side_px + 2 * pen_pad,
            center_box_side_px + 2 * pen_pad,
        )
    if mode == CrosshairMode.FULL:
        h_strip = QRect(vr.left(), cy - pen_pad, vr.width(), 2 * pen_pad + 1)
        v_strip = QRect(cx - pen_pad, vr.top(), 2 * pen_pad + 1, vr.height())
        return h_strip.united(v_strip).united(box_r).intersected(vr)
    h = max(1, local_half_px)
    arm_h = QRect(cx - h - pen_pad, cy - pen_pad, 2 * (h + pen_pad) + 1, 2 * pen_pad + 1)
    arm_v = QRect(cx - pen_pad, cy - h - pen_pad, 2 * pen_pad + 1, 2 * (h + pen_pad) + 1)
    return arm_h.united(arm_v).united(box_r).intersected(vr)


def _paint_crosshair_full_scene_mapped(
    view: QGraphicsView,
    painter: QPainter,
    ix: int,
    iy: int,
    vr: QRect,
    side: int,
) -> None:
    """Draw full-span crosshair in scene coordinates (cosmetic pen = 1 device pixel)."""

    if side <= 0:
        p_h0 = view.mapToScene(QPoint(vr.left(), iy))
        p_h1 = view.mapToScene(QPoint(vr.right(), iy))
        p_v0 = view.mapToScene(QPoint(ix, vr.top()))
        p_v1 = view.mapToScene(QPoint(ix, vr.bottom()))
        painter.drawLine(QLineF(p_h0, p_h1))
        painter.drawLine(QLineF(p_v0, p_v1))
        return
    left = ix - side // 2
    top = iy - side // 2
    right_excl = left + side
    bottom_excl = top + side
    if left - 1 >= vr.left():
        painter.drawLine(
            QLineF(view.mapToScene(QPoint(vr.left(), iy)), view.mapToScene(QPoint(left - 1, iy)))
        )
    if right_excl <= vr.right():
        painter.drawLine(
            QLineF(view.mapToScene(QPoint(right_excl, iy)), view.mapToScene(QPoint(vr.right(), iy)))
        )
    if top - 1 >= vr.top():
        painter.drawLine(
            QLineF(view.mapToScene(QPoint(ix, vr.top())), view.mapToScene(QPoint(ix, top - 1)))
        )
    if bottom_excl <= vr.bottom():
        painter.drawLine(
            QLineF(view.mapToScene(QPoint(ix, bottom_excl)), view.mapToScene(QPoint(ix, vr.bottom())))
        )


def _paint_crosshair_local_scene_mapped(
    view: QGraphicsView,
    painter: QPainter,
    ix: int,
    iy: int,
    h: int,
    side: int,
) -> None:
    """Draw short crosshair arms in scene coordinates."""

    if side <= 0:
        painter.drawLine(
            QLineF(view.mapToScene(QPoint(ix - h, iy)), view.mapToScene(QPoint(ix + h, iy)))
        )
        painter.drawLine(
            QLineF(view.mapToScene(QPoint(ix, iy - h)), view.mapToScene(QPoint(ix, iy + h)))
        )
        return
    left = ix - side // 2
    top = iy - side // 2
    right_excl = left + side
    bottom_excl = top + side
    x_lo, x_hi = ix - h, ix + h
    x2 = min(x_hi, left - 1)
    if x_lo <= x2:
        painter.drawLine(
            QLineF(view.mapToScene(QPoint(x_lo, iy)), view.mapToScene(QPoint(x2, iy)))
        )
    x1 = max(x_lo, right_excl)
    if x1 <= x_hi:
        painter.drawLine(
            QLineF(view.mapToScene(QPoint(x1, iy)), view.mapToScene(QPoint(x_hi, iy)))
        )
    y_lo, y_hi = iy - h, iy + h
    y2 = min(y_hi, top - 1)
    if y_lo <= y2:
        painter.drawLine(
            QLineF(view.mapToScene(QPoint(ix, y_lo)), view.mapToScene(QPoint(ix, y2)))
        )
    y1 = max(y_lo, bottom_excl)
    if y1 <= y_hi:
        painter.drawLine(
            QLineF(view.mapToScene(QPoint(ix, y1)), view.mapToScene(QPoint(ix, y_hi)))
        )


def _paint_crosshair_center_box_scene(
    view: QGraphicsView,
    painter: QPainter,
    ix: int,
    iy: int,
    side: int,
) -> None:
    """Draw the hollow square at the crosshair center in scene coordinates."""

    if side <= 0:
        return
    painter.setBrush(Qt.BrushStyle.NoBrush)
    tl = view.mapToScene(QPoint(ix - side // 2, iy - side // 2))
    br = view.mapToScene(QPoint(ix - side // 2 + side, iy - side // 2 + side))
    painter.drawRect(QRectF(tl, br).normalized())


class DiagramView(QGraphicsView):
    """Pan/zoom view; ``cursor_dxf_mm_changed`` emits DXF mm ``(x, y)``, or ``None`` when the cursor leaves."""

    cursor_dxf_mm_changed = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setRenderHints(
            QPainter.Antialiasing | QPainter.SmoothPixmapTransform,
        )
        # Partial viewport updates scale better than FullViewportUpdate when many items exist.
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self._pan_anchor: QPoint | None = None
        self._escape_clear_wire_tools_cb: Callable[[], None] | None = None
        self._escape_clear_sketch_tools_cb: Callable[[], None] | None = None
        vp = self.viewport()
        self._wire_len_label = QLabel(vp)
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

    def setScene(self, scene: QGraphicsScene | None) -> None:
        """Attach *scene* and repaint crosshair when selection changes (deselect included).

        ``selectionChanged`` uses :attr:`Qt.ConnectionType.QueuedConnection` so synchronous
        selection updates (e.g. in tests) do not re-enter the view paint path and crash on PySide6.

        Args:
            scene: Graphics scene for this view, or ``None`` to clear.

        Returns:
            None
        """

        old = self.scene()
        if old is not None:
            try:
                old.selectionChanged.disconnect(self._on_scene_selection_changed)
            except (TypeError, RuntimeError):
                pass
        super().setScene(scene)
        if scene is not None:
            scene.selectionChanged.connect(
                self._on_scene_selection_changed,
                Qt.ConnectionType.QueuedConnection,
            )

    def _on_scene_selection_changed(self) -> None:
        """Full viewport repaint after selection changes clears dashed outline (incl. deselect)."""

        if self._crosshair_mode == CrosshairMode.NONE:
            return
        self._repaint_crosshair_viewport()

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

    def _repaint_crosshair_viewport(self, dirty: QRect | None = None) -> None:
        """Invalidate viewport paint (scene + :meth:`drawForeground`); *dirty* limits work when set."""

        vp = self.viewport()
        if dirty is not None and dirty.isValid() and not dirty.isEmpty():
            vp.update(dirty)
        else:
            vp.update()

    def _crosshair_viewport_damage_union(self, prev: QPoint | None, cur: QPoint | None) -> QRect:
        """Union of viewport rects that must repaint (scene + crosshair) for one move.

        Args:
            prev: Prior cursor position in viewport pixels, or ``None``.
            cur: New cursor position in viewport pixels, or ``None``.

        Returns:
            Dirty rectangle intersected with the viewport, or empty when not applicable.
        """

        vr = self.viewport().rect()
        mode = self._crosshair_mode
        if mode == CrosshairMode.NONE:
            return QRect()
        local_h = self._crosshair_local_half_px
        side = self._crosshair_center_box_side_px
        rects: list[QRect] = []
        if prev is not None:
            rects.append(
                _crosshair_paint_bounds(
                    mode, int(prev.x()), int(prev.y()), vr, local_h, side
                )
            )
        if cur is not None:
            rects.append(
                _crosshair_paint_bounds(
                    mode, int(cur.x()), int(cur.y()), vr, local_h, side
                )
            )
        if not rects:
            return QRect()
        out = rects[0]
        for r in rects[1:]:
            out = out.united(r)
        return out.intersected(vr)

    def _sync_crosshair_viewport_pos(self, viewport_pos: QPoint) -> None:
        """Store the cursor position and repaint crosshair via :meth:`drawForeground`.

        Uses a small dirty union when possible. While the scene has a mouse grab (e.g. moving a
        symbol), repaints the whole viewport so the selection chrome (blue dashed outline) is not
        left behind under ``SmartViewportUpdate``.

        Args:
            viewport_pos: Cursor position in viewport coordinates.

        Returns:
            None
        """

        if self._crosshair_mode == CrosshairMode.NONE:
            self._crosshair_viewport_pos = viewport_pos
            self._update_crosshair_viewport_cursor()
            return
        if self._pan_anchor is not None:
            self._crosshair_viewport_pos = viewport_pos
            self._update_crosshair_viewport_cursor()
            return

        prev = self._crosshair_viewport_pos
        self._crosshair_viewport_pos = viewport_pos
        sc = self.scene()
        if sc is not None and sc.mouseGrabberItem() is not None:
            self._repaint_crosshair_viewport()
        else:
            dirty = self._crosshair_viewport_damage_union(prev, viewport_pos)
            if dirty.isValid() and not dirty.isEmpty():
                self._repaint_crosshair_viewport(dirty)
            else:
                self._repaint_crosshair_viewport()
        self._update_crosshair_viewport_cursor()

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        """Paint the crosshair after the scene; uses scene coordinates matching the view transform.

        Args:
            painter: Painter provided by ``QGraphicsView`` (scene space).
            rect: Exposed rectangle in scene coordinates.

        Returns:
            None
        """

        super().drawForeground(painter, rect)
        if self._crosshair_mode == CrosshairMode.NONE:
            return
        if self._pan_anchor is not None:
            return
        if self._crosshair_viewport_pos is None:
            return
        vr = self.viewport().rect()
        ix = int(self._crosshair_viewport_pos.x())
        iy = int(self._crosshair_viewport_pos.y())
        side = self._crosshair_center_box_side_px
        painter.save()
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            pen = QPen(QColor(180, 180, 190, 210))
            pen.setWidth(1)
            pen.setCosmetic(True)
            painter.setPen(pen)
            if self._crosshair_mode == CrosshairMode.FULL:
                _paint_crosshair_full_scene_mapped(self, painter, ix, iy, vr, side)
            elif self._crosshair_mode == CrosshairMode.LOCAL:
                h = max(1, self._crosshair_local_half_px)
                _paint_crosshair_local_scene_mapped(self, painter, ix, iy, h, side)
            _paint_crosshair_center_box_scene(self, painter, ix, iy, side)
        finally:
            painter.restore()

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
        """Apply persisted user preferences that affect this view (crosshair).

        Args:
            settings: Application user settings snapshot.

        Returns:
            None
        """

        self._crosshair_mode = settings.crosshair_mode
        self._crosshair_local_half_px = settings.crosshair_local_half_extent_px
        self._crosshair_center_box_side_px = settings.crosshair_center_box_side_px
        self._repaint_crosshair_viewport()
        self._update_crosshair_viewport_cursor()

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Realign children and refresh crosshair after the view resizes.

        Args:
            event: Resize event from Qt.

        Returns:
            None
        """

        super().resizeEvent(event)
        if self._crosshair_mode != CrosshairMode.NONE and self._crosshair_viewport_pos is not None:
            self._repaint_crosshair_viewport()

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
        self._repaint_crosshair_viewport()

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
        self._repaint_crosshair_viewport()

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
            self._repaint_crosshair_viewport()
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
        prev = self._crosshair_viewport_pos
        self._crosshair_viewport_pos = None
        if self._crosshair_mode != CrosshairMode.NONE and prev is not None:
            vr = self.viewport().rect()
            b = _crosshair_paint_bounds(
                self._crosshair_mode,
                int(prev.x()),
                int(prev.y()),
                vr,
                self._crosshair_local_half_px,
                self._crosshair_center_box_side_px,
            )
            self._repaint_crosshair_viewport(b)
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
            self._repaint_crosshair_viewport()
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
