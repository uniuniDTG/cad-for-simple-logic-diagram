"""Path cost: length, turns, and soft-obstacle penalties."""

from __future__ import annotations

from logic_cad.core.geometry.manhattan_metrics import (
    manhattan_distance,
    points_close_xy,
    segment_is_horizontal,
    segment_is_vertical,
)
from logic_cad.core.model.constants import (
    ROUTING_SOFT_OBSTACLE_PENALTY,
    ROUTING_TURN_COST,
)

from .obstacles import obstacle_rects_inflated, segment_hits_obstacle_rects
from .segment_policy import segment_blocks_hard_and_collinear


def path_length(pts: list[tuple[float, float]]) -> float:
    return sum(manhattan_distance(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def path_turns(pts: list[tuple[float, float]]) -> int:
    turns = 0
    prev_dir: tuple[int, int] | None = None
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        if points_close_xy(a, b):
            continue
        dx = b[0] - a[0]
        dy = b[1] - a[1]
        if segment_is_horizontal(a, b):
            cur = (1 if dx > 0 else -1, 0)
        elif segment_is_vertical(a, b):
            cur = (0, 1 if dy > 0 else -1)
        else:
            continue
        if prev_dir is not None and cur != prev_dir:
            turns += 1
        prev_dir = cur
    return turns


def path_soft_penalty(
    pts: list[tuple[float, float]],
    soft_obstacles: list[tuple[float, float, float, float]],
) -> float:
    if len(pts) < 2 or not soft_obstacles:
        return 0.0
    inflated = obstacle_rects_inflated(soft_obstacles)
    return path_soft_penalty_rects(pts, inflated)


def path_soft_penalty_rects(
    pts: list[tuple[float, float]],
    soft_rects: list[tuple[float, float, float, float]],
) -> float:
    if len(pts) < 2 or not soft_rects:
        return 0.0
    hits = 0
    for i in range(len(pts) - 1):
        if segment_hits_obstacle_rects(pts[i], pts[i + 1], soft_rects):
            hits += 1
    return hits * ROUTING_SOFT_OBSTACLE_PENALTY


def polyline_routing_cost_rects(
    pts: list[tuple[float, float]],
    soft_rects: list[tuple[float, float, float, float]],
) -> float:
    """Length + turn cost + soft penalty (pre-inflated soft rects)."""
    return (
        path_length(pts)
        + path_turns(pts) * ROUTING_TURN_COST
        + path_soft_penalty_rects(pts, soft_rects)
    )


def pick_shortest_valid(
    candidates: list[list[tuple[float, float]]],
    hard_rects: list[tuple[float, float, float, float]],
    soft_rects: list[tuple[float, float, float, float]],
    *,
    existing_wire_segments: list[tuple[tuple[float, float], tuple[float, float]]] | None = None,
) -> list[tuple[float, float]] | None:
    best: list[tuple[float, float]] | None = None
    best_cost = float("inf")
    for p in candidates:
        ok = True
        for i in range(len(p) - 1):
            if segment_blocks_hard_and_collinear(
                p[i], p[i + 1], hard_rects, existing_wire_segments
            ):
                ok = False
                break
        if not ok:
            continue
        cost = polyline_routing_cost_rects(p, soft_rects)
        if cost < best_cost:
            best_cost = cost
            best = p
    return best
