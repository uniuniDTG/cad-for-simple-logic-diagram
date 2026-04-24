"""Polyline simplification (Douglas–Peucker) for 2D points.

Used to infer a coarse guide outline from a tessellated revision cloud when
LD_APP guide vertices are missing (legacy entities).
"""

from __future__ import annotations

import math


def _perp_dist_sq(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    """Squared perpendicular distance from point *p* to segment *ab*.

    Args:
        p: Query point.
        a: Segment start.
        b: Segment end.

    Returns:
        Squared distance in drawing units.
    """
    ax, ay = a
    bx, by = b
    px, py = p
    dx = bx - ax
    dy = by - ay
    if dx * dx + dy * dy < 1e-24:
        return (px - ax) ** 2 + (py - ay) ** 2
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    qx = ax + t * dx
    qy = ay + t * dy
    return (px - qx) ** 2 + (py - qy) ** 2


def douglas_peucker(
    points: list[tuple[float, float]],
    epsilon: float,
) -> list[tuple[float, float]]:
    """Ramer–Douglas–Peucker simplification of an open 2D polyline.

    Args:
        points: Vertex chain (at least two points).
        epsilon: Maximum distance from the original polyline to the simplified one.

    Returns:
        Simplified vertices (may be shorter than input). Two-point chains return both endpoints.
    """
    if len(points) < 3:
        return list(points)
    eps_sq = float(epsilon) * float(epsilon)
    if eps_sq < 1e-24:
        return list(points)

    start = 0
    end = len(points) - 1
    keep = [False] * len(points)
    keep[start] = True
    keep[end] = True

    stack: list[tuple[int, int]] = [(start, end)]
    while stack:
        s, e = stack.pop()
        if e <= s + 1:
            continue
        a = points[s]
        b = points[e]
        best_i = s + 1
        best_d = -1.0
        for i in range(s + 1, e):
            d = _perp_dist_sq(points[i], a, b)
            if d > best_d:
                best_d = d
                best_i = i
        if best_d > eps_sq:
            keep[best_i] = True
            stack.append((s, best_i))
            stack.append((best_i, e))

    return [points[i] for i in range(len(points)) if keep[i]]


def douglas_peucker_closed(
    points: list[tuple[float, float]],
    epsilon: float,
) -> list[tuple[float, float]]:
    """Simplify a closed ring (last point not duplicated in *points*).

    Args:
        points: Ring vertices in order, length at least 3.
        epsilon: Same tolerance semantics as :func:`douglas_peucker`.

    Returns:
        Simplified ring. Falls back to a coarser open simplification if needed.
    """
    n = len(points)
    if n < 3:
        return list(points)
    # Open chain with duplicated start for distance-to-segment on closing edge.
    open_chain = list(points) + [points[0]]
    simp = douglas_peucker(open_chain, epsilon)
    if len(simp) < 2:
        return list(points)
    # Remove duplicated closing point if present.
    if simp[-1] == simp[0]:
        simp = simp[:-1]
    if len(simp) < 3:
        # Relax: return coarser open DP on ring without closing segment.
        simp2 = douglas_peucker(list(points), epsilon * 2.0)
        if len(simp2) >= 3:
            return simp2
        return list(points)
    return simp
