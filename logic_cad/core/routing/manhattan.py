"""Manhattan routing: fixed L/U candidates, optional wraparound, then OVG fallback (layers 1–4)."""

from __future__ import annotations

from logic_cad.core.model.constants import GRID_PITCH
from logic_cad.core.debug.debug_log import logic_cad_debug_routing_verbose, logic_cad_log
from ._format import fmt_pt
from .facing import compute_bypass_lines, gen_wraparound_candidates
from .obstacles import obstacle_rects_inflated, path_hits_obstacle_rects
from .overlap import path_has_collinear_overlap
from .ovg import route_ovg
from .polyline import dedupe_colinear, snap_to_grid
from .profile import DEFAULT_ROUTING_PROFILE, RoutingProfile
from .scoring import pick_shortest_valid

# Upper bound on |k| for grid detours in collect_fixed_manhattan_polylines (per-axis stripes).
FIXED_MANHATTAN_DETOUR_K_MAX = 56

# Small |k| only for 5-point Z templates (keeps candidate count bounded).
_DETOUR_K_SMALL = (-2, -1, 1, 2)


def collect_fixed_manhattan_polylines(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    pitch: float,
    obs: list[tuple[float, float, float, float]],
    soft: list[tuple[float, float, float, float]],
    src_facing: tuple[int, int] | None,
    dst_facing: tuple[int, int] | None,
    existing_wire_segments: list[tuple[tuple[float, float], tuple[float, float]]] | None = None,
) -> list[list[tuple[float, float]]]:
    """L/U, wrap, and detour polylines used before OVG fallback (same set as legacy fixed phase)."""
    candidates: list[list[tuple[float, float]]] = []

    def add(p: list[tuple[float, float]]) -> None:
        p = dedupe_colinear(p)
        if len(p) >= 2:
            candidates.append(p)

    if abs(x0 - x1) < 1e-9 or abs(y0 - y1) < 1e-9:
        add([(x0, y0), (x1, y1)])
    add([(x0, y0), (x1, y0), (x1, y1)])
    add([(x0, y0), (x0, y1), (x1, y1)])
    if src_facing is not None:
        for candidate in gen_wraparound_candidates(
            (x0, y0),
            (x1, y1),
            src_facing,
            dst_facing,
            compute_bypass_lines((x0, y0), (x1, y1), obs, pitch),
        ):
            add(candidate)

    need_detour_candidates = bool(obs or soft or (existing_wire_segments or []))
    if need_detour_candidates:
        k_max = min(
            FIXED_MANHATTAN_DETOUR_K_MAX,
            max(16, int(abs(x1 - x0) / pitch) + int(abs(y1 - y0) / pitch) + 8),
        )
        for k in range(-k_max, k_max + 1):
            if k == 0:
                continue
            ym = y0 + k * pitch
            xm = x0 + k * pitch
            ym_d = y1 + k * pitch
            xm_d = x1 + k * pitch
            add([(x0, y0), (x0, ym), (x1, ym), (x1, y1)])
            add([(x0, y0), (xm, y0), (xm, y1), (x1, y1)])
            add([(x0, y0), (x0, ym_d), (x1, ym_d), (x1, y1)])
            add([(x0, y0), (xm_d, y0), (xm_d, y1), (x1, y1)])
        mid_x, mid_y = snap_to_grid((x0 + x1) / 2, (y0 + y1) / 2, pitch)
        add([(x0, y0), (x0, mid_y), (x1, mid_y), (x1, y1)])
        add([(x0, y0), (mid_x, y0), (mid_x, y1), (x1, y1)])

        for kd in _DETOUR_K_SMALL:
            ym = snap_to_grid(x0, y0 + kd * pitch, pitch)[1]
            for km in (-1, 1):
                xm_a = snap_to_grid(x0 + km * pitch, y0, pitch)[0]
                xm_b = snap_to_grid(x1 + km * pitch, y0, pitch)[0]
                add([(x0, y0), (x0, ym), (xm_a, ym), (xm_a, y1), (x1, y1)])
                add([(x0, y0), (x0, ym), (xm_b, ym), (xm_b, y1), (x1, y1)])
        for kd in _DETOUR_K_SMALL:
            xm = snap_to_grid(x0 + kd * pitch, y0, pitch)[0]
            for km in (-1, 1):
                ym_a = snap_to_grid(x0, y0 + km * pitch, pitch)[1]
                ym_b = snap_to_grid(x0, y1 + km * pitch, pitch)[1]
                add([(x0, y0), (xm, y0), (xm, ym_a), (x1, ym_a), (x1, y1)])
                add([(x0, y0), (xm, y0), (xm, ym_b), (x1, ym_b), (x1, y1)])

    return candidates


def route_manhattan_layers_for_hard(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    obs: list[tuple[float, float, float, float]],
    soft: list[tuple[float, float, float, float]],
    pitch: float,
    profile: RoutingProfile,
    src_facing: tuple[int, int] | None,
    dst_facing: tuple[int, int] | None,
    layer_fixed: int,
    layer_ovg: int,
    existing_wire_segments: list[tuple[tuple[float, float], tuple[float, float]]] | None = None,
) -> list[tuple[float, float]] | None:
    """Try C/U-style fixed candidates (one layer id) then OVG (another). Return None if both fail."""
    candidates = collect_fixed_manhattan_polylines(
        x0,
        y0,
        x1,
        y1,
        pitch,
        obs,
        soft,
        src_facing,
        dst_facing,
        existing_wire_segments=existing_wire_segments,
    )

    hard_rects = obstacle_rects_inflated(obs) if obs else []
    soft_rects = obstacle_rects_inflated(soft) if soft else []
    best = pick_shortest_valid(
        candidates, hard_rects, soft_rects, existing_wire_segments=existing_wire_segments
    )
    if best is not None:
        if logic_cad_debug_routing_verbose():
            logic_cad_log(
                "routing",
                (
                    f"route layer={layer_fixed} fixed_candidate src={fmt_pt((x0, y0))} dst={fmt_pt((x1, y1))} "
                    f"candidates={len(candidates)} hard={len(obs)} soft={len(soft)} points={len(best)}"
                ),
            )
        return best

    if not obs:
        if logic_cad_debug_routing_verbose():
            logic_cad_log(
                "routing",
                (
                    f"route layer={layer_fixed} no_hard_obstacles src={fmt_pt((x0, y0))} "
                    f"dst={fmt_pt((x1, y1))}"
                ),
            )
        simple: list[list[tuple[float, float]]] = []
        if x0 == x1 or y0 == y1:
            simple.append([(x0, y0), (x1, y1)])
        else:
            simple.append([(x0, y0), (x1, y0), (x1, y1)])
            simple.append([(x0, y0), (x0, y1), (x1, y1)])
        for sp in simple:
            if existing_wire_segments and path_has_collinear_overlap(sp, existing_wire_segments):
                continue
            return sp

    for fb in (
        [(x0, y0), (x1, y0), (x1, y1)],
        [(x0, y0), (x0, y1), (x1, y1)],
    ):
        if len(fb) >= 2 and not path_hits_obstacle_rects(fb, hard_rects):
            if existing_wire_segments and path_has_collinear_overlap(fb, existing_wire_segments):
                continue
            if logic_cad_debug_routing_verbose():
                logic_cad_log(
                    "routing",
                    (
                        f"route layer={layer_fixed} fixed_fallback src={fmt_pt((x0, y0))} "
                        f"dst={fmt_pt((x1, y1))} points={len(fb)}"
                    ),
                )
            return fb

    if logic_cad_debug_routing_verbose():
        logic_cad_log(
            "routing",
            (
                f"route layer={layer_ovg} ovg_fallback src={fmt_pt((x0, y0))} dst={fmt_pt((x1, y1))} "
                f"hard={len(obs)} soft={len(soft)} candidates={len(candidates)}"
            ),
        )
    ovg = route_ovg(
        x0, y0, x1, y1, obs, soft, pitch, profile.max_search_states, existing_wire_segments
    )
    if ovg is not None:
        if logic_cad_debug_routing_verbose():
            logic_cad_log(
                "routing",
                (
                    f"route layer={layer_ovg} ovg_selected src={fmt_pt((x0, y0))} dst={fmt_pt((x1, y1))} "
                    f"points={len(ovg)}"
                ),
            )
        return ovg

    logic_cad_log(
        "routing",
        (
            f"route layer={layer_ovg} fail src={fmt_pt((x0, y0))} dst={fmt_pt((x1, y1))} "
            f"hard={len(obs)} soft={len(soft)}"
        ),
    )
    return None


def route_manhattan(
    src: tuple[float, float],
    dst: tuple[float, float],
    obstacles: list[tuple[float, float, float, float]] | None = None,
    pitch: float = GRID_PITCH,
    soft_obstacles: list[tuple[float, float, float, float]] | None = None,
    profile: RoutingProfile | None = None,
    src_facing: tuple[int, int] | None = None,
    dst_facing: tuple[int, int] | None = None,
    obstacles_relaxed: list[tuple[float, float, float, float]] | None = None,
    existing_wire_segments: list[tuple[tuple[float, float], tuple[float, float]]] | None = None,
) -> list[tuple[float, float]]:
    """Manhattan path; if obstacles given, try detours before falling back to simple L.

    Layers 1–2 use ``obstacles`` (symbols + wires + reserved paths as built by callers).
    When ``obstacles_relaxed`` is set (symbol-only hard rects), layers 3–4 repeat fixed
    candidates and OVG with that reduced set so routes may cross existing wires.
    """
    profile = profile or DEFAULT_ROUTING_PROFILE
    obs = obstacles or []
    soft = soft_obstacles or []
    x0, y0 = snap_to_grid(*src, pitch)
    x1, y1 = snap_to_grid(*dst, pitch)
    if (x0, y0) == (x1, y1):
        return [(x0, y0)]

    hit = route_manhattan_layers_for_hard(
        x0,
        y0,
        x1,
        y1,
        obs,
        soft,
        pitch,
        profile,
        src_facing,
        dst_facing,
        1,
        2,
        existing_wire_segments,
    )
    if hit is not None:
        return hit

    if obstacles_relaxed is not None:
        obs_r = list(obstacles_relaxed)
        hit_r = route_manhattan_layers_for_hard(
            x0,
            y0,
            x1,
            y1,
            obs_r,
            soft,
            pitch,
            profile,
            src_facing,
            dst_facing,
            3,
            4,
            existing_wire_segments,
        )
        if hit_r is not None:
            return hit_r

    logic_cad_log(
        "routing",
        (
            f"route fail_all_layers src={fmt_pt((x0, y0))} dst={fmt_pt((x1, y1))} "
            f"hard={len(obs)} soft={len(soft)} relaxed_used={obstacles_relaxed is not None}"
        ),
    )
    raise ValueError("障害物を避けるマンハッタン経路が見つかりません。")
