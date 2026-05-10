"""Compute a DXF-style ARC (center, radius, CCW start/end angles in degrees) from three points."""

from __future__ import annotations

import math

# Collinearity / duplicate-point threshold in drawing units (mm).
_EPS_LEN = 1e-9
_EPS_ANGLE = 1e-9


class ValueCollinearPointsError(ValueError):
    """Raised when three points do not define a unique circle (collinear)."""


class ValueDuplicatePointsError(ValueError):
    """Raised when two or more of the three points coincide."""


def _norm_deg_degrees(angle_deg: float) -> float:
    """Return ``angle_deg`` in ``[0, 360)``."""
    x = float(angle_deg) % 360.0
    if x < 0.0:
        x += 360.0
    return x


def _point_angle_deg(cx: float, cy: float, px: float, py: float) -> float:
    """Angle from center to *p* in degrees, DXF/CCW from +X (same as ``atan2``)."""
    return math.degrees(math.atan2(float(py) - float(cy), float(px) - float(cx)))


def _ccw_interior_exclusive_deg(start_deg: float, end_deg: float, mid_deg: float) -> bool:
    """True iff *mid* lies strictly on the CCW arc from *start* to *end* (wrapping at 360).

    Used to pick which of the two arcs from P0 to P2 passes through the user-chosen middle point.
    """
    s = _norm_deg_degrees(start_deg)
    e = _norm_deg_degrees(end_deg)
    m = _norm_deg_degrees(mid_deg)
    span = (e - s) % 360.0
    if span <= _EPS_ANGLE:
        return False
    dm = (m - s) % 360.0
    return dm > _EPS_ANGLE and dm < span - _EPS_ANGLE


def circumcenter_xy(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
) -> tuple[float, float]:
    """Return circumcenter of the triangle *p0*–*p1*–*p2*.

    Args:
        p0: First point (start of arc).
        p1: Second point (must lie on the intended arc between *p0* and *p2*).
        p2: Third point (end of arc).

    Returns:
        ``(cx, cy)`` in the same units as the inputs.

    Raises:
        ValueDuplicatePointsError: If two or more points coincide.
        ValueCollinearPointsError: If the three points are collinear.
    """
    ax, ay = float(p0[0]), float(p0[1])
    bx, by = float(p1[0]), float(p1[1])
    cx, cy = float(p2[0]), float(p2[1])
    if (abs(ax - bx) < _EPS_LEN and abs(ay - by) < _EPS_LEN) or (
        abs(bx - cx) < _EPS_LEN and abs(by - cy) < _EPS_LEN
    ) or (abs(ax - cx) < _EPS_LEN and abs(ay - cy) < _EPS_LEN):
        raise ValueDuplicatePointsError("円弧の3点に重複した点があります。")
    d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < _EPS_LEN:
        raise ValueCollinearPointsError("3点が一直線上にあるため円弧を決定できません。")
    a2 = ax * ax + ay * ay
    b2 = bx * bx + by * by
    c2 = cx * cx + cy * cy
    ux = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / d
    uy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d
    return (ux, uy)


def dxf_arc_from_three_points(
    start_xy: tuple[float, float],
    mid_xy: tuple[float, float],
    end_xy: tuple[float, float],
) -> tuple[tuple[float, float], float, float, float]:
    """Compute DXF ``ARC`` parameters from start, intermediate, and end points.

    The middle point selects which of the two arcs connecting start and end is intended
    (the arc through that middle point, in the CCW sense used by DXF).

    Args:
        start_xy: Arc start (first user click).
        mid_xy: Point on the arc (second click).
        end_xy: Arc end (third click).

    Returns:
        ``((cx, cy), radius, start_angle_deg, end_angle_deg)`` with angles in degrees,
        suitable for ``block.add_arc(center=..., radius=..., start_angle=..., end_angle=...)``.

    Raises:
        ValueDuplicatePointsError: Duplicate points among the three.
        ValueCollinearPointsError: Collinear points.
    """
    cx, cy = circumcenter_xy(start_xy, mid_xy, end_xy)
    sx, sy = float(start_xy[0]), float(start_xy[1])
    r0 = math.hypot(sx - cx, sy - cy)
    r1 = math.hypot(float(mid_xy[0]) - cx, float(mid_xy[1]) - cy)
    r2 = math.hypot(float(end_xy[0]) - cx, float(end_xy[1]) - cy)
    rmax = max(r0, r1, r2)
    rmin = min(r0, r1, r2)
    if rmax < _EPS_LEN or (rmax - rmin) > max(_EPS_LEN, 1e-6 * rmax):
        raise ValueCollinearPointsError("外接円の半径が一貫しません（ほぼ一直線）。")
    r = (r0 + r1 + r2) / 3.0

    a0 = _point_angle_deg(cx, cy, start_xy[0], start_xy[1])
    a1 = _point_angle_deg(cx, cy, mid_xy[0], mid_xy[1])
    a2 = _point_angle_deg(cx, cy, end_xy[0], end_xy[1])

    if _ccw_interior_exclusive_deg(a0, a2, a1):
        sa, ea = _norm_deg_degrees(a0), _norm_deg_degrees(a2)
    elif _ccw_interior_exclusive_deg(a2, a0, a1):
        sa, ea = _norm_deg_degrees(a2), _norm_deg_degrees(a0)
    else:
        # Degenerate: middle lies on an endpoint — still define a zero-length span by using minor arc.
        sa, ea = _norm_deg_degrees(a0), _norm_deg_degrees(a2)

    return ((cx, cy), float(r), float(sa), float(ea))
