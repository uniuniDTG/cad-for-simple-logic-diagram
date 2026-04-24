"""IN-side wire arrow head geometry (DXF mm): two wings meeting at the last polyline vertex."""

from __future__ import annotations

import math

from ezdxf.math import Vec2, bulge_to_arc

from logic_cad.core.model.constants import WIRE_ARROW_BACK_MM, WIRE_ARROW_SIDE_MM


def wire_in_arrow_wing_points_xyb(
    xyb: list[tuple[float, float, float]],
    *,
    back_mm: float = WIRE_ARROW_BACK_MM,
    side_mm: float = WIRE_ARROW_SIDE_MM,
) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]] | None:
    """Compute three vertices for an open polyline A → P → B (arrow at IN end P).

    P is the wire's last vertex (dst / IN). The incoming direction follows the last segment
    (straight or bulge). Wing tips lie upstream from P along -t by *back_mm* and offset ± *side_mm*
    perpendicular to t.

    Args:
        xyb: LWPOLYLINE vertices as (x, y, bulge_on_outgoing_segment_from_this_vertex).
        back_mm: Distance from P toward the wire upstream along the centerline (mm).
        side_mm: Half-width perpendicular offset (mm).

    Returns:
        (A, P, B) in drawing order for a 3-vertex open LWPOLYLINE, or None if degenerate.

    Raises:
        ValueError: If *xyb* has fewer than two vertices.
    """
    if len(xyb) < 2:
        raise ValueError("wire arrow needs at least two polyline vertices")
    px, py, _ = xyb[-1]
    p = (px, py)
    t_in = _resolve_incoming_direction(xyb)
    if t_in is None:
        return None
    tx, ty = t_in
    # Unit perpendicular (90° CCW from t); wings are symmetric in ±perp.
    pxv, pyv = -ty, tx
    ax = px - back_mm * tx + side_mm * pxv
    ay = py - back_mm * ty + side_mm * pyv
    bx = px - back_mm * tx - side_mm * pxv
    by = py - back_mm * ty - side_mm * pyv
    return ((ax, ay), p, (bx, by))


def _resolve_incoming_direction(
    xyb: list[tuple[float, float, float]],
) -> tuple[float, float] | None:
    """Resolve stable incoming direction at the wire IN vertex.

    We prioritize geometry nearest to the IN endpoint to keep the arrow aligned with
    the visible terminal segment:
      1) last valid segment ending at IN (skip zero-length tails),
      2) earlier valid segment when terminal points are duplicated,
      3) whole-wire src->dst fallback from the first to last vertex.

    Args:
        xyb: LWPOLYLINE vertices as (x, y, bulge).

    Returns:
        Unit direction vector pointing toward the IN endpoint, or ``None`` for
        fully degenerate geometry.
    """
    for idx in range(len(xyb) - 2, -1, -1):
        x0, y0, b0 = xyb[idx]
        x1, y1, _ = xyb[idx + 1]
        tangent = _incoming_unit_tangent_xy(x0, y0, b0, x1, y1)
        if tangent is not None:
            return tangent
    sx, sy, _ = xyb[0]
    ex, ey, _ = xyb[-1]
    dx = ex - sx
    dy = ey - sy
    ln = math.hypot(dx, dy)
    if ln < 1e-15:
        return None
    return (dx / ln, dy / ln)


def _incoming_unit_tangent_xy(
    x0: float,
    y0: float,
    bulge: float,
    x1: float,
    y1: float,
) -> tuple[float, float] | None:
    """Compute unit tangent that arrives at a segment endpoint.

    Args:
        x0: Segment start X.
        y0: Segment start Y.
        bulge: Bulge value on the segment from (x0, y0) to (x1, y1).
        x1: Segment end X.
        y1: Segment end Y.

    Returns:
        Unit tangent vector pointing from the segment interior toward (x1, y1),
        or ``None`` when the segment is degenerate.
    """
    if abs(bulge) < 1e-12:
        dx = x1 - x0
        dy = y1 - y0
        ln = math.hypot(dx, dy)
        if ln < 1e-15:
            return None
        return (dx / ln, dy / ln)
    center, sa, ea, r = bulge_to_arc(Vec2(x0, y0), Vec2(x1, y1), bulge)
    if bulge < 0:
        sa, ea = ea, sa
    cx, cy = float(center.x), float(center.y)
    span = ea - sa
    if abs(span) < 1e-15:
        return None
    # Point on the arc slightly before the end vertex (same direction as wire_item tessellation).
    delta = min(abs(span) * 1e-4, abs(span) * 0.5)
    delta = max(delta, 1e-9)
    ang_prev = ea - math.copysign(delta, span)
    x_prev = cx + r * math.cos(ang_prev)
    y_prev = cy + r * math.sin(ang_prev)
    dx = x1 - x_prev
    dy = y1 - y_prev
    ln = math.hypot(dx, dy)
    if ln < 1e-15:
        return None
    return (dx / ln, dy / ln)
