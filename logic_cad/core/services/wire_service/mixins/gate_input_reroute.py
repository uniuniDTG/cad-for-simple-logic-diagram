"""Single-wire rerouting into a gate logic input."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from logic_cad.core.model.index_store import IndexStore
from logic_cad.core.model.wire_port_helpers import wire_allows_orthogonal_cross
from logic_cad.core.model.xdata import get_uid, read_ld_app_dict
from logic_cad.core.model.constants import ROUTE_ESCAPE_MM
from logic_cad.core.routing.wire_routing_from_document import (
    DEFAULT_ROUTING_PROFILE,
    RoutingProfile,
    build_routing_obstacles,
    build_symbol_only_routing_obstacles,
)
from logic_cad.core.services.wire_service.mixins import gate_input as _gate_input_shim
from logic_cad.core.services.wire_service.mixins.gate_input_host import (
    GateInputWireServiceHost,
)


def reroute_gate_input_wire(
    host: GateInputWireServiceHost,
    index: IndexStore,
    layout_name: str,
    entity: Any,
    n_inputs: int,
    routing_profile: RoutingProfile | None = None,
) -> None:
    """Re-route one auto wire whose destination is a gate logic input.

    Args:
        host: Wire service host (doc, obstacle helpers, wire geometry).
        index: Spatial index for the layout.
        layout_name: Active paper layout name.
        entity: WIRE DXF entity to update.
        n_inputs: Dynamic gate input count (reserved for future lane logic).
        routing_profile: Optional routing knobs; defaults applied when omitted.

    Raises:
        ValueError: Propagated from the Manhattan router on infeasible geometry.
    """
    _ = n_inputs
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
    dst_target = host._gate_input_pre_entry(index, du, dp, toward=p0) or p1
    access_ports = {su: {sp}, du: {dp}}
    sym_ex = host._symbol_uids_exclude_from_routing_obstacles(su, du)
    obs_relaxed = (
        build_symbol_only_routing_obstacles(
            host.doc,
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
        host.doc,
        index,
        layout_name,
        sym_ex,
        {wu},
        access_ports=access_ports,
        symbol_margin=0.0,
    )
    esc = index.port_first_escape_world(host.doc, su, sp, ROUTE_ESCAPE_MM, toward=p1)
    lane = 0
    soft_obstacles = host._pair_symbol_soft_obstacles(index, su, du, access_ports)
    dst_facing = host._port_facing(index, du, dp)
    src_facing = host._port_facing(index, su, sp)
    overlap_segs = host._existing_wire_path_segments(layout_name, {wu} if wu else set())
    banned_src = host._banned_src_cardinals_for_route(
        layout_name, su, sp, exclude_wire_uids={wu} if wu else None
    )
    pts = _gate_input_shim.route_manhattan_with_escape(
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
    new_final = host._append_port_segment(pts, p1)
    new_final = host._normalize_auto_route_points(new_final, p0, p1)
    host.set_wire_points(layout_name, entity, new_final, snap_branches=False)
