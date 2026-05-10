"""Greedy crossing-reduction swaps on fully assigned AND/OR inputs."""

from __future__ import annotations

from logic_cad.core.model.index_store import IndexStore
from logic_cad.core.model.xdata import build_ld_app_tags, get_uid, read_ld_app_dict, set_entity_xdata
from logic_cad.core.routing.wire_path_metrics import (
    _count_segment_crossings_among,
    _polylines_cross,
)
from logic_cad.core.services.wire_service.mixins.gate_input_host import (
    GateInputWireServiceHost,
)
from logic_cad.core.services.wire_service.mixins.gate_input_reroute import (
    reroute_gate_input_wire,
)
from logic_cad.core.services.wire_service.mixins.gate_input_rows import (
    gate_input_wire_rows_in_order,
)


def optimize_and_or_crossing_swaps(
    host: GateInputWireServiceHost,
    index: IndexStore,
    layout_name: str,
    gate_uid: str,
    n: int,
) -> None:
    """Try pairwise ``dst_port`` swaps that strictly reduce overlapping crossings.

    Args:
        host: Wire service host (geometry + xdata + bridge recomputation).
        index: Spatial index for the drawing.
        layout_name: Active paper-space layout containing the wires.
        gate_uid: Destination AND/OR ``INSERT``.
        n: Expected full permutation width (matches dynamic input count).

    Raises:
        ValueError: Propagated from ``reroute_gate_input_wire`` on hard failures.
    """
    max_rounds = max(n, 1)
    any_swap = False
    for _ in range(max_rounds):
        ordered = gate_input_wire_rows_in_order(host, layout_name, gate_uid, n)
        if ordered is None:
            return
        pts_list = [host._polyline_points(r[0]) for r in ordered]
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
                old_pts_i = list(host._polyline_points(e_i))
                old_pts_j = list(host._polyline_points(e_j))
                d_i["dst_port"] = pj
                d_j["dst_port"] = pi
                set_entity_xdata(e_i, build_ld_app_tags("1", w_i, "WIRE", d_i))
                set_entity_xdata(e_j, build_ld_app_tags("1", w_j, "WIRE", d_j))
                index.rebuild(host.doc, layout_name)
                try:
                    reroute_gate_input_wire(host, index, layout_name, e_i, n)
                    reroute_gate_input_wire(host, index, layout_name, e_j, n)
                except ValueError:
                    d_i["dst_port"] = pi
                    d_j["dst_port"] = pj
                    set_entity_xdata(e_i, build_ld_app_tags("1", w_i, "WIRE", d_i))
                    set_entity_xdata(e_j, build_ld_app_tags("1", w_j, "WIRE", d_j))
                    index.rebuild(host.doc, layout_name)
                    host.set_wire_points(layout_name, e_i, old_pts_i)
                    host.set_wire_points(layout_name, e_j, old_pts_j)
                    continue
                pts_trial = [host._polyline_points(ordered[k][0]) for k in range(n)]
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
                index.rebuild(host.doc, layout_name)
                host.set_wire_points(layout_name, e_i, old_pts_i)
                host.set_wire_points(layout_name, e_j, old_pts_j)
            if improved:
                break
        if not improved:
            break
    if any_swap:
        host.recompute_all_bridges_ordered(layout_name)
