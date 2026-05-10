"""Port first-leg (axis-aligned grid hops) + OVG routing and optional vertical lane stagger."""

from __future__ import annotations

from logic_cad.core.debug.debug_log import logic_cad_debug_routing_verbose, logic_cad_log
from logic_cad.core.geometry.manhattan_metrics import manhattan_distance
from logic_cad.core.model.constants import (
    GRID_PITCH,
    ROUTE_ESCAPE_MM,
    ROUTING_VERTICAL_LANE_SPACING_MM,
)
from ._format import fmt_pt
from .constrained_router import route_manhattan_ovg_layers
from .escape_geometry import ensure_min_escape_distance
from .occupancy import Cardinal
from .polyline import dedupe_colinear, ensure_manhattan_polyline, snap_to_grid
from .profile import DEFAULT_ROUTING_PROFILE, RoutingProfile


def apply_vertical_lane_stagger(
    pts: list[tuple[float, float]],
    lane_index: int,
    pitch: float = GRID_PITCH,
    sep_mm: float = ROUTING_VERTICAL_LANE_SPACING_MM,
) -> list[tuple[float, float]]:
    """Spread overlapping vertical runs: offset the longest interior vertical segment by lane_index * sep_mm."""
    if lane_index == 0 or len(pts) < 3:
        return dedupe_colinear(pts)
    best_i = -1
    best_len = 0.0
    for i in range(1, len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        if abs(x0 - x1) >= 1e-9:
            continue
        ln = manhattan_distance((x0, y0), (x1, y1))
        if ln > best_len:
            best_len = ln
            best_i = i
    if best_i < 0 or best_len < 3 * pitch:
        return dedupe_colinear(pts)
    ox = float(round((lane_index * sep_mm) / pitch) * pitch)
    if abs(ox) < 1e-9:
        return dedupe_colinear(pts)
    x, y0 = pts[best_i]
    _, y1 = pts[best_i + 1]
    return ensure_manhattan_polyline(
        dedupe_colinear(pts[: best_i + 1] + [(x + ox, y0), (x + ox, y1)] + pts[best_i + 1 :]),
        pitch,
    )


def route_manhattan_with_escape(
    src: tuple[float, float],
    dst: tuple[float, float],
    obstacles: list[tuple[float, float, float, float]] | None = None,
    pitch: float = GRID_PITCH,
    escape_mm: float = ROUTE_ESCAPE_MM,
    first_escape_src: tuple[float, float] | None = None,
    vertical_lane: int = 0,
    soft_obstacles: list[tuple[float, float, float, float]] | None = None,
    profile: RoutingProfile | None = None,
    src_facing: tuple[int, int] | None = None,
    dst_facing: tuple[int, int] | None = None,
    obstacles_relaxed: list[tuple[float, float, float, float]] | None = None,
    dual_axis_initial_escape: bool = False,
    existing_wire_segments: list[tuple[tuple[float, float], tuple[float, float]]] | None = None,
    banned_src_cardinals: set[Cardinal] | None = None,
    skip_first_leg_hard_obstacle_check: bool = True,
) -> list[tuple[float, float]]:
    """Manhattan OVG route with mandatory axis-aligned first leg from the source port.

    ``first_escape_src`` is preferred as the first-hop target when valid (after min-length snap).
    All four axis directions are explored via the OVG multi-start search.

    ``existing_wire_segments``: other wires' segments; collinear overlap is rejected during OVG.
    ``banned_src_cardinals``: unit grid directions ((±1,0),(0,±1)) disallowed for the first leg
    (e.g. WIRE_BRANCH hub ray occupancy).

    ``src_facing`` / ``dst_facing`` enable wraparound fixed candidates on the p0→p1 collect only.
    ``dual_axis_initial_escape`` is accepted for API compatibility and ignored.
    """
    _ = dual_axis_initial_escape
    profile = profile or DEFAULT_ROUTING_PROFILE
    p0 = snap_to_grid(*src, pitch)
    p1 = snap_to_grid(*dst, pitch)
    if p0 == p1:
        return [p0]
    min_leg = max(escape_mm, pitch)
    preferred_escape = None
    if first_escape_src is not None:
        preferred_escape = ensure_min_escape_distance(
            p0, snap_to_grid(*first_escape_src, pitch), min_leg, pitch
        )
    if logic_cad_debug_routing_verbose():
        logic_cad_log(
            "routing",
            (
                f"escape fixed_then_ovg src={fmt_pt(p0)} dst={fmt_pt(p1)} "
                f"preferred={fmt_pt(preferred_escape) if preferred_escape else 'None'}"
            ),
        )
    out = route_manhattan_ovg_layers(
        p0,
        p1,
        obstacles or [],
        soft_obstacles=soft_obstacles,
        pitch=pitch,
        profile=profile,
        obstacles_relaxed=obstacles_relaxed,
        existing_wire_segments=existing_wire_segments,
        banned_src_cardinals=banned_src_cardinals,
        first_escape_src=preferred_escape,
        toward=p1,
        escape_mm=escape_mm,
        skip_first_leg_hard_obstacle_check=skip_first_leg_hard_obstacle_check,
        src_facing=src_facing,
        dst_facing=dst_facing,
    )
    out = ensure_manhattan_polyline(dedupe_colinear(out), pitch)
    if vertical_lane != 0:
        out = apply_vertical_lane_stagger(out, vertical_lane, pitch)
    if len(out) < 2:
        return [p0, p1] if (p0[0] != p1[0] or p0[1] != p1[1]) else [p0]
    return out
