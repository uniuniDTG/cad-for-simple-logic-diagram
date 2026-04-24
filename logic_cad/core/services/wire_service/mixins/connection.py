from __future__ import annotations

from dataclasses import replace
from time import perf_counter

from logic_cad.core.debug.debug_log import logic_cad_log, logic_cad_log_separator
from logic_cad.core.debug.routing_perf import routing_perf_add, routing_perf_enabled, routing_perf_span
from logic_cad.core.uid_display import format_uid_display
from logic_cad.core.model.constants import ROUTE_ESCAPE_MM
from logic_cad.core.model.wire_layers import layer_for_wire_unit
from logic_cad.core.model.connection_graph import ports_compatible, resolve_wire_unit
from logic_cad.core.model.index_store import IndexStore
from logic_cad.core.model.wire_port_helpers import (
    _and_or_input_count,
    _port_index,
    _vertical_lane_from_in_port,
    wire_allows_orthogonal_cross,
    wire_skips_auto_reroute,
)
from logic_cad.core.model.xdata import build_ld_app_tags, get_type, get_uid, new_uid, read_ld_app_dict, set_entity_xdata
from logic_cad.core.obstacles import (
    build_routing_obstacles,
    build_symbol_only_routing_obstacles,
    reserved_path_obstacles,
)
from logic_cad.core.routing import (
    DEFAULT_ROUTING_PROFILE,
    RoutingProfile,
    dedupe_colinear,
    route_manhattan_with_escape,
    snap_to_grid,
)
from logic_cad.core.routing.wire_polyline_geometry import (
    MANHATTAN_EPS as _PARALLEL_MOVE_EPS,
    _is_manhattan_polyline,
)
from logic_cad.core.services.wire_service.gate_profile import _GATE_CONNECT_OPTIMIZE_PROFILE
from logic_cad.core.graph.port_src_dst_solver import (
    assert_checkpoint_wire_capacity,
    assert_ld_port_direct_wiring_rules,
)
from logic_cad.core.undo.history import find_entity_by_uid


class WireServiceConnectionMixin:
    def _auto_route_manhattan_interior_points(
        self,
        index: IndexStore,
        layout_name: str,
        src_uid: str,
        src_port: str,
        dst_uid: str,
        dst_port: str,
        p0: tuple[float, float],
        p1: tuple[float, float],
        *,
        exclude_hard_wire_uids: set[str],
        exclude_overlap_wire_uids: set[str],
        exclude_banned_wire_uids: set[str] | None,
        routing_profile: RoutingProfile | None = None,
        wire_uid: str | None = None,
    ) -> list[tuple[float, float]]:
        """Manhattan polyline from *p0* to gate pre-entry; caller appends final leg to *p1*.

        Shared by ``connect_ports`` and ``reroute_wires_touching`` so obstacle/soft/lane logic stays aligned.
        When *wire_uid* is set and that WIRE has ``allow_orthogonal_cross`` in XDATA, routing uses
        symbol-only hard obstacles only (``obstacles_relaxed``), so paths may cross existing wire hulls.
        """
        eff_profile = routing_profile or DEFAULT_ROUTING_PROFILE
        if wire_uid:
            ent = find_entity_by_uid(self.doc, wire_uid)
            if ent is not None and get_type(ent) == "WIRE" and wire_allows_orthogonal_cross(
                read_ld_app_dict(ent)
            ):
                eff_profile = replace(eff_profile, min_cost_across_wire_obstacle_passes=True)
        n_gate = _and_or_input_count(index, dst_uid)
        access_cp = {src_uid: {src_port}, dst_uid: {dst_port}}
        sym_ex = self._symbol_uids_exclude_from_routing_obstacles(src_uid, dst_uid)
        obs_relaxed = (
            build_symbol_only_routing_obstacles(
                self.doc,
                index,
                layout_name,
                sym_ex,
                access_ports=access_cp,
            )
            if eff_profile.relax_wire_hard_layers
            else None
        )
        obs = build_routing_obstacles(
            self.doc,
            index,
            layout_name,
            sym_ex,
            exclude_hard_wire_uids,
            access_ports=access_cp,
        )
        esc = index.port_first_escape_world(self.doc, src_uid, src_port, ROUTE_ESCAPE_MM, toward=p1)
        lane = _vertical_lane_from_in_port(dst_port, n_gate) if n_gate is not None else 0
        dst_target = self._gate_input_pre_entry(index, dst_uid, dst_port, toward=p0) or p1
        soft_obstacles = None
        if n_gate is not None and _port_index(dst_port) is not None:
            bundle_paths = self._gate_input_wire_paths(layout_name, dst_uid)
            if bundle_paths:
                obs = build_routing_obstacles(
                    self.doc,
                    index,
                    layout_name,
                    sym_ex,
                    {
                        wu
                        for _e, wu, d in self.iter_wire_meta(layout_name)
                        if d.get("dst") == dst_uid
                        and _port_index(d.get("dst_port") or "") is not None
                    },
                    access_ports=access_cp,
                )
                soft_obstacles = reserved_path_obstacles(bundle_paths)
        dst_facing = self._port_facing(index, dst_uid, dst_port)
        src_facing = self._port_facing(index, src_uid, src_port)
        overlap_segs = self._existing_wire_path_segments(layout_name, exclude_overlap_wire_uids)
        banned_src = self._banned_src_cardinals_for_route(
            layout_name, src_uid, src_port, exclude_wire_uids=exclude_banned_wire_uids
        )
        return route_manhattan_with_escape(
            p0,
            dst_target,
            obs,
            first_escape_src=esc,
            vertical_lane=lane,
            soft_obstacles=soft_obstacles or [],
            profile=eff_profile,
            src_facing=src_facing,
            dst_facing=dst_facing,
            obstacles_relaxed=obs_relaxed,
            existing_wire_segments=overlap_segs,
            banned_src_cardinals=banned_src,
        )

    def _coherent_parallel_move_delta(
        self,
        su: str | None,
        du: str | None,
        symbol_uids: set[str],
        symbol_move_deltas: dict[str, tuple[float, float]] | None,
    ) -> tuple[float, float] | None:
        """If both endpoints moved with the same translation, return that delta; else None."""
        if not symbol_move_deltas or not su or not du:
            return None
        if su not in symbol_uids or du not in symbol_uids:
            return None
        ds = symbol_move_deltas.get(su)
        dd = symbol_move_deltas.get(du)
        if ds is None or dd is None:
            return None
        if abs(ds[0] - dd[0]) > _PARALLEL_MOVE_EPS or abs(ds[1] - dd[1]) > _PARALLEL_MOVE_EPS:
            return None
        return ds

    def _gate_bundle_parallel_translate_delta(
        self,
        index: IndexStore,
        layout_name: str,
        gate_uid: str,
        symbol_uids: set[str],
        symbol_move_deltas: dict[str, tuple[float, float]] | None,
    ) -> tuple[float, float] | None:
        """If gate and every auto input wire's source share one translation with the gate, return it."""
        if not symbol_move_deltas or gate_uid not in symbol_uids:
            return None
        d_gate = symbol_move_deltas.get(gate_uid)
        if d_gate is None or _and_or_input_count(index, gate_uid) is None:
            return None
        found_auto = False
        for _e, _wu, d in self.iter_wire_meta(layout_name):
            if d.get("dst") != gate_uid:
                continue
            dp = d.get("dst_port") or ""
            if _port_index(dp) is None or wire_skips_auto_reroute(d):
                continue
            found_auto = True
            su = d.get("src")
            if not su or su not in symbol_uids:
                return None
            ds = symbol_move_deltas.get(su)
            if ds is None:
                return None
            if (
                abs(ds[0] - d_gate[0]) > _PARALLEL_MOVE_EPS
                or abs(ds[1] - d_gate[1]) > _PARALLEL_MOVE_EPS
            ):
                return None
        return d_gate if found_auto else None

    def connect_ports_manual(
        self,
        index: IndexStore,
        layout_name: str,
        src_uid: str,
        src_port: str,
        dst_uid: str,
        dst_port: str,
        bend_points: list[tuple[float, float]],
    ) -> str:
        """Create WIRE along user vertices (DXF mm, grid-snapped); xdata excludes wire from gate-input bundle optimization."""
        p0 = index.get_port_world(src_uid, src_port)
        p1 = index.get_port_world(dst_uid, dst_port)
        if p0 is None or p1 is None:
            raise ValueError("不明なポートです。")
        ua = index.port_unit_from_key(src_port)
        ub = index.port_unit_from_key(dst_port)
        if ua is None or ub is None:
            raise ValueError("ポートキーが不正です。")
        if not ports_compatible(ua, ub):
            raise ValueError(f"ポート種別が一致しません（{ua!r} と {ub!r}）。")
        for _e, _wu, d in self.iter_wire_meta(layout_name):
            if (
                d.get("src") == src_uid
                and d.get("src_port") == src_port
                and d.get("dst") == dst_uid
                and d.get("dst_port") == dst_port
            ):
                raise ValueError("同じポート間の配線は既に存在します")
        # Same deps snapshot for both asserts: rules are defined against one wire graph view.
        wg = self.wire_graph_deps()
        assert_checkpoint_wire_capacity(
            layout_name, src_uid, src_port, dst_uid, dst_port, deps=wg
        )
        assert_ld_port_direct_wiring_rules(
            layout_name, src_uid, src_port, dst_uid, dst_port, deps=wg
        )
        wunit = resolve_wire_unit(ua, ub)
        n_gate = _and_or_input_count(index, dst_uid)

        interior: list[tuple[float, float]] = [
            snap_to_grid(float(bx), float(by)) for bx, by in bend_points
        ]
        pts: list[tuple[float, float]] = [p0]
        for q in interior:
            if abs(pts[-1][0] - q[0]) > 1e-9 or abs(pts[-1][1] - q[1]) > 1e-9:
                pts.append(q)
        if abs(pts[-1][0] - p1[0]) > 1e-9 or abs(pts[-1][1] - p1[1]) > 1e-9:
            pts.append(p1)
        if len(pts) < 2:
            raise ValueError("配線パスが短すぎます。")
        if not _is_manhattan_polyline(pts):
            raise ValueError("マンハッタン以外の折れは使えません（水平／垂直のみ）")
        pts = dedupe_colinear(pts)

        blk = self._layout_block(layout_name)
        wire_layer = layer_for_wire_unit(wunit)
        lw = blk.add_lwpolyline(pts, dxfattribs={"layer": wire_layer})
        uid = new_uid()
        extra = {
            "unit": wunit,
            "src": src_uid,
            "src_port": src_port,
            "dst": dst_uid,
            "dst_port": dst_port,
            "skip_auto_reroute": "1",
        }
        set_entity_xdata(lw, build_ld_app_tags("1", uid, "WIRE", extra))
        index.rebuild(self.doc, layout_name)
        if n_gate is not None and _port_index(dst_port) is not None:
            self.optimize_and_or_input_ports(
                index, layout_name, dst_uid, routing_profile=_GATE_CONNECT_OPTIMIZE_PROFILE
            )
        else:
            self.recompute_all_bridges_ordered(layout_name)
        return uid

    def connect_ports(
        self,
        index: IndexStore,
        layout_name: str,
        src_uid: str,
        src_port: str,
        dst_uid: str,
        dst_port: str,
    ) -> str:
        p0 = index.get_port_world(src_uid, src_port)
        p1 = index.get_port_world(dst_uid, dst_port)
        if p0 is None or p1 is None:
            raise ValueError("不明なポートです。")
        ua = index.port_unit_from_key(src_port)
        ub = index.port_unit_from_key(dst_port)
        if ua is None or ub is None:
            raise ValueError("ポートキーが不正です。")
        if not ports_compatible(ua, ub):
            raise ValueError(f"ポート種別が一致しません（{ua!r} と {ub!r}）。")
        for _e, _wu, d in self.iter_wire_meta(layout_name):
            if (
                d.get("src") == src_uid
                and d.get("src_port") == src_port
                and d.get("dst") == dst_uid
                and d.get("dst_port") == dst_port
            ):
                raise ValueError("同じポート間の配線は既に存在します")
        # Same deps snapshot for both asserts: rules are defined against one wire graph view.
        wg = self.wire_graph_deps()
        assert_checkpoint_wire_capacity(
            layout_name, src_uid, src_port, dst_uid, dst_port, deps=wg
        )
        assert_ld_port_direct_wiring_rules(
            layout_name, src_uid, src_port, dst_uid, dst_port, deps=wg
        )
        wunit = resolve_wire_unit(ua, ub)
        n_gate = _and_or_input_count(index, dst_uid)
        if n_gate is not None and _port_index(dst_port) is not None:
            blk = self._layout_block(layout_name)
            wire_layer = layer_for_wire_unit(wunit)
            mid = (p1[0], p0[1])
            placeholder = [p0, mid, p1] if abs(p0[0] - p1[0]) > 1e-9 and abs(p0[1] - p1[1]) > 1e-9 else [p0, p1]
            lw = blk.add_lwpolyline(placeholder, dxfattribs={"layer": wire_layer})
            uid = new_uid()
            extra = {
                "unit": wunit,
                "src": src_uid,
                "src_port": src_port,
                "dst": dst_uid,
                "dst_port": dst_port,
            }
            set_entity_xdata(lw, build_ld_app_tags("1", uid, "WIRE", extra))
            index.rebuild(self.doc, layout_name)
            self.optimize_and_or_input_ports(
                index, layout_name, dst_uid, routing_profile=_GATE_CONNECT_OPTIMIZE_PROFILE
            )
            return uid
        logic_cad_log_separator(
            f"connect_ports route layout={layout_name!r} src UUID={format_uid_display(src_uid)} "
            f"dst UUID={format_uid_display(dst_uid)} ports={src_port!r}->{dst_port!r}"
        )
        # Dynamic AND/OR logic inputs use placeholder + bundle optimize above; this path is non-IN dst.
        pts = self._auto_route_manhattan_interior_points(
            index,
            layout_name,
            src_uid,
            src_port,
            dst_uid,
            dst_port,
            p0,
            p1,
            exclude_hard_wire_uids=set(),
            exclude_overlap_wire_uids=set(),
            exclude_banned_wire_uids=None,
            routing_profile=None,
        )
        pts = self._append_port_segment(pts, p1)
        pts = self._normalize_auto_route_points(pts, p0, p1)
        blk = self._layout_block(layout_name)
        wire_layer = layer_for_wire_unit(wunit)
        lw = blk.add_lwpolyline(pts, dxfattribs={"layer": wire_layer})
        uid = new_uid()
        extra = {
            "unit": wunit,
            "src": src_uid,
            "src_port": src_port,
            "dst": dst_uid,
            "dst_port": dst_port,
        }
        set_entity_xdata(lw, build_ld_app_tags("1", uid, "WIRE", extra))
        self.recompute_all_bridges_ordered(layout_name)
        return uid

    def reroute_wires_touching(
        self,
        index: IndexStore,
        layout_name: str,
        symbol_uids: set[str],
        routing_profile: RoutingProfile | None = None,
        symbol_move_deltas: dict[str, tuple[float, float]] | None = None,
    ) -> bool:
        """Rebuild geometry for wires whose src or dst is in symbol_uids.

        Returns False if any incident wire kept old geometry due to routing failure, any gate bundle
        optimize failed, or ports were missing for a wire that should have been rerouted.
        """
        routing_profile = routing_profile or DEFAULT_ROUTING_PROFILE
        if not symbol_uids:
            return True
        ok = True
        sym_disp = ",".join(format_uid_display(u) for u in sorted(symbol_uids))
        logic_cad_log_separator(
            f"reroute wires touching layout={layout_name!r} symbols UUID=[{sym_disp}]"
        )
        perf = routing_perf_enabled()
        t_inc_par = 0.0
        t_inc_auto = 0.0
        gate_uids: set[str] = set()
        for e, wu, d in list(self.iter_wire_meta(layout_name)):
            su, du = d.get("src"), d.get("dst")
            if su not in symbol_uids and du not in symbol_uids:
                continue
            sp, dp = d.get("src_port"), d.get("dst_port")
            if not sp or not dp:
                ok = False
                continue
            n_gate = _and_or_input_count(index, du) if du else None
            if (
                n_gate is not None
                and _port_index(dp) is not None
                and not wire_skips_auto_reroute(d)
            ):
                gate_uids.add(du)
                continue
            p0 = index.get_port_world(su, sp)
            p1 = index.get_port_world(du, dp)
            if p0 is None or p1 is None:
                ok = False
                continue
            pd = self._coherent_parallel_move_delta(su, du, symbol_uids, symbol_move_deltas)
            if pd is not None:
                t0 = perf_counter() if perf else 0.0
                dx, dy = pd
                old_pts = self._polyline_points(e)
                shifted = [(float(x) + dx, float(y) + dy) for x, y in old_pts]
                shifted = self._normalize_auto_route_points(shifted, p0, p1)
                self.set_wire_points(layout_name, e, shifted, snap_branches=False)
                if perf:
                    t_inc_par += perf_counter() - t0
                continue
            ex_w = {wu} if wu else set()
            t0 = perf_counter() if perf else 0.0
            try:
                pts = self._auto_route_manhattan_interior_points(
                    index,
                    layout_name,
                    su,
                    sp,
                    du,
                    dp,
                    p0,
                    p1,
                    exclude_hard_wire_uids=ex_w,
                    exclude_overlap_wire_uids=ex_w,
                    exclude_banned_wire_uids={wu} if wu else None,
                    routing_profile=routing_profile,
                    wire_uid=wu,
                )
            except ValueError:
                if perf:
                    t_inc_auto += perf_counter() - t0
                logic_cad_log("routing", f"reroute failed wire UUID={format_uid_display(wu)}")
                ok = False
                continue
            new_final = self._append_port_segment(pts, p1)
            new_final = self._normalize_auto_route_points(new_final, p0, p1)
            self.set_wire_points(layout_name, e, new_final, snap_branches=False)
            if perf:
                t_inc_auto += perf_counter() - t0
        if perf:
            routing_perf_add("reroute.incident.parallel_shift", t_inc_par)
            routing_perf_add("reroute.incident.auto_route", t_inc_auto)
        gates_to_optimize: list[str] = []
        t_gpar = 0.0
        for gate_uid in sorted(gate_uids):
            t0 = perf_counter() if perf else 0.0
            bd = self._gate_bundle_parallel_translate_delta(
                index, layout_name, gate_uid, symbol_uids, symbol_move_deltas
            )
            if bd is not None:
                dx, dy = bd
                for e2, _wu2, d2 in list(self.iter_wire_meta(layout_name)):
                    if d2.get("dst") != gate_uid:
                        continue
                    dp2 = d2.get("dst_port") or ""
                    if _port_index(dp2) is None or wire_skips_auto_reroute(d2):
                        continue
                    su2 = d2.get("src")
                    sp2 = d2.get("src_port")
                    du2 = d2.get("dst")
                    if not su2 or not sp2 or not du2:
                        continue
                    p0_2 = index.get_port_world(su2, sp2)
                    p1_2 = index.get_port_world(du2, dp2)
                    if p0_2 is None or p1_2 is None:
                        continue
                    old_pts = self._polyline_points(e2)
                    shifted = [(float(x) + dx, float(y) + dy) for x, y in old_pts]
                    shifted = self._normalize_auto_route_points(shifted, p0_2, p1_2)
                    self.set_wire_points(layout_name, e2, shifted, snap_branches=False)
            else:
                gates_to_optimize.append(gate_uid)
            if perf:
                t_gpar += perf_counter() - t0
        if perf:
            routing_perf_add("reroute.gate.parallel_bundle", t_gpar)
        for gate_uid in gates_to_optimize:
            t0 = perf_counter() if perf else 0.0
            try:
                bundle_ok = self.optimize_and_or_input_ports(
                    index, layout_name, gate_uid, routing_profile=_GATE_CONNECT_OPTIMIZE_PROFILE
                )
            except ValueError:
                logic_cad_log(
                    "routing",
                    f"gate bundle reroute ValueError gate UUID={format_uid_display(gate_uid)}",
                )
                bundle_ok = False
            finally:
                if perf:
                    routing_perf_add("reroute.gate.optimize_bundle", perf_counter() - t0)
            if not bundle_ok:
                ok = False
                with routing_perf_span("reroute.gate.optimize_failure_index_rebuild"):
                    index.rebuild(self.doc, layout_name)
                n_fb = _and_or_input_count(index, gate_uid)
                if n_fb is not None:
                    ordered_fb = self._gate_input_wire_rows_in_order(layout_name, gate_uid, n_fb)
                    if (
                        _GATE_CONNECT_OPTIMIZE_PROFILE.enable_and_or_crossing_swaps
                        and self._ordered_gate_inputs_allow_crossing_swaps(ordered_fb)
                    ):
                        with routing_perf_span("reroute.gate.crossing_swaps"):
                            self._optimize_and_or_crossing_swaps(index, layout_name, gate_uid, n_fb)
        with routing_perf_span("reroute.bridges"):
            self.recompute_all_bridges_ordered(layout_name)
        logic_cad_log(
            "routing",
            f"reroute_wires_touching done layout={layout_name!r} ok={ok}",
        )
        return ok
