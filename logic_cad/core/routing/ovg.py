"""Orthogonal visibility graph (OVG) routing; edges use segment_policy hard+collinear rules."""

from __future__ import annotations

import math
from collections import defaultdict
from heapq import heappop, heappush

from logic_cad.core.model.constants import (
    GRID_PITCH,
    ROUTING_SOFT_OBSTACLE_PENALTY,
    ROUTING_STEP_COST,
    ROUTING_TURN_COST,
)
from logic_cad.core.debug.debug_log import logic_cad_debug_routing_verbose, logic_cad_log
from ._format import fmt_pt
from .obstacles import (
    obstacle_rects_inflated,
    segment_hits_obstacle_rects,
)
from .occupancy import Cardinal, cardinal_from_delta
from .polyline import dedupe_colinear, snap_to_grid
from .segment_policy import first_axis_leg_clear, segment_blocks_hard_and_collinear


def _world_to_ij(x: float, y: float, pitch: float) -> tuple[int, int]:
    return (int(round(x / pitch)), int(round(y / pitch)))


def _build_ovg_nodes(
    src: tuple[float, float],
    dst: tuple[float, float],
    obstacles: list[tuple[float, float, float, float]],
    pitch: float,
    extra_points: list[tuple[float, float]] | None = None,
    *,
    dense_corridor: bool = False,
) -> list[tuple[float, float]]:
    """Corner and edge-mid nodes offset by one pitch outside each obstacle bbox, plus src/dst."""
    seen: set[tuple[float, float]] = set()

    def add(x: float, y: float) -> None:
        seen.add(snap_to_grid(x, y, pitch))

    def add_cross(p: tuple[float, float], rings: int = 3) -> None:
        """Add port point and axis neighbors so OVG has degree on sparse layouts."""
        px, py = p
        add(px, py)
        for r in range(1, rings + 1):
            step = r * pitch
            add(px + step, py)
            add(px - step, py)
            add(px, py + step)
            add(px, py - step)

    add_cross(src)
    add_cross(dst)
    for ex, ey in extra_points or ():
        add(ex, ey)
    for x0, y0, x1, y1 in obstacles:
        for cx in (x0 - pitch, x1 + pitch):
            for cy in (y0 - pitch, y1 + pitch):
                add(cx, cy)
        mid_x = (x0 + x1) / 2
        mid_y = (y0 + y1) / 2
        add(mid_x, y0 - pitch)
        add(mid_x, y1 + pitch)
        add(x0 - pitch, mid_y)
        add(x1 + pitch, mid_y)

    if dense_corridor:
        # Dense grid between endpoints so visibility graph stays connected in open areas
        # (corner-only nodes can leave disjoint components).
        pad = max(30.0, (abs(dst[0] - src[0]) + abs(dst[1] - src[1])) * 0.35 + 20.0)
        x_lo = min(src[0], dst[0]) - pad
        x_hi = max(src[0], dst[0]) + pad
        y_lo = min(src[1], dst[1]) - pad
        y_hi = max(src[1], dst[1]) + pad
        x_lo, y_lo = snap_to_grid(x_lo, y_lo, pitch)
        x_hi, y_hi = snap_to_grid(x_hi, y_hi, pitch)
        max_cells = 25_00
        span_x = max(0.0, x_hi - x_lo)
        span_y = max(0.0, y_hi - y_lo)
        nx = int(span_x / pitch) + 1 if pitch > 1e-12 else 1
        ny = int(span_y / pitch) + 1 if pitch > 1e-12 else 1
        cells = max(1, nx) * max(1, ny)
        grid_step = pitch
        if cells > max_cells:
            grid_step = pitch * math.ceil(math.sqrt(cells / max_cells))
        gx = x_lo
        while gx <= x_hi + 1e-9:
            gy = y_lo
            while gy <= y_hi + 1e-9:
                add(gx, gy)
                gy += grid_step
            gx += grid_step

    return list(seen)


def _build_ovg_edges(
    nodes: list[tuple[float, float]],
    hard_rects: list[tuple[float, float, float, float]],
    pitch: float,
    existing_wire_segments: list[tuple[tuple[float, float], tuple[float, float]]] | None = None,
) -> dict[int, list[tuple[int, float]]]:
    """Horizontal/vertical visibility edges between consecutive nodes on each grid line."""
    by_col: dict[int, list[int]] = defaultdict(list)
    by_row: dict[int, list[int]] = defaultdict(list)
    for idx, (x, y) in enumerate(nodes):
        gi, gj = _world_to_ij(x, y, pitch)
        by_col[gi].append(idx)
        by_row[gj].append(idx)

    adj: dict[int, list[tuple[int, float]]] = {}

    def try_edge(i: int, j: int) -> None:
        a, b = nodes[i], nodes[j]
        if segment_blocks_hard_and_collinear(a, b, hard_rects, existing_wire_segments):
            return
        dist = abs(b[0] - a[0]) + abs(b[1] - a[1])
        adj.setdefault(i, []).append((j, dist))
        adj.setdefault(j, []).append((i, dist))

    for col_nodes in by_col.values():
        col_sorted = sorted(col_nodes, key=lambda idx: nodes[idx][1])
        for k in range(len(col_sorted) - 1):
            try_edge(col_sorted[k], col_sorted[k + 1])
    for row_nodes in by_row.values():
        row_sorted = sorted(row_nodes, key=lambda idx: nodes[idx][0])
        for k in range(len(row_sorted) - 1):
            try_edge(row_sorted[k], row_sorted[k + 1])
    return adj


def route_ovg(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    obs: list[tuple[float, float, float, float]],
    soft_obstacles: list[tuple[float, float, float, float]],
    pitch: float,
    max_search_states: int,
    existing_wire_segments: list[tuple[tuple[float, float], tuple[float, float]]] | None = None,
) -> list[tuple[float, float]] | None:
    """Orthogonal visibility graph routing (grid A* fallback replacement)."""
    src = snap_to_grid(x0, y0, pitch)
    dst = snap_to_grid(x1, y1, pitch)
    if src == dst:
        return [src]

    if logic_cad_debug_routing_verbose():
        logic_cad_log(
            "routing",
            (
                f"ovg start src={fmt_pt(src)} dst={fmt_pt(dst)} "
                f"hard={len(obs)} soft={len(soft_obstacles)} cap={max_search_states}"
            ),
        )

    hard_rects = obstacle_rects_inflated(obs)
    soft_rects = obstacle_rects_inflated(soft_obstacles) if soft_obstacles else []

    for dense in (False, True):
        nodes = _build_ovg_nodes(
            src, dst, obs, pitch, None, dense_corridor=dense
        )
        hit = _ovg_search(
            nodes,
            src,
            dst,
            hard_rects,
            soft_rects,
            pitch,
            max_search_states,
            existing_wire_segments,
            multi_starts=None,
            anchor_p0=None,
        )
        if hit is not None:
            return hit
    return None


def _ovg_search(
    nodes: list[tuple[float, float]],
    src: tuple[float, float],
    dst: tuple[float, float],
    hard_rects: list[tuple[float, float, float, float]],
    soft_rects: list[tuple[float, float, float, float]],
    pitch: float,
    max_search_states: int,
    existing_wire_segments: list[tuple[tuple[float, float], tuple[float, float]]] | None,
    *,
    multi_starts: list[tuple[int, int, float]] | None = None,
    anchor_p0: tuple[float, float] | None = None,
) -> list[tuple[float, float]] | None:
    """Run OVG A*. If multi_starts is set, each entry is (node_idx, prev_dir_01, g0_cost)."""
    node_index = {pt: i for i, pt in enumerate(nodes)}
    dst_idx = node_index[dst]

    adj = _build_ovg_edges(nodes, hard_rects, pitch, existing_wire_segments)
    if logic_cad_debug_routing_verbose():
        edge_pairs = sum(len(v) for v in adj.values()) // 2
        start_count = len(multi_starts) if multi_starts else 1
        logic_cad_log(
            "routing",
            (
                f"ovg graph nodes={len(nodes)} edges={edge_pairs} starts={start_count} "
                f"hard_rects={len(hard_rects)} soft_rects={len(soft_rects)}"
            ),
        )
    if not adj.get(dst_idx):
        if logic_cad_debug_routing_verbose():
            logic_cad_log(
                "routing",
                f"ovg no_edges_to_dst src={fmt_pt(src)} dst={fmt_pt(dst)}",
            )
        return None

    pitch_safe = pitch if pitch > 1e-12 else GRID_PITCH

    def segment_dir(i: int, j: int) -> int:
        xi, yi = nodes[i]
        xj, yj = nodes[j]
        return 0 if abs(yj - yi) < 1e-9 else 1

    def heuristic(idx: int) -> float:
        x, y = nodes[idx]
        xd, yd = nodes[dst_idx]
        return (abs(xd - x) + abs(yd - y)) / pitch_safe * ROUTING_STEP_COST

    INF = float("inf")
    best_cost: dict[tuple[int, int | None], float] = {}
    came: dict[tuple[int, int | None], tuple[int, int | None] | None] = {}
    pq: list[tuple[float, int, float, int, int | None]] = []
    goal_state: tuple[int, int | None] | None = None
    explored = 0
    tie = 0

    if multi_starts:
        for idx0, prev_d, g0 in multi_starts:
            st = (idx0, prev_d)
            best_cost[st] = g0
            came[st] = None
            tie += 1
            heappush(pq, (g0 + heuristic(idx0), tie, g0, idx0, prev_d))
    else:
        src_idx = node_index[src]
        start_state = (src_idx, None)
        best_cost[start_state] = 0.0
        came[start_state] = None
        tie += 1
        heappush(pq, (heuristic(src_idx), tie, 0.0, src_idx, None))

    while pq:
        _f, _tie, g, cur_idx, prev_dir = heappop(pq)
        state = (cur_idx, prev_dir)
        if g > best_cost.get(state, INF) + 1e-9:
            continue
        explored += 1
        if explored > max_search_states:
            logic_cad_log(
                "routing",
                (
                    f"ovg abort state_cap src={fmt_pt(src)} dst={fmt_pt(dst)} "
                    f"explored={explored} limit={max_search_states}"
                ),
            )
            return None
        if cur_idx == dst_idx:
            goal_state = state
            break
        for nb_idx, geo_dist in adj.get(cur_idx, []):
            d = segment_dir(cur_idx, nb_idx)
            turn_cost = ROUTING_TURN_COST if (prev_dir is not None and d != prev_dir) else 0.0
            seg_a, seg_b = nodes[cur_idx], nodes[nb_idx]
            soft_cost = (
                ROUTING_SOFT_OBSTACLE_PENALTY
                if soft_rects and segment_hits_obstacle_rects(seg_a, seg_b, soft_rects)
                else 0.0
            )
            step_base = (geo_dist / pitch_safe) * ROUTING_STEP_COST
            ng = g + step_base + turn_cost + soft_cost
            nb_state = (nb_idx, d)
            if ng >= best_cost.get(nb_state, INF) - 1e-9:
                continue
            best_cost[nb_state] = ng
            came[nb_state] = state
            tie += 1
            heappush(pq, (ng + heuristic(nb_idx), tie, ng, nb_idx, d))

    if goal_state is None:
        if logic_cad_debug_routing_verbose():
            logic_cad_log("routing", f"ovg no_path src={fmt_pt(src)} dst={fmt_pt(dst)}")
        return None

    rev: list[tuple[float, float]] = []
    cur: tuple[int, int | None] | None = goal_state
    while cur is not None:
        rev.append(nodes[cur[0]])
        cur = came.get(cur)
    rev.reverse()
    result = dedupe_colinear(rev)
    if anchor_p0 is not None and result:
        if (
            abs(result[0][0] - anchor_p0[0]) > 1e-9
            or abs(result[0][1] - anchor_p0[1]) > 1e-9
        ):
            result = dedupe_colinear([anchor_p0] + result)
    if logic_cad_debug_routing_verbose():
        logic_cad_log(
            "routing",
            (
                f"ovg success src={fmt_pt(src)} dst={fmt_pt(dst)} "
                f"explored={explored} points={len(result)}"
            ),
        )
    return result


def route_ovg_multi_start(
    p0: tuple[float, float],
    x1: float,
    y1: float,
    obs: list[tuple[float, float, float, float]],
    soft_obstacles: list[tuple[float, float, float, float]],
    pitch: float,
    max_search_states: int,
    first_hop_points: list[tuple[float, float]],
    existing_wire_segments: list[tuple[tuple[float, float], tuple[float, float]]] | None,
    banned_cardinals: set[Cardinal] | None,
    min_first_leg_mm: float,
    *,
    skip_first_leg_hard_obstacle_check: bool = True,
) -> list[tuple[float, float]] | None:
    """OVG from port *p0* with mandatory first leg ending at one of *first_hop_points*."""
    src0 = snap_to_grid(p0[0], p0[1], pitch)
    dst = snap_to_grid(x1, y1, pitch)
    if src0 == dst:
        return [src0]

    hops_snapped = [snap_to_grid(x, y, pitch) for x, y in first_hop_points]
    hops_snapped = list(dict.fromkeys(hops_snapped))  # stable unique

    if logic_cad_debug_routing_verbose():
        logic_cad_log(
            "routing",
            (
                f"ovg_multi start anchor={fmt_pt(src0)} dst={fmt_pt(dst)} "
                f"hops={len(hops_snapped)} cap={max_search_states}"
            ),
        )

    hard_rects = obstacle_rects_inflated(obs)
    soft_rects = obstacle_rects_inflated(soft_obstacles) if soft_obstacles else []

    raw_starts: list[tuple[tuple[float, float], int, float]] = []
    pitch_safe = pitch if pitch > 1e-12 else GRID_PITCH

    for fh in hops_snapped:
        dx = fh[0] - src0[0]
        dy = fh[1] - src0[1]
        if abs(dx) > 1e-9 and abs(dy) > 1e-9:
            continue
        leg_len = abs(dx) + abs(dy)
        if leg_len + 1e-9 < min_first_leg_mm:
            continue
        cd = cardinal_from_delta(dx, dy)
        if cd is None:
            continue
        if banned_cardinals and cd in banned_cardinals:
            continue
        if not first_axis_leg_clear(
            src0,
            fh,
            hard_rects,
            existing_wire_segments,
            pitch,
            min_first_leg_mm,
            skip_first_leg_hard_obstacle_check=skip_first_leg_hard_obstacle_check,
        ):
            continue
        prev_d = 0 if abs(dy) < 1e-9 else 1
        g0 = (leg_len / pitch_safe) * ROUTING_STEP_COST
        raw_starts.append((fh, prev_d, g0))

    if not raw_starts:
        if logic_cad_debug_routing_verbose():
            logic_cad_log("routing", f"ovg_multi no_valid_first_hops anchor={fmt_pt(src0)}")
        return None

    fh_nodes = [t[0] for t in raw_starts]
    for dense in (False, True):
        nodes = _build_ovg_nodes(
            src0, dst, obs, pitch, fh_nodes, dense_corridor=dense
        )
        node_index = {pt: i for i, pt in enumerate(nodes)}

        indexed_starts: list[tuple[int, int, float]] = []
        for fh, prev_d, g0 in raw_starts:
            idx = node_index.get(fh)
            if idx is None:
                continue
            indexed_starts.append((idx, prev_d, g0))

        if not indexed_starts:
            if logic_cad_debug_routing_verbose():
                logic_cad_log(
                    "routing",
                    f"ovg_multi first_hops_not_in_graph dense={dense}",
                )
            continue
        if logic_cad_debug_routing_verbose():
            logic_cad_log(
                "routing",
                (
                    f"ovg_multi attempt dense={dense} nodes={len(nodes)} "
                    f"valid_starts={len(indexed_starts)} raw_starts={len(raw_starts)}"
                ),
            )

        res = _ovg_search(
            nodes,
            src0,
            dst,
            hard_rects,
            soft_rects,
            pitch,
            max_search_states,
            existing_wire_segments,
            multi_starts=indexed_starts,
            anchor_p0=src0,
        )
        if res is not None:
            if logic_cad_debug_routing_verbose():
                logic_cad_log(
                    "routing",
                    f"ovg_multi solved dense={dense} points={len(res)}",
                )
            return res
    if logic_cad_debug_routing_verbose():
        logic_cad_log(
            "routing",
            f"ovg_multi exhausted anchor={fmt_pt(src0)} dst={fmt_pt(dst)}",
        )
    return None
