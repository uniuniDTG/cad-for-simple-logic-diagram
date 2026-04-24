"""Collinear overlap between Manhattan wire segments (centerline vs existing wires)."""

from __future__ import annotations

from logic_cad.core.model.constants import ROUTING_COLLINEAR_OVERLAP_MIN_MM

from .polyline import polyline_segments


def wire_paths_to_flat_segments(
    paths: list[list[tuple[float, float]]],
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Flatten polylines to axis-aligned segments (one list for reuse per route call)."""
    out: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for pts in paths:
        if len(pts) < 2:
            continue
        out.extend(polyline_segments(pts))
    return out


def segment_collinear_overlap_length(
    a0: tuple[float, float],
    a1: tuple[float, float],
    b0: tuple[float, float],
    b1: tuple[float, float],
    eps: float = 1e-9,
) -> float:
    """Positive length only when both segments are collinear on the same horizontal or vertical line."""
    if abs(a0[0] - a1[0]) < eps and abs(b0[0] - b1[0]) < eps and abs(a0[0] - b0[0]) < eps:
        lo = max(min(a0[1], a1[1]), min(b0[1], b1[1]))
        hi = min(max(a0[1], a1[1]), max(b0[1], b1[1]))
        return max(0.0, hi - lo)
    if abs(a0[1] - a1[1]) < eps and abs(b0[1] - b1[1]) < eps and abs(a0[1] - b0[1]) < eps:
        lo = max(min(a0[0], a1[0]), min(b0[0], b1[0]))
        hi = min(max(a0[0], a1[0]), max(b0[0], b1[0]))
        return max(0.0, hi - lo)
    return 0.0


def segment_overlaps_existing_collinear(
    a0: tuple[float, float],
    a1: tuple[float, float],
    existing_segments: list[tuple[tuple[float, float], tuple[float, float]]],
    min_overlap_mm: float = ROUTING_COLLINEAR_OVERLAP_MIN_MM,
    eps: float = 1e-9,
) -> bool:
    if not existing_segments:
        return False
    horiz = abs(a0[1] - a1[1]) < eps
    vert = abs(a0[0] - a1[0]) < eps
    if not horiz and not vert:
        return False
    for b0, b1 in existing_segments:
        bh = abs(b0[1] - b1[1]) < eps
        bv = abs(b0[0] - b1[0]) < eps
        if horiz and not bh:
            continue
        if vert and not bv:
            continue
        if segment_collinear_overlap_length(a0, a1, b0, b1) > min_overlap_mm:
            return True
    return False


def path_has_collinear_overlap(
    path: list[tuple[float, float]],
    existing_segments: list[tuple[tuple[float, float], tuple[float, float]]],
    min_overlap_mm: float = ROUTING_COLLINEAR_OVERLAP_MIN_MM,
    eps: float = 1e-9,
) -> bool:
    if len(path) < 2 or not existing_segments:
        return False
    for i in range(len(path) - 1):
        if segment_overlaps_existing_collinear(
            path[i], path[i + 1], existing_segments, min_overlap_mm=min_overlap_mm, eps=eps
        ):
            return True
    return False
