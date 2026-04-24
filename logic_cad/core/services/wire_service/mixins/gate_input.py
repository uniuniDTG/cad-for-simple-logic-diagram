from __future__ import annotations

from dataclasses import replace
from time import perf_counter

from logic_cad.core.debug.debug_log import (
    logic_cad_debug_routing_verbose,
    logic_cad_log,
    logic_cad_log_separator,
)
from logic_cad.core.debug.routing_perf import routing_perf_add, routing_perf_enabled, routing_perf_span
from logic_cad.core.uid_display import format_uid_display
from logic_cad.core.model.constants import (
    GRID_PITCH,
    ROUTE_ESCAPE_MM,
    ROUTING_MIN_WIRE_SEPARATION_MM,
)
from logic_cad.core.model.index_store import IndexStore
from logic_cad.core.model.wire_port_helpers import (
    _and_or_input_count,
    _port_index,
    wire_allows_orthogonal_cross,
    wire_skips_auto_reroute,
)
from logic_cad.core.model.xdata import build_ld_app_tags, get_uid, read_ld_app_dict, set_entity_xdata
from logic_cad.core.obstacles import (
    build_routing_obstacles,
    build_symbol_only_routing_obstacles,
    reserved_path_obstacles,
    symbol_obstacles,
    wire_obstacles,
)
from logic_cad.core.routing import (
    DEFAULT_ROUTING_PROFILE,
    RoutingProfile,
    path_hits_obstacles,
    route_manhattan_with_escape,
)
from logic_cad.core.routing.polyline import polyline_segments
from logic_cad.core.routing.wire_path_metrics import (
    _count_segment_crossings_among,
    _count_segment_overlaps_among,
    _log_vertical_parallel_overlap_diagnosis,
    _polylines_cross,
)


def _fmt_pt(pt: tuple[float, float]) -> str:
    return f"({pt[0]:.1f},{pt[1]:.1f})"


def _routing_profile_summary(p: RoutingProfile) -> str:
    return (
        f"fixed={p.use_fixed_manhattan} ovg_multi={p.use_ovg_multi} "
        f"relax_hard={p.relax_wire_hard_layers} cleanup={p.gate_cleanup_pass} "
        f"swaps={p.enable_and_or_crossing_swaps} max_states={p.max_search_states}"
    )


def _bundle_penalty_score(score: tuple[int, int, int, float]) -> tuple[int, int, int]:
    """Return penalty components used for bundle order pruning.

    Args:
        score: Bundle evaluation score tuple.

    Returns:
        Crossing/overlap/symbol-overlap tuple.
    """
    return score[0], score[1], score[2]


def _is_perfect_bundle_score(score: tuple[int, int, int, float]) -> bool:
    """Check whether a bundle score is conflict-free.

    Args:
        score: Bundle evaluation score tuple.

    Returns:
        ``True`` when crossings/overlaps/symbol-overlap are all zero.
    """
    return _bundle_penalty_score(score) == (0, 0, 0)


class WireServiceGateInputMixin:
    def wire_uses_input_port(self, layout_name: str, gate_uid: str, port_key: str) -> bool:
        for _e, _wu, d in self.iter_wire_meta(layout_name):
            if d.get("dst") == gate_uid and d.get("dst_port") == port_key:
                return True
        return False

    def all_and_inputs_wired(self, layout_name: str, gate_uid: str, n_inputs: int) -> bool:
        for i in range(n_inputs):
            pk = f"IN{i}_LOGIC"
            if not self.wire_uses_input_port(layout_name, gate_uid, pk):
                return False
        return True

    def first_free_and_input(self, layout_name: str, gate_uid: str, n_inputs: int) -> str | None:
        for i in range(n_inputs):
            pk = f"IN{i}_LOGIC"
            if not self.wire_uses_input_port(layout_name, gate_uid, pk):
                return pk
        return None

    def _gate_input_rows_all(
        self, layout_name: str, gate_uid: str
    ) -> list[tuple[object, str, str, str, str, int]]:
        """Every WIRE into *gate_uid* logic inputs."""
        rows: list[tuple[object, str, str, str, str, int]] = []
        for e, wu, d in self.iter_wire_meta(layout_name):
            if d.get("dst") != gate_uid:
                continue
            dp = d.get("dst_port") or ""
            idx = _port_index(dp)
            if idx is None:
                continue
            su, sp = d.get("src"), d.get("src_port")
            if not su or not sp:
                continue
            rows.append((e, wu, su, sp, dp, idx))
        return rows

    def _gate_input_rows(
        self, layout_name: str, gate_uid: str
    ) -> list[tuple[object, str, str, str, str, int]]:
        """Gate-input bundle rows (same as all rows into logic inputs)."""
        return self._gate_input_rows_all(layout_name, gate_uid)

    def _assign_gate_input_ports_by_source_order(
        self,
        index: IndexStore,
        layout_name: str,
        gate_uid: str,
        rows: list[tuple[object, str, str, str, str, int]],
        n_inputs: int,
        reserved_indices: set[int],
    ) -> list[tuple[object, str, str, str, str, int]] | None:
        """Map auto wires to IN* ports using free slots only (skip manual wires' IN indices).

        Sources with OUT west of the gate input cluster (min IN world X) keep monotonic
        Y matching: lowest source Y to lowest free IN port Y, etc. Sources east of that
        reference use only extreme free ports (bottom/top in world Y), with interior wires
        consuming remaining free slots if more than two wrap-around connections exist.
        """
        _ = layout_name

        def _in_port_y(slot: int) -> float:
            ipw = index.get_port_world(gate_uid, f"IN{slot}_LOGIC")
            return float(ipw[1]) if ipw is not None else float(slot)

        free_slots = [i for i in range(n_inputs) if i not in reserved_indices]
        in_x_coords: list[float] = []
        for k in range(n_inputs):
            ipw = index.get_port_world(gate_uid, f"IN{k}_LOGIC")
            if ipw is not None:
                in_x_coords.append(ipw[0])
        if not in_x_coords:
            return None
        ref_x = min(in_x_coords)

        ranked: list[tuple[float, float, tuple[object, str, str, str, str, int]]] = []
        for r in rows:
            pw = index.get_port_world(r[2], r[3])
            if pw is None:
                continue
            ranked.append((pw[1], pw[0], r))
        if len(ranked) > len(free_slots):
            logic_cad_log(
                "routing",
                (
                    f"gate assign skip gate UUID={format_uid_display(gate_uid)}: need {len(ranked)} IN slots for auto wires "
                    f"but only {len(free_slots)} free (n={n_inputs} reserved={sorted(reserved_indices)})"
                ),
            )
            return None

        free_by_y = sorted(free_slots, key=_in_port_y)
        left_side: list[tuple[float, float, tuple[object, str, str, str, str, int]]] = []
        right_side: list[tuple[float, float, tuple[object, str, str, str, str, int]]] = []
        for t in ranked:
            src_x = t[1]
            if src_x <= ref_x + 1e-9:
                left_side.append(t)
            else:
                right_side.append(t)
        left_side.sort(key=lambda t: (t[0], t[1]))
        right_side.sort(key=lambda t: (t[0], t[1]))

        slot_for_wire: dict[str, int] = {}
        used_slots: set[int] = set()

        bottom_slot = free_by_y[0]
        top_slot = free_by_y[-1]

        if right_side:
            if len(free_by_y) == 1:
                only = free_by_y[0]
                if len(right_side) > 1:
                    logic_cad_log(
                        "routing",
                        (
                            f"gate assign skip gate UUID={format_uid_display(gate_uid)}: {len(right_side)} wrap wires "
                            f"but only one free IN slot"
                        ),
                    )
                    return None
                slot_for_wire[right_side[0][2][1]] = only
                used_slots.add(only)
            elif len(right_side) == 1:
                ry, _, rr = right_side[0]
                yb, yt = _in_port_y(bottom_slot), _in_port_y(top_slot)
                pick = (
                    bottom_slot
                    if abs(ry - yb) <= abs(ry - yt) + 1e-9
                    else top_slot
                )
                slot_for_wire[rr[1]] = pick
                used_slots.add(pick)
            else:
                lo_t = right_side[0]
                hi_t = right_side[-1]
                slot_for_wire[lo_t[2][1]] = bottom_slot
                used_slots.add(bottom_slot)
                if hi_t[2][1] != lo_t[2][1]:
                    slot_for_wire[hi_t[2][1]] = top_slot
                    if top_slot != bottom_slot:
                        used_slots.add(top_slot)
                mid = right_side[1:-1]
                pool = sorted(
                    [s for s in free_by_y if s not in used_slots],
                    key=_in_port_y,
                )
                mid_sorted = sorted(mid, key=lambda t: (t[0], t[1]))
                if len(mid_sorted) > len(pool):
                    logic_cad_log(
                        "routing",
                        (
                            f"gate assign skip gate UUID={format_uid_display(gate_uid)}: wrap bundle needs "
                            f"{len(mid_sorted)} extra IN slots but only {len(pool)} remain"
                        ),
                    )
                    return None
                for t, sl in zip(mid_sorted, pool):
                    slot_for_wire[t[2][1]] = sl
                    used_slots.add(sl)

        pool_left = sorted(
            [s for s in free_by_y if s not in used_slots],
            key=_in_port_y,
        )
        if len(left_side) > len(pool_left):
            logic_cad_log(
                "routing",
                (
                    f"gate assign skip gate UUID={format_uid_display(gate_uid)}: left_slots={len(pool_left)} "
                    f"left_wires={len(left_side)} (not enough after wrap assignment)"
                ),
            )
            return None
        # Fewer left wires than free INs (e.g. AND_2 with one auto wire): use the
        # lowest-Y free ports so IN0 is preferred when it is the bottom input.
        chosen_left = pool_left[: len(left_side)]
        for t, sl in zip(left_side, chosen_left):
            slot_for_wire[t[2][1]] = sl

        out: list[tuple[object, str, str, str, str, int]] = []
        for _y, _x, r in sorted(ranked, key=lambda t: (t[0], t[1])):
            entity = r[0]
            slot = slot_for_wire[r[1]]
            new_port = f"IN{slot}_LOGIC"
            e, wu = r[0], r[1]
            if r[4] != new_port:
                d = dict(read_ld_app_dict(e))
                d["dst_port"] = new_port
                set_entity_xdata(e, build_ld_app_tags("1", wu, "WIRE", d))
            out.append((e, wu, r[2], r[3], new_port, slot))
        return out

    def _route_gate_input_rows(
        self,
        index: IndexStore,
        layout_name: str,
        gate_uid: str,
        n_inputs: int,
        rows: list[tuple[object, str, str, str, str, int]],
        routing_profile: RoutingProfile | None = None,
    ) -> None:
        routing_profile = routing_profile or DEFAULT_ROUTING_PROFILE
        if not rows:
            return
        perf = routing_perf_enabled()
        logic_cad_log(
            "routing",
            (
                f"bundle start gate UUID={format_uid_display(gate_uid)} layout={layout_name!r} "
                f"profile({_routing_profile_summary(routing_profile)})"
            ),
        )
        with routing_perf_span("gate_input.bundle.setup"):
            index.rebuild(self.doc, layout_name)
            exclude_wire_uids = {r[1] for r in rows}
            base_soft_obstacles = wire_obstacles(
                self.doc, layout_name, exclude_wire_uids=exclude_wire_uids, index=index
            )
            # For bundle passes, hard wire obstacles are identical to this base set.
            base_wire_hard_obstacles = list(base_soft_obstacles)
            # Non-bundle segments are invariant during candidate evaluation/cleanup.
            non_bundle_segments_by_wire_uid: dict[
                str, list[tuple[tuple[float, float], tuple[float, float]]]
            ] = {}
            for ent, wu2, _d2 in self.iter_wire_meta(layout_name):
                if not wu2 or wu2 in exclude_wire_uids:
                    continue
                non_bundle_segments_by_wire_uid[wu2] = polyline_segments(
                    self._polyline_points(ent)
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
                (r[0], list(self._polyline_points(r[0]))) for r in rows
            ]

        def restore_initial_pts() -> None:
            for ent, pts in initial_snapshot:
                self.set_wire_points(layout_name, ent, pts, snap_branches=False)

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
                        self.doc,
                        index,
                        self._symbol_uids_exclude_from_routing_obstacles(su, gate_uid),
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
                        self.doc,
                        index,
                        self._symbol_uids_exclude_from_routing_obstacles(su, gate_uid),
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
                dst_target = self._gate_input_pre_entry(index, gate_uid, dp, toward=p0, extra_offset_mm=pre_entry_offset) or p1
                esc = index.port_first_escape_world(self.doc, su, sp, ROUTE_ESCAPE_MM, toward=p1)
                if spread_pre_entry:
                    esc = self._spread_escape_point(
                        p0,
                        esc,
                        ROUTING_MIN_WIRE_SEPARATION_MM * _idx,
                    )
                lane = 0
                access_ports = {su: {sp}, gate_uid: {dp}}
                sym_ex = symbol_exclude_cache.get(su)
                if sym_ex is None:
                    sym_ex = self._symbol_uids_exclude_from_routing_obstacles(su, gate_uid)
                    symbol_exclude_cache[su] = set(sym_ex)
                key = (su, sp, dp)
                soft_obstacles = list(base_soft_obstacles) + list(seeded_soft)
                pair_soft = pair_soft_obstacles_cache.get(key)
                if pair_soft is None:
                    pair_soft = self._pair_symbol_soft_obstacles(
                        index, su, gate_uid, access_ports
                    )
                    pair_soft_obstacles_cache[key] = list(pair_soft)
                soft_obstacles.extend(pair_soft)
                dst_facing_key = (gate_uid, dp)
                dst_facing = port_facing_cache.get(dst_facing_key)
                if dst_facing_key not in port_facing_cache:
                    dst_facing = self._port_facing(index, gate_uid, dp)
                    port_facing_cache[dst_facing_key] = dst_facing
                src_facing_key = (su, sp)
                src_facing = port_facing_cache.get(src_facing_key)
                if src_facing_key not in port_facing_cache:
                    src_facing = self._port_facing(index, su, sp)
                    port_facing_cache[src_facing_key] = src_facing
                hard_symbol = hard_symbol_obstacles_cache.get(key)
                if hard_symbol is None:
                    hard_symbol = build_symbol_only_routing_obstacles(
                        self.doc,
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
                            f"p0={_fmt_pt(p0)} target={_fmt_pt(dst_target)} "
                            f"escape={_fmt_pt(esc) if esc is not None else 'None'} "
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
                    banned_src = self._banned_src_cardinals_for_route(
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
                pts = route_manhattan_with_escape(
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
                final_pts = self._append_port_segment(pts, p1)
                final_pts = self._normalize_auto_route_points(final_pts, p0, p1)
                self.set_wire_points(layout_name, entity, final_pts, snap_branches=False)
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
                    wire_len += abs(bx - ax) + abs(by - ay)
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
                    self.set_wire_points(layout_name, ent, pts, snap_branches=False)

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
            pen_bu = _bundle_penalty_score(score_bu)
            pen_nf = _bundle_penalty_score(score_nf)
            if pen_bu == pen_nf:
                return True
            if _is_perfect_bundle_score(score_bu) or _is_perfect_bundle_score(score_nf):
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
                (entity, list(self._polyline_points(entity)))
                for entity, _wu, _su, _sp, _dp, _idx in ordered_rows
            ]

            if len(rows) > 1 and fp_bu is None and fp_td is None and fp_nf is None:
                restore_initial_pts()
                try:
                    first_pass = run_pass()
                except ValueError:
                    for ent, old_pts in bundle_wire_snapshots:
                        self.set_wire_points(layout_name, ent, old_pts, snap_branches=False)
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
                        (entity, list(self._polyline_points(entity)))
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
                        self.set_wire_points(layout_name, ent, old_pts, snap_branches=False)
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
                    (entity, list(self._polyline_points(entity)))
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
                        self.set_wire_points(layout_name, ent, old_pts, snap_branches=False)
        with routing_perf_span("gate_input.bundle.finalize"):
            final_paths = self._gate_input_wire_paths(layout_name, gate_uid)
            final_overlap = _count_segment_overlaps_among(final_paths) if final_paths else 0
            _log_vertical_parallel_overlap_diagnosis(
                final_paths,
                GRID_PITCH,
                "after_bundle",
                gate_uid,
                final_overlap,
            )

    def _gate_input_wire_paths(
        self,
        layout_name: str,
        gate_uid: str,
        exclude_wire_uids: set[str] | None = None,
    ) -> list[list[tuple[float, float]]]:
        excluded = exclude_wire_uids or set()
        paths: list[list[tuple[float, float]]] = []
        for entity, wu, data in self.iter_wire_meta(layout_name):
            if wu in excluded:
                continue
            if data.get("dst") != gate_uid:
                continue
            if _port_index(data.get("dst_port") or "") is None:
                continue
            paths.append(self._polyline_points(entity))
        return paths

    def _reroute_gate_input_wire(
        self,
        index: IndexStore,
        layout_name: str,
        entity,
        n_inputs: int,
        routing_profile: RoutingProfile | None = None,
    ) -> None:
        routing_profile = routing_profile or DEFAULT_ROUTING_PROFILE
        d = read_ld_app_dict(entity)
        if wire_allows_orthogonal_cross(d):
            routing_profile = replace(
                routing_profile, min_cost_across_wire_obstacle_passes=True
            )
        su, du = d.get("src"), d.get("dst")
        sp, dp = d.get("src_port"), d.get("dst_port")
        wu = get_uid(entity)
        if not su or not du or not sp or not dp or not wu:
            return
        p0 = index.get_port_world(su, sp)
        p1 = index.get_port_world(du, dp)
        if p0 is None or p1 is None:
            return
        dst_target = self._gate_input_pre_entry(index, du, dp, toward=p0) or p1
        access_ports = {su: {sp}, du: {dp}}
        sym_ex = self._symbol_uids_exclude_from_routing_obstacles(su, du)
        obs_relaxed = (
            build_symbol_only_routing_obstacles(
                self.doc,
                index,
                layout_name,
                sym_ex,
                access_ports=access_ports,
                symbol_margin=0.0,
            )
            if routing_profile.relax_wire_hard_layers
            else None
        )
        obs2 = build_routing_obstacles(
            self.doc,
            index,
            layout_name,
            sym_ex,
            {wu},
            access_ports=access_ports,
            symbol_margin=0.0,
        )
        esc = index.port_first_escape_world(self.doc, su, sp, ROUTE_ESCAPE_MM, toward=p1)
        lane = 0
        soft_obstacles = self._pair_symbol_soft_obstacles(index, su, du, access_ports)
        dst_facing = self._port_facing(index, du, dp)
        src_facing = self._port_facing(index, su, sp)
        overlap_segs = self._existing_wire_path_segments(layout_name, {wu} if wu else set())
        banned_src = self._banned_src_cardinals_for_route(
            layout_name, su, sp, exclude_wire_uids={wu} if wu else None
        )
        pts = route_manhattan_with_escape(
            p0,
            dst_target,
            obs2,
            first_escape_src=esc,
            vertical_lane=lane,
            soft_obstacles=soft_obstacles,
            profile=routing_profile,
            src_facing=src_facing,
            dst_facing=dst_facing,
            obstacles_relaxed=obs_relaxed,
            existing_wire_segments=overlap_segs,
            banned_src_cardinals=banned_src,
        )
        new_final = self._append_port_segment(pts, p1)
        new_final = self._normalize_auto_route_points(new_final, p0, p1)
        self.set_wire_points(layout_name, entity, new_final, snap_branches=False)

    def _gate_input_wire_rows_in_order(
        self, layout_name: str, gate_uid: str, n: int
    ) -> list[tuple[object, str, str, str, str, int]] | None:
        rows = self._gate_input_rows_all(layout_name, gate_uid)
        if len(rows) != n:
            return None
        if {r[5] for r in rows} != set(range(n)):
            return None
        return sorted(rows, key=lambda r: r[5])

    def _ordered_gate_inputs_allow_crossing_swaps(
        self, ordered: list[tuple[object, str, str, str, str, int]] | None
    ) -> bool:
        if ordered is None:
            return False
        for r in ordered:
            ent = r[0]
            d = read_ld_app_dict(ent)
            if wire_skips_auto_reroute(d):
                return False
        return True

    def _optimize_and_or_crossing_swaps(
        self,
        index: IndexStore,
        layout_name: str,
        gate_uid: str,
        n: int,
    ) -> None:
        max_rounds = max(n, 1)
        any_swap = False
        for _ in range(max_rounds):
            ordered = self._gate_input_wire_rows_in_order(layout_name, gate_uid, n)
            if ordered is None:
                return
            pts_list = [self._polyline_points(r[0]) for r in ordered]
            total_before = _count_segment_crossings_among(pts_list)
            if total_before == 0:
                break
            improved = False
            for i in range(n):
                for j in range(i + 1, n):
                    if not _polylines_cross(pts_list[i], pts_list[j]):
                        continue
                    e_i, e_j = ordered[i][0], ordered[j][0]
                    w_i, w_j = get_uid(e_i), get_uid(e_j)
                    if not w_i or not w_j:
                        continue
                    d_i = dict(read_ld_app_dict(e_i))
                    d_j = dict(read_ld_app_dict(e_j))
                    pi, pj = d_i["dst_port"], d_j["dst_port"]
                    old_pts_i = list(self._polyline_points(e_i))
                    old_pts_j = list(self._polyline_points(e_j))
                    d_i["dst_port"] = pj
                    d_j["dst_port"] = pi
                    set_entity_xdata(e_i, build_ld_app_tags("1", w_i, "WIRE", d_i))
                    set_entity_xdata(e_j, build_ld_app_tags("1", w_j, "WIRE", d_j))
                    index.rebuild(self.doc, layout_name)
                    try:
                        self._reroute_gate_input_wire(index, layout_name, e_i, n)
                        self._reroute_gate_input_wire(index, layout_name, e_j, n)
                    except ValueError:
                        d_i["dst_port"] = pi
                        d_j["dst_port"] = pj
                        set_entity_xdata(e_i, build_ld_app_tags("1", w_i, "WIRE", d_i))
                        set_entity_xdata(e_j, build_ld_app_tags("1", w_j, "WIRE", d_j))
                        index.rebuild(self.doc, layout_name)
                        self.set_wire_points(layout_name, e_i, old_pts_i)
                        self.set_wire_points(layout_name, e_j, old_pts_j)
                        continue
                    pts_trial = [self._polyline_points(ordered[k][0]) for k in range(n)]
                    total_after = _count_segment_crossings_among(pts_trial)
                    if total_after < total_before:
                        improved = True
                        any_swap = True
                        ordered[i], ordered[j] = ordered[j], ordered[i]
                        break
                    d_i["dst_port"] = pi
                    d_j["dst_port"] = pj
                    set_entity_xdata(e_i, build_ld_app_tags("1", w_i, "WIRE", d_i))
                    set_entity_xdata(e_j, build_ld_app_tags("1", w_j, "WIRE", d_j))
                    index.rebuild(self.doc, layout_name)
                    self.set_wire_points(layout_name, e_i, old_pts_i)
                    self.set_wire_points(layout_name, e_j, old_pts_j)
                if improved:
                    break
            if not improved:
                break
        if any_swap:
            self.recompute_all_bridges_ordered(layout_name)

    def optimize_and_or_input_ports(
        self,
        index: IndexStore,
        layout_name: str,
        gate_uid: str,
        routing_profile: RoutingProfile | None = None,
    ) -> bool:
        """Assign connected inputs in source order, then route the whole gate input bundle together."""
        routing_profile = routing_profile or DEFAULT_ROUTING_PROFILE
        perf = routing_perf_enabled()
        n = _and_or_input_count(index, gate_uid)
        if n is None:
            return False

        rows = self._gate_input_rows(layout_name, gate_uid)
        if not rows:
            return False

        auto_rows = [r for r in rows if not wire_skips_auto_reroute(read_ld_app_dict(r[0]))]
        if not auto_rows:
            with routing_perf_span("gate_input.optimize.bridges_auto_rows_empty"):
                self.recompute_all_bridges_ordered(layout_name)
            return True

        with routing_perf_span("gate_input.optimize.prepare"):
            reserved_indices: set[int] = set()
            for entity, _wu, _su, _sp, dp, _idx in rows:
                if not wire_skips_auto_reroute(read_ld_app_dict(entity)):
                    continue
                pi = _port_index(dp)
                if pi is not None:
                    reserved_indices.add(pi)

            logic_cad_log_separator(
                f"gate input bundle gate UUID={format_uid_display(gate_uid)} layout={layout_name!r} rows={len(rows)} "
                f"auto_rows={len(auto_rows)} reserved_IN={sorted(reserved_indices)}"
            )

            backup: list[tuple[object, str, dict, list[tuple[float, float]]]] = []
            translate_snapshot: dict[
                str,
                tuple[
                    object,
                    list[tuple[float, float]],
                    str,
                    tuple[float, float],
                    tuple[float, float],
                ],
            ] = {}
            for entity, wu, _su, _sp, _dp, _idx in auto_rows:
                old_src = index.get_port_world(_su, _sp)
                old_dst = index.get_port_world(gate_uid, _dp)
                if old_src is not None and old_dst is not None:
                    translate_snapshot[wu] = (
                        entity,
                        list(self._polyline_points(entity)),
                        _dp,
                        (float(old_src[0]), float(old_src[1])),
                        (float(old_dst[0]), float(old_dst[1])),
                    )
                backup.append(
                    (entity, wu, dict(read_ld_app_dict(entity)), list(self._polyline_points(entity)))
                )

        t_asn = perf_counter() if perf else 0.0
        assigned = self._assign_gate_input_ports_by_source_order(
            index, layout_name, gate_uid, auto_rows, n, reserved_indices
        )
        if perf:
            routing_perf_add("gate_input.optimize.assign_ports", perf_counter() - t_asn)
        if assigned is None:
            with routing_perf_span("gate_input.optimize.bridges_assign_failed"):
                self.recompute_all_bridges_ordered(layout_name)
            return False
        with routing_perf_span("gate_input.optimize.index_rebuild_after_assign"):
            index.rebuild(self.doc, layout_name)
        rows_to_reroute: list[tuple[object, str, str, str, str, int]] = []
        translated_count = 0
        for row in assigned:
            entity, wu, su, sp, dp, _idx = row
            snap = translate_snapshot.get(wu)
            if snap is None:
                rows_to_reroute.append(row)
                continue
            snap_entity, old_pts, old_dp, _old_src, _old_dst = snap
            if snap_entity is not entity or old_dp != dp:
                rows_to_reroute.append(row)
                continue
            if len(old_pts) < 2:
                rows_to_reroute.append(row)
                continue
            new_src = index.get_port_world(su, sp)
            new_dst = index.get_port_world(gate_uid, dp)
            if new_src is None or new_dst is None:
                rows_to_reroute.append(row)
                continue
            dx_src = float(new_src[0]) - float(old_pts[0][0])
            dy_src = float(new_src[1]) - float(old_pts[0][1])
            dx_dst = float(new_dst[0]) - float(old_pts[-1][0])
            dy_dst = float(new_dst[1]) - float(old_pts[-1][1])
            if abs(dx_src - dx_dst) > 1e-9 or abs(dy_src - dy_dst) > 1e-9:
                rows_to_reroute.append(row)
                continue
            shifted = [(float(x) + dx_src, float(y) + dy_src) for x, y in old_pts]
            normalized = self._normalize_auto_route_points(
                shifted,
                (float(new_src[0]), float(new_src[1])),
                (float(new_dst[0]), float(new_dst[1])),
            )
            self.set_wire_points(layout_name, entity, normalized, snap_branches=False)
            translated_count += 1
        if translated_count > 0:
            logic_cad_log(
                "routing",
                (
                    f"gate input partial_translate gate UUID={format_uid_display(gate_uid)} "
                    f"translated={translated_count} reroute={len(rows_to_reroute)}"
                ),
            )
        if translated_count > 1:
            translated_paths: list[list[tuple[float, float]]] = []
            for ent, _wu, _su, _sp, _dp, _idx in assigned:
                translated_paths.append(self._polyline_points(ent))
            translated_overlap = _count_segment_overlaps_among(translated_paths)
            translated_cross = _count_segment_crossings_among(translated_paths)
            if translated_overlap > 0 or translated_cross > 0:
                rows_to_reroute = list(assigned)
                logic_cad_log(
                    "routing",
                    (
                        f"gate input partial_translate fallback_full_reroute "
                        f"gate UUID={format_uid_display(gate_uid)} overlaps={translated_overlap} "
                        f"crossings={translated_cross}"
                    ),
                )
        try:
            if rows_to_reroute:
                self._route_gate_input_rows(
                    index,
                    layout_name,
                    gate_uid,
                    n,
                    rows_to_reroute,
                    routing_profile=routing_profile,
                )
        except ValueError:
            logic_cad_log(
                "routing",
                f"gate bundle route failed; restoring auto_rows gate UUID={format_uid_display(gate_uid)}",
            )
            with routing_perf_span("gate_input.optimize.restore_on_route_failure"):
                for entity, wu, old_d, old_pts in backup:
                    set_entity_xdata(entity, build_ld_app_tags("1", wu, "WIRE", old_d))
                    self.set_wire_points(layout_name, entity, old_pts)
                index.rebuild(self.doc, layout_name)
            with routing_perf_span("gate_input.optimize.bridges_after_route_failure"):
                self.recompute_all_bridges_ordered(layout_name)
            return False
        with routing_perf_span("gate_input.optimize.post_route_ordered"):
            ordered = self._gate_input_wire_rows_in_order(layout_name, gate_uid, n)
        if (
            routing_profile.enable_and_or_crossing_swaps
            and self._ordered_gate_inputs_allow_crossing_swaps(ordered)
        ):
            with routing_perf_span("gate_input.optimize.index_rebuild_before_crossing_swaps"):
                index.rebuild(self.doc, layout_name)
            with routing_perf_span("gate_input.optimize.crossing_swaps"):
                self._optimize_and_or_crossing_swaps(index, layout_name, gate_uid, n)
        with routing_perf_span("gate_input.optimize.bridges_success"):
            self.recompute_all_bridges_ordered(layout_name)
        return True
