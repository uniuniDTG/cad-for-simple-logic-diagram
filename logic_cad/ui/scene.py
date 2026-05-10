"""Scene bound to LogicDiagram (grid background, wiring, moves).

Printing/PDF (future): render this QGraphicsScene or export the same Drawing as DXF so output matches the editor.
"""

from __future__ import annotations

import os
import math
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from ezdxf import revcloud
from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen, QTransform
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSceneContextMenuEvent,
    QGraphicsSceneMouseEvent,
    QMenu,
    QWidget,
)

from logic_cad.core.geometry.manhattan_metrics import manhattan_distance
from logic_cad.core.model.constants import (
    ENTITY_TYPE_CHECKPOINT,
    ENTITY_TYPE_GATE_INPUT_STUB_ARROW,
    ENTITY_TYPE_INPAGE_REF,
    ENTITY_TYPE_PAPER_FRAME,
    ENTITY_TYPE_TOC_HEADER,
    ENTITY_TYPE_TOC_ROW,
    ENTITY_TYPE_WIRE_ARROW,
    ENTITY_TYPE_WIRE_BRANCH,
    ENTITY_TYPE_USER_ARC,
    ENTITY_TYPE_USER_CIRCLE,
    ENTITY_TYPE_USER_CLOUD,
    ENTITY_TYPE_USER_LINE,
    ENTITY_TYPE_USER_TEXT,
    GRID_PITCH,
    INPAGE_SYM_HEIGHT_MM,
    INPAGE_SYM_HEIGHT_XDATA,
    LAYER_ANNOTATION,
    LAYER_CONTENTS_AREA,
    LAYER_FRAME,
    LAYER_SYMBOL,
    LAYER_VPORT,
    LAYER_WIRE_COM,
    LINETYPE_CONTINUOUS,
    LINETYPE_LOGIC,
    PEER_UID_XDATA,
    TARGET_LAYOUT_XDATA,
    USER_CLOUD_BULGE,
    USER_TEXT_DEFAULT_HEIGHT_MM,
)
from logic_cad.core.logic_diagram import RerouteAfterGeometryChangeError
from logic_cad.core.obstacles import build_routing_obstacles
from logic_cad.core.uid_display import format_uid_display
from logic_cad.core.pages.inpage_ref import refresh_inpage_ref_syms_on_layout
from logic_cad.core.pages.page_order import is_toc_layout_name
from logic_cad.core.pages.page_ref import (
    page_ref_insert_target_unresolved_for_editor,
    refresh_page_ref_syms_on_layout,
)
from logic_cad.core.routing.wire_polyline_geometry import offset_polyline_segment_parallel
from logic_cad.core.services.toc_frame_service import TOC_TEXT_TYPE
from logic_cad.core.model.user_sketch_layers import (
    is_user_sketch_wire_layer,
    normalize_user_sketch_linetype,
    user_sketch_display_linetype_for_entity,
)
from logic_cad.core.model.wire_layers import is_wire_layer
from logic_cad.core.model.xdata import get_type, get_uid, read_ld_app_dict
from logic_cad.core.text.layout_resolver import normalize_dxf_text_entity
from logic_cad.ui.dialogs.user_text_place_dialog import prompt_dxf_text_string_and_height
from logic_cad.ui.bulge_path import append_bulge_arc_to_path
from logic_cad.ui.scene_item.z_order import CANVAS_Z_FRAME_VPORT_PREVIEW
from logic_cad.ui.scene_item.osnap import OsnapCandidate, pick_osnap_candidate
from logic_cad.ui.dxf_display_color import entity_stroke_qcolor
from logic_cad.ui.items.mtext_item import DxfMTextItem
from logic_cad.ui.items.symbol_item import SymbolItem
from logic_cad.ui.items.user_geometry_items import (
    UserArcItem,
    UserCircleItem,
    UserCloudItem,
    UserLineItem,
    UserTextItem,
)
from logic_cad.ui.items.wire_arrow_item import WireArrowItem
from logic_cad.ui.items.wire_item import WireItem, apply_dxf_linetype_to_pen, dxf_to_scene
from logic_cad.ui.passive_dxf_primitives import add_passive_layout_primitive_items
from logic_cad.ui.sketch_arc_interaction import (
    arc_vertex_marker_half_mm,
    circle_radius_mm_from_anchor_and_cursor_dxf,
    same_dxf_point,
    try_dxf_arc_through_three_points,
    user_arc_preview_qpainterpath_from_three_points,
)
from logic_cad.ui.snap_utils import dxf_from_scene_pos, snap_dxf_pos, snap_parallel_drag_delta_mm, user_line_end_dxf_from_scene
from logic_cad.ui.view_fit_rect import DEFAULT_DIAGRAM_VIEW_FIT_MARGIN_MM, default_a4_fit_rect_mm

if TYPE_CHECKING:
    from logic_cad.core.logic_diagram import LogicDiagram


ENV_SHOW_ROUTING_BBOX = "LOGIC_CAD_SHOW_ROUTING_BBOX"
ENV_SHOW_CONNECT_BBOX = "LOGIC_CAD_SHOW_CONNECT_BBOX"


def _env_truthy(name: str) -> bool:
    """Return True when environment variable *name* is set to a truthy value."""
    raw = (os.environ.get(name) or "").strip().lower()
    return raw not in ("", "0", "false", "no", "off")


def _dist_sq_point_to_segment(
    px: float, py: float, x0: float, y0: float, x1: float, y1: float
) -> float:
    dx, dy = x1 - x0, y1 - y0
    d2 = dx * dx + dy * dy
    if d2 < 1e-18:
        return (px - x0) ** 2 + (py - y0) ** 2
    t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / d2))
    qx, qy = x0 + t * dx, y0 + t * dy
    return (px - qx) ** 2 + (py - qy) ** 2


def _min_dist_sq_point_to_wire_chords(px: float, py: float, wire: WireItem) -> float:
    pts = wire.points_dxf()
    if len(pts) < 2:
        return float("inf")
    best = float("inf")
    for i in range(len(pts) - 1):
        x0, y0 = pts[i][0], pts[i][1]
        x1, y1 = pts[i + 1][0], pts[i + 1][1]
        best = min(best, _dist_sq_point_to_segment(px, py, x0, y0, x1, y1))
    return best


class DiagramScene(QGraphicsScene):
    def __init__(self, diagram: LogicDiagram, parent=None) -> None:
        super().__init__(parent)
        self._diagram = diagram
        self._on_navigate_page: Callable[[str, str | None], None] | None = None
        self._on_navigate_inpage_peer: Callable[[str], None] | None = None
        self._wire_start: tuple[str, str] | None = None
        self._wire_rubber: QGraphicsLineItem | None = None
        self._wire_anchor: QPointF | None = None
        self._symbol_items: dict[str, SymbolItem] = {}
        self._wire_mode = False
        self._manual_wire_mode = False
        self._manual_bends_dxf: list[tuple[float, float]] = []
        self._manual_p0_dxf: tuple[float, float] | None = None
        self._manual_preview_solid: QGraphicsPathItem | None = None
        self._manual_preview_dash: QGraphicsPathItem | None = None
        self._on_reroute_failed: Callable[[str], None] | None = None
        self._on_wire_error: Callable[[str], None] | None = None
        self._on_hit_wire_clear_tools: Callable[[], None] | None = None
        self._on_clipboard_copy: Callable[[], None] | None = None
        self._on_clipboard_paste: Callable[[], None] | None = None
        self._on_after_delete: Callable[[], None] | None = None
        self._wire_seg_drag: (
            tuple[WireItem, int, tuple[float, float], list[tuple[float, float, float]], float] | None
        ) = None
        self._user_line_endpoint_drag: tuple[UserLineItem, int] | None = None
        self._wire_preview_length_mm: float | None = None
        self._osnap_marker: QGraphicsEllipseItem | None = None
        self._sketch_tool: str = "none"
        self._sketch_p0_dxf: tuple[float, float] | None = None
        self._sketch_preview_line: QGraphicsLineItem | None = None
        self._sketch_preview_circle: QGraphicsEllipseItem | None = None
        self._sketch_cloud_vertices_dxf: list[tuple[float, float]] = []
        self._sketch_preview_cloud: QGraphicsPathItem | None = None
        self._sketch_arc_dxf_pts: list[tuple[float, float]] = []
        self._sketch_preview_arc: QGraphicsPathItem | None = None
        self._sketch_preview_arc_chord: QGraphicsLineItem | None = None
        self._sketch_preview_arc_markers: list[QGraphicsRectItem] = []
        self._sketch_line_preview_length_mm: float | None = None
        self._user_sketch_line_linetype: str = normalize_user_sketch_linetype(LINETYPE_CONTINUOUS)
        self._show_routing_bbox = _env_truthy(ENV_SHOW_ROUTING_BBOX)
        self._show_connect_bbox = _env_truthy(ENV_SHOW_CONNECT_BBOX)
        self._connect_bbox_hover_port: tuple[str, str] | None = None
        self.setSceneRect(-500, -500, 2000, 2000)
        self.rebuild()

    def wire_item_at_scene_pos(self, scene_pos: QPointF) -> WireItem | None:
        """All items whose shape contains *scene_pos*; prefer WireItem, break ties by chord distance in DXF mm."""
        items = self.items(
            scene_pos,
            Qt.ItemSelectionMode.IntersectsItemShape,
            Qt.SortOrder.DescendingOrder,
        )
        wires = [it for it in items if isinstance(it, WireItem)]
        if not wires:
            return None
        px, py = dxf_from_scene_pos(scene_pos)
        if len(wires) == 1:
            return wires[0]
        return min(wires, key=lambda w: _min_dist_sq_point_to_wire_chords(px, py, w))

    def set_wire_mode(self, on: bool) -> None:
        """オン時のみポートクリックで配線。オフ時は通常の選択・移動。"""
        on = bool(on)
        if not on:
            self.cancel_wire_rubber()
        self._wire_mode = on
        if not on:
            self._set_connect_bbox_hover_port(None)

    def wire_mode(self) -> bool:
        return self._wire_mode

    def set_manual_wire_mode(self, on: bool) -> None:
        """オン: 配線は中間クリックで折れ点、終了ポートで確定（自動再配線除外フラグ付き）。"""
        on = bool(on)
        if on == self._manual_wire_mode:
            return
        self._manual_wire_mode = on
        self.cancel_wire_rubber()

    def manual_wire_mode(self) -> bool:
        return self._manual_wire_mode

    def hover_port_hint(self, scene_pos: QPointF) -> str:
        """ステータス／ツールチップ用: ポート上ならレイヤ名とキー。"""
        for _uid, sym in self._symbol_items.items():
            pk = sym.port_at_scene_pos(scene_pos)
            if pk:
                layer = f"LD_PORT_{pk}"
                bdef = sym.definition_block_name or ""
                return f"{layer}   port={pk!r}   block={bdef!r}   uid={sym.symbol_uid}"
        return ""

    def set_diagram(self, diagram: LogicDiagram) -> None:
        self._diagram = diagram
        self.rebuild()

    def set_navigate_page_callback(self, cb: Callable[[str, str | None], None] | None) -> None:
        """Called with layout name and optional PAGE_REF peer uid to focus after switch (TOC passes None)."""
        self._on_navigate_page = cb

    def set_navigate_inpage_peer_callback(self, cb: Callable[[str], None] | None) -> None:
        """Called with peer INSERT uid when user Ctrl+clicks an INPAGE_REF (not on a port)."""
        self._on_navigate_inpage_peer = cb

    def set_reroute_failed_callback(self, cb: Callable[[str], None] | None) -> None:
        """After move/rotate rollback when wire rerouting could not complete (e.g. status toast)."""
        self._on_reroute_failed = cb

    def set_wire_error_callback(self, cb: Callable[[str], None] | None) -> None:
        """Manual wire confirm failed (e.g. non-Manhattan path): show message in status bar."""
        self._on_wire_error = cb

    def set_hit_wire_clear_tools_callback(self, cb: Callable[[], None] | None) -> None:
        """Clicking an existing wire clears auto/manual routing modes (MainWindow updates buttons)."""
        self._on_hit_wire_clear_tools = cb

    def set_clipboard_callbacks(
        self, copy_cb: Callable[[], None] | None, paste_cb: Callable[[], None] | None
    ) -> None:
        self._on_clipboard_copy = copy_cb
        self._on_clipboard_paste = paste_cb

    def set_after_delete_callback(self, cb: Callable[[], None] | None) -> None:
        """Clear property panel (or similar) after context-menu delete; optional."""
        self._on_after_delete = cb

    def run_clipboard_copy(self) -> None:
        if self._on_clipboard_copy is not None:
            self._on_clipboard_copy()

    def run_clipboard_paste(self) -> None:
        if self._on_clipboard_paste is not None:
            self._on_clipboard_paste()

    def select_symbol_uids(self, uids: set[str]) -> None:
        """Clear selection and select SymbolItems whose ``symbol_uid`` is in *uids*."""
        self.clearSelection()
        for u in uids:
            sym = self._symbol_items.get(u)
            if sym is not None:
                sym.setSelected(True)

    def select_pasted_items(self, symbol_uids: set[str], sketch_uids: set[str]) -> None:
        """Select symbols and user sketch items by uid (e.g. after paste or after ``rebuild``)."""
        self.clearSelection()
        if not symbol_uids and not sketch_uids:
            return
        for it in self.items():
            if isinstance(it, SymbolItem) and it.symbol_uid in symbol_uids:
                it.setSelected(True)
            if isinstance(
                it, (UserLineItem, UserCircleItem, UserArcItem, UserCloudItem, UserTextItem)
            ) and it.sketch_uid in sketch_uids:
                it.setSelected(True)

    def deliver_context_menu(
        self,
        scene_pos: QPointF,
        screen_global_pos,
        view_widget: QWidget,
        device_transform,
    ) -> bool:
        """Show symbol menu for topmost editable symbol, else clipboard menu. Returns True if handled."""
        items = self.items(
            scene_pos,
            Qt.ItemSelectionMode.IntersectsItemShape,
            Qt.SortOrder.DescendingOrder,
            device_transform,
        )
        top = items[0] if items else None
        if isinstance(top, SymbolItem) and top.entity_type not in (
            ENTITY_TYPE_PAPER_FRAME,
            ENTITY_TYPE_TOC_HEADER,
            ENTITY_TYPE_TOC_ROW,
        ):
            ev = QGraphicsSceneContextMenuEvent(QEvent.Type.GraphicsSceneContextMenu)
            if hasattr(ev, "setWidget"):
                ev.setWidget(view_widget)
            ev.setScenePos(scene_pos)
            ev.setScreenPos(screen_global_pos)
            if hasattr(ev, "setModifiers"):
                ev.setModifiers(QApplication.keyboardModifiers())
            top.contextMenuEvent(ev)
            if ev.isAccepted():
                return True
        if self._on_clipboard_copy is None and self._on_clipboard_paste is None:
            return False
        menu = QMenu()
        if self._on_clipboard_copy is not None:
            menu.addAction("コピー", self.run_clipboard_copy)
        if self._on_clipboard_paste is not None:
            menu.addAction("貼り付け", self.run_clipboard_paste)
        if menu.isEmpty():
            return False
        menu.exec(screen_global_pos)
        return True

    def escape_clears_wiring_tools(self) -> bool:
        """True if no SymbolItem is selected (Esc may turn off auto/manual wire and sketch tools)."""
        for it in self.selectedItems():
            if isinstance(it, SymbolItem):
                return False
        return True

    def request_rotate_symbol(self, uid: str, delta_deg: int) -> None:
        try:
            with self._diagram.begin("rotate"):
                if not self._diagram.rotate_symbol(uid, float(delta_deg)):
                    raise RerouteAfterGeometryChangeError()
        except RerouteAfterGeometryChangeError:
            if self._on_reroute_failed is not None:
                self._on_reroute_failed(format_uid_display(uid))
        self.rebuild()

    def request_delete_symbols(self, uids: Sequence[str]) -> None:
        ordered = list(dict.fromkeys(u for u in uids if u))
        if not ordered:
            return
        with self._diagram.begin("delete"):
            for uid in ordered:
                self._diagram.delete_by_uid(uid)
        self.clearSelection()
        if self._on_after_delete is not None:
            self._on_after_delete()
        self.rebuild()

    def request_delete_symbol(self, uid: str) -> None:
        self.request_delete_symbols((uid,))

    def request_delete_selected_symbols(self, context_item: SymbolItem) -> None:
        """Delete every selected deletable symbol; if none, delete *context_item* (right-click target)."""
        blocked = (
            ENTITY_TYPE_TOC_HEADER,
            ENTITY_TYPE_TOC_ROW,
            ENTITY_TYPE_PAPER_FRAME,
        )
        uids: list[str] = []
        for it in self.selectedItems():
            if isinstance(it, SymbolItem) and it.entity_type not in blocked:
                uids.append(it.symbol_uid)
        if not uids and context_item.entity_type not in blocked:
            uids = [context_item.symbol_uid]
        self.request_delete_symbols(uids)

    def request_align_selected(self, mode: str) -> None:
        """Align or distribute selected symbols by scene bounding box."""
        blocked = (
            ENTITY_TYPE_TOC_HEADER,
            ENTITY_TYPE_TOC_ROW,
            ENTITY_TYPE_PAPER_FRAME,
        )
        items: list[SymbolItem] = []
        for it in self.selectedItems():
            if isinstance(it, SymbolItem) and it.entity_type not in blocked:
                items.append(it)
        if len(items) < 2:
            return
        rects = [it.sceneBoundingRect() for it in items]
        min_l = min(r.left() for r in rects)
        max_r = max(r.right() for r in rects)
        min_t = min(r.top() for r in rects)
        max_b = max(r.bottom() for r in rects)
        mid_x = 0.5 * (min_l + max_r)
        mid_y = 0.5 * (min_t + max_b)

        moves: list[tuple[SymbolItem, float, float]] = []
        if mode == "hdistribute":
            pairs = sorted(zip(items, rects, strict=True), key=lambda pr: pr[1].left())
            ordered_items = [p[0] for p in pairs]
            ordered_rects = [p[1] for p in pairs]
            n = len(ordered_rects)
            total_w = sum(float(r.width()) for r in ordered_rects)
            span = max_r - min_l
            gap = (span - total_w) / (n - 1) if n >= 2 else 0.0
            x = min_l
            for it, r in zip(ordered_items, ordered_rects, strict=True):
                dx = x - r.left()
                moves.append((it, dx, 0.0))
                x += float(r.width()) + gap
        elif mode == "vdistribute":
            pairs = sorted(zip(items, rects, strict=True), key=lambda pr: pr[1].top())
            ordered_items = [p[0] for p in pairs]
            ordered_rects = [p[1] for p in pairs]
            n = len(ordered_rects)
            total_h = sum(float(r.height()) for r in ordered_rects)
            span_v = max_b - min_t
            gap = (span_v - total_h) / (n - 1) if n >= 2 else 0.0
            y = min_t
            for it, r in zip(ordered_items, ordered_rects, strict=True):
                dy = y - r.top()
                moves.append((it, 0.0, dy))
                y += float(r.height()) + gap
        else:
            for it, r in zip(items, rects, strict=True):
                if mode == "left":
                    dx, dy = min_l - r.left(), 0.0
                elif mode == "right":
                    dx, dy = max_r - r.right(), 0.0
                elif mode == "hcenter":
                    dx, dy = mid_x - r.center().x(), 0.0
                elif mode == "top":
                    dx, dy = 0.0, min_t - r.top()
                elif mode == "bottom":
                    dx, dy = 0.0, max_b - r.bottom()
                elif mode == "vcenter":
                    dx, dy = 0.0, mid_y - r.center().y()
                else:
                    return
                moves.append((it, dx, dy))

        moved_symbol_targets: dict[str, tuple[float, float]] = {}
        symbol_move_deltas: dict[str, tuple[float, float]] = {}
        uids: set[str] = set()
        for it, dx, dy in moves:
            if abs(dx) < 1e-9 and abs(dy) < 1e-9:
                continue
            ox, oy = float(it.insert_xy[0]), float(it.insert_xy[1])
            nx, ny = snap_dxf_pos(ox + dx, oy - dy)
            moved_symbol_targets[it.symbol_uid] = (nx, ny)
            symbol_move_deltas[it.symbol_uid] = (nx - ox, ny - oy)
            uids.add(it.symbol_uid)

        if not moved_symbol_targets:
            return

        # rebuild() で全アイテムが作り直されても選択を維持するため、操作対象全 UID を退避する
        selected_uids = {it.symbol_uid for it in items}

        try:
            with self._diagram.begin("move"):
                for uid, pos in moved_symbol_targets.items():
                    self._diagram.symbols.move_insert(self._diagram.current_layout_name, uid, pos)
                if not self._diagram.reroute_wires_after_symbol_moves(
                    uids, symbol_move_deltas=symbol_move_deltas or None
                ):
                    raise RerouteAfterGeometryChangeError()
        except RerouteAfterGeometryChangeError:
            if self._on_reroute_failed is not None:
                disp = "、".join(format_uid_display(u) for u in sorted(uids))
                self._on_reroute_failed(disp)
        self.rebuild()
        self.select_symbol_uids(selected_uids)

    def _clear_wire_hover_segments(self) -> None:
        for it in self.items():
            if isinstance(it, WireItem):
                it.set_hover_segment(None)

    def _update_wire_segment_hover(self, scene_pos: QPointF) -> None:
        self._clear_wire_hover_segments()
        if self._wire_mode or self._wire_seg_drag is not None or self._user_line_endpoint_drag is not None:
            return
        sels = self.selectedItems()
        if len(sels) != 1 or not isinstance(sels[0], WireItem):
            return
        wi = sels[0]
        seg = wi.hit_eligible_parallel_segment(scene_pos)
        wi.set_hover_segment(seg)

    def _set_osnap_marker(self, scene_pos: QPointF) -> None:
        if self._osnap_marker is None:
            marker = QGraphicsEllipseItem()
            marker.setPen(QPen(QColor(130, 220, 255), 0))
            marker.setBrush(QBrush(QColor(130, 220, 255, 70)))
            marker.setZValue(10003.0)
            self._osnap_marker = marker
            self.addItem(marker)
        radius = 1.3
        self._osnap_marker.setRect(
            scene_pos.x() - radius,
            scene_pos.y() - radius,
            radius * 2.0,
            radius * 2.0,
        )

    def _clear_osnap_marker(self) -> None:
        if self._osnap_marker is None:
            return
        self.removeItem(self._osnap_marker)
        self._osnap_marker = None

    def _pick_wire_port_osnap(self, scene_pos: QPointF) -> OsnapCandidate | None:
        return pick_osnap_candidate(
            scene_pos,
            selected_items=[],
            symbol_items=self._symbol_items,
            include_user_line_endpoints=False,
            include_wire_ports=True,
        )

    def _wire_port_hit_at_scene_pos(
        self, scene_pos: QPointF, *, allow_osnap: bool
    ) -> tuple[str, str, SymbolItem] | None:
        for uid, sym in self._symbol_items.items():
            port_key = sym.port_at_scene_pos(scene_pos)
            if port_key:
                return uid, port_key, sym
        if not allow_osnap:
            return None
        cand = self._pick_wire_port_osnap(scene_pos)
        if cand is None or cand.symbol_uid is None or cand.port_key is None:
            return None
        sym = self._symbol_items.get(cand.symbol_uid)
        if sym is None:
            return None
        return cand.symbol_uid, cand.port_key, sym

    def _update_osnap_feedback(self, scene_pos: QPointF) -> None:
        if self._wire_seg_drag is not None or self._user_line_endpoint_drag is not None:
            self._clear_osnap_marker()
            return
        cand = None
        if self._wire_mode:
            cand = self._pick_wire_port_osnap(scene_pos)
        elif not self._wire_mode:
            cand = pick_osnap_candidate(
                scene_pos,
                selected_items=self.selectedItems(),
                symbol_items=self._symbol_items,
                include_user_line_endpoints=True,
                include_wire_ports=False,
            )
        if cand is None:
            self._clear_osnap_marker()
            return
        self._set_osnap_marker(cand.scene_pos)

    def _normalize_wire_endpoint_port_key(self, uid: str, raw_port_key: str) -> str:
        """Normalize click-hit port key to the actual endpoint key used by wire commands."""
        sym = self._symbol_items.get(uid)
        if sym is None:
            return raw_port_key
        if sym.entity_type == ENTITY_TYPE_WIRE_BRANCH:
            return "INOUT0_MULTI"
        if sym.entity_type == ENTITY_TYPE_CHECKPOINT:
            if self._wire_start is None:
                return "OUT0_MULTI"
            return "IN0_MULTI"
        return raw_port_key

    def _set_connect_bbox_hover_port(self, value: tuple[str, str] | None) -> None:
        """Store connect bbox hover candidate and repaint when changed."""
        if self._connect_bbox_hover_port == value:
            return
        self._connect_bbox_hover_port = value
        self.update()

    def _update_connect_bbox_hover_port(self, scene_pos: QPointF) -> None:
        """Update hover endpoint used by connect-bbox overlay in wire mode."""
        if not self._show_connect_bbox or not self._wire_mode or self._wire_start is None:
            self._set_connect_bbox_hover_port(None)
            return
        hit = self._wire_port_hit_at_scene_pos(scene_pos, allow_osnap=True)
        if hit is None:
            self._set_connect_bbox_hover_port(None)
            return
        uid, raw_pk, _sym = hit
        self._set_connect_bbox_hover_port((uid, self._normalize_wire_endpoint_port_key(uid, raw_pk)))

    def wire_preview_length_mm(self) -> float | None:
        """While auto/manual wire preview is active, length in mm; else None."""
        return self._wire_preview_length_mm

    def length_hud_mm(self) -> float | None:
        """Wire rubber/manual length, or USER_LINE drag preview length (mm)."""
        if self._wire_preview_length_mm is not None:
            return self._wire_preview_length_mm
        return self._sketch_line_preview_length_mm

    def deselect_user_sketch_items(self) -> None:
        """Clear selection from placed user sketch items."""
        for it in list(self.selectedItems()):
            if isinstance(it, (UserLineItem, UserCircleItem, UserArcItem, UserCloudItem, UserTextItem)):
                it.setSelected(False)

    def set_user_sketch_tool(self, tool: str) -> None:
        """``none`` | ``line`` | ``circle`` | ``arc`` | ``cloud`` | ``text``."""
        t = tool if tool in ("none", "line", "circle", "arc", "cloud", "text") else "none"
        if t != self._sketch_tool:
            self.cancel_user_sketch()
        self._sketch_tool = t

    def user_sketch_tool(self) -> str:
        """``none`` | ``line`` | ``circle`` | ``arc`` | ``cloud`` | ``text`` (read-only)."""
        return self._sketch_tool

    def user_sketch_line_default_linetype(self) -> str:
        """Return the linetype used for the next line drawn with the line sketch tool.

        Returns:
            One of ``CONTINUOUS``, ``DASHED``, ``CENTER`` (normalized).
        """
        return self._user_sketch_line_linetype

    def set_user_sketch_line_default_linetype(self, linetype: str) -> None:
        """Set the default linetype for the line sketch tool (next placement).

        The value is normalized via ``normalize_user_sketch_linetype``. If a preview line
        is active (first point set), its pen is updated to match.

        Args:
            linetype: Raw DXF/UI name (e.g. ``CONTINUOUS``, ``DASHED``, ``LINETYPE_VALUE``).
        """
        self._user_sketch_line_linetype = normalize_user_sketch_linetype(linetype)
        if self._sketch_preview_line is not None:
            pen = QPen(QColor(180, 220, 255), 0)
            pen.setCosmetic(True)
            apply_dxf_linetype_to_pen(pen, self._user_sketch_line_linetype)
            self._sketch_preview_line.setPen(pen)
        if self._sketch_preview_arc is not None:
            pen = QPen(QColor(180, 220, 255), 0)
            pen.setCosmetic(True)
            apply_dxf_linetype_to_pen(pen, self._user_sketch_line_linetype)
            self._sketch_preview_arc.setPen(pen)

    def user_sketch_has_in_progress_geometry(self) -> bool:
        """Return True when a sketch tool has committed partial input (e.g. line first point).

        Used so Esc can cancel the in-flight preview without turning off the sketch tool;
        a second Esc (with no partial geometry) exits the tool.

        Args:
            None

        Returns:
            True if a user sketch tool is active and ``cancel_user_sketch`` would clear
            partial line/circle state (``_sketch_p0_dxf``), arc clicks, or cloud vertices.
        """
        if self._sketch_tool == "none":
            return False
        if self._sketch_p0_dxf is not None:
            return True
        if self._sketch_arc_dxf_pts:
            return True
        if self._sketch_cloud_vertices_dxf:
            return True
        return False

    def cancel_user_sketch(self) -> None:
        self._sketch_p0_dxf = None
        self._sketch_cloud_vertices_dxf.clear()
        self._clear_osnap_marker()
        if self._sketch_preview_line is not None:
            self.removeItem(self._sketch_preview_line)
            self._sketch_preview_line = None
        if self._sketch_preview_circle is not None:
            self.removeItem(self._sketch_preview_circle)
            self._sketch_preview_circle = None
        if self._sketch_preview_cloud is not None:
            self.removeItem(self._sketch_preview_cloud)
            self._sketch_preview_cloud = None
        self._clear_sketch_arc_draft_auxiliary_graphics()
        self._sketch_arc_dxf_pts.clear()
        if self._sketch_preview_arc is not None:
            self.removeItem(self._sketch_preview_arc)
            self._sketch_preview_arc = None
        self._sketch_line_preview_length_mm = None

    def cancel_wire_rubber(self) -> None:
        self._wire_seg_drag = None
        self._user_line_endpoint_drag = None
        self._wire_preview_length_mm = None
        self._set_connect_bbox_hover_port(None)
        self._clear_osnap_marker()
        if self._manual_preview_solid is not None:
            self.removeItem(self._manual_preview_solid)
            self._manual_preview_solid = None
        if self._manual_preview_dash is not None:
            self.removeItem(self._manual_preview_dash)
            self._manual_preview_dash = None
        self._manual_bends_dxf.clear()
        self._manual_p0_dxf = None
        if self._wire_rubber is not None:
            self.removeItem(self._wire_rubber)
            self._wire_rubber = None
        self._wire_anchor = None
        self._wire_start = None

    def _dxf_last_for_manual(self) -> tuple[float, float] | None:
        if self._manual_p0_dxf is None:
            return None
        if not self._manual_bends_dxf:
            return self._manual_p0_dxf
        return self._manual_bends_dxf[-1]

    def _manhattan_extension_dxf(
        self, last: tuple[float, float], target: tuple[float, float]
    ) -> list[tuple[float, float]]:
        tx, ty = target
        if abs(last[0] - tx) < 1e-9 and abs(last[1] - ty) < 1e-9:
            return []
        if abs(last[0] - tx) < 1e-9 or abs(last[1] - ty) < 1e-9:
            return [(tx, ty)]
        return [(tx, last[1]), (tx, ty)]

    def _manual_wire_preview_points_dxf(self, mouse_scene: QPointF) -> list[tuple[float, float]] | None:
        if self._manual_p0_dxf is None:
            return None
        xd, yd = dxf_from_scene_pos(mouse_scene)
        mx, my = snap_dxf_pos(xd, yd)
        last = self._dxf_last_for_manual()
        if last is None:
            return None
        extra = self._manhattan_extension_dxf(last, (mx, my))
        return [self._manual_p0_dxf] + list(self._manual_bends_dxf) + extra

    @staticmethod
    def _polyline_manhattan_length_mm(pts: list[tuple[float, float]]) -> float:
        t = 0.0
        for i in range(len(pts) - 1):
            ax, ay = pts[i]
            bx, by = pts[i + 1]
            t += manhattan_distance((ax, ay), (bx, by))
        return t

    def _compute_wire_preview_length_mm(self, scene_pos: QPointF) -> float | None:
        if self._manual_wire_mode and self._wire_start is not None and self._manual_preview_dash is not None:
            pts = self._manual_wire_preview_points_dxf(scene_pos)
            if pts is None or len(pts) < 2:
                return None
            return self._polyline_manhattan_length_mm(pts)
        if self._wire_rubber is not None and self._wire_anchor is not None:
            ax, ay = self._wire_anchor.x(), self._wire_anchor.y()
            sp = scene_pos
            return float(math.hypot(sp.x() - ax, sp.y() - ay))
        return None

    def _update_manual_preview(self, mouse_scene: QPointF) -> None:
        if self._manual_preview_dash is None or self._manual_p0_dxf is None:
            return
        full = self._manual_wire_preview_points_dxf(mouse_scene)
        if full is None:
            return
        fixed = [self._manual_p0_dxf] + list(self._manual_bends_dxf)
        last = self._dxf_last_for_manual()
        if last is None:
            return
        extra = full[len(fixed) :]

        solid = QPainterPath()
        if len(fixed) >= 2:
            solid.moveTo(dxf_to_scene(*fixed[0]))
            for p in fixed[1:]:
                solid.lineTo(dxf_to_scene(*p))
        if self._manual_preview_solid is not None:
            self._manual_preview_solid.setPath(solid)

        dash = QPainterPath()
        dash.moveTo(dxf_to_scene(*last))
        for p in extra:
            dash.lineTo(dxf_to_scene(*p))
        self._manual_preview_dash.setPath(dash)

    def extent_rect_for_view_fit(self) -> QRectF:
        """Rectangle for middle-double-click zoom-to-content with an A4 landscape floor.

        When the scene has drawable items, returns the union of padded item bounds and
        the default A4 sheet rectangle (same as :meth:`DiagramView.fit_a4_page`).
        With no items, returns only the A4 rectangle.

        Returns:
            Scene-axis-aligned rectangle in millimetres suitable for ``fitInView``.
        """

        margin = float(DEFAULT_DIAGRAM_VIEW_FIT_MARGIN_MM)
        floor = default_a4_fit_rect_mm(margin_mm=margin)
        br = self.itemsBoundingRect()
        if br.isValid() and not br.isEmpty():
            return br.adjusted(-margin, -margin, margin, margin).united(floor)
        return floor

    def drawBackground(self, painter, rect) -> None:
        painter.fillRect(rect, QColor(34, 36, 40))
        pen = QPen(QColor(55, 58, 64))
        pen.setCosmetic(True)
        painter.setPen(pen)
        pitch = GRID_PITCH
        margin = pitch * 2
        left, top = rect.left() - margin, rect.top() - margin
        right, bottom = rect.right() + margin, rect.bottom() + margin
        xi0 = int(math.floor(left / pitch))
        xi1 = int(math.ceil(right / pitch))
        for i in range(xi0, xi1 + 1):
            x = i * pitch
            painter.drawLine(x, top, x, bottom)
        j0 = int(math.floor(top / pitch))
        j1 = int(math.ceil(bottom / pitch))
        for j in range(j0, j1 + 1):
            y = j * pitch
            painter.drawLine(left, y, right, y)

    def _draw_obstacle_rects(
        self,
        painter,
        rect,
        obstacles: list[tuple[float, float, float, float]],
        *,
        pen_color: QColor,
        brush_color: QColor,
    ) -> None:
        """Draw obstacle AABB list in scene space."""
        if not obstacles:
            return
        painter.save()
        pen = QPen(pen_color)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(QBrush(brush_color))
        for x0, y0, x1, y1 in obstacles:
            p0 = dxf_to_scene(float(x0), float(y0))
            p1 = dxf_to_scene(float(x1), float(y1))
            left = min(p0.x(), p1.x())
            right = max(p0.x(), p1.x())
            top = min(p0.y(), p1.y())
            bottom = max(p0.y(), p1.y())
            if right < rect.left() or left > rect.right() or bottom < rect.top() or top > rect.bottom():
                continue
            painter.drawRect(left, top, right - left, bottom - top)
        painter.restore()

    def drawForeground(self, painter, rect) -> None:
        super().drawForeground(painter, rect)
        if not self._show_routing_bbox and not self._show_connect_bbox:
            return
        base_obstacles: list[tuple[float, float, float, float]] = []
        try:
            if self._show_routing_bbox:
                base_obstacles = build_routing_obstacles(
                    self._diagram.doc,
                    self._diagram.index,
                    self._diagram.current_layout_name,
                    set(),
                )
        except Exception:
            base_obstacles = []
        if self._show_routing_bbox:
            self._draw_obstacle_rects(
                painter,
                rect,
                base_obstacles,
                pen_color=QColor(255, 110, 80, 220),
                brush_color=QColor(255, 110, 80, 45),
            )
        if not self._show_connect_bbox or not self._wire_mode or self._wire_start is None:
            return
        access_ports: dict[str, set[str]] = {self._wire_start[0]: {self._wire_start[1]}}
        if self._connect_bbox_hover_port is not None:
            hu, hp = self._connect_bbox_hover_port
            access_ports.setdefault(hu, set()).add(hp)
        try:
            connect_obstacles = build_routing_obstacles(
                self._diagram.doc,
                self._diagram.index,
                self._diagram.current_layout_name,
                set(),
                access_ports=access_ports,
            )
        except Exception:
            return
        self._draw_obstacle_rects(
            painter,
            rect,
            connect_obstacles,
            pen_color=QColor(120, 210, 255, 240),
            brush_color=QColor(120, 210, 255, 45),
        )

    def rebuild(self) -> None:
        self.cancel_user_sketch()
        self.cancel_wire_rubber()
        self._clear_osnap_marker()
        self.clear()
        self._symbol_items.clear()
        self._diagram.rebuild_index()
        layout = self._diagram.doc.layouts.get(self._diagram.current_layout_name)
        blk = self._diagram.doc.blocks.get(layout.block_record_name)
        refreshed_page_refs = False
        refreshed_inpage_refs = False

        for e in blk:
            if e.dxftype() == "LWPOLYLINE" and str(e.dxf.layer) == LAYER_CONTENTS_AREA:
                continue
            uid = get_uid(e)
            _layer_name = str(e.dxf.layer)
            if e.dxftype() == "INSERT" and uid:
                ins = e
                name = ins.dxf.name
                et = get_type(ins) or "SYMBOL"
                sym_label = name
                sym_visible = False
                for a in ins.attribs:
                    if a.dxf.tag == "SYM":
                        sym_label = a.dxf.text
                        sym_visible = not bool(a.dxf.invisible)
                        break
                if et == "PAGE_REF":
                    xd = read_ld_app_dict(ins)
                    sym_label = (xd.get("sym") or "").strip() or sym_label
                    tgt = (xd.get(TARGET_LAYOUT_XDATA) or "").strip()
                    if not sym_label.strip() and tgt:
                        if not refreshed_page_refs:
                            refresh_page_ref_syms_on_layout(
                                self._diagram.doc, self._diagram.current_layout_name
                            )
                            refreshed_page_refs = True
                        xd = read_ld_app_dict(ins)
                        sym_label = (xd.get("sym") or "").strip() or sym_label
                    if not sym_label.strip() and tgt:
                        sym_label = tgt
                inpage_sym_height_mm: float | None = None
                if et == ENTITY_TYPE_INPAGE_REF:
                    xd = read_ld_app_dict(ins)
                    sym_label = (xd.get("sym") or "").strip() or sym_label
                    peer_u = (xd.get(PEER_UID_XDATA) or "").strip()
                    if (not sym_label.strip() or not peer_u) and not refreshed_inpage_refs:
                        refresh_inpage_ref_syms_on_layout(
                            self._diagram.doc, self._diagram.current_layout_name
                        )
                        refreshed_inpage_refs = True
                        xd = read_ld_app_dict(ins)
                        sym_label = (xd.get("sym") or "").strip() or sym_label
                    raw_h = (xd.get(INPAGE_SYM_HEIGHT_XDATA) or "").strip()
                    if raw_h:
                        try:
                            inpage_sym_height_mm = float(raw_h)
                        except ValueError:
                            inpage_sym_height_mm = None
                    if inpage_sym_height_mm is None:
                        for a in ins.attribs:
                            if str(a.dxf.tag).upper() == "SYM":
                                try:
                                    inpage_sym_height_mm = float(
                                        getattr(a.dxf, "height", 0.0) or 0.0
                                    )
                                except (TypeError, ValueError):
                                    inpage_sym_height_mm = None
                                break
                    if inpage_sym_height_mm is None:
                        inpage_sym_height_mm = INPAGE_SYM_HEIGHT_MM
                if et in (ENTITY_TYPE_PAPER_FRAME, ENTITY_TYPE_TOC_HEADER, ENTITY_TYPE_TOC_ROW):
                    sym_label = ""
                static_label: str | None = None
                if et in ("AND", "OR"):
                    sl = ""
                    for a in ins.attribs:
                        if a.dxf.tag == "STATIC_LABEL0":
                            sl = a.dxf.text
                            break
                    static_label = sl or (
                        GATE_STATIC_LABEL_AND if et == "AND" else GATE_STATIC_LABEL_OR
                    )
                ix, iy = float(ins.dxf.insert.x), float(ins.dxf.insert.y)
                sx = float(getattr(ins.dxf, "xscale", 1.0) or 1.0)
                sy = float(getattr(ins.dxf, "yscale", 1.0) or 1.0)
                inst_attribs: dict[str, tuple[str, bool]] = {}
                seen_attrib_tag: set[str] = set()
                for a in ins.attribs:
                    tu = str(a.dxf.tag).upper()
                    if tu in seen_attrib_tag:
                        continue
                    seen_attrib_tag.add(tu)
                    inst_attribs[str(a.dxf.tag)] = (str(a.dxf.text or ""), bool(a.dxf.invisible))
                page_ref_break = False
                if et == "PAGE_REF":
                    xd_pr = read_ld_app_dict(ins)
                    page_ref_break = page_ref_insert_target_unresolved_for_editor(
                        self._diagram.doc,
                        str(xd_pr.get(TARGET_LAYOUT_XDATA) or "").strip(),
                        layout_here=self._diagram.current_layout_name,
                        ld_app=dict(xd_pr),
                    )
                it = SymbolItem(
                    uid,
                    sym_label,
                    self._diagram.index,
                    (ix, iy),
                    entity_type=et,
                    rotation_deg=float(ins.dxf.rotation),
                    static_label=static_label,
                    sym_visible=sym_visible
                    and et != ENTITY_TYPE_PAPER_FRAME
                    and et != ENTITY_TYPE_WIRE_BRANCH,
                    insert_block_name=name,
                    doc=self._diagram.doc,
                    scale_x=sx,
                    scale_y=sy,
                    instance_attribs=inst_attribs,
                    inpage_sym_height_mm=inpage_sym_height_mm
                    if et == ENTITY_TYPE_INPAGE_REF
                    else None,
                    page_ref_target_broken=page_ref_break,
                )
                self.addItem(it)
                self._symbol_items[uid] = it
            if e.dxftype() == "LWPOLYLINE" and is_wire_layer(str(e.dxf.layer)) and get_type(e) == "WIRE" and uid:
                pts = [
                    (float(r[0]), float(r[1]), float(r[2]) if len(r) > 2 else 0.0)
                    for r in e.get_points("xyb")
                ]
                log_ok, geo_ok = self._diagram.wire_connection_health(uid)
                broken = not (log_ok and geo_ok)
                lt_raw = getattr(e.dxf, "linetype", None)
                lt = str(lt_raw).strip() if lt_raw else ""
                if not lt:
                    lt = LINETYPE_LOGIC
                st = entity_stroke_qcolor(self._diagram.doc, e)
                if str(e.dxf.layer).strip().upper() == LAYER_WIRE_COM.upper():
                    st.setAlpha(0)
                wi = WireItem(uid, pts, broken=broken, linetype=lt, stroke_color=st)
                self.addItem(wi)
            if e.dxftype() == "LWPOLYLINE" and is_wire_layer(str(e.dxf.layer)) and get_type(e) == ENTITY_TYPE_WIRE_ARROW:
                row_list = list(e.get_points("xyb"))
                if len(row_list) < 2:
                    continue
                pts_xy = [(float(r[0]), float(r[1])) for r in row_list]
                lt_raw = getattr(e.dxf, "linetype", None)
                lt_a = str(lt_raw).strip() if lt_raw else ""
                if not lt_a:
                    lt_a = LINETYPE_LOGIC
                st_a = entity_stroke_qcolor(self._diagram.doc, e)
                # COM base wire centerline is hidden, but arrowheads must remain visible.
                self.addItem(WireArrowItem(pts_xy, linetype=lt_a, stroke_color=st_a))
            elif (
                e.dxftype() == "LWPOLYLINE"
                and str(e.dxf.layer) == LAYER_SYMBOL
                and get_type(e) == ENTITY_TYPE_GATE_INPUT_STUB_ARROW
            ):
                rows_ga = list(e.get_points("xyb"))
                if len(rows_ga) < 2:
                    continue
                pts_gate_arr = [(float(r[0]), float(r[1])) for r in rows_ga]
                lt_g = getattr(e.dxf, "linetype", None)
                lt_ag = str(lt_g).strip() if lt_g else ""
                if not lt_ag:
                    lt_ag = LINETYPE_CONTINUOUS
                st_ag = entity_stroke_qcolor(self._diagram.doc, e)
                self.addItem(WireArrowItem(pts_gate_arr, linetype=lt_ag, stroke_color=st_ag))
            if e.dxftype() == "LWPOLYLINE" and e.dxf.layer in (LAYER_FRAME, LAYER_VPORT):
                pts: list[tuple[float, float]] = []
                with e.points() as p:
                    for row in p:
                        x, y, *_ = row
                        pts.append((float(x), float(y)))
                if len(pts) < 2:
                    continue
                path = QPainterPath()
                path.moveTo(dxf_to_scene(*pts[0]))
                for xy in pts[1:]:
                    path.lineTo(dxf_to_scene(*xy))
                if bool(e.closed):
                    path.closeSubpath()
                pip = QGraphicsPathItem(path)
                if e.dxf.layer == LAYER_FRAME:
                    pc = QColor(110, 115, 128)
                else:
                    pc = QColor(75, 115, 135)
                pp = QPen(pc, 0)
                pp.setCosmetic(True)
                if e.dxf.layer == LAYER_VPORT:
                    pp.setStyle(Qt.PenStyle.DashLine)
                pip.setPen(pp)
                pip.setZValue(CANVAS_Z_FRAME_VPORT_PREVIEW)
                self.addItem(pip)
            if e.dxftype() == "LWPOLYLINE" and uid and is_user_sketch_wire_layer(_layer_name):
                et = get_type(e)
                if et == ENTITY_TYPE_USER_CLOUD:
                    points_xyb = [
                        (float(row[0]), float(row[1]), float(row[2]) if len(row) > 2 else 0.0)
                        for row in e.get_points("xyb")
                    ]
                    lt = user_sketch_display_linetype_for_entity(e)
                    st = entity_stroke_qcolor(self._diagram.doc, e)
                    self.addItem(
                        UserCloudItem(
                            uid,
                            points_xyb,
                            is_closed=bool(e.closed),
                            linetype=lt,
                            stroke_color=st,
                        )
                    )
            if e.dxftype() == "MTEXT" and uid:
                et = get_type(e)
                if et == TOC_TEXT_TYPE:
                    layout = normalize_dxf_text_entity(e)
                    it = DxfMTextItem(layout)
                    self.addItem(it)
            if e.dxftype() == "LINE" and uid and (
                _layer_name == LAYER_ANNOTATION or is_user_sketch_wire_layer(_layer_name)
            ):
                et = get_type(e)
                if et == ENTITY_TYPE_USER_LINE:
                    x0, y0 = float(e.dxf.start.x), float(e.dxf.start.y)
                    x1, y1 = float(e.dxf.end.x), float(e.dxf.end.y)
                    lt = user_sketch_display_linetype_for_entity(e)
                    st = entity_stroke_qcolor(self._diagram.doc, e)
                    self.addItem(UserLineItem(uid, x0, y0, x1, y1, linetype=lt, stroke_color=st))
            if e.dxftype() == "CIRCLE" and uid and (
                _layer_name == LAYER_ANNOTATION or is_user_sketch_wire_layer(_layer_name)
            ):
                et = get_type(e)
                if et == ENTITY_TYPE_USER_CIRCLE:
                    cx, cy = float(e.dxf.center.x), float(e.dxf.center.y)
                    r = float(e.dxf.radius)
                    lt = user_sketch_display_linetype_for_entity(e)
                    st = entity_stroke_qcolor(self._diagram.doc, e)
                    self.addItem(UserCircleItem(uid, cx, cy, r, linetype=lt, stroke_color=st))
            if e.dxftype() == "ARC" and uid and (
                _layer_name == LAYER_ANNOTATION or is_user_sketch_wire_layer(_layer_name)
            ):
                et = get_type(e)
                if et == ENTITY_TYPE_USER_ARC:
                    cx, cy = float(e.dxf.center.x), float(e.dxf.center.y)
                    r = float(e.dxf.radius)
                    sa = float(e.dxf.start_angle)
                    ea = float(e.dxf.end_angle)
                    lt = user_sketch_display_linetype_for_entity(e)
                    st = entity_stroke_qcolor(self._diagram.doc, e)
                    self.addItem(
                        UserArcItem(uid, cx, cy, r, sa, ea, linetype=lt, stroke_color=st)
                    )
            if e.dxftype() == "TEXT" and str(e.dxf.layer) == LAYER_ANNOTATION and uid:
                et = get_type(e)
                if et == ENTITY_TYPE_USER_TEXT:
                    self.addItem(UserTextItem.from_dxf_entity(uid, e))
            add_passive_layout_primitive_items(self._diagram.doc, self, e)

    def _line_end_dxf(self, p0: tuple[float, float], scene_pos: QPointF, shift: bool) -> tuple[float, float]:
        return user_line_end_dxf_from_scene(p0, scene_pos, shift)

    def _circle_radius_mm(self, center: tuple[float, float], scene_pos: QPointF) -> float:
        tx, ty = snap_dxf_pos(*dxf_from_scene_pos(scene_pos))
        return circle_radius_mm_from_anchor_and_cursor_dxf(
            center, (tx, ty), snap_pitch_mm=float(GRID_PITCH)
        )

    @staticmethod
    def _signed_area2(vertices: list[tuple[float, float]]) -> float:
        if len(vertices) < 3:
            return 0.0
        area2 = 0.0
        count = len(vertices)
        for i in range(count):
            x0, y0 = vertices[i]
            x1, y1 = vertices[(i + 1) % count]
            area2 += x0 * y1 - x1 * y0
        return area2

    def _open_preview_bulge(self, vertices: list[tuple[float, float]]) -> float:
        if self._signed_area2(vertices) > 0.0:
            return abs(float(USER_CLOUD_BULGE))
        return -abs(float(USER_CLOUD_BULGE))

    def _update_sketch_line_preview(self, mouse_scene: QPointF, modifiers: Qt.KeyboardModifier) -> None:
        if self._sketch_preview_line is None or self._sketch_p0_dxf is None:
            return
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        p1 = self._line_end_dxf(self._sketch_p0_dxf, mouse_scene, shift)
        p0s = dxf_to_scene(*self._sketch_p0_dxf)
        p1s = dxf_to_scene(*p1)
        self._sketch_preview_line.setLine(p0s.x(), p0s.y(), p1s.x(), p1s.y())

    def _update_sketch_circle_preview(self, mouse_scene: QPointF) -> None:
        if self._sketch_preview_circle is None or self._sketch_p0_dxf is None:
            return
        r = self._circle_radius_mm(self._sketch_p0_dxf, mouse_scene)
        cx, cy = self._sketch_p0_dxf
        top_left = dxf_to_scene(cx - r, cy + r)
        self._sketch_preview_circle.setRect(top_left.x(), top_left.y(), 2 * r, 2 * r)

    def _update_sketch_arc_preview(self, mouse_scene: QPointF) -> None:
        """Rubber-band arc through two fixed points and the snapped cursor position."""
        if self._sketch_preview_arc is None or len(self._sketch_arc_dxf_pts) != 2:
            return
        p0, p1 = self._sketch_arc_dxf_pts[0], self._sketch_arc_dxf_pts[1]
        tx, ty = snap_dxf_pos(*dxf_from_scene_pos(mouse_scene))
        path = user_arc_preview_qpainterpath_from_three_points(p0, p1, (tx, ty))
        if path is None:
            self._sketch_preview_arc.setPath(QPainterPath())
            return
        self._sketch_preview_arc.setPath(path)

    def _clear_sketch_arc_draft_auxiliary_graphics(self) -> None:
        """Remove chord rubber-band and vertex handles used only during USER_ARC placement."""

        if self._sketch_preview_arc_chord is not None:
            self.removeItem(self._sketch_preview_arc_chord)
            self._sketch_preview_arc_chord = None
        self._clear_sketch_arc_markers_only()

    def _clear_sketch_arc_markers_only(self) -> None:
        for mr in self._sketch_preview_arc_markers:
            self.removeItem(mr)
        self._sketch_preview_arc_markers.clear()

    def _update_sketch_arc_chord_preview(self, mouse_scene: QPointF) -> None:
        if self._sketch_preview_arc_chord is None or len(self._sketch_arc_dxf_pts) != 1:
            return
        p0 = self._sketch_arc_dxf_pts[0]
        tx, ty = snap_dxf_pos(*dxf_from_scene_pos(mouse_scene))
        p0s = dxf_to_scene(*p0)
        p1s = dxf_to_scene(tx, ty)
        self._sketch_preview_arc_chord.setLine(p0s.x(), p0s.y(), p1s.x(), p1s.y())

    def _add_sketch_arc_locked_vertex_markers(self) -> None:
        self._clear_sketch_arc_markers_only()
        if len(self._sketch_arc_dxf_pts) < 2:
            return
        half = arc_vertex_marker_half_mm(float(GRID_PITCH))
        for x, y in self._sketch_arc_dxf_pts[:2]:
            mr = QGraphicsRectItem(-half, -half, 2.0 * half, 2.0 * half)
            mr.setBrush(QColor(100, 180, 220))
            mr.setPen(Qt.PenStyle.NoPen)
            mr.setZValue(10002.5)
            ps = dxf_to_scene(x, y)
            mr.setPos(ps)
            self.addItem(mr)
            self._sketch_preview_arc_markers.append(mr)

    def _cloud_preview_vertices(self, mouse_scene: QPointF) -> list[tuple[float, float]]:
        if not self._sketch_cloud_vertices_dxf:
            return []
        x, y = snap_dxf_pos(*dxf_from_scene_pos(mouse_scene))
        last_x, last_y = self._sketch_cloud_vertices_dxf[-1]
        if abs(x - last_x) < 1e-9 and abs(y - last_y) < 1e-9:
            return list(self._sketch_cloud_vertices_dxf)
        return [*self._sketch_cloud_vertices_dxf, (x, y)]

    def _update_sketch_cloud_preview(self, mouse_scene: QPointF) -> None:
        if self._sketch_preview_cloud is None:
            return
        vertices = self._cloud_preview_vertices(mouse_scene)
        path = QPainterPath()
        if len(vertices) < 2:
            self._sketch_preview_cloud.setPath(path)
            return
        if len(vertices) < 3:
            path.moveTo(dxf_to_scene(*vertices[0]))
            for x, y in vertices[1:]:
                path.lineTo(dxf_to_scene(x, y))
            self._sketch_preview_cloud.setPath(path)
            return
        try:
            bulge = self._open_preview_bulge(vertices)
            cloud_points = [
                (float(row[0]), float(row[1]), float(row[4]) if len(row) > 4 else 0.0)
                for row in revcloud.points(
                    vertices=vertices,
                    segment_length=max(0.25, GRID_PITCH),
                    bulge=bulge,
                    end_width=0.0,
                )
            ]
        except ValueError:
            path.moveTo(dxf_to_scene(*vertices[0]))
            for x, y in vertices[1:]:
                path.lineTo(dxf_to_scene(x, y))
            self._sketch_preview_cloud.setPath(path)
            return
        path.moveTo(dxf_to_scene(cloud_points[0][0], cloud_points[0][1]))
        seg_count = len(cloud_points) - 1
        for idx in range(max(0, seg_count)):
            x0, y0, bulge = cloud_points[idx]
            x1, y1, _next_bulge = cloud_points[(idx + 1) % len(cloud_points)]
            if abs(bulge) < 1e-12:
                path.lineTo(dxf_to_scene(x1, y1))
                continue
            append_bulge_arc_to_path(path, x0, y0, x1, y1, bulge, arc_segments=24)
        self._sketch_preview_cloud.setPath(path)

    def _finalize_sketch_cloud(self, *, is_closed: bool) -> None:
        if len(self._sketch_cloud_vertices_dxf) < 2:
            self.cancel_user_sketch()
            return
        min_vertices = 3 if is_closed else 2
        if len(self._sketch_cloud_vertices_dxf) < min_vertices:
            return
        try:
            with self._diagram.begin("user_geom"):
                self._diagram.add_user_cloud(
                    list(self._sketch_cloud_vertices_dxf),
                    segment_length=max(GRID_PITCH, 3),
                    linetype=LINETYPE_CONTINUOUS,
                    is_closed=is_closed,
                )
        except Exception:
            pass
        self.rebuild()

    def _handle_sketch_left_press(self, sp: QPointF, modifiers: Qt.KeyboardModifier) -> None:
        if self._sketch_tool == "line":
            if self._sketch_p0_dxf is None:
                self._sketch_p0_dxf = snap_dxf_pos(*dxf_from_scene_pos(sp))
                ln = QGraphicsLineItem()
                pen = QPen(QColor(180, 220, 255), 0)
                pen.setCosmetic(True)
                apply_dxf_linetype_to_pen(pen, self._user_sketch_line_linetype)
                ln.setPen(pen)
                ln.setZValue(10002.0)
                self._sketch_preview_line = ln
                self.addItem(ln)
                self._update_sketch_line_preview(sp, modifiers)
            else:
                p1 = self._line_end_dxf(self._sketch_p0_dxf, sp, bool(modifiers & Qt.KeyboardModifier.ShiftModifier))
                if abs(p1[0] - self._sketch_p0_dxf[0]) < 1e-9 and abs(p1[1] - self._sketch_p0_dxf[1]) < 1e-9:
                    return
                try:
                    with self._diagram.begin("user_geom"):
                        self._diagram.add_user_line(
                            self._sketch_p0_dxf, p1, self._user_sketch_line_linetype
                        )
                except Exception:
                    pass
                self.rebuild()
            return
        if self._sketch_tool == "circle":
            if self._sketch_p0_dxf is None:
                self._sketch_p0_dxf = snap_dxf_pos(*dxf_from_scene_pos(sp))
                el = QGraphicsEllipseItem()
                pen = QPen(QColor(180, 220, 255), 0)
                pen.setStyle(Qt.PenStyle.DashLine)
                pen.setCosmetic(True)
                el.setPen(pen)
                el.setBrush(Qt.BrushStyle.NoBrush)
                el.setZValue(10002.0)
                self._sketch_preview_circle = el
                self.addItem(el)
                self._update_sketch_circle_preview(sp)
            else:
                r = self._circle_radius_mm(self._sketch_p0_dxf, sp)
                if r < GRID_PITCH * 0.5:
                    return
                try:
                    with self._diagram.begin("user_geom"):
                        self._diagram.add_user_circle(self._sketch_p0_dxf, r, LINETYPE_CONTINUOUS)
                except Exception:
                    pass
                self.rebuild()
            return
        if self._sketch_tool == "arc":
            xd, yd = snap_dxf_pos(*dxf_from_scene_pos(sp))
            if len(self._sketch_arc_dxf_pts) == 0:
                self._sketch_arc_dxf_pts.append((xd, yd))
                chord = QGraphicsLineItem()
                pen_ch = QPen(QColor(180, 220, 255), 0)
                pen_ch.setStyle(Qt.PenStyle.DashLine)
                pen_ch.setCosmetic(True)
                chord.setPen(pen_ch)
                chord.setZValue(10002.0)
                self._sketch_preview_arc_chord = chord
                self.addItem(chord)
                self._update_sketch_arc_chord_preview(sp)
                return
            if len(self._sketch_arc_dxf_pts) == 1:
                if same_dxf_point(self._sketch_arc_dxf_pts[0], (xd, yd)):
                    return
                self._sketch_arc_dxf_pts.append((xd, yd))
                if self._sketch_preview_arc_chord is not None:
                    self.removeItem(self._sketch_preview_arc_chord)
                    self._sketch_preview_arc_chord = None
                self._add_sketch_arc_locked_vertex_markers()
                pip = QGraphicsPathItem()
                pen = QPen(QColor(180, 220, 255), 0)
                pen.setCosmetic(True)
                apply_dxf_linetype_to_pen(pen, self._user_sketch_line_linetype)
                pip.setPen(pen)
                pip.setBrush(Qt.BrushStyle.NoBrush)
                pip.setZValue(10002.0)
                self._sketch_preview_arc = pip
                self.addItem(pip)
                self._update_sketch_arc_preview(sp)
                return
            if len(self._sketch_arc_dxf_pts) == 2:
                p0, p1 = self._sketch_arc_dxf_pts[0], self._sketch_arc_dxf_pts[1]
                if same_dxf_point(p0, (xd, yd)) or same_dxf_point(p1, (xd, yd)):
                    return
                geom = try_dxf_arc_through_three_points(p0, p1, (xd, yd))
                if geom is None:
                    return
                (cx, cy), r, sa, ea = geom
                try:
                    with self._diagram.begin("user_geom"):
                        self._diagram.add_user_arc(
                            (cx, cy), r, sa, ea, self._user_sketch_line_linetype
                        )
                except Exception:
                    pass
                self.rebuild()
            return
        if self._sketch_tool == "cloud":
            xd, yd = snap_dxf_pos(*dxf_from_scene_pos(sp))
            if self._sketch_cloud_vertices_dxf:
                lx, ly = self._sketch_cloud_vertices_dxf[-1]
                if abs(xd - lx) < 1e-9 and abs(yd - ly) < 1e-9:
                    return
            self._sketch_cloud_vertices_dxf.append((xd, yd))
            if self._sketch_preview_cloud is None:
                pip = QGraphicsPathItem()
                pen = QPen(QColor(180, 220, 255), 0)
                pen.setStyle(Qt.PenStyle.DashLine)
                pen.setCosmetic(True)
                pip.setPen(pen)
                pip.setZValue(10002.0)
                self._sketch_preview_cloud = pip
                self.addItem(pip)
            self._update_sketch_cloud_preview(sp)
            return
        if self._sketch_tool == "text":
            xd, yd = snap_dxf_pos(*dxf_from_scene_pos(sp))
            par = QApplication.activeWindow()
            prompted = prompt_dxf_text_string_and_height(
                par,
                window_title="注釈テキスト",
                empty_text_warning_title="注釈テキスト",
                default_height_mm=float(USER_TEXT_DEFAULT_HEIGHT_MM),
            )
            if prompted is None:
                return
            text, h_mm = prompted
            try:
                with self._diagram.begin("user_geom"):
                    self._diagram.add_user_text((xd, yd), text.strip(), h_mm)
            except Exception:
                pass
            self.rebuild()

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._wire_seg_drag is not None:
            self._wire_preview_length_mm = None
            self._sketch_line_preview_length_mm = None
            self._clear_osnap_marker()
            wi, seg_i, press_dxf, orig_pts, _ = self._wire_seg_drag
            xd, yd = dxf_from_scene_pos(event.scenePos())
            p0, p1 = orig_pts[seg_i], orig_pts[seg_i + 1]
            if abs(p0[1] - p1[1]) < 1e-9:
                raw = yd - press_dxf[1]
            else:
                raw = xd - press_dxf[0]
            delta = snap_parallel_drag_delta_mm(raw, GRID_PITCH)
            new_pts = offset_polyline_segment_parallel(orig_pts, seg_i, delta)
            if new_pts is not None:
                wi.set_polyline_points(new_pts)
            else:
                wi.set_polyline_points(orig_pts)
            self._wire_seg_drag = (wi, seg_i, press_dxf, orig_pts, delta)
            event.accept()
            return
        if self._user_line_endpoint_drag is not None:
            self._wire_preview_length_mm = None
            self._sketch_line_preview_length_mm = None
            self._clear_osnap_marker()
            li, end_i = self._user_line_endpoint_drag
            ms = event.modifiers() | QApplication.keyboardModifiers()
            shift = bool(ms & Qt.KeyboardModifier.ShiftModifier)
            li.set_dragged_endpoint_scene(end_i, event.scenePos(), shift=shift)
            event.accept()
            return
        if self._sketch_tool == "line" and self._sketch_p0_dxf is not None and self._sketch_preview_line is not None:
            self._update_sketch_line_preview(event.scenePos(), event.modifiers())
        elif self._sketch_tool == "circle" and self._sketch_p0_dxf is not None and self._sketch_preview_circle is not None:
            self._update_sketch_circle_preview(event.scenePos())
        elif (
            self._sketch_tool == "arc"
            and len(self._sketch_arc_dxf_pts) == 1
            and self._sketch_preview_arc_chord is not None
        ):
            self._update_sketch_arc_chord_preview(event.scenePos())
        elif (
            self._sketch_tool == "arc"
            and len(self._sketch_arc_dxf_pts) == 2
            and self._sketch_preview_arc is not None
        ):
            self._update_sketch_arc_preview(event.scenePos())
        elif self._sketch_tool == "cloud" and self._sketch_cloud_vertices_dxf and self._sketch_preview_cloud is not None:
            self._update_sketch_cloud_preview(event.scenePos())
        super().mouseMoveEvent(event)
        spos = event.scenePos()
        if self._manual_wire_mode and self._wire_start is not None and self._manual_preview_dash is not None:
            self._update_manual_preview(spos)
            self._wire_preview_length_mm = self._compute_wire_preview_length_mm(spos)
            self._sketch_line_preview_length_mm = None
            self._clear_osnap_marker()
            self._update_connect_bbox_hover_port(spos)
            return
        if self._wire_rubber is not None and self._wire_anchor is not None:
            sp = spos
            self._wire_rubber.setLine(
                self._wire_anchor.x(),
                self._wire_anchor.y(),
                sp.x(),
                sp.y(),
            )
            self._wire_preview_length_mm = self._compute_wire_preview_length_mm(spos)
            self._sketch_line_preview_length_mm = None
        else:
            self._wire_preview_length_mm = None
        if self._sketch_tool == "line" and self._sketch_p0_dxf is not None and self._sketch_preview_line is not None:
            ln = self._sketch_preview_line.line()
            self._sketch_line_preview_length_mm = float(
                math.hypot(ln.x2() - ln.x1(), ln.y2() - ln.y1())
            )
        else:
            self._sketch_line_preview_length_mm = None
        if not self._wire_mode and self._wire_seg_drag is None and self._user_line_endpoint_drag is None:
            self._update_wire_segment_hover(spos)
        self._update_osnap_feedback(spos)
        self._update_connect_bbox_hover_port(spos)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            if self._sketch_tool != "none" and (
                self._sketch_p0_dxf is not None or self._sketch_arc_dxf_pts
            ):
                self.cancel_user_sketch()
                event.accept()
                return
        if event.button() == Qt.MouseButton.LeftButton:
            sp = event.scenePos()
            if (
                self._sketch_tool != "none"
                and not self._wire_mode
                and not self._manual_wire_mode
            ):
                self._handle_sketch_left_press(sp, event.modifiers())
                event.accept()
                return
            top = self.itemAt(sp, QTransform())
            if (
                isinstance(top, WireItem)
                and self._on_hit_wire_clear_tools is not None
                and not self._wire_mode
                and not self._manual_wire_mode
            ):
                self._on_hit_wire_clear_tools()
            if not self._wire_mode:
                sels = self.selectedItems()
                if len(sels) == 1 and isinstance(sels[0], WireItem):
                    wi = sels[0]
                    seg = wi.hit_eligible_parallel_segment(sp)
                    if seg is not None:
                        self._wire_seg_drag = (wi, seg, dxf_from_scene_pos(sp), wi.points_dxf(), 0.0)
                        event.accept()
                        return
                if len(sels) == 1 and isinstance(sels[0], UserLineItem):
                    li2 = sels[0]
                    end_i = li2.hit_endpoint_index(sp)
                    if end_i is not None:
                        self._user_line_endpoint_drag = (li2, end_i)
                        event.accept()
                        return
            if self._wire_mode:
                port_hit = self._wire_port_hit_at_scene_pos(
                    sp,
                    allow_osnap=True,
                )
                if port_hit is not None:
                    uid, pk, _sym = port_hit
                    pk = self._normalize_wire_endpoint_port_key(uid, pk)
                    sym = self._symbol_items.get(uid)
                    if sym is None:
                        event.accept()
                        return
                    if self._manual_wire_mode:
                        if self._wire_start is None:
                            self._wire_start = (uid, pk)
                            self.update()
                            self._diagram.rebuild_index()
                            pw = self._diagram.index.get_port_world(uid, pk)
                            if pw is not None:
                                self._manual_p0_dxf = (float(pw[0]), float(pw[1]))
                            else:
                                self._manual_p0_dxf = None
                            self._manual_bends_dxf.clear()
                            ap = sym.port_scene_pos(pk)
                            if ap is not None and self._manual_p0_dxf is not None:
                                pen_s = QPen(QColor(255, 200, 130), 0)
                                pen_s.setStyle(Qt.PenStyle.SolidLine)
                                pen_s.setCosmetic(True)
                                sol = QGraphicsPathItem()
                                sol.setPen(pen_s)
                                sol.setZValue(10000.0)
                                self._manual_preview_solid = sol
                                self.addItem(sol)
                                pen_d = QPen(QColor(255, 190, 120), 0)
                                pen_d.setStyle(Qt.PenStyle.DashLine)
                                pen_d.setCosmetic(True)
                                dash = QGraphicsPathItem()
                                dash.setPen(pen_d)
                                dash.setZValue(10001.0)
                                self._manual_preview_dash = dash
                                self.addItem(dash)
                                self._update_manual_preview(sp)
                        else:
                            su, spk = self._wire_start
                            if uid != su or pk != spk:
                                try:
                                    with self._diagram.begin("wire_manual"):
                                        self._diagram.connect_ports_manual(
                                            su, spk, uid, pk, list(self._manual_bends_dxf)
                                        )
                                except ValueError as ex:
                                    if self._on_wire_error is not None:
                                        self._on_wire_error(str(ex))
                                self.rebuild()
                        event.accept()
                        return
                    if self._wire_start is None:
                        self._wire_start = (uid, pk)
                        self.update()
                        ap = sym.port_scene_pos(pk)
                        if ap is not None:
                            self._wire_anchor = ap
                            ln = QGraphicsLineItem(ap.x(), ap.y(), ap.x(), ap.y())
                            pen = QPen(QColor(120, 200, 255), 0)
                            pen.setStyle(Qt.PenStyle.DashLine)
                            pen.setCosmetic(True)
                            ln.setPen(pen)
                            ln.setZValue(10000.0)
                            self._wire_rubber = ln
                            self.addItem(ln)
                    else:
                        assert self._wire_start is not None
                        su, spk = self._wire_start
                        if su != uid:
                            try:
                                with self._diagram.begin("wire"):
                                    self._diagram.connect_ports(su, spk, uid, pk)
                            except ValueError as ex:
                                if self._on_wire_error is not None:
                                    self._on_wire_error(str(ex))
                        self.rebuild()
                    event.accept()
                    return
                if self._manual_wire_mode and self._wire_start is not None and self._manual_p0_dxf is not None:
                    xd, yd = dxf_from_scene_pos(sp)
                    tx, ty = snap_dxf_pos(xd, yd)
                    last = self._dxf_last_for_manual()
                    if last is not None:
                        if abs(last[0] - tx) < 1e-9 and abs(last[1] - ty) < 1e-9:
                            event.accept()
                            return
                        if abs(last[0] - tx) > 1e-9 and abs(last[1] - ty) > 1e-9:
                            event.accept()
                            return
                        self._manual_bends_dxf.append((tx, ty))
                        self._update_manual_preview(sp)
                    event.accept()
                    return
            if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier:
                top = self.itemAt(sp, QTransform())
                if isinstance(top, WireItem):
                    pass
                elif isinstance(top, SymbolItem) and top.entity_type == "PAGE_REF" and not top.port_at_scene_pos(sp):
                    if self._on_navigate_page is not None:
                        ins = self._diagram.symbols.insert_by_uid(self._diagram.current_layout_name, top.symbol_uid)
                        if ins is not None:
                            xd = read_ld_app_dict(ins)
                            tgt = xd.get(TARGET_LAYOUT_XDATA)
                            if tgt and str(tgt) in self._diagram.list_pages():
                                peer = (xd.get(PEER_UID_XDATA) or "").strip()
                                self._on_navigate_page(str(tgt), peer or None)
                    event.accept()
                    return
                elif (
                    isinstance(top, SymbolItem)
                    and top.entity_type == ENTITY_TYPE_INPAGE_REF
                    and not top.port_at_scene_pos(sp)
                ):
                    if self._on_navigate_inpage_peer is not None:
                        ins = self._diagram.symbols.insert_by_uid(self._diagram.current_layout_name, top.symbol_uid)
                        if ins is not None:
                            xd = read_ld_app_dict(ins)
                            peer = (xd.get(PEER_UID_XDATA) or "").strip()
                            if peer:
                                self._on_navigate_inpage_peer(peer)
                    event.accept()
                    return
                elif isinstance(top, SymbolItem) and top.entity_type == ENTITY_TYPE_TOC_ROW and not top.port_at_scene_pos(
                    sp
                ):
                    if self._on_navigate_page is not None:
                        ins = self._diagram.symbols.insert_by_uid(self._diagram.current_layout_name, top.symbol_uid)
                        if ins is not None:
                            tgt = ""
                            for a in ins.attribs:
                                if str(a.dxf.tag).upper() == "PAGE_NAME":
                                    tgt = str(a.dxf.text or "").strip()
                                    break
                            if tgt and tgt in self._diagram.list_pages() and not is_toc_layout_name(tgt):
                                self._on_navigate_page(tgt, None)
                    event.accept()
                    return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._sketch_tool == "cloud"
            and self._sketch_cloud_vertices_dxf
            and not self._wire_mode
            and not self._manual_wire_mode
        ):
            clicked = snap_dxf_pos(*dxf_from_scene_pos(event.scenePos()))
            start = self._sketch_cloud_vertices_dxf[0]
            if same_dxf_point(clicked, start, tol=GRID_PITCH * 0.5):
                if same_dxf_point(self._sketch_cloud_vertices_dxf[-1], start):
                    self._sketch_cloud_vertices_dxf.pop()
                self._finalize_sketch_cloud(is_closed=True)
            else:
                if not same_dxf_point(self._sketch_cloud_vertices_dxf[-1], clicked):
                    self._sketch_cloud_vertices_dxf.append(clicked)
                self._finalize_sketch_cloud(is_closed=False)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._user_line_endpoint_drag is not None:
            self._user_line_endpoint_drag = None
        if event.button() == Qt.MouseButton.LeftButton and self._wire_seg_drag is not None:
            wi, seg_i, _press_dxf, orig_pts, last_delta = self._wire_seg_drag
            self._wire_seg_drag = None
            delta = last_delta
            if abs(delta) >= 1e-9:
                with self._diagram.begin("wire_segment_offset"):
                    ok = self._diagram.offset_wire_segment_parallel(wi.wire_uid, seg_i, delta)
                if not ok and self._on_wire_error is not None:
                    self._on_wire_error("辺の並行移動を適用できませんでした。")
            self.rebuild()
            event.accept()
            super().mouseReleaseEvent(event)
            return
        super().mouseReleaseEvent(event)
        if event.button() != Qt.MouseButton.LeftButton:
            return
        moved_syms: list[SymbolItem] = []
        moved_user: list[
            UserLineItem | UserCircleItem | UserArcItem | UserCloudItem | UserTextItem
        ] = []
        for it in self.selectedItems():
            if isinstance(it, SymbolItem) and getattr(it, "_moved", False):
                moved_syms.append(it)
            elif isinstance(
                it, (UserLineItem, UserCircleItem, UserArcItem, UserCloudItem, UserTextItem)
            ) and getattr(it, "_moved", False):
                moved_user.append(it)
        if not moved_syms and not moved_user:
            return
        # rebuild() でアイテムが作り直されるため、再構築前に選択 UID を退避する（整列・貼り付けと同様）
        preserve_symbol_uids: set[str] = set()
        preserve_sketch_uids: set[str] = set()
        for sel in self.selectedItems():
            if isinstance(sel, SymbolItem):
                preserve_symbol_uids.add(sel.symbol_uid)
            elif isinstance(
                sel, (UserLineItem, UserCircleItem, UserArcItem, UserCloudItem, UserTextItem)
            ):
                preserve_sketch_uids.add(sel.sketch_uid)
        uids = {it.symbol_uid for it in moved_syms}
        moved_symbol_targets: dict[str, tuple[float, float]] = {}
        symbol_move_deltas: dict[str, tuple[float, float]] = {}
        for it in moved_syms:
            x, y = it.dxf_insert_from_scene_pos()
            x, y = snap_dxf_pos(x, y)
            moved_symbol_targets[it.symbol_uid] = (x, y)
            ox, oy = float(it.insert_xy[0]), float(it.insert_xy[1])
            symbol_move_deltas[it.symbol_uid] = (x - ox, y - oy)
        try:
            with self._diagram.begin("move"):
                for it in moved_user:
                    self._commit_user_sketch_move(it)
                for it in moved_syms:
                    x, y = moved_symbol_targets[it.symbol_uid]
                    self._diagram.symbols.move_insert(self._diagram.current_layout_name, it.symbol_uid, (x, y))
                if moved_syms and not self._diagram.reroute_wires_after_symbol_moves(
                    uids, symbol_move_deltas=symbol_move_deltas or None
                ):
                    raise RerouteAfterGeometryChangeError()
        except RerouteAfterGeometryChangeError:
            if self._on_reroute_failed is not None:
                disp = "、".join(format_uid_display(u) for u in sorted(uids))
                self._on_reroute_failed(disp)
        finally:
            for it in moved_syms:
                it._moved = False
            for it in moved_user:
                it._moved = False
        self.rebuild()
        self.select_pasted_items(preserve_symbol_uids, preserve_sketch_uids)

    def _commit_user_sketch_move(
        self, it: UserLineItem | UserCircleItem | UserArcItem | UserCloudItem | UserTextItem
    ) -> None:
        g = self._diagram.user_geom
        if isinstance(it, UserLineItem):
            (x0, y0), (x1, y1) = it.line_endpoints_dxf()
            x0, y0 = snap_dxf_pos(x0, y0)
            x1, y1 = snap_dxf_pos(x1, y1)
            g.set_user_line_geometry(it.sketch_uid, (x0, y0), (x1, y1))
        elif isinstance(it, UserCircleItem):
            (cx, cy), r = it.center_radius_dxf()
            cx, cy = snap_dxf_pos(cx, cy)
            r = max(GRID_PITCH, round(r / GRID_PITCH) * GRID_PITCH)
            g.set_user_circle_geometry(it.sketch_uid, (cx, cy), r)
        elif isinstance(it, UserArcItem):
            (cx, cy), r, sa, ea = it.arc_geometry_dxf()
            cx, cy = snap_dxf_pos(cx, cy)
            r = max(GRID_PITCH, round(r / GRID_PITCH) * GRID_PITCH)
            g.set_user_arc_geometry(it.sketch_uid, (cx, cy), r, sa, ea)
        elif isinstance(it, UserCloudItem):
            points_xyb, is_closed = it.cloud_points_dxf()
            snapped = [(float(x), float(y), float(b)) for x, y, b in points_xyb]
            g.set_user_cloud_geometry(it.sketch_uid, snapped, is_closed=is_closed)
        elif isinstance(it, UserTextItem):
            ix, iy = it.insert_dxf()
            ix, iy = snap_dxf_pos(ix, iy)
            g.set_user_text_insert(it.sketch_uid, (ix, iy))
