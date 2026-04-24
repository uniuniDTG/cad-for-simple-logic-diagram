"""Single source for hard/collinear segment rules shared by fixed candidates and OVG."""

from __future__ import annotations

from logic_cad.core.model.constants import GRID_PITCH, ROUTE_ESCAPE_MM

from .obstacles import segment_hits_obstacle_rects
from .occupancy import Cardinal, cardinal_from_delta
from .overlap import segment_overlaps_existing_collinear


def segment_blocks_hard_and_collinear(
    a: tuple[float, float],
    b: tuple[float, float],
    hard_rects: list[tuple[float, float, float, float]],
    existing_wire_segments: list[tuple[tuple[float, float], tuple[float, float]]] | None,
) -> bool:
    """True if this axis segment may not be used (hard obstacle interior or collinear wire overlap)."""
    if hard_rects and segment_hits_obstacle_rects(a, b, hard_rects):
        return True
    if existing_wire_segments and segment_overlaps_existing_collinear(
        a, b, existing_wire_segments
    ):
        return True
    return False


def first_axis_leg_clear(
    src0: tuple[float, float],
    fh: tuple[float, float],
    hard_rects: list[tuple[float, float, float, float]],
    existing_wire_segments: list[tuple[tuple[float, float], tuple[float, float]]] | None,
    pitch: float,
    min_first_leg_mm: float,
    *,
    skip_first_leg_hard_obstacle_check: bool,
) -> bool:
    """Port first hop: same rules as ``route_ovg_multi_start`` for one candidate end *fh*."""
    if existing_wire_segments and segment_overlaps_existing_collinear(
        src0, fh, existing_wire_segments
    ):
        return False
    dx = fh[0] - src0[0]
    dy = fh[1] - src0[1]
    if abs(dx) > 1e-9 and abs(dy) > 1e-9:
        return False
    leg_len = abs(dx) + abs(dy)
    if leg_len + 1e-9 < min_first_leg_mm:
        return False
    pitch_safe = pitch if pitch > 1e-12 else GRID_PITCH
    if skip_first_leg_hard_obstacle_check:
        step_free = ROUTE_ESCAPE_MM + pitch_safe
        if abs(dx) >= abs(dy) and abs(dx) > 1e-9:
            sx = 1.0 if dx > 0 else -1.0
            run = abs(dx)
            jx = src0[0] + sx * min(run, step_free)
            joint = (jx, src0[1])
        else:
            sy = 1.0 if dy > 0 else -1.0
            run = abs(dy)
            jy = src0[1] + sy * min(run, step_free)
            joint = (src0[0], jy)
        tail_len = max(0.0, leg_len - min(leg_len, step_free))
        if tail_len > 1e-9 and segment_hits_obstacle_rects(joint, fh, hard_rects):
            return False
        return True
    return not segment_hits_obstacle_rects(src0, fh, hard_rects)


def path_valid_under_port_first_leg_policy(
    pts: list[tuple[float, float]],
    hard_rects: list[tuple[float, float, float, float]],
    existing_wire_segments: list[tuple[tuple[float, float], tuple[float, float]]] | None,
    pitch: float,
    min_first_leg_mm: float,
    *,
    skip_first_leg_hard_obstacle_check: bool,
    banned_src_cardinals: set[Cardinal] | None,
) -> bool:
    """Full polyline: segment 0 uses first-leg rules; later segments use full hard+collinear."""
    if len(pts) < 2:
        return False
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        if i == 0:
            cd = cardinal_from_delta(b[0] - a[0], b[1] - a[1])
            if cd is None:
                return False
            if banned_src_cardinals and cd in banned_src_cardinals:
                return False
            if not first_axis_leg_clear(
                a,
                b,
                hard_rects,
                existing_wire_segments,
                pitch,
                min_first_leg_mm,
                skip_first_leg_hard_obstacle_check=skip_first_leg_hard_obstacle_check,
            ):
                return False
        elif segment_blocks_hard_and_collinear(a, b, hard_rects, existing_wire_segments):
            return False
    return True
