"""AND/OR gate input port optimization: assign, translate shortcut, bundle route, swaps."""

from __future__ import annotations

from time import perf_counter
from typing import Any

from logic_cad.core.debug.debug_log import logic_cad_log, logic_cad_log_separator
from logic_cad.core.debug.routing_perf import (
    routing_perf_add,
    routing_perf_enabled,
    routing_perf_span,
)
from logic_cad.core.uid_display import format_uid_display
from logic_cad.core.model.index_store import IndexStore
from logic_cad.core.model.wire_port_helpers import (
    _and_or_input_count,
    _port_index,
    wire_skips_auto_reroute,
)
from logic_cad.core.model.xdata import build_ld_app_tags, read_ld_app_dict, set_entity_xdata
from logic_cad.core.routing.wire_path_metrics import (
    _count_segment_crossings_among,
    _count_segment_overlaps_among,
)
from logic_cad.core.routing.wire_routing_from_document import (
    DEFAULT_ROUTING_PROFILE,
    RoutingProfile,
)
from logic_cad.core.services.wire_service.mixins.gate_input_crossing_swaps import (
    optimize_and_or_crossing_swaps,
)
from logic_cad.core.services.wire_service.mixins.gate_input_host import GateInputWireServiceHost
from logic_cad.core.services.wire_service.mixins.gate_input_port_assignment import (
    assign_gate_input_ports_by_source_order,
)
from logic_cad.core.services.wire_service.mixins.gate_input_rows import (
    collect_gate_input_rows_all,
    gate_input_wire_rows_in_order,
    ordered_gate_inputs_allow_crossing_swaps,
)


def optimize_and_or_input_ports_impl(
    host: GateInputWireServiceHost,
    index: IndexStore,
    layout_name: str,
    gate_uid: str,
    routing_profile: RoutingProfile | None = None,
) -> bool:
    """Assign inputs in heuristic order, then route the gate bundle as a coordinated set.

    Args:
        host: Wire service mixin host (drawing + mutation hooks).
        index: Spatial index for the diagram.
        layout_name: Target paper-space layout.
        gate_uid: Dynamic AND/OR ``INSERT`` UID.
        routing_profile: Optional routing knobs; defaults match ``DEFAULT_ROUTING_PROFILE``.

    Returns:
        ``True`` after a successful reroute/post-process; ``False`` when reroute restores
        the previous assignment or callers should treat the gate unchanged.
    """
    routing_profile = routing_profile or DEFAULT_ROUTING_PROFILE
    perf = routing_perf_enabled()
    n = _and_or_input_count(index, gate_uid)
    if n is None:
        return False

    rows = collect_gate_input_rows_all(host, layout_name, gate_uid)
    if not rows:
        return False

    auto_rows = [r for r in rows if not wire_skips_auto_reroute(read_ld_app_dict(r[0]))]
    if not auto_rows:
        with routing_perf_span("gate_input.optimize.bridges_auto_rows_empty"):
            host.recompute_all_bridges_ordered(layout_name)
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

        backup: list[tuple[Any, str, dict[str, Any], list[tuple[float, float]]]] = []
        translate_snapshot: dict[
            str,
            tuple[
                Any,
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
                    list(host._polyline_points(entity)),
                    _dp,
                    (float(old_src[0]), float(old_src[1])),
                    (float(old_dst[0]), float(old_dst[1])),
                )
            backup.append(
                (entity, wu, dict(read_ld_app_dict(entity)), list(host._polyline_points(entity)))
            )

    t_asn = perf_counter() if perf else 0.0
    assigned = assign_gate_input_ports_by_source_order(
        index, layout_name, gate_uid, auto_rows, n, reserved_indices
    )
    if perf:
        routing_perf_add("gate_input.optimize.assign_ports", perf_counter() - t_asn)
    if assigned is None:
        with routing_perf_span("gate_input.optimize.bridges_assign_failed"):
            host.recompute_all_bridges_ordered(layout_name)
        return False
    with routing_perf_span("gate_input.optimize.index_rebuild_after_assign"):
        index.rebuild(host.doc, layout_name)
    rows_to_reroute: list[tuple[Any, str, str, str, str, int]] = []
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
        normalized = host._normalize_auto_route_points(
            shifted,
            (float(new_src[0]), float(new_src[1])),
            (float(new_dst[0]), float(new_dst[1])),
        )
        host.set_wire_points(layout_name, entity, normalized, snap_branches=False)
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
            translated_paths.append(host._polyline_points(ent))
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
            host._route_gate_input_rows(
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
                host.set_wire_points(layout_name, entity, old_pts)
            index.rebuild(host.doc, layout_name)
        with routing_perf_span("gate_input.optimize.bridges_after_route_failure"):
            host.recompute_all_bridges_ordered(layout_name)
        return False
    with routing_perf_span("gate_input.optimize.post_route_ordered"):
        ordered = gate_input_wire_rows_in_order(host, layout_name, gate_uid, n)
    if routing_profile.enable_and_or_crossing_swaps and ordered_gate_inputs_allow_crossing_swaps(
        ordered
    ):
        with routing_perf_span("gate_input.optimize.index_rebuild_before_crossing_swaps"):
            index.rebuild(host.doc, layout_name)
        with routing_perf_span("gate_input.optimize.crossing_swaps"):
            optimize_and_or_crossing_swaps(host, index, layout_name, gate_uid, n)
    with routing_perf_span("gate_input.optimize.bridges_success"):
        host.recompute_all_bridges_ordered(layout_name)
    return True
