"""Chord-based 2D / xyb polyline geometry for wires (bulges ignored except where sampled)."""

from __future__ import annotations

import math

from ezdxf.math import Vec2, bulge_to_arc

from logic_cad.core.model.constants import (
    GRID_PITCH,
    WIRE_BRANCH_ARC_END_CLAMP_FRAC,
    WIRE_DRAG_ARC_SAMPLES,
)

MANHATTAN_EPS = 1e-9


def _point_segment_dist_sq(px: float, py: float, x0: float, y0: float, x1: float, y1: float) -> float:
    dx, dy = x1 - x0, y1 - y0
    d2 = dx * dx + dy * dy
    if d2 < 1e-18:
        return (px - x0) ** 2 + (py - y0) ** 2
    t = ((px - x0) * dx + (py - y0) * dy) / d2
    t = max(0.0, min(1.0, t))
    qx, qy = x0 + t * dx, y0 + t * dy
    return (px - qx) ** 2 + (py - qy) ** 2


def _near_pt(a: tuple[float, float], b: tuple[float, float], eps: float = 1e-5) -> bool:
    return abs(a[0] - b[0]) < eps and abs(a[1] - b[1]) < eps


def _vertical_segment_wire_uid(
    pi: list[tuple[float, float]],
    ui: str,
    pj: list[tuple[float, float]],
    uj: str,
    vseg: tuple[tuple[float, float], tuple[float, float]],
) -> str | None:
    v0, v1 = vseg
    for uid, pts in ((ui, pi), (uj, pj)):
        for k in range(len(pts) - 1):
            p0, p1 = pts[k], pts[k + 1]
            if abs(p0[0] - p1[0]) > MANHATTAN_EPS:
                continue
            if (_near_pt(p0, v0) and _near_pt(p1, v1)) or (_near_pt(p0, v1) and _near_pt(p1, v0)):
                return uid
    return None


def _segment_axis_aligned(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return abs(a[0] - b[0]) < MANHATTAN_EPS or abs(a[1] - b[1]) < MANHATTAN_EPS


def _polyline_is_manhattan(pts: list[tuple[float, float]]) -> bool:
    if len(pts) < 2:
        return True
    for i in range(len(pts) - 1):
        if not _segment_axis_aligned(pts[i], pts[i + 1]):
            return False
    return True


def _polyline_no_zero_segments(pts: list[tuple[float, float]]) -> bool:
    for i in range(len(pts) - 1):
        if (
            abs(pts[i][0] - pts[i + 1][0]) < MANHATTAN_EPS
            and abs(pts[i][1] - pts[i + 1][1]) < MANHATTAN_EPS
        ):
            return False
    return True


def closest_point_on_polyline_xy(
    px: float, py: float, pts_xy: list[tuple[float, float]]
) -> tuple[float, float]:
    """Closest point on a polyline (chord segments; bulges ignored)."""
    if not pts_xy:
        return (px, py)
    if len(pts_xy) == 1:
        return (float(pts_xy[0][0]), float(pts_xy[0][1]))
    best_q = (float(pts_xy[0][0]), float(pts_xy[0][1]))
    best_d = float("inf")
    for i in range(len(pts_xy) - 1):
        x0, y0 = float(pts_xy[i][0]), float(pts_xy[i][1])
        x1, y1 = float(pts_xy[i + 1][0]), float(pts_xy[i + 1][1])
        d2 = _point_segment_dist_sq(px, py, x0, y0, x1, y1)
        if d2 >= best_d:
            continue
        best_d = d2
        dx, dy = x1 - x0, y1 - y0
        dlen = dx * dx + dy * dy
        if dlen < 1e-18:
            best_q = (x0, y0)
        else:
            t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / dlen))
            best_q = (x0 + t * dx, y0 + t * dy)
    return best_q


def polyline_chain_length_xy(pts_xy: list[tuple[float, float]]) -> float:
    """Total length of a 2D polyline (vertex chain; bulges ignored)."""
    if len(pts_xy) < 2:
        return 0.0
    tot = 0.0
    for i in range(len(pts_xy) - 1):
        tot += math.hypot(
            float(pts_xy[i + 1][0]) - float(pts_xy[i][0]),
            float(pts_xy[i + 1][1]) - float(pts_xy[i][1]),
        )
    return tot


def distance_from_polyline_start_to_closest_point_xy(
    px: float, py: float, pts_xy: list[tuple[float, float]]
) -> tuple[float, float, tuple[float, float]]:
    """Arc-length from pts_xy[0] to the closest point on the chain, total length L, and that closest point q.

    Matches segment choice in closest_point_on_polyline_xy (first segment wins ties).
    """
    if not pts_xy:
        return (0.0, 0.0, (px, py))
    if len(pts_xy) == 1:
        q = (float(pts_xy[0][0]), float(pts_xy[0][1]))
        return (0.0, 0.0, q)
    best_q = (float(pts_xy[0][0]), float(pts_xy[0][1]))
    best_d = float("inf")
    best_s = 0.0
    cum = 0.0
    for i in range(len(pts_xy) - 1):
        x0, y0 = float(pts_xy[i][0]), float(pts_xy[i][1])
        x1, y1 = float(pts_xy[i + 1][0]), float(pts_xy[i + 1][1])
        seg_len = math.hypot(x1 - x0, y1 - y0)
        d2 = _point_segment_dist_sq(px, py, x0, y0, x1, y1)
        dx, dy = x1 - x0, y1 - y0
        dlen = dx * dx + dy * dy
        if dlen < 1e-18:
            t = 0.0
            qx, qy = x0, y0
        else:
            t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / dlen))
            qx, qy = x0 + t * dx, y0 + t * dy
        if d2 < best_d:
            best_d = d2
            best_q = (qx, qy)
            best_s = cum + t * seg_len
        cum += seg_len
    return (best_s, cum, best_q)


def point_on_polyline_at_arc_length_xy(
    pts_xy: list[tuple[float, float]], arc_len: float
) -> tuple[float, float]:
    """Point at arc-length arc_len from pts_xy[0], clamped to the chain; bulges ignored."""
    if not pts_xy:
        raise ValueError("ポリラインが空です。")
    if len(pts_xy) == 1:
        return (float(pts_xy[0][0]), float(pts_xy[0][1]))
    L = polyline_chain_length_xy(pts_xy)
    if L < 1e-12:
        return (float(pts_xy[0][0]), float(pts_xy[0][1]))
    d = max(0.0, min(float(arc_len), L))
    cum = 0.0
    for i in range(len(pts_xy) - 1):
        x0, y0 = float(pts_xy[i][0]), float(pts_xy[i][1])
        x1, y1 = float(pts_xy[i + 1][0]), float(pts_xy[i + 1][1])
        seg_len = math.hypot(x1 - x0, y1 - y0)
        if cum + seg_len >= d - 1e-12:
            if seg_len < 1e-12:
                return (x0, y0)
            t = (d - cum) / seg_len
            return (x0 + t * (x1 - x0), y0 + t * (y1 - y0))
        cum += seg_len
    return (float(pts_xy[-1][0]), float(pts_xy[-1][1]))


def _branch_arc_fraction_clamp_bounds(L: float) -> tuple[float, float] | None:
    """Inset (lo, hi) for dimensionless arc parameter t in (0,1); None if clamp would collapse."""
    if L < 1e-9:
        return None
    eps = min(
        float(WIRE_BRANCH_ARC_END_CLAMP_FRAC),
        max(1e-9, (0.5 * float(GRID_PITCH)) / L),
    )
    if 2.0 * eps >= 1.0 - 1e-12:
        return None
    return (eps, 1.0 - eps)


def clamp_branch_arc_fraction_t(t: float, L: float) -> float:
    """Keep tee along trunk away from t=0/t=1 (port vertices) when L is long enough."""
    b = _branch_arc_fraction_clamp_bounds(L)
    if b is None:
        return t
    lo, hi = b
    return max(lo, min(hi, t))


def _edge_vertical_axis_xyb(xyb: list[tuple[float, float, float]], e_idx: int) -> float | None:
    x0, y0, _b = xyb[e_idx]
    x1, y1, _ = xyb[e_idx + 1]
    if abs(x0 - x1) >= MANHATTAN_EPS:
        return None
    return 0.5 * (x0 + x1)


def _edge_horizontal_axis_xyb(xyb: list[tuple[float, float, float]], e_idx: int) -> float | None:
    x0, y0, _b = xyb[e_idx]
    x1, y1, _ = xyb[e_idx + 1]
    if abs(y0 - y1) >= MANHATTAN_EPS:
        return None
    return 0.5 * (y0 + y1)


def vertical_run_edge_range_xyb(
    xyb: list[tuple[float, float, float]], seg_i: int
) -> tuple[int, int] | None:
    """Maximal contiguous edge indices with the same vertical (constant-x) chord or straight."""
    xv = _edge_vertical_axis_xyb(xyb, seg_i)
    if xv is None:
        return None
    n_edge = len(xyb) - 1
    e_lo = seg_i
    while e_lo > 0:
        x2 = _edge_vertical_axis_xyb(xyb, e_lo - 1)
        if x2 is None or abs(x2 - xv) > MANHATTAN_EPS:
            break
        e_lo -= 1
    e_hi = seg_i
    while e_hi < n_edge - 1:
        x2 = _edge_vertical_axis_xyb(xyb, e_hi + 1)
        if x2 is None or abs(x2 - xv) > MANHATTAN_EPS:
            break
        e_hi += 1
    return (e_lo, e_hi)


def horizontal_run_edge_range_xyb(
    xyb: list[tuple[float, float, float]], seg_i: int
) -> tuple[int, int] | None:
    yv = _edge_horizontal_axis_xyb(xyb, seg_i)
    if yv is None:
        return None
    n_edge = len(xyb) - 1
    e_lo = seg_i
    while e_lo > 0:
        y2 = _edge_horizontal_axis_xyb(xyb, e_lo - 1)
        if y2 is None or abs(y2 - yv) > MANHATTAN_EPS:
            break
        e_lo -= 1
    e_hi = seg_i
    while e_hi < n_edge - 1:
        y2 = _edge_horizontal_axis_xyb(xyb, e_hi + 1)
        if y2 is None or abs(y2 - yv) > MANHATTAN_EPS:
            break
        e_hi += 1
    return (e_lo, e_hi)


def parallel_run_edge_range_xyb(
    xyb: list[tuple[float, float, float]], seg_i: int
) -> tuple[int, int] | None:
    vr = vertical_run_edge_range_xyb(xyb, seg_i)
    if vr is not None:
        return vr
    return horizontal_run_edge_range_xyb(xyb, seg_i)


def parallel_drag_run_edge_range_xyb(
    xyb: list[tuple[float, float, float]], seg_i: int
) -> tuple[int, int] | None:
    """Full geometric colinear run through seg_i; requires at least one interior edge in the run."""
    run = parallel_run_edge_range_xyb(xyb, seg_i)
    if run is None:
        return None
    g_lo, g_hi = run
    n = len(xyb)
    if not any(g_lo <= s <= g_hi for s in range(1, n - 2)):
        return None
    if not (g_lo <= seg_i <= g_hi):
        return None
    return (g_lo, g_hi)


def distance_sq_to_parallel_drag_run_xyb(
    px: float,
    py: float,
    xyb: list[tuple[float, float, float]],
    e_lo: int,
    e_hi: int,
) -> float:
    best = float("inf")
    ns = max(8, WIRE_DRAG_ARC_SAMPLES)
    for e in range(e_lo, e_hi + 1):
        x0, y0, b0 = xyb[e][0], xyb[e][1], xyb[e][2]
        x1, y1 = xyb[e + 1][0], xyb[e + 1][1]
        if abs(b0) < 1e-12:
            d2 = _point_segment_dist_sq(px, py, x0, y0, x1, y1)
            best = min(best, d2)
        else:
            center, sa, ea, r = bulge_to_arc(Vec2(x0, y0), Vec2(x1, y1), b0)
            if b0 < 0:
                sa, ea = ea, sa
            cx, cy = float(center.x), float(center.y)
            for k in range(ns + 1):
                t = k / ns
                ang = sa + t * (ea - sa)
                xd = cx + r * math.cos(ang)
                yd = cy + r * math.sin(ang)
                best = min(best, (px - xd) ** 2 + (py - yd) ** 2)
    return best


def segment_eligible_for_parallel_offset_xyb(
    xyb: list[tuple[float, float, float]], seg_i: int
) -> bool:
    """True if seg_i lies in an interior vertical or horizontal run (straight and/or bulge chord)."""
    n = len(xyb)
    if n < 4 or seg_i < 0 or seg_i >= n - 1:
        return False
    return parallel_drag_run_edge_range_xyb(xyb, seg_i) is not None


def segment_eligible_for_parallel_offset(pts: list[tuple[float, float]], seg_i: int) -> bool:
    """True if both endpoints are interior vertices and the segment is axis-aligned (Manhattan)."""
    xyb = [(p[0], p[1], p[2] if len(p) > 2 else 0.0) for p in pts]
    return segment_eligible_for_parallel_offset_xyb(xyb, seg_i)


def offset_polyline_segment_parallel_xyb(
    xyb: list[tuple[float, float, float]], seg_i: int, delta: float
) -> list[tuple[float, float, float]] | None:
    """Slide the full geometric colinear run through seg_i perpendicular by delta."""
    n = len(xyb)
    if n < 4 or seg_i < 0 or seg_i >= n - 1:
        return None
    drag_run = parallel_drag_run_edge_range_xyb(xyb, seg_i)
    if drag_run is None:
        return None
    e_lo, e_hi = drag_run
    vr = vertical_run_edge_range_xyb(xyb, seg_i)
    if vr is not None:
        out = [tuple(t) for t in xyb]
        for v in range(e_lo, e_hi + 2):
            x, y, b = out[v]
            out[v] = (x + delta, y, b)
        flat = [(t[0], t[1]) for t in out]
        if not _polyline_is_manhattan(flat) or not _polyline_no_zero_segments(flat):
            return None
        return out
    out = [tuple(t) for t in xyb]
    for v in range(e_lo, e_hi + 2):
        x, y, b = out[v]
        out[v] = (x, y + delta, b)
    flat = [(t[0], t[1]) for t in out]
    if not _polyline_is_manhattan(flat) or not _polyline_no_zero_segments(flat):
        return None
    return out


def offset_polyline_segment_parallel(
    pts: list[tuple[float, ...]], seg_i: int, delta: float
) -> list[tuple[float, float, float]] | None:
    """Slide segment seg_i perpendicular by delta (mm): dy if horizontal, dx if vertical)."""
    xyb = [(float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0) for p in pts]
    out_xyb = offset_polyline_segment_parallel_xyb(xyb, seg_i, delta)
    if out_xyb is None:
        return None
    return [(float(t[0]), float(t[1]), float(t[2])) for t in out_xyb]


def _dist_mm(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _is_manhattan_polyline(pts: list[tuple[float, float]]) -> bool:
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        if abs(a[0] - b[0]) > 1e-9 and abs(a[1] - b[1]) > 1e-9:
            return False
    return True


def _lwpolyline_vertices(e) -> list[tuple[float, float]]:
    return [(float(r[0]), float(r[1])) for r in e.get_points("xyb")]
