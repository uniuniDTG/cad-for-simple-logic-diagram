"""Port first-leg constraints: fixed Manhattan candidates, then OVG (shared segment rules)."""

from __future__ import annotations

import math
from dataclasses import dataclass

from logic_cad.core.geometry.manhattan_metrics import (
    manhattan_distance,
    points_close_xy,
    segment_is_axis_aligned,
)
from logic_cad.core.model.constants import GRID_PITCH, ROUTE_ESCAPE_MM
from logic_cad.core.routing.escape_geometry import ensure_min_escape_distance
from logic_cad.core.routing.manhattan import collect_fixed_manhattan_polylines
from logic_cad.core.routing.obstacles import obstacle_rects_inflated
from logic_cad.core.routing.occupancy import CARDINALS, Cardinal
from logic_cad.core.routing.ovg import route_ovg_multi_start
from logic_cad.core.routing.polyline import dedupe_colinear, snap_to_grid
from logic_cad.core.routing.profile import (
    DEFAULT_ROUTING_PROFILE,
    RoutingProfile,
    apply_routing_env_overrides,
)
from logic_cad.core.routing.scoring import polyline_routing_cost_rects
from logic_cad.core.routing.segment_policy import path_valid_under_port_first_leg_policy


@dataclass(frozen=True)
class _PortFirstLegHybridContext:
    """Shared parameters for fixed-Manhattan and OVG multi-start attempts.

    The hard-obstacle rectangle list is passed separately to each attempt; all other
    routing inputs are held here so callers do not thread long argument lists through
    nested closures.

    Attributes:
        p0: Snapped source grid point.
        p1: Snapped destination grid point.
        soft: Soft obstacle rectangles (scoring only).
        pitch: Grid pitch (mm).
        existing_wire_segments: Other wires for collinear overlap rejection.
        banned_src_cardinals: Unit directions disallowed for the first leg from *p0*.
        skip_first_leg_hard_obstacle_check: If True, use joint-based hard check on first leg.
        escape_mm: Minimum escape distance from the port (mm).
        first_escape_src: Optional preferred first-hop target for fixed phase.
        src_facing: Optional source port facing for wraparound fixed candidates.
        dst_facing: Optional destination facing for wraparound fixed candidates.
        hops: Axis-aligned first-hop grid points for OVG multi-start.
        min_leg: Effective minimum first-leg length (max of escape and pitch).
        max_search_states: OVG heap expansion budget from the active routing profile.
    """

    p0: tuple[float, float]
    p1: tuple[float, float]
    soft: list[tuple[float, float, float, float]]
    pitch: float
    existing_wire_segments: list[tuple[tuple[float, float], tuple[float, float]]] | None
    banned_src_cardinals: set[Cardinal] | None
    skip_first_leg_hard_obstacle_check: bool
    escape_mm: float
    first_escape_src: tuple[float, float] | None
    src_facing: tuple[int, int] | None
    dst_facing: tuple[int, int] | None
    hops: list[tuple[float, float]]
    min_leg: float
    max_search_states: int


def _try_fixed_with_context(
    ctx: _PortFirstLegHybridContext,
    obs: list[tuple[float, float, float, float]],
) -> list[tuple[float, float]] | None:
    """Run the fixed Manhattan + escape phase for one hard-obstacle set.

    Args:
        ctx: Shared port-first-leg parameters and OVG hop metadata (obstacles excluded).
        obs: Hard obstacle rectangles for this pass.

    Returns:
        Best-cost valid polyline, or None if no fixed candidate satisfies policy.
    """
    return _try_fixed_manhattan_escape_phase(
        ctx.p0,
        ctx.p1,
        obs,
        ctx.soft,
        ctx.pitch,
        existing_wire_segments=ctx.existing_wire_segments,
        banned_src_cardinals=ctx.banned_src_cardinals,
        skip_first_leg_hard_obstacle_check=ctx.skip_first_leg_hard_obstacle_check,
        escape_mm=ctx.escape_mm,
        first_escape_src=ctx.first_escape_src,
        src_facing=ctx.src_facing,
        dst_facing=ctx.dst_facing,
    )


def _try_ovg_with_context(
    ctx: _PortFirstLegHybridContext,
    obs: list[tuple[float, float, float, float]],
) -> list[tuple[float, float]] | None:
    """Run OVG multi-start for one hard-obstacle set using *ctx* first hops and budgets.

    Args:
        ctx: Shared port-first-leg parameters including ``hops`` and ``max_search_states``.
        obs: Hard obstacle rectangles for this pass.

    Returns:
        A valid OVG path, or None if search fails or no first hop is admissible.
    """
    return route_ovg_multi_start(
        ctx.p0,
        ctx.p1[0],
        ctx.p1[1],
        obs,
        ctx.soft,
        ctx.pitch,
        ctx.max_search_states,
        ctx.hops,
        ctx.existing_wire_segments,
        ctx.banned_src_cardinals,
        min_first_leg_mm=ctx.min_leg,
        skip_first_leg_hard_obstacle_check=ctx.skip_first_leg_hard_obstacle_check,
    )


def build_axis_aligned_first_hops(
    p0: tuple[float, float],
    pitch: float,
    min_first_leg_mm: float,
    max_steps: int,
    priority_points: list[tuple[float, float]] | None = None,
    toward: tuple[float, float] | None = None,
) -> list[tuple[float, float]]:
    """Grid points along ±X/±Y from p0, at least min_first_leg_mm away (Manhattan).

    Ordering: optional priority_points first, then by Manhattan distance to *toward* (if given),
    then by (leg_len, cardinal index, k) for determinism.
    """
    p0s = snap_to_grid(p0[0], p0[1], pitch)
    raw: list[tuple[float, float, int, int, tuple[float, float]]] = []
    for ci, d in enumerate(CARDINALS):
        for k in range(1, max_steps + 1):
            fh = snap_to_grid(
                p0s[0] + d[0] * k * pitch,
                p0s[1] + d[1] * k * pitch,
                pitch,
            )
            leg = manhattan_distance(p0s, fh)
            if leg + 1e-9 < min_first_leg_mm:
                continue
            tw_dist = manhattan_distance(fh, toward) if toward is not None else leg
            raw.append((tw_dist, leg, ci, k, fh))

    raw.sort(key=lambda t: (t[0], t[1], t[2], t[3]))
    ordered: list[tuple[float, float]] = [t[4] for t in raw]

    out: list[tuple[float, float]] = []
    seen: set[tuple[float, float]] = set()
    for px, py in priority_points or ():
        s = snap_to_grid(px, py, pitch)
        if s in seen:
            continue
        if manhattan_distance(p0s, s) + 1e-9 < min_first_leg_mm:
            continue
        if not segment_is_axis_aligned(p0s, s):
            continue
        seen.add(s)
        out.append(s)
    for fh in ordered:
        if fh in seen:
            continue
        seen.add(fh)
        out.append(fh)
    return out


def _try_fixed_manhattan_escape_phase(
    p0: tuple[float, float],
    p1: tuple[float, float],
    obs: list[tuple[float, float, float, float]],
    soft: list[tuple[float, float, float, float]],
    pitch: float,
    *,
    existing_wire_segments: list[tuple[tuple[float, float], tuple[float, float]]] | None,
    banned_src_cardinals: set[Cardinal] | None,
    skip_first_leg_hard_obstacle_check: bool,
    escape_mm: float,
    first_escape_src: tuple[float, float] | None,
    src_facing: tuple[int, int] | None = None,
    dst_facing: tuple[int, int] | None = None,
) -> list[tuple[float, float]] | None:
    """Evaluate legacy fixed polylines with the same first-leg / hard / collinear rules as OVG."""
    min_leg = max(escape_mm, pitch)
    hard_rects = obstacle_rects_inflated(obs) if obs else []
    soft_rects = obstacle_rects_inflated(soft) if soft else []

    merged: list[list[tuple[float, float]]] = []
    merged.extend(
        collect_fixed_manhattan_polylines(
            p0[0],
            p0[1],
            p1[0],
            p1[1],
            pitch,
            obs,
            soft,
            src_facing,
            dst_facing,
            existing_wire_segments=existing_wire_segments,
        )
    )

    if first_escape_src is not None:
        ex = ensure_min_escape_distance(
            p0,
            snap_to_grid(first_escape_src[0], first_escape_src[1], pitch),
            min_leg,
            pitch,
        )
        tails = collect_fixed_manhattan_polylines(
            ex[0],
            ex[1],
            p1[0],
            p1[1],
            pitch,
            obs,
            soft,
            None,
            None,
            existing_wire_segments=existing_wire_segments,
        )
        for t in tails:
            if len(t) < 1:
                continue
            if points_close_xy(t[0], ex):
                full = dedupe_colinear([p0] + t)
            else:
                full = dedupe_colinear([p0, ex] + t)
            merged.append(full)

    best: list[tuple[float, float]] | None = None
    best_c = float("inf")
    seen: set[tuple[tuple[float, float], ...]] = set()
    for raw in merged:
        p = dedupe_colinear(raw)
        if len(p) < 2:
            continue
        key = tuple(p)
        if key in seen:
            continue
        seen.add(key)
        if not path_valid_under_port_first_leg_policy(
            p,
            hard_rects,
            existing_wire_segments,
            pitch,
            min_leg,
            skip_first_leg_hard_obstacle_check=skip_first_leg_hard_obstacle_check,
            banned_src_cardinals=banned_src_cardinals,
        ):
            continue
        c = polyline_routing_cost_rects(p, soft_rects)
        if c < best_c:
            best_c = c
            best = p
    return best


def _try_route_for_obstacle_set(
    ctx: _PortFirstLegHybridContext,
    obs: list[tuple[float, float, float, float]],
    profile: RoutingProfile,
) -> list[tuple[float, float]] | None:
    """Run fixed Manhattan then OVG for one hard-obstacle list; return first success or None."""
    if profile.use_fixed_manhattan:
        hit = _try_fixed_with_context(ctx, obs)
        if hit is not None:
            return hit
    if profile.use_ovg_multi:
        hit = _try_ovg_with_context(ctx, obs)
        if hit is not None:
            return hit
    return None


def route_manhattan_ovg_layers(
    src: tuple[float, float],
    dst: tuple[float, float],
    obstacles: list[tuple[float, float, float, float]],
    *,
    soft_obstacles: list[tuple[float, float, float, float]] | None = None,
    pitch: float = GRID_PITCH,
    profile: RoutingProfile | None = None,
    obstacles_relaxed: list[tuple[float, float, float, float]] | None = None,
    existing_wire_segments: list[tuple[tuple[float, float], tuple[float, float]]] | None = None,
    banned_src_cardinals: set[Cardinal] | None = None,
    first_escape_src: tuple[float, float] | None = None,
    toward: tuple[float, float] | None = None,
    escape_mm: float = ROUTE_ESCAPE_MM,
    skip_first_leg_hard_obstacle_check: bool = True,
    src_facing: tuple[int, int] | None = None,
    dst_facing: tuple[int, int] | None = None,
) -> list[tuple[float, float]]:
    """Fixed Manhattan candidates (port first-leg rules), then OVG multi-start on the same constraints.

    When ``profile.min_cost_across_wire_obstacle_passes`` is True and ``obstacles_relaxed`` is set,
    only the relaxed (symbol-only hard) obstacle list is used; the full ``obstacles`` list is skipped.
    """
    profile = apply_routing_env_overrides(profile or DEFAULT_ROUTING_PROFILE)
    if not profile.use_fixed_manhattan and not profile.use_ovg_multi:
        raise ValueError(
            "ルーティング設定で固定マンハッタンと OVG 複数起点の両方が無効です（試行する手段がありません）。"
        )
    soft = soft_obstacles or []

    p0 = snap_to_grid(src[0], src[1], pitch)
    p1 = snap_to_grid(dst[0], dst[1], pitch)
    if p0 == p1:
        return [p0]

    min_leg = max(escape_mm, pitch)

    max_steps = min(
        16,
        max(
            3,
            int(math.ceil(max(escape_mm, pitch) / pitch)) + profile.max_escape_candidates + 4,
        ),
    )
    priority: list[tuple[float, float]] = []
    if first_escape_src is not None:
        priority.append(first_escape_src)

    hops = build_axis_aligned_first_hops(
        p0,
        pitch,
        min_leg,
        max_steps,
        priority_points=priority or None,
        toward=toward if toward is not None else p1,
    )

    ctx = _PortFirstLegHybridContext(
        p0=p0,
        p1=p1,
        soft=soft,
        pitch=pitch,
        existing_wire_segments=existing_wire_segments,
        banned_src_cardinals=banned_src_cardinals,
        skip_first_leg_hard_obstacle_check=skip_first_leg_hard_obstacle_check,
        escape_mm=escape_mm,
        first_escape_src=first_escape_src,
        src_facing=src_facing,
        dst_facing=dst_facing,
        hops=hops,
        min_leg=min_leg,
        max_search_states=profile.max_search_states,
    )

    use_min_cost = profile.min_cost_across_wire_obstacle_passes and obstacles_relaxed is not None
    if use_min_cost:
        p_relax = _try_route_for_obstacle_set(ctx, list(obstacles_relaxed), profile)
        if p_relax is None:
            raise ValueError(
                "障害物を避けるマンハッタン経路が見つかりません（固定候補と OVG を使い切りました）。"
            )
        return p_relax

    obstacle_passes: list[list[tuple[float, float, float, float]]] = [obstacles]
    if obstacles_relaxed is not None:
        obstacle_passes.append(list(obstacles_relaxed))

    for obs in obstacle_passes:
        hit = _try_route_for_obstacle_set(ctx, obs, profile)
        if hit is not None:
            return hit

    raise ValueError(
        "障害物を避けるマンハッタン経路が見つかりません（固定候補と OVG を使い切りました）。"
    )
