"""Graphics items for user-drawn sketch entities."""

from __future__ import annotations

import math

from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPainterPathStroker, QPen
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QStyle,
    QStyleOptionGraphicsItem,
    QWidget,
)

from logic_cad.core.model.constants import GRID_PITCH, LINETYPE_CONTINUOUS
from logic_cad.core.routing import snap_to_grid
from logic_cad.core.text.layout_resolver import NormalizedTextLayout, normalize_dxf_text_entity
from logic_cad.ui.block_paint import paint_text_path_mm, text_path_bounds_item_local
from logic_cad.ui.bulge_path import append_bulge_arc_to_path
from logic_cad.ui.items.wire_item import WIRE_AXIS_HIT_WIDTH_MM, apply_dxf_linetype_to_pen, dxf_to_scene
from logic_cad.ui.scene_item.hits import DEFAULT_SCENE_HIT_TOL_MM
from logic_cad.ui.scene_item.z_order import (
    CANVAS_Z_USER_ARC,
    CANVAS_Z_USER_CIRCLE,
    CANVAS_Z_USER_CLOUD,
    CANVAS_Z_USER_LINE,
    CANVAS_Z_USER_TEXT,
)
from logic_cad.ui.snap_utils import (
    dxf_from_scene_pos,
    scene_pos_from_dxf,
    snap_pitch_for_qgraphics_item,
    user_line_end_dxf_from_scene,
)


class UserLineItem(QGraphicsLineItem):
    def __init__(
        self,
        sketch_uid: str,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        *,
        linetype: str = LINETYPE_CONTINUOUS,
        stroke_color: QColor | None = None,
        parent=None,
    ) -> None:
        p0 = dxf_to_scene(x0, y0)
        p1 = dxf_to_scene(x1, y1)
        super().__init__(p0.x(), p0.y(), p1.x(), p1.y(), parent)
        self.sketch_uid = sketch_uid
        self._linetype = linetype
        base = QColor(200, 200, 210) if stroke_color is None else QColor(stroke_color)
        pen = QPen(base, 0)
        pen.setCosmetic(True)
        apply_dxf_linetype_to_pen(pen, linetype)
        self.setPen(pen)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(CANVAS_Z_USER_LINE)
        self._moved = False

    def shape(self) -> QPainterPath:
        """Pick corridor like wire routing (≈ ±0.5 mm from axis)."""
        ln = self.line()
        path = QPainterPath()
        path.moveTo(ln.p1())
        path.lineTo(ln.p2())
        stroker = QPainterPathStroker()
        stroker.setWidth(WIRE_AXIS_HIT_WIDTH_MM)
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return stroker.createStroke(path)

    def boundingRect(self) -> QRectF:
        s = self.shape()
        if s.isEmpty():
            return super().boundingRect()
        return s.boundingRect()

    def line_endpoints_dxf(self) -> tuple[tuple[float, float], tuple[float, float]]:
        ln = self.line()
        a = self.mapToScene(ln.p1())
        b = self.mapToScene(ln.p2())
        return dxf_from_scene_pos(a), dxf_from_scene_pos(b)

    def hit_endpoint_index(
        self, scene_pos: QPointF, *, tol_mm: float = DEFAULT_SCENE_HIT_TOL_MM
    ) -> int | None:
        """Return 0/1 for start/end if *scene_pos* is within *tol_mm* in DXF space, else None."""
        ln = self.line()
        ax, ay = dxf_from_scene_pos(self.mapToScene(ln.p1()))
        bx, by = dxf_from_scene_pos(self.mapToScene(ln.p2()))
        px, py = dxf_from_scene_pos(scene_pos)
        d0 = (px - ax) ** 2 + (py - ay) ** 2
        d1 = (px - bx) ** 2 + (py - by) ** 2
        tol2 = float(tol_mm) * float(tol_mm)
        ok0, ok1 = d0 <= tol2, d1 <= tol2
        if ok0 and ok1:
            return 0 if d0 <= d1 else 1
        if ok0:
            return 0
        if ok1:
            return 1
        return None

    def set_dragged_endpoint_scene(self, index: int, scene_pos: QPointF, *, shift: bool = False) -> None:
        """Update one endpoint (grid; Shift matches new-line tool ortho). Opposite end is the anchor."""
        a, b = self.line_endpoints_dxf()
        anchor = b if index == 0 else a
        pitch = snap_pitch_for_qgraphics_item(self)
        sx, sy = user_line_end_dxf_from_scene(anchor, scene_pos, shift, pitch=pitch)
        pl = self.mapFromScene(scene_pos_from_dxf(sx, sy))
        ln = self.line()
        if index == 0:
            self.setLine(pl.x(), pl.y(), ln.x2(), ln.y2())
        else:
            self.setLine(ln.x1(), ln.y1(), pl.x(), pl.y())
        self._moved = True
        self.update()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            if isinstance(value, QPointF):
                xd, yd = dxf_from_scene_pos(value)
                pitch = snap_pitch_for_qgraphics_item(self)
                sx, sy = snap_to_grid(xd, yd, pitch)
                value = scene_pos_from_dxf(sx, sy)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self._moved = True
        return super().itemChange(change, value)

    def paint(self, painter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None) -> None:
        super().paint(painter, option, widget)
        ln = self.line()
        if option.state & QStyle.StateFlag.State_Selected:
            p = QPen(QColor(90, 170, 255), 0)
            p.setCosmetic(True)
            base = self.pen()
            p.setStyle(base.style())
            p.setDashPattern(base.dashPattern())
            painter.setPen(p)
            painter.drawLine(ln)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(90, 170, 255, 90))
            grip = 0.5
            for pt in (ln.p1(), ln.p2()):
                painter.drawEllipse(pt, grip, grip)


class UserCircleItem(QGraphicsEllipseItem):
    def __init__(
        self,
        sketch_uid: str,
        cx: float,
        cy: float,
        radius: float,
        *,
        linetype: str = LINETYPE_CONTINUOUS,
        stroke_color: QColor | None = None,
        parent=None,
    ) -> None:
        r = float(radius)
        top_left = dxf_to_scene(cx - r, cy + r)
        br = QRectF(top_left.x(), top_left.y(), 2 * r, 2 * r)
        super().__init__(br, parent)
        self.sketch_uid = sketch_uid
        self._linetype = linetype
        base = QColor(200, 200, 210) if stroke_color is None else QColor(stroke_color)
        pen = QPen(base, 0)
        pen.setCosmetic(True)
        apply_dxf_linetype_to_pen(pen, linetype)
        self.setPen(pen)
        self.setBrush(Qt.BrushStyle.NoBrush)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(CANVAS_Z_USER_CIRCLE)
        self._moved = False

    def center_radius_dxf(self) -> tuple[tuple[float, float], float]:
        c_scene = self.mapToScene(self.rect().center())
        xd, yd = dxf_from_scene_pos(c_scene)
        r = float(self.rect().width()) * 0.5
        return (xd, yd), r

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            if isinstance(value, QPointF):
                xd, yd = dxf_from_scene_pos(value)
                pitch = snap_pitch_for_qgraphics_item(self)
                sx, sy = snap_to_grid(xd, yd, pitch)
                value = scene_pos_from_dxf(sx, sy)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self._moved = True
        return super().itemChange(change, value)

    def paint(self, painter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None) -> None:
        super().paint(painter, option, widget)
        if option.state & QStyle.StateFlag.State_Selected:
            p = QPen(QColor(90, 170, 255), 0)
            p.setCosmetic(True)
            base = self.pen()
            p.setStyle(base.style())
            p.setDashPattern(base.dashPattern())
            painter.setPen(p)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(self.rect())


_ARC_TESSELLATION_SEGMENTS: int = 64


def _dxf_arc_ccw_span_deg(start_deg: float, end_deg: float) -> float:
    """Return CCW angle span in degrees from DXF *start_deg* to *end_deg* (may be 360)."""
    span = (float(end_deg) - float(start_deg)) % 360.0
    if span <= 1e-12:
        return 360.0
    return span


def _build_user_arc_path(
    cx: float,
    cy: float,
    radius: float,
    start_angle_deg: float,
    end_angle_deg: float,
) -> QPainterPath:
    """Polyline-approximated arc in scene coordinates (DXF CCW)."""
    r = float(radius)
    sa = float(start_angle_deg)
    span = _dxf_arc_ccw_span_deg(sa, float(end_angle_deg))
    path = QPainterPath()
    n = max(8, _ARC_TESSELLATION_SEGMENTS)
    for i in range(n + 1):
        t = i / n
        ang = math.radians(sa + span * t)
        xd = float(cx) + r * math.cos(ang)
        yd = float(cy) + r * math.sin(ang)
        pt = dxf_to_scene(xd, yd)
        if i == 0:
            path.moveTo(pt)
        else:
            path.lineTo(pt)
    return path


def user_arc_path_scene(
    cx: float,
    cy: float,
    radius: float,
    start_angle_deg: float,
    end_angle_deg: float,
) -> QPainterPath:
    """Return a scene-space polyline path for a DXF CCW arc (for preview / items)."""
    return _build_user_arc_path(cx, cy, radius, start_angle_deg, end_angle_deg)


class UserArcItem(QGraphicsPathItem):
    """USER_ARC (DXF ARC): local path from stored center/radius/angles; ``pos()`` translates."""

    def __init__(
        self,
        sketch_uid: str,
        cx: float,
        cy: float,
        radius: float,
        start_angle_deg: float,
        end_angle_deg: float,
        *,
        linetype: str = LINETYPE_CONTINUOUS,
        stroke_color: QColor | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.sketch_uid = sketch_uid
        self._cx = float(cx)
        self._cy = float(cy)
        self._r = max(1e-303, float(radius))
        self._sa = float(start_angle_deg)
        self._ea = float(end_angle_deg)
        self._linetype = linetype
        self._moved = False
        self.setPath(user_arc_path_scene(self._cx, self._cy, self._r, self._sa, self._ea))
        base = QColor(200, 200, 210) if stroke_color is None else QColor(stroke_color)
        pen = QPen(base, 0)
        pen.setCosmetic(True)
        apply_dxf_linetype_to_pen(pen, linetype)
        self.setPen(pen)
        self.setBrush(Qt.BrushStyle.NoBrush)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(CANVAS_Z_USER_ARC)

    def shape(self) -> QPainterPath:
        """Axis corridor for picking (matches wire/user-line style)."""
        core = self.path()
        stroker = QPainterPathStroker()
        stroker.setWidth(WIRE_AXIS_HIT_WIDTH_MM)
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return stroker.createStroke(core)

    def boundingRect(self) -> QRectF:
        s = self.shape()
        if s.isEmpty():
            return super().boundingRect()
        return s.boundingRect()

    def arc_geometry_dxf(self) -> tuple[tuple[float, float], float, float, float]:
        """Return center, radius, and angles with scene translation applied (DXF mm, degrees)."""
        ox, oy = dxf_from_scene_pos(self.pos())
        return (self._cx + ox, self._cy + oy), self._r, self._sa, self._ea

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            if isinstance(value, QPointF):
                xd, yd = dxf_from_scene_pos(value)
                pitch = snap_pitch_for_qgraphics_item(self)
                sx, sy = snap_to_grid(xd, yd, pitch)
                value = scene_pos_from_dxf(sx, sy)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self._moved = True
        return super().itemChange(change, value)

    def paint(self, painter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None) -> None:
        super().paint(painter, option, widget)
        if option.state & QStyle.StateFlag.State_Selected:
            p = QPen(QColor(90, 170, 255), 0)
            p.setCosmetic(True)
            base = self.pen()
            p.setStyle(base.style())
            p.setDashPattern(base.dashPattern())
            painter.setPen(p)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self.path())


class UserCloudItem(QGraphicsPathItem):
    def __init__(
        self,
        sketch_uid: str,
        points_xyb: list[tuple[float, float, float]],
        *,
        is_closed: bool,
        linetype: str = LINETYPE_CONTINUOUS,
        stroke_color: QColor | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.sketch_uid = sketch_uid
        self._linetype = linetype
        self._points_xyb = [
            (float(x), float(y), float(b))
            for x, y, b in points_xyb
        ]
        self._is_closed = bool(is_closed)
        self._moved = False
        self._build_path()
        base = QColor(200, 200, 210) if stroke_color is None else QColor(stroke_color)
        pen = QPen(base, 0)
        pen.setCosmetic(True)
        apply_dxf_linetype_to_pen(pen, linetype)
        self.setPen(pen)
        self.setBrush(Qt.BrushStyle.NoBrush)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(CANVAS_Z_USER_CLOUD)

    def _build_path(self) -> None:
        path = QPainterPath()
        if not self._points_xyb:
            self.setPath(path)
            return
        path.moveTo(dxf_to_scene(self._points_xyb[0][0], self._points_xyb[0][1]))
        count = len(self._points_xyb)
        seg_count = count if self._is_closed else count - 1
        for idx in range(max(0, seg_count)):
            x0, y0, bulge = self._points_xyb[idx]
            x1, y1, _next_bulge = self._points_xyb[(idx + 1) % count]
            if abs(bulge) < 1e-12:
                path.lineTo(dxf_to_scene(x1, y1))
                continue
            append_bulge_arc_to_path(path, x0, y0, x1, y1, bulge, arc_segments=32)
        if self._is_closed:
            path.closeSubpath()
        self.setPath(path)

    def cloud_points_dxf(self) -> tuple[list[tuple[float, float, float]], bool]:
        offset_dxf = dxf_from_scene_pos(self.pos())
        ox, oy = float(offset_dxf[0]), float(offset_dxf[1])
        points = [(x + ox, y + oy, b) for x, y, b in self._points_xyb]
        return points, self._is_closed

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            if isinstance(value, QPointF):
                xd, yd = dxf_from_scene_pos(value)
                pitch = snap_pitch_for_qgraphics_item(self)
                sx, sy = snap_to_grid(xd, yd, pitch)
                value = scene_pos_from_dxf(sx, sy)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self._moved = True
        return super().itemChange(change, value)

    def paint(self, painter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None) -> None:
        super().paint(painter, option, widget)
        if option.state & QStyle.StateFlag.State_Selected:
            p = QPen(QColor(90, 170, 255), 0)
            p.setCosmetic(True)
            base = self.pen()
            p.setStyle(base.style())
            p.setDashPattern(base.dashPattern())
            painter.setPen(p)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self.path())


class UserTextItem(QGraphicsItem):
    """USER_TEXT (DXF TEXT): item origin is the normalized alignment anchor."""

    def __init__(
        self,
        sketch_uid: str,
        layout: NormalizedTextLayout,
        *,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.sketch_uid = sketch_uid
        self._layout = layout
        self.setPos(dxf_to_scene(self._layout.anchor_x, self._layout.anchor_y))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(CANVAS_Z_USER_TEXT)
        self._moved = False

    @classmethod
    def from_dxf_entity(cls, sketch_uid: str, entity: Any, *, parent=None) -> "UserTextItem":
        """Build from a layout TEXT tagged as USER_TEXT."""

        lay = normalize_dxf_text_entity(entity)
        return cls(sketch_uid, lay, parent=parent)

    def insert_dxf(self) -> tuple[float, float]:
        return dxf_from_scene_pos(self.pos())

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            if isinstance(value, QPointF):
                xd, yd = dxf_from_scene_pos(value)
                pitch = snap_pitch_for_qgraphics_item(self)
                sx, sy = snap_to_grid(xd, yd, pitch)
                value = scene_pos_from_dxf(sx, sy)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self._moved = True
        return super().itemChange(change, value)

    def boundingRect(self) -> QRectF:
        r = text_path_bounds_item_local(
            self._layout.text,
            self._layout.height_mm,
            QPointF(0, 0),
            rot_deg=self._layout.render_rotation_deg,
            halign=self._layout.render_halign,
            valign=self._layout.render_valign,
            width_fac=self._layout.render_width_factor,
            fit_length_mm=self._layout.render_fit_length_mm,
            fit_mode=self._layout.render_fit_mode,
            font_family=self._layout.font_family,
            font_families=self._layout.font_families,
        )
        if r is None or r.isEmpty():
            return QRectF(0, 0, 1, 1)
        return r

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None) -> None:
        paint_text_path_mm(
            painter,
            self._layout.text,
            self._layout.height_mm,
            QPointF(0, 0),
            rot_deg=self._layout.render_rotation_deg,
            halign=self._layout.render_halign,
            valign=self._layout.render_valign,
            width_fac=self._layout.render_width_factor,
            fit_length_mm=self._layout.render_fit_length_mm,
            fit_mode=self._layout.render_fit_mode,
            fill=QColor(200, 200, 210),
            font_family=self._layout.font_family,
            font_families=self._layout.font_families,
        )
        if option.state & QStyle.StateFlag.State_Selected:
            p = QPen(QColor(90, 170, 255), 0)
            p.setCosmetic(True)
            p.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(p)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect())
