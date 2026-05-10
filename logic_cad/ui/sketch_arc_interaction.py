"""Shared sketch helpers for USER_ARC placement on main diagram and block editor scenes.

Keeps three-point arc math, tolerance checks, and preview path construction identical
where both editors must behave the same. DXF mutations stay in ``LogicDiagram`` /
``BlockEditSession`` call sites.
"""

from __future__ import annotations

import math

from PySide6.QtGui import QPainterPath

from logic_cad.core.geometry.arc_through_three_points import (
    ValueCollinearPointsError,
    ValueDuplicatePointsError,
    dxf_arc_from_three_points,
)
from logic_cad.ui.items.user_geometry_items import user_arc_path_scene


def same_dxf_point(
    a: tuple[float, float],
    b: tuple[float, float],
    *,
    tol: float = 1e-9,
) -> bool:
    """Return True when two DXF-space points match within *tol* (mm).

    Args:
        a: First point in DXF millimetres.
        b: Second point in DXF millimetres.
        tol: Absolute tolerance on each axis.

    Returns:
        True if both coordinate deltas are within *tol*.
    """
    return abs(float(a[0]) - float(b[0])) <= tol and abs(float(a[1]) - float(b[1])) <= tol


def arc_vertex_marker_half_mm(snap_pitch_mm: float) -> float:
    """Half-edge length (mm) for square handles on the first two arc definition points.

    The formula matches the historical main-canvas and block-editor sizing: a small
    floor so markers stay visible on coarse grids, scaled slightly with pitch.

    Args:
        snap_pitch_mm: Active grid step in millimetres (``GRID_PITCH`` or finer).

    Returns:
        Half-width / half-height of each square marker in scene mm.
    """
    return max(0.35, float(snap_pitch_mm) * 0.12)


def circle_radius_mm_from_anchor_and_cursor_dxf(
    center_dxf: tuple[float, float],
    cursor_dxf: tuple[float, float],
    *,
    snap_pitch_mm: float,
) -> float:
    """Snapped circle radius for USER_CIRCLE rubber-band and commit (shared semantics).

    When the cursor coincides with the center in DXF space, returns *snap_pitch_mm*
    so a non-degenerate preview remains. Otherwise returns the distance from center
    to cursor, rounded to the nearest multiple of *snap_pitch_mm*, floored at one step.

    Args:
        center_dxf: Circle center ``(x, y)`` in DXF mm.
        cursor_dxf: Snapped cursor ``(x, y)`` in DXF mm.
        snap_pitch_mm: Grid step used for rounding (main diagram vs auxiliary grid).

    Returns:
        Radius in DXF millimetres, at least *snap_pitch_mm*.
    """
    cx, cy = float(center_dxf[0]), float(center_dxf[1])
    tx, ty = float(cursor_dxf[0]), float(cursor_dxf[1])
    dx, dy = tx - cx, ty - cy
    dist = float(math.hypot(dx, dy))
    sp = float(snap_pitch_mm)
    if dist < 1e-9:
        return sp
    return max(sp, round(dist / sp) * sp)


def try_dxf_arc_through_three_points(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
) -> tuple[tuple[float, float], float, float, float] | None:
    """Compute DXF arc parameters from three points, or None if geometry is invalid.

    Maps :func:`~logic_cad.core.geometry.arc_through_three_points.dxf_arc_from_three_points`
    into a nullable form so both scenes share the same exception set without duplicating
    ``try``/``except`` blocks.

    Args:
        p0: First point on the arc (DXF mm).
        p1: Second point on the arc (DXF mm).
        p2: Third point (DXF mm), typically the moving snap position.

    Returns:
        ``((cx, cy), r, start_angle, end_angle)`` on success; ``None`` if the points are
        degenerate or collinear (same outcomes as an empty preview / ignored click).
    """
    try:
        (cx, cy), r, sa, ea = dxf_arc_from_three_points(p0, p1, p2)
    except (ValueCollinearPointsError, ValueDuplicatePointsError, ValueError):
        return None
    return (cx, cy), r, sa, ea


def user_arc_preview_qpainterpath_from_three_points(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
) -> QPainterPath | None:
    """Build the scene-space preview path for a three-point arc, or None if invalid.

    Args:
        p0: First fixed point (DXF mm).
        p1: Second fixed point (DXF mm).
        p2: Third point (DXF mm), usually the live snapped cursor.

    Returns:
        Path for ``QGraphicsPathItem.setPath``, or ``None`` when the caller should clear
        the preview (empty degenerate arc).
    """
    geom = try_dxf_arc_through_three_points(p0, p1, p2)
    if geom is None:
        return None
    (cx, cy), r, sa, ea = geom
    return user_arc_path_scene(cx, cy, r, sa, ea)
