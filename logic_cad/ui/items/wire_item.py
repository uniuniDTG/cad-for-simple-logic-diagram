"""Graphics item for WIRE LWPOLYLINE (layers LD_WIRE_LOGIC / LD_WIRE_VALUE)."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPainterPathStroker, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem, QStyle, QStyleOptionGraphicsItem, QWidget
from ezdxf.math import Vec2, bulge_to_arc

from logic_cad.core.model.constants import LINETYPE_LOGIC, LINETYPE_VALUE, WIRE_BULGE_ARC_SEGMENTS
from logic_cad.core.routing.wire_polyline_geometry import (
    distance_sq_to_parallel_drag_run_xyb,
    parallel_drag_run_edge_range_xyb,
)
from logic_cad.ui.scene_item.hits import DEFAULT_SCENE_HIT_TOL_MM
from logic_cad.ui.scene_item.z_order import CANVAS_Z_WIRE
from logic_cad.ui.snap_utils import dxf_from_scene_pos

# Hit testing: corridor around centerline (± half width in mm, scene coords == DXF mm).
WIRE_AXIS_HIT_WIDTH_MM = 1.0

# Canvas preview for DXF CENTER (long dash, gap, short dash, gap) in pen-width units.
CENTER_DASH_PATTERN: list[float] = [20.0, 4.0, 4.0, 4.0]
DASH_PATTERN: list[float] = [10.0, 3.0]


def apply_dxf_linetype_to_pen(pen: QPen, linetype: str) -> None:
    u = (linetype or "").strip().upper()
    if u in ("BYLAYER", "BYBLOCK", "", LINETYPE_LOGIC, "CONTINUOUS"):
        pen.setStyle(Qt.PenStyle.SolidLine)
        pen.setDashPattern([])
        return
    if u == "CENTER":
        pen.setStyle(Qt.PenStyle.CustomDashLine)
        pen.setDashPattern(CENTER_DASH_PATTERN)
        return
    if u in (LINETYPE_VALUE, "DASHED", "HIDDEN", "PHANTOM", "DOT"):
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setDashPattern(DASH_PATTERN)
        return
    pen.setStyle(Qt.PenStyle.SolidLine)
    pen.setDashPattern([])


def dxf_to_scene(x: float, y: float) -> QPointF:
    return QPointF(x, -y)


def _normalize_xyb(
    points: list[tuple[float, ...]],
) -> list[tuple[float, float, float]]:
    out: list[tuple[float, float, float]] = []
    for p in points:
        x, y = float(p[0]), float(p[1])
        b = float(p[2]) if len(p) > 2 else 0.0
        out.append((x, y, b))
    return out


def _append_bulge_arc_to_path(path: QPainterPath, x0: float, y0: float, x1: float, y1: float, bulge: float) -> None:
    center, sa, ea, r = bulge_to_arc(Vec2(x0, y0), Vec2(x1, y1), bulge)
    # ezdxf returns CCW angles; for negative bulge they run end→start — swap so t=1..n hits chord end.
    if bulge < 0:
        sa, ea = ea, sa
    cx, cy = float(center.x), float(center.y)
    n = max(8, WIRE_BULGE_ARC_SEGMENTS)
    for k in range(1, n + 1):
        t = k / float(n)
        ang = sa + t * (ea - sa)
        xd = cx + r * math.cos(ang)
        yd = cy + r * math.sin(ang)
        path.lineTo(dxf_to_scene(xd, yd))


class WireItem(QGraphicsPathItem):
    def __init__(
        self,
        wire_uid: str,
        points: list[tuple[float, ...]],
        *,
        broken: bool = False,
        linetype: str = LINETYPE_LOGIC,
        stroke_color: QColor | None = None,
        parent=None,
    ) -> None:
        """Create a WIRE polyline item.

        Args:
            wire_uid: Stable wire entity UID.
            points: DXF ``xyb`` vertices.
            broken: When True, draw as disconnected (warning palette).
            linetype: DXF linetype name for dash style.
            stroke_color: BYLAYER-resolved stroke; default gray when omitted.
            parent: Optional parent item.
        """
        super().__init__(parent)
        self.wire_uid = wire_uid
        self._points = _normalize_xyb(points)
        self._broken = broken
        self._linetype = str(linetype or LINETYPE_LOGIC)
        self._hover_segment: int | None = None
        self._build_path(self._points)
        base = QColor(200, 200, 210) if stroke_color is None else QColor(stroke_color)
        pen = QPen(QColor(220, 80, 80) if broken else base, 0)
        pen.setCosmetic(True)
        apply_dxf_linetype_to_pen(pen, self._linetype)
        self.setPen(pen)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        # Below symbols so clicks hit SymbolItem first where paths overlap (see scene rebuild order).
        self.setZValue(CANVAS_Z_WIRE)

    def shape(self) -> QPainterPath:
        """Hit test along segments only, not the axis-aligned box of the whole polyline."""
        center = self.path()
        if center.isEmpty():
            return QPainterPath()
        stroker = QPainterPathStroker()
        stroker.setWidth(WIRE_AXIS_HIT_WIDTH_MM)
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return stroker.createStroke(center)

    def boundingRect(self):
        s = self.shape()
        if s.isEmpty():
            return super().boundingRect()
        return s.boundingRect()

    def points_dxf(self) -> list[tuple[float, float, float]]:
        return list(self._points)

    def _build_path(self, pts: list[tuple[float, float, float]]) -> None:
        path = QPainterPath()
        if not pts:
            self.setPath(path)
            return
        path.moveTo(dxf_to_scene(pts[0][0], pts[0][1]))
        for i in range(len(pts) - 1):
            x0, y0, b0 = pts[i][0], pts[i][1], pts[i][2]
            x1, y1 = pts[i + 1][0], pts[i + 1][1]
            if abs(b0) < 1e-12:
                path.lineTo(dxf_to_scene(x1, y1))
            else:
                _append_bulge_arc_to_path(path, x0, y0, x1, y1, b0)
        self.setPath(path)

    def _parallel_run_scene_path(self, e_lo: int, e_hi: int) -> QPainterPath:
        pts = self._points
        path = QPainterPath()
        path.moveTo(dxf_to_scene(pts[e_lo][0], pts[e_lo][1]))
        for i in range(e_lo, e_hi + 1):
            x0, y0, b0 = pts[i][0], pts[i][1], pts[i][2]
            x1, y1 = pts[i + 1][0], pts[i + 1][1]
            if abs(b0) < 1e-12:
                path.lineTo(dxf_to_scene(x1, y1))
            else:
                _append_bulge_arc_to_path(path, x0, y0, x1, y1, b0)
        return path

    def set_polyline_points(self, pts: list[tuple[float, ...]]) -> None:
        """Update geometry from DXF points (preview during segment drag)."""
        self._points = _normalize_xyb(pts)
        self._build_path(self._points)

    def set_hover_segment(self, seg_i: int | None) -> None:
        self._hover_segment = seg_i
        self.update()

    def hit_eligible_parallel_segment(
        self, scene_pos: QPointF, tol_mm: float = DEFAULT_SCENE_HIT_TOL_MM
    ) -> int | None:
        """Return first edge index of the logical run for P4 parallel drag, or None."""
        px, py = dxf_from_scene_pos(scene_pos)
        tol2 = tol_mm * tol_mm
        best_i: int | None = None
        best_d = tol2
        xyb = self._points
        n = len(xyb)
        processed: set[tuple[int, int]] = set()
        for seg_i in range(n - 1):
            run = parallel_drag_run_edge_range_xyb(xyb, seg_i)
            if run is None or run in processed:
                continue
            processed.add(run)
            e_lo, e_hi = run
            d2 = distance_sq_to_parallel_drag_run_xyb(px, py, xyb, e_lo, e_hi)
            if d2 <= best_d:
                best_d = d2
                best_i = e_lo
        return best_i

    def paint(self, painter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None) -> None:
        super().paint(painter, option, widget)
        if option.state & QStyle.StateFlag.State_Selected:
            p = QPen(QColor(255, 180, 90) if self._broken else QColor(90, 170, 255), 0)
            p.setCosmetic(True)
            base = self.pen()
            p.setStyle(base.style())
            p.setDashPattern(base.dashPattern())
            p.setDashOffset(base.dashOffset())
            painter.setPen(p)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self.path())
        if self._hover_segment is not None and 0 <= self._hover_segment < len(self._points) - 1:
            run = parallel_drag_run_edge_range_xyb(self._points, self._hover_segment)
            if run is not None:
                e_lo, e_hi = run
                hp = QPen(QColor(120, 255, 200), 0)
                hp.setCosmetic(True)
                hp.setStyle(Qt.PenStyle.SolidLine)
                painter.setPen(hp)
                painter.drawPath(self._parallel_run_scene_path(e_lo, e_hi))
