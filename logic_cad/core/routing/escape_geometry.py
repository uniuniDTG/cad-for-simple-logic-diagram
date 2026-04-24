"""Axis-aligned escape extension from a port toward a first-hop grid point.

Kept separate from :mod:`logic_cad.core.routing.escape` so modules that only need this
geometry (e.g. hybrid fixed routing) do not participate in import cycles with the
high-level escape entry points.
"""

from __future__ import annotations

import math

from logic_cad.core.routing.polyline import snap_to_grid


def ensure_min_escape_distance(
    p0: tuple[float, float],
    ex: tuple[float, float],
    min_len: float,
    pitch: float,
) -> tuple[float, float]:
    """Extend the first escape along the axis-aligned ray from *p0* toward *ex*.

    The result is snapped to *pitch* and lies on the same horizontal or vertical line
    as *p0*→*ex*, with geometric distance from *p0* at least *min_len* when possible.

    Args:
        p0: Source port position in world coordinates (mm).
        ex: Preferred first-hop point; may be closer than *min_len* along the ray.
        min_len: Minimum first-leg length from *p0* (mm).
        pitch: Grid pitch for snapping the returned point (mm).

    Returns:
        Snapped grid coordinates for the first hop after enforcing *min_len*.
    """
    dx = ex[0] - p0[0]
    dy = ex[1] - p0[1]
    dist = math.hypot(dx, dy)
    if dist >= min_len - 1e-9:
        return snap_to_grid(ex[0], ex[1], pitch)
    if dist < 1e-12:
        return snap_to_grid(ex[0], ex[1], pitch)
    if abs(dx) < 1e-9:
        sign = 1.0 if dy > 0 else -1.0
        ty = p0[1] + sign * min_len
        return snap_to_grid(p0[0], ty, pitch)
    if abs(dy) < 1e-9:
        sign = 1.0 if dx > 0 else -1.0
        tx = p0[0] + sign * min_len
        return snap_to_grid(tx, p0[1], pitch)
    if abs(dx) >= abs(dy):
        sign = 1.0 if dx > 0 else -1.0
        tx = p0[0] + sign * min_len
        return snap_to_grid(tx, p0[1], pitch)
    sign = 1.0 if dy > 0 else -1.0
    ty = p0[1] + sign * min_len
    return snap_to_grid(p0[0], ty, pitch)
