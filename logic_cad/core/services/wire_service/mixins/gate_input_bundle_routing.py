"""Multi-wire bundle routing into AND/OR gate logic inputs."""

from __future__ import annotations

from dataclasses import replace
from time import perf_counter
from typing import Any

from logic_cad.core.debug.debug_log import (
    logic_cad_debug_routing_verbose,
    logic_cad_log,
)
from logic_cad.core.debug.routing_perf import (
    routing_perf_add,
    routing_perf_enabled,
    routing_perf_span,
)
from logic_cad.core.uid_display import format_uid_display
from logic_cad.core.geometry.manhattan_metrics import manhattan_distance
from logic_cad.core.model.constants import (
    GRID_PITCH,
    ROUTE_ESCAPE_MM,
    ROUTING_MIN_WIRE_SEPARATION_MM,
)
from logic_cad.core.model.index_store import IndexStore
from logic_cad.core.model.wire_port_helpers import wire_allows_orthogonal_cross
from logic_cad.core.model.xdata import read_ld_app_dict
from logic_cad.core.routing.wire_path_metrics import (
    _count_segment_crossings_among,
    _count_segment_overlaps_among,
    _log_vertical_parallel_overlap_diagnosis,
    _polylines_cross,
)
from logic_cad.core.routing.wire_routing_from_document import (
    DEFAULT_ROUTING_PROFILE,
    RoutingProfile,
    build_symbol_only_routing_obstacles,
    path_hits_obstacles,
    polyline_segments,
    reserved_path_obstacles,
    symbol_obstacles,
    wire_obstacles,
)
from logic_cad.core.services.wire_service.mixins import gate_input as _gate_input_shim
from logic_cad.core.services.wire_service.mixins.gate_input_bundle_helpers import (
    bundle_penalty_score,
    fmt_gate_input_pt,
    is_perfect_bundle_score,
    routing_profile_summary,
)
from logic_cad.core.services.wire_service.mixins.gate_input_host import GateInputWireServiceHost
from logic_cad.core.services.wire_service.mixins.gate_input_rows import gate_input_wire_paths


def route_gate_input_bundle_rows(
    host: GateInputWireServiceHost,
    index: IndexStore,
    layout_name: str,
    gate_uid: str,
    n_inputs: int,
    rows: list[tuple[Any, str, str, str, str, int]],
    routing_profile: RoutingProfile | None = None,
) -> None:
    """Route all bundle rows into *gate_uid* with order-pick, cleanup, and perf spans.

    This is the multi-wire analogue of ``reroute_gate_input_wire`` shared across AND/OR inputs.

    Args:
        host: Wire service facade (DOC + routing helpers implemented by ``WireService`` mixins).
        index: ``IndexStore`` for the layout; rebuilt as needed internally.
        layout_name: Target paper-space layout containing the wires.
        gate_uid: Destination AND/OR ``INSERT`` UID.
        n_inputs: Dynamic gate input count (used for port ordering/heuristics).
        rows: Active bundle rows referencing WIRE entities in the DXF drawing.
        routing_profile: Optional routing profile; sensible defaults applied when omitted.

    Raises:
        RuntimeError: If order-picking finds a logical winner path record but lacks geometry.
        ValueError: Bubbled up from Manhattan routing when a bundle pass is infeasible.
    """
    routing_profile = routing_profile or DEFAULT_ROUTING_PROFILE
    if not rows:
        return
    perf = routing_perf_enabled()
    logic_cad_log(
        "routing",
        (
            f"bundle start gate UUID={format_uid_display(gate_uid)} layout={layout_name!r} "
            f"profile({routing_profile_summary(routing_profile)})"
        ),
    )
    with routing_perf_span("gate_input.bundle.setup"):
        index.rebuild(host.doc, layout_name)
        exclude_wire_uids = {r[1] for r in rows}
        base_soft_obstacles = wire_obstacles(
            host.doc, layout_name, exclude_wire_uids=exclude_wire_uids, index=index
        )
        # For bundle passes, hard wire obstacles are identical to this base set.
        base_wire_hard_obstacles = list(base_soft_obstacles)
        # Non-bundle segments are invariant during candidate evaluation/cleanup.
        non_bundle_segments_by_wire_uid: dict[
            str, list[tuple[tuple[float, float], tuple[float, float]]]
        ] = {}
        for ent, wu2, _d2 in host.iter_wire_meta(layout_name):
            if not wu2 or wu2 in exclude_wire_uids:
                continue
            non_bundle_segments_by_wire_uid[wu2] = polyline_segments(
                host._polyline_points(ent)
            )

        bottom_up = sorted(rows, key=lambda r: (r[5], r[1]))
        top_down = sorted(rows, key=lambda r: (-r[5], r[1]))
        _in_valid: list[tuple[float, float]] = []
        for _i in range(n_inputs):
            _pw = index.get_port_world(gate_uid, f"IN{_i}_LOGIC")
            if _pw is not None:
                _in_valid.append(_pw)
        if _in_valid:
            _gcx = sum(p[0] for p in _in_valid) / len(_in_valid)
            _gcy = sum(p[1] for p in _in_valid) / len(_in_valid)

            def _near_first_key(r: tuple[object, str, str, str, str, int]) -> tuple[float, str]:
                _e, wu, su, sp, _dp, _idx = r
                src_w = index.get_port_world(su, sp)
                if src_w is None:
                    return (float("inf"), wu)
                dx = src_w[0] - _gcx
                dy = src_w[1] - _gcy
                return (dx * dx + dy * dy, wu)

            near_first = sorted(rows, key=_near_first_key)
        else:
            near_first = list(bottom_up)

        initial_snapshot: list[tuple[object, list[tuple[float, float]]]] = [
            (r[0], list(host._polyline_points(r[0]))) for r in rows
        ]

    def restore_initial_pts() -> None:
        for ent, pts in initial_snapshot:
            host.set_wire_points(layout_name, ent, pts, snap_branches=False)

    ordered_rows: list[tuple[object, str, str, str, str, int]] = list(bottom_up)
    pair_soft_obstacles_cache: dict[
        tuple[str, str, str], list[tuple[float, float, float, float]]
    ] = {}
    hard_symbol_obstacles_cache: dict[
        tuple[str, str, str], list[tuple[float, float, float, float]]
    ] = {}
    overlap_symbol_obstacles_cache: dict[
        tuple[str, str, str], list[tuple[float, float, float, float]]
    ] = {}
    overlap_segments_cache: dict[
        str, list[tuple[tuple[float, float], tuple[float, float]]]
    ] = {}
    symbol_exclude_cache: dict[str, set[str]] = {}
    port_facing_cache: dict[tuple[str, str], tuple[int, int] | None] = {}
    banned_src_cache: dict[
        tuple[str, str, str], set[tuple[int, int]] | None
    ] = {}

    def has_symbol_overlap_for(
        routed_paths: list[list[tuple[float, float]]],
        row_order: list[tuple[object, str, str, str, str, int]],
    ) -> bool:
        for pts, row in zip(routed_paths, row_order):
            if not pts:
                continue
            _entity, _wu, su, sp, dp, _idx = row
            key = (su, sp, dp)
            obstacles = overlap_symbol_obstacles_cache.get(key)
            if obstacles is None:
                obstacles = symbol_obstacles(
                    host.doc,
                    index,
                    host._symbol_uids_exclude_from_routing_obstacles(su, gate_uid),
                    access_ports={su: {sp}, gate_uid: {dp}},
                )
                overlap_symbol_obstacles_cache[key] = list(obstacles)
            if path_hits_obstacles(pts, obstacles):
                return True
        return False

    def _symbol_overlap_wire_uids_for(
        routed_paths: list[list[tuple[float, float]]],
        row_order: list[tuple[object, str, str, str, str, int]],
    ) -> set[str]:
        """Collect wire UIDs whose routed path intersects symbol obstacles.

        Args:
            routed_paths: Routed paths in the same order as ``row_order``.
            row_order: Bundle rows to inspect.

        Returns:
            Set of wire UIDs that overlap symbol obstacles.
        """
        overlapped: set[str] = set()
        for pts, row in zip(routed_paths, row_order):
            if not pts:
                continue
            _entity, wu, su, sp, dp, _idx = row
            key = (su, sp, dp)
            obstacles = overlap_symbol_obstacles_cache.get(key)
            if obstacles is None:
                obstacles = symbol_obstacles(
                    host.doc,
                    index,
                    host._symbol_uids_exclude_from_routing_obstacles(su, gate_uid),
                    access_ports={su: {sp}, gate_uid: {dp}},
                )
                overlap_symbol_obstacles_cache[key] = list(obstacles)
            if path_hits_obstacles(pts, obstacles):
                overlapped.add(wu)
        return overlapped

    def _overlap_segments_excluding(
        wire_uid: str,
    ) -> list[tuple[tuple[float, float], tuple[float, float]]]:
        """Return non-bundle segments excluding current wire.

        Args:
            wire_uid: Wire UID being rerouted.

        Returns:
            Segments from other wires in the same layout.
        """
        cached = overlap_segments_cache.get(wire_uid)
        if cached is not None:
            return cached
        merged: list[tuple[tuple[float, float], tuple[float, float]]] = []
        for wu2, segs2 in non_bundle_segments_by_wire_uid.items():
            if wu2 == wire_uid:
                continue
            merged.extend(segs2)
        overlap_segments_cache[wire_uid] = merged
        return merged

    def run_pass(
        seed_soft_paths: list[list[tuple[float, float]]] | None = None,
        spread_pre_entry: bool = False,
        row_order: list[tuple[object, str, str, str, str, int]] | None = None,
        *,
        routing_log_verbose: bool | None = None,
    ) -> list[list[tuple[float, float]]]:
        seq = row_order if row_order is not None else ordered_rows
        routed: list[list[tuple[float, float]]] = []
        reserved_paths: list[list[tuple[float, float]]] = []
        seeded_soft = [] if spread_pre_entry else reserved_path_obstacles(seed_soft_paths or [])
        row_verbose = (
            logic_cad_debug_routing_verbose()
            if routing_log_verbose is None
            else routing_log_verbose
        )
        if row_verbose:
            logic_cad_log(
                "routing",
                (
                    f"bundle pass gate UUID={format_uid_display(gate_uid)} spread_pre_entry={spread_pre_entry} "
                    f"seeded_soft={len(seeded_soft)} rows={len(seq)}"
                ),
            )

        for entity, _wu, su, sp, dp, _idx in seq:
            p0 = index.get_port_world(su, sp)
            p1 = index.get_port_world(gate_uid, dp)
            if p0 is None or p1 is None:
                routed.append([])
                continue
            if perf:
                t_pf0 = perf_counter()
                t_obs = perf_counter()
            pre_entry_offset = (
                ROUTING_MIN_WIRE_SEPARATION_MM * (_idx + 1) if spread_pre_entry else 0.0
            )
            dst_target = host._gate_input_pre_entry(index, gate_uid, dp, toward=p0, extra_offset_mm=pre_entry_offset) or p1
            esc = index.port_first_escape_world(host.doc, su, sp, ROUTE_ESCAPE_MM, toward=p1)
            if spread_pre_entry:
                esc = host._spread_escape_point(
                    p0,
                    esc,
                    ROUTING_MIN_WIRE_SEPARATION_MM * _idx,
                )
            lane = 0
            access_ports = {su: {sp}, gate_uid: {dp}}
            sym_ex = symbol_exclude_cache.get(su)
            if sym_ex is None:
                sym_ex = host._symbol_uids_exclude_from_routing_obstacles(su, gate_uid)
                symbol_exclude_cache[su] = set(sym_ex)
            key = (su, sp, dp)
            soft_obstacles = list(base_soft_obstacles) + list(seeded_soft)
            pair_soft = pair_soft_obstacles_cache.get(key)
            if pair_soft is None:
                pair_soft = host._pair_symbol_soft_obstacles(
                    index, su, gate_uid, access_ports
                )
                pair_soft_obstacles_cache[key] = list(pair_soft)
            soft_obstacles.extend(pair_soft)
            dst_facing_key = (gate_uid, dp)
            dst_facing = port_facing_cache.get(dst_facing_key)
            if dst_facing_key not in port_facing_cache:
                dst_facing = host._port_facing(index, gate_uid, dp)
                port_facing_cache[dst_facing_key] = dst_facing
            src_facing_key = (su, sp)
            src_facing = port_facing_cache.get(src_facing_key)
            if src_facing_key not in port_facing_cache:
                src_facing = host._port_facing(index, su, sp)
                port_facing_cache[src_facing_key] = src_facing
            hard_symbol = hard_symbol_obstacles_cache.get(key)
            if hard_symbol is None:
                hard_symbol = build_symbol_only_routing_obstacles(
                    host.doc,
                    index,
                    layout_name,
                    sym_ex,
                    access_ports=access_ports,
                    symbol_margin=0.0,
                )
                hard_symbol_obstacles_cache[key] = list(hard_symbol)
            obs_relaxed = (
                hard_symbol
                if routing_profile.relax_wire_hard_layers
                else None
            )
            if row_verbose:
                logic_cad_log(
                    "routing",
                    (
                        f"bundle row gate UUID={format_uid_display(gate_uid)} "
                        f"src UUID={format_uid_display(su)} dst_port={dp} "
                        f"p0={fmt_gate_input_pt(p0)} target={fmt_gate_input_pt(dst_target)} "
                        f"escape={fmt_gate_input_pt(esc) if esc is not None else 'None'} "
                        f"spread_pre_entry={spread_pre_entry}"
                    ),
                )
            if perf:
                routing_perf_add(
                    "gate_input.bundle.rm_preflight.obstacles",
                    perf_counter() - t_obs,
                )
                t_overlap = perf_counter()
            overlap_segs = _overlap_segments_excluding(_wu)
            banned_src_key = (su, sp, _wu)
            banned_src = banned_src_cache.get(banned_src_key)
            if banned_src is None:
                banned_src = host._banned_src_cardinals_for_route(
                    layout_name, su, sp, exclude_wire_uids={_wu}
                )
                banned_src_cache[banned_src_key] = (
                    set(banned_src) if banned_src is not None else None
                )
            if perf:
                routing_perf_add(
                    "gate_input.bundle.rm_preflight.overlap_segments",
                    perf_counter() - t_overlap,
                )
                t_ovg_inputs = perf_counter()
            hard_obs = list(hard_symbol)
            hard_obs.extend(base_wire_hard_obstacles)
            hard_obs.extend(reserved_path_obstacles(reserved_paths))
            if perf:
                routing_perf_add(
                    "gate_input.bundle.rm_preflight.ovg_inputs",
                    perf_counter() - t_ovg_inputs,
                )
                routing_perf_add(
                    "gate_input.bundle.rm_preflight_and_obstacles",
                    perf_counter() - t_pf0,
                )
                t_rm = perf_counter()
            eff_rm_profile = routing_profile
            if wire_allows_orthogonal_cross(read_ld_app_dict(entity)):
                eff_rm_profile = replace(
                    routing_profile, min_cost_across_wire_obstacle_passes=True
                )
            pts = _gate_input_shim.route_manhattan_with_escape(
                p0,
                dst_target,
                hard_obs,
                first_escape_src=esc,
                vertical_lane=lane,
                soft_obstacles=soft_obstacles,
                profile=eff_rm_profile,
                src_facing=src_facing,
                dst_facing=dst_facing,
                obstacles_relaxed=obs_relaxed,
                existing_wire_segments=overlap_segs,
                banned_src_cardinals=banned_src,
            )
            if perf:
                routing_perf_add("gate_input.bundle.rm_route", perf_counter() - t_rm)
                t_ap = perf_counter()
            final_pts = host._append_port_segment(pts, p1)
            final_pts = host._normalize_auto_route_points(final_pts, p0, p1)
            host.set_wire_points(layout_name, entity, final_pts, snap_branches=False)
            reserved_paths.append(final_pts)
            routed.append(final_pts)
            if perf:
                routing_perf_add("gate_input.bundle.rm_apply", perf_counter() - t_ap)
        return routed

    BAD_SCORE = (10**9, 10**9, 1, 10**15)

    def _fmt_bundle_eval_cost(s: tuple[int, int, int, float]) -> str:
        xc, oc, so, wl = s
        return f"crossings={xc} overlaps={oc} sym_overlap={so} wire_len={wl:.3f}"

    def _fmt_bundle_eval_cost_for_log(
        s: tuple[int, int, int, float], eval_ok: bool
    ) -> str:
        if not eval_ok:
            return "n/a (eval failed; BAD_SCORE sentinel, not measured)"
        return _fmt_bundle_eval_cost(s)

    def eval_bundle_order(
        candidate_name: str,
        seq: list[tuple[object, str, str, str, str, int]],
    ) -> tuple[tuple[int, int, int, float], list[list[tuple[float, float]]] | None]:
        restore_initial_pts()
        t_eval = perf_counter() if perf else 0.0
        try:
            fp = run_pass(row_order=seq, routing_log_verbose=False)
        except ValueError:
            if perf:
                routing_perf_add(
                    f"gate_input.bundle.order_pick.candidate.{candidate_name}.fail",
                    perf_counter() - t_eval,
                )
            return BAD_SCORE, None
        if perf:
            routing_perf_add(
                f"gate_input.bundle.order_pick.candidate.{candidate_name}.ok",
                perf_counter() - t_eval,
            )
            t_sc = perf_counter()
        paths = [p for p in fp if p]
        xc = _count_segment_crossings_among(paths) if paths else 0
        oc = _count_segment_overlaps_among(paths) if paths else 0
        so = int(has_symbol_overlap_for(fp, seq))
        wire_len = 0.0
        for p in paths:
            for i in range(len(p) - 1):
                ax, ay = p[i]
                bx, by = p[i + 1]
                wire_len += manhattan_distance((ax, ay), (bx, by))
        if perf:
            routing_perf_add("gate_input.bundle.eval_scoring", perf_counter() - t_sc)
        fp_copy = [[tuple(p) for p in row] for row in fp]
        return (xc, oc, so, wire_len), fp_copy

    def apply_routed_paths(
        seq: list[tuple[object, str, str, str, str, int]],
        fp: list[list[tuple[float, float]]],
    ) -> None:
        for row, pts in zip(seq, fp):
            ent = row[0]
            if pts:
                host.set_wire_points(layout_name, ent, pts, snap_branches=False)

    chose_bottom_up = True
    s_bu: tuple[int, int, int, float] = BAD_SCORE
    s_td: tuple[int, int, int, float] = BAD_SCORE
    s_nf: tuple[int, int, int, float] = BAD_SCORE
    fp_bu: list[list[tuple[float, float]]] | None = None
    fp_td: list[list[tuple[float, float]]] | None = None
    fp_nf: list[list[tuple[float, float]]] | None = None
    winner_seq: list[tuple[object, str, str, str, str, int]] = list(bottom_up)
    winner_fp: list[list[tuple[float, float]]] | None = None
    winner_name: str = "bottom_up"

    eval_cache: dict[
        tuple[str, ...],
        tuple[tuple[int, int, int, float], list[list[tuple[float, float]]] | None],
    ] = {}

    def _sequence_signature(seq: list[tuple[object, str, str, str, str, int]]) -> tuple[str, ...]:
        return tuple(f"{r[1]}:{r[2]}:{r[3]}:{r[4]}:{r[5]}" for r in seq)

    def eval_bundle_order_cached(
        candidate_name: str,
        seq: list[tuple[object, str, str, str, str, int]],
    ) -> tuple[tuple[int, int, int, float], list[list[tuple[float, float]]] | None]:
        sig = _sequence_signature(seq)
        cached = eval_cache.get(sig)
        if cached is not None:
            return cached
        result = eval_bundle_order(candidate_name, seq)
        eval_cache[sig] = result
        return result

    def _should_eval_top_down(
        score_bu: tuple[int, int, int, float],
        score_nf: tuple[int, int, int, float],
        fp_bu_local: list[list[tuple[float, float]]] | None,
        fp_nf_local: list[list[tuple[float, float]]] | None,
    ) -> bool:
        """Decide whether the third candidate needs full evaluation.

        Args:
            score_bu: Bottom-up score.
            score_nf: Near-first score.
            fp_bu_local: Bottom-up paths when evaluation succeeded.
            fp_nf_local: Near-first paths when evaluation succeeded.

        Returns:
            ``True`` when top-down should be fully evaluated.
        """
        if fp_bu_local is None or fp_nf_local is None:
            return True
        pen_bu = bundle_penalty_score(score_bu)
        pen_nf = bundle_penalty_score(score_nf)
        if pen_bu == pen_nf:
            return True
        if is_perfect_bundle_score(score_bu) or is_perfect_bundle_score(score_nf):
            # Keep quality when both are close in wire length.
            wire_gap = abs(score_bu[3] - score_nf[3])
            return wire_gap <= GRID_PITCH
        distance = sum(abs(a - b) for a, b in zip(pen_bu, pen_nf))
        return distance <= 1

    with routing_perf_span("gate_input.bundle.order_pick"):
        if len(rows) <= 1:
            ordered_rows = list(bottom_up)
        else:
            s_bu, fp_bu = eval_bundle_order_cached("bottom_up", bottom_up)
            s_nf, fp_nf = eval_bundle_order_cached("nearest_src", near_first)
            top_down_evaluated = False
            if _should_eval_top_down(s_bu, s_nf, fp_bu, fp_nf):
                s_td, fp_td = eval_bundle_order_cached("top_down", top_down)
                top_down_evaluated = True
            else:
                s_td = BAD_SCORE
                fp_td = None
                logic_cad_log(
                    "routing",
                    (
                        f"bundle order_pick skip_top_down gate UUID={format_uid_display(gate_uid)} "
                        f"bottom_up={s_bu} nearest_src={s_nf}"
                    ),
                )
            all_evals_failed = fp_bu is None and fp_td is None and fp_nf is None
            _gid = format_uid_display(gate_uid)
            logic_cad_log(
                "routing",
                (
                    f"bundle_order_candidate gate UUID={_gid} asc(IN昇順) "
                    f"cost={_fmt_bundle_eval_cost_for_log(s_bu, fp_bu is not None)} "
                    f"eval={'ok' if fp_bu is not None else 'FAIL'}"
                ),
            )
            logic_cad_log(
                "routing",
                (
                    f"bundle_order_candidate gate UUID={_gid} desc(IN降順) "
                    f"cost={_fmt_bundle_eval_cost_for_log(s_td, fp_td is not None)} "
                    f"eval={'ok' if fp_td is not None else ('SKIP' if not top_down_evaluated else 'FAIL')}"
                ),
            )
            logic_cad_log(
                "routing",
                (
                    f"bundle_order_candidate gate UUID={_gid} nearest(ソース近い順) "
                    f"cost={_fmt_bundle_eval_cost_for_log(s_nf, fp_nf is not None)} "
                    f"eval={'ok' if fp_nf is not None else 'FAIL'}"
                ),
            )
            if all_evals_failed:
                ordered_rows = list(bottom_up)
                chose_bottom_up = True
                logic_cad_log(
                    "routing",
                    (
                        f"bundle order_pick gate UUID={_gid} all_evals_failed "
                        f"bottom_up_score={s_bu} top_down_score={s_td} nearest_src_score={s_nf}"
                    ),
                )
            else:
                _candidates = (
                    (s_bu, fp_bu, bottom_up, "bottom_up"),
                    (s_td, fp_td, top_down, "top_down"),
                    (s_nf, fp_nf, near_first, "nearest_src"),
                )
                _, winner_fp, winner_seq, winner_name = min(_candidates, key=lambda t: t[0])
                ordered_rows = list(winner_seq)
                chose_bottom_up = winner_name == "bottom_up"
                logic_cad_log(
                    "routing",
                    (
                        f"bundle order_pick gate UUID={_gid} bottom_up_score={s_bu} "
                        f"top_down_score={s_td} nearest_src_score={s_nf} chose={winner_name!r}"
                    ),
                )

    with routing_perf_span("gate_input.bundle.first_pass_block"):
        bundle_wire_snapshots = [
            (entity, list(host._polyline_points(entity)))
            for entity, _wu, _su, _sp, _dp, _idx in ordered_rows
        ]

        if len(rows) > 1 and fp_bu is None and fp_td is None and fp_nf is None:
            restore_initial_pts()
            try:
                first_pass = run_pass()
            except ValueError:
                for ent, old_pts in bundle_wire_snapshots:
                    host.set_wire_points(layout_name, ent, old_pts, snap_branches=False)
                logic_cad_log(
                    "routing",
                    (
                        f"bundle order_fallback gate UUID={format_uid_display(gate_uid)} mode="
                        f"{'top_first' if chose_bottom_up else 'bottom_first'}"
                    ),
                )
                ordered_rows = list(top_down if chose_bottom_up else bottom_up)
                chose_bottom_up = not chose_bottom_up
                bundle_wire_snapshots = [
                    (entity, list(host._polyline_points(entity)))
                    for entity, _wu, _su, _sp, _dp, _idx in ordered_rows
                ]
                first_pass = run_pass()
        elif len(rows) > 1:
            restore_initial_pts()
            if winner_fp is None:
                raise RuntimeError(
                    f"ゲート束ね配線で順序は決まりましたが、評価用パスが見つかりません（内部エラー: {winner_name!r}）。"
                )
            apply_routed_paths(winner_seq, winner_fp)
            first_pass = winner_fp
            ordered_rows = list(winner_seq)
        else:
            try:
                first_pass = run_pass()
            except ValueError:
                for ent, old_pts in bundle_wire_snapshots:
                    host.set_wire_points(layout_name, ent, old_pts, snap_branches=False)
                raise
    with routing_perf_span("gate_input.bundle.analyze_first_pass"):
        first_pass_paths = [p for p in first_pass if p]
        crossing_count = _count_segment_crossings_among(first_pass_paths) if first_pass_paths else 0
        overlap_count = _count_segment_overlaps_among(first_pass_paths) if first_pass_paths else 0
        _log_vertical_parallel_overlap_diagnosis(
            first_pass_paths,
            GRID_PITCH,
            "first_pass",
            gate_uid,
            overlap_count,
        )
        symbol_overlap = has_symbol_overlap_for(first_pass_paths, ordered_rows)
        needs_cleanup = len(rows) > 1 and any(first_pass) and (
            crossing_count > 0 or overlap_count > 0 or symbol_overlap
        )
        cleanup_wire_uids: set[str] = set()
        if needs_cleanup:
            symbol_overlap_uids = _symbol_overlap_wire_uids_for(first_pass, ordered_rows)
            cleanup_wire_uids.update(symbol_overlap_uids)
            indexed_paths = [
                (row, path)
                for row, path in zip(ordered_rows, first_pass)
                if path
            ]
            for i in range(len(indexed_paths)):
                row_i, pa = indexed_paths[i]
                for j in range(i + 1, len(indexed_paths)):
                    row_j, pb = indexed_paths[j]
                    if _polylines_cross(pa, pb):
                        cleanup_wire_uids.add(row_i[1])
                        cleanup_wire_uids.add(row_j[1])
                    elif _count_segment_overlaps_among([pa, pb]) > 0:
                        cleanup_wire_uids.add(row_i[1])
                        cleanup_wire_uids.add(row_j[1])
            if not cleanup_wire_uids:
                cleanup_wire_uids = {row[1] for row in ordered_rows}
    with routing_perf_span("gate_input.bundle.cleanup_pass"):
        if needs_cleanup and routing_profile.gate_cleanup_pass:
            cleanup_rows = [
                row for row in ordered_rows if row[1] in cleanup_wire_uids
            ] or list(ordered_rows)
            logic_cad_log(
                "routing",
                (
                    f"bundle cleanup gate UUID={format_uid_display(gate_uid)} crossings={crossing_count} "
                    f"overlaps={overlap_count} symbol_overlap={symbol_overlap} "
                    f"target_rows={len(cleanup_rows)}/{len(ordered_rows)}"
                ),
            )
            snap_cleanup = [
                (entity, list(host._polyline_points(entity)))
                for entity, _wu, _su, _sp, _dp, _idx in cleanup_rows
            ]
            cleanup_seed_paths = [
                p
                for p, row in zip(first_pass, ordered_rows)
                if row[1] not in cleanup_wire_uids and p
            ]
            try:
                run_pass(
                    cleanup_seed_paths,
                    spread_pre_entry=True,
                    row_order=cleanup_rows,
                )
            except ValueError:
                logic_cad_log(
                    "routing",
                    f"bundle cleanup_failed gate UUID={format_uid_display(gate_uid)}",
                )
                for ent, old_pts in snap_cleanup:
                    host.set_wire_points(layout_name, ent, old_pts, snap_branches=False)
    with routing_perf_span("gate_input.bundle.finalize"):
        final_paths = gate_input_wire_paths(host, layout_name, gate_uid)
        final_overlap = _count_segment_overlaps_among(final_paths) if final_paths else 0
        _log_vertical_parallel_overlap_diagnosis(
            final_paths,
            GRID_PITCH,
            "after_bundle",
            gate_uid,
            final_overlap,
        )

