"""QGraphicsView with zoom / pan."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPoint, QPointF, QRect, Qt, QTimer, Signal
from PySide6.QtGui import (
    QContextMenuEvent,
    QCursor,
    QEnterEvent,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QResizeEvent,
    QShowEvent,
    QTransform,
    QWheelEvent,
)
from PySide6.QtWidgets import QApplication, QGraphicsItem, QGraphicsScene, QGraphicsView, QLabel
from shiboken6 import isValid as shiboken_is_valid

from logic_cad.ui.app_user_settings import (
    AppUserSettings,
    CrosshairMode,
    DEFAULT_CROSSHAIR_LOCAL_HALF_EXTENT_PX,
)
from logic_cad.ui.graphics_view_navigation import apply_wheel_pan_scroll_delta, wheel_zoom_multiplier
from logic_cad.ui.scene import DiagramScene
from logic_cad.ui.snap_utils import dxf_from_scene_pos
from logic_cad.ui.view_fit_rect import default_a4_fit_rect_mm
from logic_cad.ui.views.crosshair_overlay import CrosshairOverlay, crosshair_paint_bounds

_POINTER_FEEDBACK_INTERVAL_MS = 16
_TOOLTIP_INTERVAL_MS = 50


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
        self._pending_viewport_pos: QPoint | None = None
        self._last_tool_tip: str = ""
        # Overlay must be a child of the view, not the viewport (transparent widgets on the
        # viewport are not composited over QGraphicsView's scene on Windows).
        self._crosshair_overlay = CrosshairOverlay(self)
        self._crosshair_overlay.hide()
        self._pointer_feedback_timer = QTimer(self)
        self._pointer_feedback_timer.setSingleShot(True)
        self._pointer_feedback_timer.setInterval(_POINTER_FEEDBACK_INTERVAL_MS)
        self._pointer_feedback_timer.timeout.connect(self._flush_pointer_feedback)
        self._tooltip_timer = QTimer(self)
        self._tooltip_timer.setSingleShot(True)
        self._tooltip_timer.setInterval(_TOOLTIP_INTERVAL_MS)
        self._tooltip_timer.timeout.connect(self._flush_port_tooltip)

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
        """Refresh crosshair overlay after selection changes (scene chrome is separate)."""
        if self._crosshair_mode == CrosshairMode.NONE:
            return
        self._crosshair_overlay.update()

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

    def _mouse_viewport_pos(self, event: QMouseEvent) -> QPoint:
        """Map a view-space mouse position to viewport pixel coordinates."""
        return self.viewport().mapFrom(self, event.pos())

    def _viewport_pos_to_scene(self, viewport_pos: QPoint) -> QPointF:
        """Convert viewport pixel coordinates to scene coordinates."""
        return self.mapToScene(self.viewport().mapTo(self, viewport_pos))

    def _update_cursor_dxf_status(self, viewport_pos: QPoint) -> None:
        self._last_scene_pos = self._viewport_pos_to_scene(viewport_pos)
        xd, yd = dxf_from_scene_pos(self._last_scene_pos)
        self.cursor_dxf_mm_changed.emit((xd, yd))

    def _sync_crosshair_viewport_pos(self, viewport_pos: QPoint) -> None:
        """Store cursor position and update the viewport overlay (no scene repaint)."""
        self._crosshair_viewport_pos = viewport_pos
        self._crosshair_overlay.sync_cursor_viewport_pos(viewport_pos)
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
        return dxf_from_scene_pos(self._viewport_pos_to_scene(vc))

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
        self._refresh_crosshair_overlay(restyle=True)

    def _refresh_crosshair_overlay(self, *, restyle: bool) -> None:
        """Sync overlay geometry and visibility after layout or settings change.

        Startup calls :meth:`apply_user_settings` before the view is in the window hierarchy;
        :meth:`showEvent` calls this again so the overlay is sized and stacked correctly.

        Args:
            restyle: When True, push mode/size into :class:`CrosshairOverlay` (settings change).

        Returns:
            None
        """

        if restyle:
            self._crosshair_overlay.set_crosshair_style(
                self._crosshair_mode,
                self._crosshair_local_half_px,
                self._crosshair_center_box_side_px,
            )
        vp = self.viewport()
        top_left = vp.mapTo(self, QPoint(0, 0))
        self._crosshair_overlay.setGeometry(QRect(top_left, vp.size()))
        if self._crosshair_mode != CrosshairMode.NONE:
            self._crosshair_overlay.show()
            self._crosshair_overlay.raise_()
            if self._crosshair_viewport_pos is None:
                self._crosshair_viewport_pos = vp.rect().center()
                self._crosshair_overlay.sync_cursor_viewport_pos(self._crosshair_viewport_pos)
        self._wire_len_label.raise_()
        if self._crosshair_viewport_pos is not None:
            self._crosshair_overlay.sync_cursor_viewport_pos(self._crosshair_viewport_pos)
        self._update_crosshair_viewport_cursor()

    def showEvent(self, event: QShowEvent) -> None:
        """Re-apply crosshair overlay once the view is shown (geometry was wrong at early init)."""
        super().showEvent(event)
        self._refresh_crosshair_overlay(restyle=True)

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Realign children and refresh crosshair after the view resizes.

        Args:
            event: Resize event from Qt.

        Returns:
            None
        """

        super().resizeEvent(event)
        self._refresh_crosshair_overlay(restyle=False)

    def fit_a4_page(self) -> None:
        """Reset transform and fit roughly one A4 sheet (mm) in scene coordinates.

        Returns:
            None
        """

        self.setTransform(QTransform())
        self.fitInView(default_a4_fit_rect_mm(), Qt.AspectRatioMode.KeepAspectRatio)
        if self._crosshair_viewport_pos is not None:
            self._crosshair_overlay.sync_cursor_viewport_pos(self._crosshair_viewport_pos)

    def fit_scene_extent_or_default_sheet(self) -> None:
        """Reset transform and fit diagram content with an A4 landscape minimum frame.

        When the scene is a :class:`DiagramScene`, uses
        :meth:`~logic_cad.ui.scene.DiagramScene.extent_rect_for_view_fit`; otherwise
        uses :func:`~logic_cad.ui.view_fit_rect.default_a4_fit_rect_mm`.

        Returns:
            None
        """

        self.setTransform(QTransform())
        sc = self.scene()
        rect = (
            sc.extent_rect_for_view_fit()
            if isinstance(sc, DiagramScene)
            else default_a4_fit_rect_mm()
        )
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        if self._crosshair_viewport_pos is not None:
            self._crosshair_overlay.sync_cursor_viewport_pos(self._crosshair_viewport_pos)

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
        factor = wheel_zoom_multiplier(event.angleDelta().y())
        anchor = self.transformationAnchor()
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.scale(factor, factor)
        self.setTransformationAnchor(anchor)
        if self._crosshair_viewport_pos is not None:
            self._crosshair_overlay.sync_cursor_viewport_pos(self._crosshair_viewport_pos)

    def _pointer_feedback_needs_immediate(self) -> bool:
        if self._pan_anchor is not None:
            return True
        sc = self.scene()
        if sc is not None and sc.mouseGrabberItem() is not None:
            return True
        if isinstance(sc, DiagramScene) and sc.pointer_feedback_needs_immediate_update():
            return True
        return False

    def _schedule_pointer_feedback(self, viewport_pos: QPoint) -> None:
        self._pending_viewport_pos = viewport_pos
        if self._pointer_feedback_needs_immediate():
            self._flush_pointer_feedback()
            return
        if not self._pointer_feedback_timer.isActive():
            self._pointer_feedback_timer.start()

    def _flush_pointer_feedback(self) -> None:
        pos = self._pending_viewport_pos
        if pos is None:
            return
        self._update_cursor_dxf_status(pos)
        sc = self.scene()
        if isinstance(sc, DiagramScene):
            sc.update_pointer_feedback(self._viewport_pos_to_scene(pos))
        self._update_length_hud(pos)

    def _schedule_port_tooltip(self, viewport_pos: QPoint) -> None:
        self._pending_viewport_pos = viewport_pos
        if not self._tooltip_timer.isActive():
            self._tooltip_timer.start()

    def _flush_port_tooltip(self) -> None:
        pos = self._pending_viewport_pos
        if pos is None:
            return
        sc = self.scene()
        if sc is None or not hasattr(sc, "hover_port_hint"):
            return
        hint = sc.hover_port_hint(self._viewport_pos_to_scene(pos))
        if hint == self._last_tool_tip:
            return
        self._last_tool_tip = hint
        self.setToolTip(hint)

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
            self._crosshair_overlay.set_pan_active(True)
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

    def enterEvent(self, event: QEnterEvent) -> None:
        """Track cursor when the pointer enters so crosshair appears without waiting for move."""
        super().enterEvent(event)
        vp = self.viewport()
        pos = vp.mapFromGlobal(QCursor.pos())
        if vp.rect().contains(pos):
            self._pending_viewport_pos = pos
            self._sync_crosshair_viewport_pos(pos)

    def leaveEvent(self, event) -> None:
        self._wire_len_label.hide()
        self._pointer_feedback_timer.stop()
        self._tooltip_timer.stop()
        self._pending_viewport_pos = None
        prev = self._crosshair_viewport_pos
        self._crosshair_viewport_pos = None
        self._crosshair_overlay.sync_cursor_viewport_pos(None)
        if self._crosshair_mode != CrosshairMode.NONE and prev is not None:
            vr = self.viewport().rect()
            b = crosshair_paint_bounds(
                self._crosshair_mode,
                int(prev.x()),
                int(prev.y()),
                vr,
                self._crosshair_local_half_px,
                self._crosshair_center_box_side_px,
            )
            if b.isValid() and not b.isEmpty():
                self._crosshair_overlay.update(b)
        self._update_crosshair_viewport_cursor()
        self._last_tool_tip = ""
        self.setToolTip("")
        self.cursor_dxf_mm_changed.emit(None)
        self._clear_shift_rubber_merge()
        super().leaveEvent(event)

    def mouseMoveEvent(self, event) -> None:
        vp_pos = (
            self._mouse_viewport_pos(event) if isinstance(event, QMouseEvent) else event.pos()
        )
        if self._pan_anchor is not None:
            self._wire_len_label.hide()
            delta = event.pos() - self._pan_anchor
            self._pan_anchor = event.pos()
            apply_wheel_pan_scroll_delta(self, delta)
            self._pending_viewport_pos = vp_pos
            self._update_cursor_dxf_status(vp_pos)
            self._sync_crosshair_viewport_pos(vp_pos)
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
        self._pending_viewport_pos = vp_pos
        self._schedule_pointer_feedback(vp_pos)
        self._schedule_port_tooltip(vp_pos)
        self._sync_crosshair_viewport_pos(vp_pos)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_anchor = None
            self.unsetCursor()
            self._crosshair_overlay.set_pan_active(False)
            self._update_crosshair_viewport_cursor()
            if self._crosshair_viewport_pos is not None:
                self._crosshair_overlay.sync_cursor_viewport_pos(self._crosshair_viewport_pos)
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
        """Middle-button double-click: reset pan/zoom to content extent with A4 floor.

        Args:
            event: Qt mouse event.

        Returns:
            None
        """

        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_anchor = None
            self.unsetCursor()
            self._update_crosshair_viewport_cursor()
            self.fit_scene_extent_or_default_sheet()
            event.accept()
            return
        super().mouseDoubleClickEvent(self._strip_physical_ctrl_modifier(event))
