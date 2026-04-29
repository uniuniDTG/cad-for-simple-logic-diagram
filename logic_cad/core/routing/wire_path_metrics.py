"""Multi-polyline crossing/overlap metrics and optional debug diagnostics for bundle routing."""

from __future__ import annotations

from logic_cad.core.debug.debug_log import (
    logic_cad_debug_routing_verbose,
    logic_cad_log,
)
from logic_cad.core.uid_display import format_uid_display
from logic_cad.core.model.constants import GRID_PITCH
from logic_cad.core.routing.crossings import segments_intersect
from logic_cad.core.routing.polyline import polyline_segments


def _segment_overlap_length(
    a0: tuple[float, float],
    a1: tuple[float, float],
    b0: tuple[float, float],
    b1: tuple[float, float],
    eps: float = 1e-9,
) -> float:
    if abs(a0[0] - a1[0]) < eps and abs(b0[0] - b1[0]) < eps and abs(a0[0] - b0[0]) < eps:
        lo = max(min(a0[1], a1[1]), min(b0[1], b1[1]))
        hi = min(max(a0[1], a1[1]), max(b0[1], b1[1]))
        return max(0.0, hi - lo)
    if abs(a0[1] - a1[1]) < eps and abs(b0[1] - b1[1]) < eps and abs(a0[1] - b0[1]) < eps:
        lo = max(min(a0[0], a1[0]), min(b0[0], b1[0]))
        hi = min(max(a0[0], a1[0]), max(b0[0], b1[0]))
        return max(0.0, hi - lo)
    return 0.0


def _count_segment_crossings_among(pts_list: list[list[tuple[float, float]]]) -> int:
    """Count unordered segment–segment intersections between distinct polylines."""
    total = 0
    n = len(pts_list)
    for i in range(n):
        segs_i = polyline_segments(pts_list[i])
        for j in range(i + 1, n):
            segs_j = polyline_segments(pts_list[j])
            for a0, a1 in segs_i:
                for b0, b1 in segs_j:
                    if segments_intersect(a0, a1, b0, b1) is not None:
                        total += 1
    return total


def _polylines_cross(pts_a: list[tuple[float, float]], pts_b: list[tuple[float, float]]) -> bool:
    for a0, a1 in polyline_segments(pts_a):
        for b0, b1 in polyline_segments(pts_b):
            if segments_intersect(a0, a1, b0, b1) is not None:
                return True
    return False


def _count_segment_overlaps_among(pts_list: list[list[tuple[float, float]]]) -> int:
    total = 0
    n = len(pts_list)
    for i in range(n):
        segs_i = polyline_segments(pts_list[i])
        for j in range(i + 1, n):
            segs_j = polyline_segments(pts_list[j])
            for a0, a1 in segs_i:
                for b0, b1 in segs_j:
                    if _segment_overlap_length(a0, a1, b0, b1) > 1e-9:
                        total += 1
    return total


def _vertical_parallel_y_overlap_info(
    a0: tuple[float, float],
    a1: tuple[float, float],
    b0: tuple[float, float],
    b1: tuple[float, float],
    eps: float = 1e-9,
) -> tuple[float, float, float] | None:
    """両方が縦辺で Y 範囲が重なるとき (xa, xb, overlap_mm)。そうでなければ None。"""
    if abs(a0[0] - a1[0]) >= eps or abs(b0[0] - b1[0]) >= eps:
        return None
    lo = max(min(a0[1], a1[1]), min(b0[1], b1[1]))
    hi = min(max(a0[1], a1[1]), max(b0[1], b1[1]))
    ov = hi - lo
    if ov <= 1e-9:
        return None
    return (a0[0], b0[0], ov)


def _log_vertical_parallel_overlap_diagnosis(
    pts_list: list[list[tuple[float, float]]],
    pitch: float,
    phase: str,
    gate_uid: str,
    overlap_count_all: int,
) -> None:
    """root logger が DEBUG のとき、縦並行辺の診断を詳細ログ。"""
    if not logic_cad_debug_routing_verbose():
        return
    n = len(pts_list)
    same_x = 0
    one_grid = 0
    wider = 0
    max_ov_same = 0.0
    max_ov_1 = 0.0
    examples: list[str] = []
    pitch_safe = pitch if pitch > 1e-12 else GRID_PITCH
    for i in range(n):
        segs_i = polyline_segments(pts_list[i])
        for j in range(i + 1, n):
            segs_j = polyline_segments(pts_list[j])
            for a0, a1 in segs_i:
                for b0, b1 in segs_j:
                    info = _vertical_parallel_y_overlap_info(a0, a1, b0, b1)
                    if info is None:
                        continue
                    xa, xb, ov = info
                    dx = abs(xa - xb)
                    if dx < 1e-6:
                        same_x += 1
                        max_ov_same = max(max_ov_same, ov)
                        if len(examples) < 4:
                            examples.append(f"same_x y_ov={ov:.2f}mm x={xa:.3f}")
                    else:
                        n_grids = round(dx / pitch_safe)
                        if abs(dx - n_grids * pitch_safe) < 0.05 and n_grids == 1:
                            one_grid += 1
                            max_ov_1 = max(max_ov_1, ov)
                            if len(examples) < 4:
                                examples.append(f"dx=1gr y_ov={ov:.2f}mm x={xa:.3f}/{xb:.3f}")
                        else:
                            wider += 1
                            if len(examples) < 4:
                                examples.append(f"dx={dx:.3f}mm y_ov={ov:.2f}mm")
    ex = f" examples={examples}" if examples else ""
    logic_cad_log(
        "routing",
        (
            f"bundle vertical_parallel_diag phase={phase} gate UUID={format_uid_display(gate_uid)} "
            f"overlap_segments_any_axis={overlap_count_all} "
            f"vert_same_x_pairs={same_x} vert_adjacent_1grid_pairs={one_grid} "
            f"vert_wider_pairs={wider} max_y_overlap_same_x_mm={max_ov_same:.3f} "
            f"max_y_overlap_1grid_mm={max_ov_1:.3f}{ex}"
        ),
    )
