"""Single graphics item per INSERT (ports + PAGE_REF: library block or chevron fallback)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsSceneContextMenuEvent,
    QMenu,
    QStyle,
    QStyleOptionGraphicsItem,
    QWidget,
)

from logic_cad.core.model.index_store import IndexStore
from logic_cad.core.routing import snap_to_grid
from logic_cad.core.services.dynamic_gate_factory import (
    GATE_SYM_TEXT_HEIGHT_MM,
    GateViewGeometry,
    gate_view_geometry_from_block_name,
)
from logic_cad.core.model.constants import (
    CHECKPOINT_MARK_RADIUS_MM,
    ENTITY_TYPE_CHECKPOINT,
    ENTITY_TYPE_INPAGE_REF,
    ENTITY_TYPE_PAPER_FRAME,
    ENTITY_TYPE_TOC_HEADER,
    ENTITY_TYPE_TOC_ROW,
    ENTITY_TYPE_WIRE_BRANCH,
    GATE_STATIC_TEXT_HEIGHT_AND_MM,
    GATE_STATIC_TEXT_HEIGHT_OR_MM,
    LINETYPE_LOGIC,
    WIRE_BRANCH_RADIUS_MM,
)
from logic_cad.core.routing.wire_arrow_geometry import wire_in_arrow_wing_points_xyb
from logic_cad.ui.block_paint import (
    block_has_sym_attdef,
    block_scaled_bounds_with_instance,
    glyph_upright_extra_deg,
    paint_block_definition,
    paint_text_path_mm,
)
from logic_cad.ui.scene_item.z_order import CANVAS_Z_PAPER_LIKE_SYMBOL, CANVAS_Z_SYMBOL_AND_WIRE_ARROW
from logic_cad.ui.items.wire_item import apply_dxf_linetype_to_pen, dxf_to_scene
from logic_cad.ui.snap_utils import dxf_from_scene_pos, scene_pos_from_dxf

if TYPE_CHECKING:
    from ezdxf.document import Drawing


def _dxf_to_local(dx: float, dy: float) -> QPointF:
    return QPointF(dx, -dy)


def _with_glyph_spin(painter: QPainter, g_extra: float, anchor: QPointF) -> bool:
    """If g_extra != 0, apply translate/rotate/translate around anchor; return True if caller must restore."""
    if abs(g_extra) < 1e-9:
        return False
    painter.save()
    painter.translate(anchor)
    painter.rotate(g_extra)
    painter.translate(-anchor)
    return True


class SymbolItem(QGraphicsItem):
    def __init__(
        self,
        symbol_uid: str,
        block_name: str,
        index: IndexStore,
        insert_xy: tuple[float, float],
        entity_type: str = "SYMBOL",
        rotation_deg: float = 0.0,
        static_label: str | None = None,
        sym_visible: bool = True,
        insert_block_name: str | None = None,
        doc: Drawing | None = None,
        scale_x: float = 1.0,
        scale_y: float = 1.0,
        instance_attribs: dict[str, tuple[str, bool]] | None = None,
        show_input_stub_in_arrow: bool = False,
        inpage_sym_height_mm: float | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.symbol_uid = symbol_uid
        self.block_name = block_name
        self.insert_xy = insert_xy
        self.entity_type = entity_type
        self._static_label = static_label
        self._sym_visible = sym_visible
        self._insert_block_name = insert_block_name
        self._doc = doc
        self._sx = float(scale_x) if scale_x else 1.0
        self._sy = float(scale_y) if scale_y else 1.0
        self._instance_attribs = dict(instance_attribs) if instance_attribs else {}
        self._rotation_deg = float(rotation_deg)
        self._gate_geom: GateViewGeometry | None = None
        _paper_like = entity_type in (
            ENTITY_TYPE_PAPER_FRAME,
            ENTITY_TYPE_TOC_HEADER,
            ENTITY_TYPE_TOC_ROW,
        )
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, not _paper_like)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not _paper_like)
        # Above WireItem so symbols take priority on overlapping picks (see scene_item.z_order).
        self.setZValue(CANVAS_Z_PAPER_LIKE_SYMBOL if _paper_like else CANVAS_Z_SYMBOL_AND_WIRE_ARROW)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges, True)
        self._moved = False
        self._ortho_axis_locked: str | None = None
        self._port_local: dict[str, QPointF] = {}
        self._bounds = QRectF()
        # WIRE_BRANCH: True when XDATA shows wires on both IN0_MULTI and OUT0_MULTI.
        self._wire_branch_fully_connected = True
        self._show_input_stub_in_arrow = bool(show_input_stub_in_arrow)
        self._inpage_sym_height_mm = inpage_sym_height_mm
        self._rebuild_geometry(index)
        ix, iy = insert_xy
        self.setPos(ix, -iy)
        # Match DXF INSERT: rotation about insertion point / block origin in item space, not bbox center.
        self.setTransformOriginPoint(0.0, 0.0)
        self.setRotation(-float(rotation_deg))
        self._moved = False

    def _rebuild_geometry(self, index: IndexStore) -> None:
        self._port_local.clear()
        ix, iy = self.insert_xy
        xs: list[float] = []
        ys: list[float] = []
        used_block = False
        for (uid, pk), (bx, by) in index.port_block_local.items():
            if uid != self.symbol_uid:
                continue
            used_block = True
            px = bx * self._sx
            py = -by * self._sy
            self._port_local[pk] = QPointF(px, py)
            xs.append(px)
            ys.append(py)
        if not used_block:
            for key, (wx, wy) in index.ports.items():
                if key[0] != self.symbol_uid:
                    continue
                port_key = key[1]
                lx, ly = wx - ix, wy - iy
                pt = _dxf_to_local(lx, ly)
                self._port_local[port_key] = pt
                xs.append(pt.x())
                ys.append(pt.y())

        pr = 0.35
        pad = 1.0
        self._gate_geom = None
        if self._insert_block_name:
            self._gate_geom = gate_view_geometry_from_block_name(self._insert_block_name)
        if self._gate_geom is not None:
            g = self._gate_geom
            margin = 0.2
            sym_bottom = 0.55
            if xs:
                x0 = min(0.0, min(xs)) - margin
                x1 = max(g.x_out, max(xs)) + margin
                y_top = min(-g.yT, min(ys)) - margin
                y_bot = max(-g.yB, max(ys), sym_bottom) + margin
            else:
                x0 = 0.0 - margin
                x1 = g.x_out + margin
                y_top = -g.yT - margin
                y_bot = max(-g.yB, sym_bottom) + margin
            self._bounds = QRectF(x0, y_top, x1 - x0, y_bot - y_top)
        elif xs:
            x0, x1 = min(xs) - pad - pr, max(xs) + pad + pr
            y0, y1 = min(ys) - pad - pr, max(ys) + pad + pr
            self._bounds = QRectF(x0, y0, x1 - x0, y1 - y0)
        else:
            self._bounds = QRectF(-2, -2, 8, 8)

        if self._doc is not None and self._insert_block_name and self._gate_geom is None:
            # PAGE_REF: SYM is often invisible in DXF for plot; editor still shows link target text.
            sym_vis = True if self.entity_type in ("PAGE_REF", ENTITY_TYPE_INPAGE_REF) else self._sym_visible
            qb = block_scaled_bounds_with_instance(
                self._doc,
                self._insert_block_name,
                self._sx,
                self._sy,
                glyph_extra_deg=glyph_upright_extra_deg(self._rotation_deg),
                instance_attribs=self._instance_attribs,
                sym_display_text=self.block_name,
                sym_tag_visible=sym_vis,
            )
            if qb is not None and not qb.isEmpty():
                self._bounds = self._bounds.united(qb)

        if self.entity_type == ENTITY_TYPE_CHECKPOINT:
            r = CHECKPOINT_MARK_RADIUS_MM
            pad = 0.35
            if xs:
                cx = sum(xs) / len(xs)
                cy = sum(ys) / len(ys)
            else:
                cx, cy = 0.0, 0.0
            self._bounds = QRectF(cx - r - pad, cy - r - pad, 2 * r + 2 * pad, 2 * r + 2 * pad)

        if self.entity_type == ENTITY_TYPE_WIRE_BRANCH:
            uid = self.symbol_uid
            in_ok = (uid, "IN0_MULTI") in index.connected_endpoint_ports
            out_ok = (uid, "OUT0_MULTI") in index.connected_endpoint_ports
            self._wire_branch_fully_connected = in_ok and out_ok

    def boundingRect(self) -> QRectF:
        return self._bounds

    @property
    def definition_block_name(self) -> str | None:
        """INSERT のブロック名（FLIPFLOP 等）。表示用 SYM 文字列は block_name。"""
        return self._insert_block_name

    def _paint_gate_body(self, painter: QPainter, g: GateViewGeometry) -> None:
        painter.setPen(QPen(QColor(220, 220, 220), 0))
        painter.setBrush(Qt.BrushStyle.NoBrush)

        def bl(x: float, y_block: float) -> QPointF:
            return QPointF(x, -y_block)

        # Left vertical (column grows with input count); input stubs; 4×4 square on right; output stub.
        painter.drawLine(bl(g.xL, g.yB), bl(g.xL, g.yT))
        for yi in g.stub_ys:
            painter.drawLine(bl(0.0, yi), bl(g.xL, yi))
        painter.drawLine(bl(g.xL, g.y_sq_B), bl(g.xR, g.y_sq_B))
        painter.drawLine(bl(g.xL, g.y_sq_T), bl(g.xR, g.y_sq_T))
        painter.drawLine(bl(g.xR, g.y_sq_B), bl(g.xR, g.y_sq_T))
        painter.drawLine(bl(g.xR, g.mid_y), bl(g.x_out, g.mid_y))

    def _paint_gate_stub_in_arrows(self, painter: QPainter, g: GateViewGeometry) -> None:
        """Draw WIRE-style IN arrow heads at each input stub root (vertical bar), not at port tips.

        Args:
            painter: Active painter (item coordinates; rotation applied by the item).
            g: Dynamic AND/OR geometry; uses ``stub_ys`` and ``xL`` for stub polylines.

        Returns:
            None
        """
        pen = QPen(QColor(200, 200, 210), 0)
        pen.setCosmetic(True)
        apply_dxf_linetype_to_pen(pen, LINETYPE_LOGIC)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for yi in g.stub_ys:
            tri = wire_in_arrow_wing_points_xyb([(0.0, yi, 0.0), (g.xL, yi, 0.0)])
            if tri is None:
                continue
            a_pt, p_pt, b_pt = tri
            path = QPainterPath()
            path.moveTo(dxf_to_scene(*a_pt))
            path.lineTo(dxf_to_scene(*p_pt))
            path.lineTo(dxf_to_scene(*b_pt))
            painter.drawPath(path)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        g_extra = glyph_upright_extra_deg(self._rotation_deg)
        if self.entity_type == "PAGE_REF":
            painted = (
                self._doc is not None
                and self._insert_block_name
                and paint_block_definition(
                    painter,
                    self._doc,
                    self._insert_block_name,
                    scale_x=self._sx,
                    scale_y=self._sy,
                    glyph_extra_deg=g_extra,
                    sym_tag_visible=True,
                    sym_display_text=self.block_name,
                    instance_attribs=self._instance_attribs,
                )
            )
            if not painted:
                painter.setPen(QPen(QColor(180, 200, 255), 0))
                painter.setBrush(QBrush(QColor(40, 50, 70)))
                painter.drawRoundedRect(self._bounds, 0.4, 0.4)
                painter.setFont(QFont("Consolas", 2.0))
                label = self.block_name[:28] if len(self.block_name) > 28 else self.block_name
                tr = self._bounds.adjusted(1.2, 0.2, -1.2, -0.2)
                spin = _with_glyph_spin(painter, g_extra, tr.center())
                try:
                    painter.drawText(
                        tr,
                        Qt.AlignmentFlag.AlignCenter,
                        f"> {label} >",
                    )
                finally:
                    if spin:
                        painter.restore()
            pr = 0.12
            painter.setPen(QPen(QColor(120, 220, 120), 0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for _pk, pt in self._port_local.items():
                painter.drawEllipse(pt, pr, pr)
        elif self.entity_type == ENTITY_TYPE_INPAGE_REF:
            painted = (
                self._doc is not None
                and self._insert_block_name
                and paint_block_definition(
                    painter,
                    self._doc,
                    self._insert_block_name,
                    scale_x=self._sx,
                    scale_y=self._sy,
                    glyph_extra_deg=g_extra,
                    sym_tag_visible=True,
                    sym_display_text=self.block_name,
                    instance_attribs=self._instance_attribs,
                    sym_height_mm=self._inpage_sym_height_mm,
                )
            )
            if not painted:
                painter.setPen(QPen(QColor(200, 200, 210), 0))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawText(self._bounds, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.block_name)
            pr = 0.12
            painter.setPen(QPen(QColor(120, 220, 120), 0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for _pk, pt in self._port_local.items():
                painter.drawEllipse(pt, pr, pr)
        elif self.entity_type == ENTITY_TYPE_CHECKPOINT:
            cx = cy = 0.0
            if self._port_local:
                pts = list(self._port_local.values())
                cx = sum(p.x() for p in pts) / len(pts)
                cy = sum(p.y() for p in pts) / len(pts)
            r = CHECKPOINT_MARK_RADIUS_MM
            painter.setPen(QPen(QColor(70, 130, 255), 0))
            painter.setBrush(QBrush(QColor(80, 150, 255, 200)))
            painter.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))
            pr = 0.12
            painter.setPen(QPen(QColor(120, 220, 120), 0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for _pk, pt in self._port_local.items():
                painter.drawEllipse(pt, pr, pr)
        elif self.entity_type == ENTITY_TYPE_WIRE_BRANCH:
            r = WIRE_BRANCH_RADIUS_MM
            # Body colour from XDATA wire endpoints only (not click-time port hints).
            if self._wire_branch_fully_connected:
                pen_c = QColor(220, 220, 220)
                fill_c = QColor(220, 220, 220)
            else:
                pen_c = QColor(200, 50, 50)
                fill_c = QColor(220, 80, 80)
            painter.setPen(QPen(pen_c, 0))
            painter.setBrush(QBrush(fill_c))
            painter.drawEllipse(QRectF(-r, -r, 2 * r, 2 * r))
        else:
            painter.setPen(QPen(QColor(220, 220, 220), 0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if self._gate_geom is not None:
                self._paint_gate_body(painter, self._gate_geom)
                if self._show_input_stub_in_arrow and self.entity_type in ("AND", "OR"):
                    self._paint_gate_stub_in_arrows(painter, self._gate_geom)
            elif (
                self._doc is not None
                and self._insert_block_name
                and paint_block_definition(
                    painter,
                    self._doc,
                    self._insert_block_name,
                    scale_x=self._sx,
                    scale_y=self._sy,
                    glyph_extra_deg=g_extra,
                    sym_tag_visible=self._sym_visible,
                    sym_display_text=self.block_name,
                    instance_attribs=self._instance_attribs,
                )
            ):
                pass
            else:
                painter.drawRect(self._bounds)

            pr = 0.12
            painter.setPen(QPen(QColor(120, 220, 120), 0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for _pk, pt in self._port_local.items():
                painter.drawEllipse(pt, pr, pr)

            painter.setPen(QPen(QColor(220, 220, 220), 0))
            _txt_col = QColor(220, 220, 220)
            _sf = min(abs(self._sx), abs(self._sy)) if self._sx and self._sy else 1.0
            if self._static_label is not None:
                if self._gate_geom is not None:
                    g = self._gate_geom
                    cx = (g.xL + g.xR) / 2.0
                    pos_st = QPointF(cx, -g.mid_y)
                    h_st = (
                        GATE_STATIC_TEXT_HEIGHT_AND_MM
                        if self.entity_type == "AND"
                        else GATE_STATIC_TEXT_HEIGHT_OR_MM
                    )
                    paint_text_path_mm(
                        painter,
                        self._static_label,
                        h_st * _sf,
                        pos_st,
                        glyph_extra_deg=g_extra,
                        halign=1,
                        valign=2,
                        fill=_txt_col,
                    )
                else:
                    painter.setFont(QFont("sans-serif", 2.2))
                    sr = self._bounds.adjusted(0.5, 0.3, -0.5, -1.2)
                    spin = _with_glyph_spin(painter, g_extra, sr.center())
                    try:
                        painter.drawText(
                            sr,
                            Qt.AlignmentFlag.AlignCenter,
                            self._static_label,
                        )
                    finally:
                        if spin:
                            painter.restore()
                if self._sym_visible and self.block_name:
                    if self._gate_geom is not None:
                        g = self._gate_geom
                        pos_sym = QPointF(g.xL + 0.15, -g.sym_y)
                        paint_text_path_mm(
                            painter,
                            self.block_name[:24],
                            GATE_SYM_TEXT_HEIGHT_MM * _sf,
                            pos_sym,
                            glyph_extra_deg=g_extra,
                            fill=_txt_col,
                        )
                    elif not (
                        self._doc is not None
                        and self._insert_block_name
                        and block_has_sym_attdef(self._doc, self._insert_block_name)
                    ):
                        painter.setFont(QFont("sans-serif", 1.35))
                        foot = QRectF(
                            self._bounds.left(),
                            self._bounds.bottom() + 0.15,
                            self._bounds.width(),
                            1.8,
                        )
                        spin = _with_glyph_spin(painter, g_extra, foot.center())
                        try:
                            painter.drawText(
                                foot,
                                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                                self.block_name[:24],
                            )
                        finally:
                            if spin:
                                painter.restore()
            elif self._sym_visible:
                # SYM is already drawn via ATTDEF in paint_block_definition when the block defines SYM.
                if (
                    self._doc is not None
                    and self._insert_block_name
                    and block_has_sym_attdef(self._doc, self._insert_block_name)
                ):
                    pass
                else:
                    c = self._bounds.center()
                    pt = c + QPointF(-18, 4)
                    spin = _with_glyph_spin(painter, g_extra, pt)
                    try:
                        painter.drawText(pt, self.block_name[:12])
                    finally:
                        if spin:
                            painter.restore()

        if option.state & QStyle.StateFlag.State_Selected:
            r = self._bounds.adjusted(-0.5, -0.5, 0.5, 0.5)
            pen = QPen(QColor(90, 170, 255), 0)
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(r)

    def refresh_ports(self, index: IndexStore) -> None:
        self.prepareGeometryChange()
        self._rebuild_geometry(index)
        self.setTransformOriginPoint(0.0, 0.0)
        self.update()

    def port_scene_pos(self, port_key: str) -> QPointF | None:
        pt = self._port_local.get(port_key)
        if pt is None:
            return None
        return self.mapToScene(pt)

    def port_keys(self) -> tuple[str, ...]:
        """Return all port keys currently present on this symbol item."""
        return tuple(self._port_local.keys())

    def port_at_scene_pos(self, scene_pos: QPointF, tol: float = 1.2) -> str | None:
        lp = self.mapFromScene(scene_pos)
        for key, pt in self._port_local.items():
            if (lp - pt).manhattanLength() <= tol + 0.15:
                return key
        return None

    def dxf_insert_from_scene_pos(self) -> tuple[float, float]:
        p = self.pos()
        return float(p.x()), float(-p.y())

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
        if self.entity_type in (
            ENTITY_TYPE_TOC_HEADER,
            ENTITY_TYPE_TOC_ROW,
            ENTITY_TYPE_PAPER_FRAME,
        ):
            event.accept()
            return
        menu = QMenu()
        sc = self.scene()
        if sc is not None:
            rc = getattr(sc, "run_clipboard_copy", None)
            rp = getattr(sc, "run_clipboard_paste", None)
            if callable(rc):
                menu.addAction("コピー", rc)
            if callable(rp):
                menu.addAction("貼り付け", rp)
            if menu.actions():
                menu.addSeparator()
        a_cw = menu.addAction("90° 回転（時計回り）")
        a_ccw = menu.addAction("90° 回転（反時計回り）")
        menu.addSeparator()
        a_del = menu.addAction("削除")
        chosen = menu.exec(event.screenPos())
        if sc is None:
            event.accept()
            return
        if chosen == a_cw and hasattr(sc, "request_rotate_symbol"):
            sc.request_rotate_symbol(self.symbol_uid, -90)
        elif chosen == a_ccw and hasattr(sc, "request_rotate_symbol"):
            sc.request_rotate_symbol(self.symbol_uid, 90)
        elif chosen == a_del and hasattr(sc, "request_delete_selected_symbols"):
            sc.request_delete_selected_symbols(self)
        event.accept()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            if isinstance(value, QPointF):
                kb = QApplication.keyboardModifiers()
                if kb & Qt.KeyboardModifier.ShiftModifier and self.isSelected():
                    old_pos = self.pos()
                    delta = value - old_pos
                    if self._ortho_axis_locked is None:
                        if abs(delta.x()) >= abs(delta.y()):
                            self._ortho_axis_locked = "h"
                        else:
                            self._ortho_axis_locked = "v"
                    if self._ortho_axis_locked == "h":
                        value = QPointF(value.x(), old_pos.y())
                    else:
                        value = QPointF(old_pos.x(), value.y())
                else:
                    self._ortho_axis_locked = None

                xd, yd = dxf_from_scene_pos(value)
                sx, sy = snap_to_grid(xd, yd)
                value = scene_pos_from_dxf(sx, sy)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self._moved = True
            if not (QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier) or not self.isSelected():
                self._ortho_axis_locked = None
        return super().itemChange(change, value)
