"""Wire–wire crossing detection and vertical LWPOLYLINE semicircle bulges (bridge jumps)."""

from __future__ import annotations

import math

# Interior margin for orthogonal wire crossing (mm): avoids T-junctions and float edge cases.
_WIRE_CROSSING_INTERIOR_EPS = 1e-4

# |bulge| for a 180° arc (DXF bulge = tan(θ/4))
BULGE_SEMICIRCLE = math.tan(math.pi / 4)  # 1.0


def segments_intersect(
    a0: tuple[float, float],
    a1: tuple[float, float],
    b0: tuple[float, float],
    b1: tuple[float, float],
    eps: float = 1e-6,
) -> tuple[float, float] | None:
    """Return intersection point or None. Endpoints touching same point => None."""
    x1, y1 = a0
    x2, y2 = a1
    x3, y3 = b0
    x4, y4 = b1

    def near(p: tuple[float, float], q: tuple[float, float]) -> bool:
        return abs(p[0] - q[0]) < eps and abs(p[1] - q[1]) < eps

    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(den) < eps:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / den
    if not (0 < t < 1 and 0 < u < 1):
        return None
    px = x1 + t * (x2 - x1)
    py = y1 + t * (y2 - y1)
    pt = (px, py)
    ends_a = (near(a0, pt), near(a1, pt))
    ends_b = (near(b0, pt), near(b1, pt))
    if any(ends_a) and any(ends_b):
        return None
    return pt


def orthogonal_segments_crossing_relaxed(
    a0: tuple[float, float],
    a1: tuple[float, float],
    b0: tuple[float, float],
    b1: tuple[float, float],
    *,
    tol: float = 1e-6,
    interior_eps: float = _WIRE_CROSSING_INTERIOR_EPS,
) -> tuple[tuple[float, float], tuple[tuple[float, float], tuple[float, float]], tuple[tuple[float, float], tuple[float, float]]] | None:
    """Axis-aligned crossing: horizontal × vertical interior on both segments.

    Returns ``(point, horizontal_seg, vertical_seg)``. Endpoints on either segment are rejected
    (T-junctions). ``interior_eps`` relaxes float noise near ports / grid.
    """
    ha = abs(a0[1] - a1[1]) < tol
    va = abs(a0[0] - a1[0]) < tol
    hb = abs(b0[1] - b1[1]) < tol
    vb = abs(b0[0] - b1[0]) < tol
    if ha and vb:
        h0, h1, v0, v1 = a0, a1, b0, b1
    elif hb and va:
        h0, h1, v0, v1 = b0, b1, a0, a1
    else:
        return None
    if abs(h0[1] - h1[1]) > tol or abs(v0[0] - v1[0]) > tol:
        return None
    y_h = 0.5 * (h0[1] + h1[1])
    x_v = 0.5 * (v0[0] + v1[0])
    xh_min, xh_max = (h0[0], h1[0]) if h0[0] <= h1[0] else (h1[0], h0[0])
    yv_min, yv_max = (v0[1], v1[1]) if v0[1] <= v1[1] else (v1[1], v0[1])
    if not (xh_min - tol <= x_v <= xh_max + tol and yv_min - tol <= y_h <= yv_max + tol):
        return None
    if x_v <= xh_min + interior_eps or x_v >= xh_max - interior_eps:
        return None
    if y_h <= yv_min + interior_eps or y_h >= yv_max - interior_eps:
        return None
    pt = (x_v, y_h)
    return (pt, (h0, h1), (v0, v1))


def horizontal_segment_goes_east(h0: tuple[float, float], h1: tuple[float, float], *, tol: float = 1e-9) -> bool:
    return (h1[0] - h0[0]) >= -tol


def strip_wire_xyb_semijumps(
    vertices: list[tuple[float, float, float]],
    *,
    bulge_min: float = 0.9,
    pos_tol: float = 1e-6,
) -> list[tuple[float, float, float]]:
    """Remove 180° bulge jumps (vertical chord) inserted for wire crossings."""
    out = [(float(x), float(y), float(b)) for x, y, b in vertices]
    i = 0
    while i < len(out) - 1:
        x0, y0, b0 = out[i]
        x1, y1, _b1 = out[i + 1]
        if abs(b0) >= bulge_min and abs(x0 - x1) < pos_tol and abs(y0 - y1) > pos_tol:
            if i + 2 < len(out):
                del out[i : i + 2]
                continue
        i += 1
    return out


def _try_insert_one_vertical_semijump(
    xyb: list[tuple[float, float, float]],
    xc: float,
    yc: float,
    want_east: bool,
    radius: float,
    *,
    pos_tol: float = 1e-6,
) -> list[tuple[float, float, float]] | None:
    for i in range(len(xyb) - 1):
        if abs(xyb[i][2]) > 1e-9:
            continue
        x0, y0, _b0 = xyb[i]
        x1, y1, _b2 = xyb[i + 1]
        if abs(x0 - x1) > pos_tol or abs(x0 - xc) > pos_tol:
            continue
        y_lo, y_hi = (y0, y1) if y0 <= y1 else (y1, y0)
        if not (y_lo + radius < yc < y_hi - radius):
            continue
        going_up = y1 > y0
        if going_up:
            y_a, y_b = yc - radius, yc + radius
        else:
            y_a, y_b = yc + radius, yc - radius
        bulge = -BULGE_SEMICIRCLE if (going_up == want_east) else BULGE_SEMICIRCLE
        new0 = (xc, y_a, bulge)
        new1 = (xc, y_b, 0.0)
        return xyb[: i + 1] + [new0, new1] + xyb[i + 1 :]
    return None


def apply_vertical_semijumps_to_xyb(
    base_xy: list[tuple[float, float]],
    crossings: list[tuple[float, float, bool]],
    radius: float,
) -> list[tuple[float, float, float]]:
    """Insert semicircle bulges on vertical segments for each (xc, yc, want_east)."""
    xyb: list[tuple[float, float, float]] = [(float(x), float(y), 0.0) for x, y in base_xy]
    todo = sorted(crossings, key=lambda t: (t[1], t[0]))
    while todo:
        progressed = False
        rest: list[tuple[float, float, bool]] = []
        for c in todo:
            nxt = _try_insert_one_vertical_semijump(xyb, c[0], c[1], c[2], radius)
            if nxt is not None:
                xyb = nxt
                progressed = True
            else:
                rest.append(c)
        if not progressed:
            break
        todo = rest
    return xyb
