"""Grid snapping, colinear vertex removal, and Manhattan polyline helpers."""

from __future__ import annotations

from logic_cad.core.geometry.manhattan_metrics import (
    manhattan_distance_via,
    points_close_xy,
    segment_is_axis_aligned,
)
from logic_cad.core.model.constants import GRID_PITCH


def snap_to_grid(x: float, y: float, pitch: float = GRID_PITCH) -> tuple[float, float]:
    return (round(x / pitch) * pitch, round(y / pitch) * pitch)


def dedupe_colinear(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(pts) < 2:
        return pts
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        ax, ay = out[-1]
        bx, by = pts[i]
        cx, cy = pts[i + 1]
        same_h = abs(ay - by) < 1e-9 and abs(by - cy) < 1e-9
        same_v = abs(ax - bx) < 1e-9 and abs(bx - cx) < 1e-9
        if same_h or same_v:
            continue
        out.append((bx, by))
    out.append(pts[-1])
    return out


def polyline_segments(pts: list[tuple[float, float]]) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    out = []
    for i in range(len(pts) - 1):
        out.append((pts[i], pts[i + 1]))
    return out


def ensure_manhattan_polyline(
    pts: list[tuple[float, float]],
    pitch: float = GRID_PITCH,
) -> list[tuple[float, float]]:
    """Ensure every segment is horizontal or vertical (inserts corners if needed)."""
    if len(pts) < 2:
        return pts
    out: list[tuple[float, float]] = [snap_to_grid(*pts[0], pitch)]
    for i in range(1, len(pts)):
        a = out[-1]
        b = snap_to_grid(*pts[i], pitch)
        if points_close_xy(a, b):
            continue
        if segment_is_axis_aligned(a, b):
            out.append(b)
            continue
        mid1 = snap_to_grid(b[0], a[1], pitch)
        mid2 = snap_to_grid(a[0], b[1], pitch)
        m1 = manhattan_distance_via(a, mid1, b)
        m2 = manhattan_distance_via(a, mid2, b)
        mid = mid1 if m1 <= m2 else mid2
        if not points_close_xy(mid, a):
            out.append(mid)
        if not points_close_xy(b, out[-1]):
            out.append(b)
    return dedupe_colinear(out)
