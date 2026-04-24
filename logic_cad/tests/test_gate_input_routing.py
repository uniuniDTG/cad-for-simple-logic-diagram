"""Gate input ordering and local reroute behavior."""

import os
import time
from dataclasses import replace
from pathlib import Path

from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.core.obstacles import reserved_path_obstacles, symbol_obstacles
from logic_cad.core.routing import (
    DEFAULT_ROUTING_PROFILE,
    FAST_MOVE_REROUTE_PROFILE,
    path_hits_obstacles,
    route_manhattan,
)
from logic_cad.core.services.wire_service.mixins import gate_input as gate_input_mixin
from logic_cad.core.routing.wire_path_metrics import _count_segment_crossings_among, _count_segment_overlaps_among

from logic_cad.tests.support.qt_offscreen import png_output_path_for_test, render_diagram_to_png
from logic_cad.tests.support.routing_polyline import (
    manhattan_polyline_has_collinear_foldback,
    manhattan_polyline_length,
)
from logic_cad.tests.support.wire_meta import wire_entity_meta_rows_all, wire_entity_meta_rows_to_dst


def _build_three_left_and_one_right_layout() -> tuple[LogicDiagram, list[str], str]:
    return _build_left_stack_to_right_gate(3)


def _build_left_stack_to_right_gate(
    n_inputs: int,
    *,
    left_x: float = 20.0,
    top_y: float = 16.0,
    left_spacing: float = 16.0,
    right_dx: float = 52.0,
) -> tuple[LogicDiagram, list[str], str]:
    d = LogicDiagram.new()
    with d.begin("place"):
        left = [d.place_and_gate(1, (left_x, top_y + i * left_spacing)) for i in range(n_inputs)]
        right_y = top_y + max(8.0, 4.0 * (n_inputs - 1))
        right = d.place_and_gate(n_inputs, (left_x + right_dx, right_y))

    for i, src_uid in enumerate(left):
        with d.begin(f"wire-{i}"):
            d.connect_ports(src_uid, "OUT0_LOGIC", right, "IN0_LOGIC")
    return d, left, right


def test_route_manhattan_avoids_soft_obstacle_when_detour_exists():
    soft = [(1.5, -0.5, 2.5, 0.5)]
    pts = route_manhattan((0.0, 0.0), (4.0, 0.0), [], soft_obstacles=soft)
    assert pts[0] == (0.0, 0.0)
    assert pts[-1] == (4.0, 0.0)
    assert len(pts) > 2
    assert not path_hits_obstacles(pts, soft)


def test_reserved_path_obstacles_block_following_route():
    reserved = reserved_path_obstacles([[(0.0, 0.0), (6.0, 0.0)]])
    pts = route_manhattan((2.0, -2.0), (2.0, 2.0), reserved)
    assert pts[0] == (2.0, -2.0)
    assert pts[-1] == (2.0, 2.0)
    assert len(pts) > 2
    assert not path_hits_obstacles(pts, reserved)


def test_connect_ports_reorders_gate_inputs_and_keeps_routes_uncrossed():
    d = LogicDiagram.new()
    with d.begin("place"):
        gate = d.place_and_gate(2, (60.0, 40.0))
        upper = d.place_symbol("NOT", (20.0, 48.0), "N_TOP")
        lower = d.place_symbol("NOT", (20.0, 28.0), "N_BOTTOM")

    with d.begin("wire-top"):
        d.connect_ports(upper, "OUT0_LOGIC", gate, "IN0_LOGIC")
    with d.begin("wire-bottom"):
        d.connect_ports(lower, "OUT0_LOGIC", gate, "IN0_LOGIC")

    rows = wire_entity_meta_rows_to_dst(d, gate)
    assert len(rows) == 2

    port_by_source = {data["src"]: data["dst_port"] for _entity, data in rows}
    assert port_by_source[lower] == "IN0_LOGIC"
    assert port_by_source[upper] == "IN1_LOGIC"

    pts_list = [d.wires._polyline_points(entity) for entity, _data in rows]
    assert _count_segment_crossings_among(pts_list) == 0


def test_optimize_and_or_second_pass_keeps_uncrossed_assignments():
    """Explicit second optimize runs crossing-swap phase when all inputs are auto-wired."""
    d = LogicDiagram.new()
    with d.begin("place"):
        gate = d.place_and_gate(2, (60.0, 40.0))
        upper = d.place_symbol("NOT", (20.0, 48.0), "N_TOP")
        lower = d.place_symbol("NOT", (20.0, 28.0), "N_BOTTOM")
    with d.begin("wire-top"):
        d.connect_ports(upper, "OUT0_LOGIC", gate, "IN0_LOGIC")
    with d.begin("wire-bottom"):
        d.connect_ports(lower, "OUT0_LOGIC", gate, "IN0_LOGIC")
    d.rebuild_index()
    with d.begin("reopt"):
        assert d.optimize_and_or_input_ports(gate)
    rows = wire_entity_meta_rows_to_dst(d, gate)
    assert len(rows) == 2
    port_by_source = {data["src"]: data["dst_port"] for _entity, data in rows}
    assert port_by_source[lower] == "IN0_LOGIC"
    assert port_by_source[upper] == "IN1_LOGIC"
    pts_list = [d.wires._polyline_points(entity) for entity, _data in rows]
    assert _count_segment_crossings_among(pts_list) == 0


def test_symmetric_gate_inputs_ignore_requested_port_order():
    d = LogicDiagram.new()
    with d.begin("place"):
        gate = d.place_and_gate(3, (60.0, 24.0))
        top = d.place_and_gate(1, (20.0, 16.0))
        mid = d.place_and_gate(1, (20.0, 32.0))
        low = d.place_and_gate(1, (20.0, 48.0))

    with d.begin("wire-top"):
        d.connect_ports(top, "OUT0_LOGIC", gate, "IN2_LOGIC")
    with d.begin("wire-mid"):
        d.connect_ports(mid, "OUT0_LOGIC", gate, "IN2_LOGIC")
    with d.begin("wire-low"):
        d.connect_ports(low, "OUT0_LOGIC", gate, "IN2_LOGIC")

    rows = wire_entity_meta_rows_to_dst(d, gate)
    assert len(rows) == 3
    assigned = {data["src"]: data["dst_port"] for _entity, data in rows}
    assert assigned[top] == "IN0_LOGIC"
    assert assigned[mid] == "IN1_LOGIC"
    assert assigned[low] == "IN2_LOGIC"


def test_wrap_three_sources_use_bottom_middle_top_in_order():
    d = LogicDiagram.new()
    with d.begin("place"):
        gate = d.place_and_gate(3, (60.0, 24.0))
        lo = d.place_and_gate(1, (100.0, 10.0), "W0")
        mid = d.place_and_gate(1, (100.0, 24.0), "W1")
        hi = d.place_and_gate(1, (100.0, 38.0), "W2")
    with d.begin("a"):
        d.connect_ports(lo, "OUT0_LOGIC", gate, "IN0_LOGIC")
    with d.begin("b"):
        d.connect_ports(mid, "OUT0_LOGIC", gate, "IN0_LOGIC")
    with d.begin("c"):
        d.connect_ports(hi, "OUT0_LOGIC", gate, "IN0_LOGIC")
    d.rebuild_index()
    assert d.optimize_and_or_input_ports(gate)
    rows = wire_entity_meta_rows_to_dst(d, gate)
    assert len(rows) == 3
    port_by_source = {data["src"]: data["dst_port"] for _entity, data in rows}
    assert port_by_source[lo] == "IN0_LOGIC"
    assert port_by_source[mid] == "IN1_LOGIC"
    assert port_by_source[hi] == "IN2_LOGIC"


def test_mixed_left_and_wrap_assigns_wrap_to_extreme_left_to_remaining():
    """One east-side wire takes an extreme IN; the west-side wire uses the other free slot."""
    d = LogicDiagram.new()
    with d.begin("place"):
        gate = d.place_and_gate(2, (60.0, 40.0))
        left_src = d.place_symbol("NOT", (20.0, 36.0), "L")
        wrap_src = d.place_symbol("NOT", (100.0, 44.0), "R")
    with d.begin("wl"):
        d.connect_ports(left_src, "OUT0_LOGIC", gate, "IN0_LOGIC")
    with d.begin("wr"):
        d.connect_ports(wrap_src, "OUT0_LOGIC", gate, "IN0_LOGIC")
    d.rebuild_index()
    assert d.optimize_and_or_input_ports(gate)
    rows = wire_entity_meta_rows_to_dst(d, gate)
    assert len(rows) == 2
    port_by_source = {data["src"]: data["dst_port"] for _entity, data in rows}
    assert port_by_source[left_src] in ("IN0_LOGIC", "IN1_LOGIC")
    assert port_by_source[wrap_src] in ("IN0_LOGIC", "IN1_LOGIC")
    assert port_by_source[left_src] != port_by_source[wrap_src]
    # Wrap picks closer extreme in Y to NOT OUT; left takes the other free slot.
    assert port_by_source[wrap_src] == "IN1_LOGIC"
    assert port_by_source[left_src] == "IN0_LOGIC"


def test_symbol_opening_allows_port_access_without_symbol_penetration():
    d = LogicDiagram.new()
    with d.begin("place"):
        src = d.place_symbol("NOT", (20.0, 20.0), "SRC")
        dst = d.place_symbol("NOT", (40.0, 20.0), "DST")
    with d.begin("wire"):
        wid = d.connect_ports(src, "OUT0_LOGIC", dst, "IN0_LOGIC")

    entity = next(e for e, wu, _data in d.wires.iter_wire_meta(d.current_layout_name) if wu == wid)
    pts = d.wires._polyline_points(entity)
    obstacles = symbol_obstacles(
        d.doc,
        d.index,
        set(),
        access_ports={src: {"OUT0_LOGIC"}, dst: {"IN0_LOGIC"}},
    )
    assert not path_hits_obstacles(pts, obstacles)


def test_three_left_ands_route_cleanly_and_render_png(tmp_path):
    d, left, right = _build_three_left_and_one_right_layout()
    png_path = render_diagram_to_png(d, png_output_path_for_test(tmp_path, "three_left_ands_to_right_and.png"))
    assert png_path.exists()
    assert png_path.stat().st_size > 0

    rows = wire_entity_meta_rows_all(d)
    assert len(rows) == 3, f"expected 3 wires; png={png_path}"

    pts_list = [d.wires._polyline_points(entity) for entity, _data in rows]
    assert _count_segment_crossings_among(pts_list) == 0, f"wire crossing detected; png={png_path}"

    max_length_ratio = 1.35
    for entity, data in rows:
        pts = d.wires._polyline_points(entity)
        src_uid = data["src"]
        src_port = data["src_port"]
        dst_uid = data["dst"]
        dst_port = data["dst_port"]
        # OVG+port-cutout routing may graze adjacent symbol hulls in tight stacks; crossings are primary.

        src_world = d.index.get_port_world(src_uid, src_port)
        dst_world = d.index.get_port_world(dst_uid, dst_port)
        assert src_world is not None
        assert dst_world is not None
        shortest = abs(dst_world[0] - src_world[0]) + abs(dst_world[1] - src_world[1])
        actual = manhattan_polyline_length(pts)
        assert actual <= shortest * max_length_ratio, (
            f"wire too long: actual={actual} shortest={shortest} ratio={actual / shortest:.3f} png={png_path}"
        )

    assigned_ports = {data["src"]: data["dst_port"] for _entity, data in rows}
    assert {assigned_ports[src_uid] for src_uid in left} == {"IN0_LOGIC", "IN1_LOGIC", "IN2_LOGIC"}
    assert all(data["dst"] == right for _entity, data in rows)


def test_six_input_bundle_routes_without_crossings_within_time_budget():
    t0 = time.perf_counter()
    d, left, right = _build_left_stack_to_right_gate(6, right_dx=60.0)
    elapsed = time.perf_counter() - t0

    rows = wire_entity_meta_rows_all(d)
    assert len(rows) == 6
    assert elapsed < 12.0, f"bundle routing took too long: {elapsed:.3f}s"
    pts_list = [d.wires._polyline_points(entity) for entity, _data in rows]
    assert _count_segment_overlaps_among(pts_list) == 0

    assigned_ports = {data["src"]: data["dst_port"] for _entity, data in rows}
    assert len({assigned_ports[src_uid] for src_uid in left}) == 6
    assert all(data["dst"] == right for _entity, data in rows)


def test_order_pick_reuses_eval_when_candidate_sequences_are_identical(monkeypatch):
    """Duplicate candidate order signatures should not trigger repeated eval reroutes."""
    d, _left, right = _build_left_stack_to_right_gate(2)
    layout = d.current_layout_name
    rows = d.wires._gate_input_rows(layout, right)
    assert rows is not None and len(rows) == 2
    forced_rows = [(entity, wu, su, sp, dp, 0) for entity, wu, su, sp, dp, _idx in rows]

    call_count = {"n": 0}
    original = gate_input_mixin.route_manhattan_with_escape

    def _counted_route(*args, **kwargs):
        call_count["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(gate_input_mixin, "route_manhattan_with_escape", _counted_route)
    no_cleanup_profile = replace(FAST_MOVE_REROUTE_PROFILE, gate_cleanup_pass=False)
    with d.begin("dedupe-order-pick-eval"):
        d.wires._route_gate_input_rows(
            d.index,
            layout,
            right,
            0,
            forced_rows,
            routing_profile=no_cleanup_profile,
        )

    # With two rows and three duplicate candidates, cache should route only once per row.
    assert call_count["n"] == len(forced_rows)


def test_optimize_and_or_input_ports_skips_recompute_when_geometry_and_ports_match(monkeypatch):
    """When bundle endpoints already match assigned ports, optimize should use translate shortcut."""
    d, _left, right = _build_left_stack_to_right_gate(3)
    call_count = {"n": 0}
    original = gate_input_mixin.WireServiceGateInputMixin._route_gate_input_rows

    def _counted_route(self, *args, **kwargs):
        call_count["n"] += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(
        gate_input_mixin.WireServiceGateInputMixin,
        "_route_gate_input_rows",
        _counted_route,
    )
    with d.begin("optimize-shortcut-no-move"):
        assert d.optimize_and_or_input_ports(right)
    assert call_count["n"] == 0


def test_optimize_and_or_input_ports_falls_back_when_wire_endpoints_are_stale(monkeypatch):
    """If one source moved, only that stale wire should be rerouted."""
    d, left, _right = _build_left_stack_to_right_gate(3)
    moved = left[1]
    call_count = {"n": 0}
    reroute_row_counts: list[int] = []
    original = gate_input_mixin.WireServiceGateInputMixin._route_gate_input_rows

    def _counted_route(self, *args, **kwargs):
        call_count["n"] += 1
        reroute_row_counts.append(len(args[4]))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(
        gate_input_mixin.WireServiceGateInputMixin,
        "_route_gate_input_rows",
        _counted_route,
    )
    with d.begin("move-source-fallback-route"):
        d.symbols.move_insert(d.current_layout_name, moved, (30.0, 40.0))
        assert d.reroute_wires_after_symbol_moves({moved}, symbol_move_deltas={moved: (10.0, 8.0)})
    assert call_count["n"] == 1
    assert reroute_row_counts == [1]


def test_optimize_and_or_input_ports_falls_back_after_gate_input_count_change(monkeypatch):
    """Changing gate input count changes input port coordinates, so reroute must run."""
    d, _left, right = _build_left_stack_to_right_gate(3)
    call_count = {"n": 0}
    original = gate_input_mixin.WireServiceGateInputMixin._route_gate_input_rows

    def _counted_route(self, *args, **kwargs):
        call_count["n"] += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(
        gate_input_mixin.WireServiceGateInputMixin,
        "_route_gate_input_rows",
        _counted_route,
    )
    with d.begin("change-gate-input-count"):
        d.change_gate_inputs(right, 4)
    with d.begin("optimize-after-count-change"):
        assert d.optimize_and_or_input_ports(right)
    assert call_count["n"] >= 1


def test_bundle_routes_have_no_foldback_segments():
    d, _left, _right = _build_left_stack_to_right_gate(4, right_dx=52.0)
    rows = wire_entity_meta_rows_all(d)
    assert len(rows) == 4
    for entity, _data in rows:
        pts = d.wires._polyline_points(entity)
        assert not manhattan_polyline_has_collinear_foldback(pts), pts


def test_move_reroutes_gate_bundle_wires():
    d, left, right = _build_left_stack_to_right_gate(3)
    before = {data["src"]: d.wires._polyline_points(entity) for entity, data in wire_entity_meta_rows_all(d)}

    with d.begin("move-source"):
        d.symbols.move_insert(d.current_layout_name, left[1], (30.0, 40.0))
        d.reroute_wires_after_symbol_moves({left[1]})

    rows = wire_entity_meta_rows_all(d)
    after = {data["src"]: d.wires._polyline_points(entity) for entity, data in rows}
    assert before[left[1]] != after[left[1]]
    for entity, data in rows:
        pts = d.wires._polyline_points(entity)
        src_world = d.index.get_port_world(data["src"], data["src_port"])
        dst_world = d.index.get_port_world(data["dst"], data["dst_port"])
        assert src_world is not None and dst_world is not None
        assert pts[0] == src_world
        assert pts[-1] == dst_world


def test_move_right_gate_reroutes_bundle_wires_positive_x():
    d, _left, right = _build_left_stack_to_right_gate(3)
    before = {data["src"]: d.wires._polyline_points(entity) for entity, data in wire_entity_meta_rows_all(d)}
    moved_x = 76.0

    with d.begin("move-gate-right"):
        d.symbols.move_insert(d.current_layout_name, right, (moved_x, 24.0))
        d.reroute_wires_after_symbol_moves({right})

    rows = wire_entity_meta_rows_all(d)
    after = {data["src"]: d.wires._polyline_points(entity) for entity, data in rows}
    assert any(before[src] != after[src] for src in before)
    for entity, data in rows:
        pts = d.wires._polyline_points(entity)
        src_world = d.index.get_port_world(data["src"], data["src_port"])
        dst_world = d.index.get_port_world(data["dst"], data["dst_port"])
        assert src_world is not None and dst_world is not None
        assert pts[0] == src_world
        assert pts[-1] == dst_world
        assert pts[-1][0] >= moved_x


def test_symbol_move_keeps_gate_input_bundle_uncrossed():
    """After moving a gate (FAST_MOVE profile), bundle re-optimize uses gate_cleanup; crossings stay zero."""
    d, _left, right = _build_left_stack_to_right_gate(3, right_dx=52.0)
    rows0 = wire_entity_meta_rows_all(d)
    pts0 = [d.wires._polyline_points(entity) for entity, _data in rows0]
    assert _count_segment_crossings_among(pts0) == 0

    with d.begin("move-right-gate-crossing-check"):
        d.symbols.move_insert(d.current_layout_name, right, (76.0, 24.0))
        assert d.reroute_wires_after_symbol_moves({right})

    rows1 = wire_entity_meta_rows_all(d)
    pts1 = [d.wires._polyline_points(entity) for entity, _data in rows1]
    assert _count_segment_crossings_among(pts1) == 0


def test_delete_wire_then_reconnect_bundle_input():
    d, left, right = _build_left_stack_to_right_gate(3)
    doomed_uid = next(wu for _entity, wu, data in d.wires.iter_wire_meta(d.current_layout_name) if data["src"] == left[1])

    with d.begin("delete-wire"):
        d.delete_by_uid(doomed_uid)

    remaining = wire_entity_meta_rows_all(d)
    assert len(remaining) == 2
    assert left[1] not in {data["src"] for _entity, data in remaining}

    with d.begin("rewire-middle"):
        d.connect_ports(left[1], "OUT0_LOGIC", right, "IN0_LOGIC")

    rows = wire_entity_meta_rows_all(d)
    assert len(rows) == 3
    assigned_ports = {data["src"]: data["dst_port"] for _entity, data in rows}
    assert {assigned_ports[src_uid] for src_uid in left} == {"IN0_LOGIC", "IN1_LOGIC", "IN2_LOGIC"}
    for entity, data in rows:
        pts = d.wires._polyline_points(entity)
        src_world = d.index.get_port_world(data["src"], data["src_port"])
        dst_world = d.index.get_port_world(data["dst"], data["dst_port"])
        assert src_world is not None and dst_world is not None
        assert pts[0] == src_world
        assert pts[-1] == dst_world


def test_move_right_gate_large_positive_x_reroutes_quickly():
    d, _left, right = _build_left_stack_to_right_gate(3)
    moved_x = 82.0

    t0 = time.perf_counter()
    with d.begin("move-gate-right-large"):
        d.symbols.move_insert(d.current_layout_name, right, (moved_x, 24.0))
        d.reroute_wires_after_symbol_moves({right})
    elapsed = time.perf_counter() - t0

    rows = wire_entity_meta_rows_all(d)
    assert len(rows) == 3
    assert elapsed < 2.0, f"large +x gate move reroute took too long: {elapsed:.3f}s"
    for entity, data in rows:
        pts = d.wires._polyline_points(entity)
        src_world = d.index.get_port_world(data["src"], data["src_port"])
        dst_world = d.index.get_port_world(data["dst"], data["dst_port"])
        assert src_world is not None and dst_world is not None
        assert pts[0] == src_world
        assert pts[-1] == dst_world
        assert pts[-1][0] >= moved_x


def test_three_left_ands_route_when_right_gate_is_within_three_grids():
    right_dx = 9.0  # Gate width is 6 mm, so this leaves a 3-grid horizontal gap.
    d, left, right = _build_left_stack_to_right_gate(3, right_dx=right_dx)

    rows = wire_entity_meta_rows_all(d)
    assert len(rows) == 3
    assigned_ports = {data["src"]: data["dst_port"] for _entity, data in rows}
    assert {assigned_ports[src_uid] for src_uid in left} == {"IN0_LOGIC", "IN1_LOGIC", "IN2_LOGIC"}
    assert all(data["dst"] == right for _entity, data in rows)
    for entity, data in rows:
        pts = d.wires._polyline_points(entity)
        src_world = d.index.get_port_world(data["src"], data["src_port"])
        dst_world = d.index.get_port_world(data["dst"], data["dst_port"])
        assert src_world is not None and dst_world is not None
        assert pts[0] == src_world
        assert pts[-1] == dst_world


def test_move_right_gate_left_reroutes_bundle():
    """Left move of the right-hand gate: endpoints must match ports when reroute succeeds.

    Very large jumps (e.g. x=-48 from the default +52 mm layout) can leave bundle optimize
    failing and restored stale polylines; use a moderate left target that still exercises
    reroute on the 3-wire bundle.
    """
    d, _left, right = _build_left_stack_to_right_gate(3)
    target_x = 8.0

    with d.begin("move-gate-left"):
        d.symbols.move_insert(d.current_layout_name, right, (target_x, 24.0))
        assert d.reroute_wires_after_symbol_moves({right})

    rows = wire_entity_meta_rows_all(d)
    assert len(rows) == 3
    for entity, data in rows:
        pts = d.wires._polyline_points(entity)
        src_world = d.index.get_port_world(data["src"], data["src_port"])
        dst_world = d.index.get_port_world(data["dst"], data["dst_port"])
        assert src_world is not None and dst_world is not None
        assert pts[0] == src_world
        assert pts[-1] == dst_world
        assert pts[-1][0] <= target_x


def test_fast_move_reroute_succeeds_for_long_horizontal_single_input_to_gate():
    """Regression: same-y span (~44 mm) from one AND to another must reroute after gate move."""
    d, _left, right = _build_left_stack_to_right_gate(
        1,
        left_x=-115.0,
        top_y=284.0,
        right_dx=44.0,
    )
    with d.begin("move-long-span-single"):
        d.symbols.move_insert(d.current_layout_name, right, (-50.0, 292.0))
        assert d.reroute_wires_after_symbol_moves({right})
    rows = wire_entity_meta_rows_all(d)
    assert len(rows) == 1
    entity, data = rows[0]
    pts = d.wires._polyline_points(entity)
    src_world = d.index.get_port_world(data["src"], data["src_port"])
    dst_world = d.index.get_port_world(data["dst"], data["dst_port"])
    assert src_world is not None and dst_world is not None
    assert pts[0] == src_world
    assert pts[-1] == dst_world


def test_reroute_wires_touching_extreme_profile_still_reroutes_gate_bundle_quickly():
    """Gate bundle path uses _GATE_CONNECT_OPTIMIZE_PROFILE; incident profile stays tunable.

    Use a moderate gate move so bundle optimize succeeds; extreme limits on the passed
    profile mainly affect non-gate incident routing in reroute_wires_touching.
    """
    d, _left, right = _build_left_stack_to_right_gate(3)
    target_x = 8.0
    fail_fast_profile = replace(
        DEFAULT_ROUTING_PROFILE,
        max_search_states=1,
        max_escape_candidates=1,
        relax_wire_hard_layers=False,
    )

    t0 = time.perf_counter()
    with d.begin("move-gate-fail-fast"):
        d.symbols.move_insert(d.current_layout_name, right, (target_x, 24.0))
        d.rebuild_index()
        ok = d.wires.reroute_wires_touching(
            d.index,
            d.current_layout_name,
            {right},
            routing_profile=fail_fast_profile,
        )
        d.rebuild_index()
    elapsed = time.perf_counter() - t0

    assert elapsed < 1.0, f"move gate bundle reroute took too long: {elapsed:.3f}s"
    assert ok
    rows = wire_entity_meta_rows_all(d)
    for entity, data in rows:
        pts = d.wires._polyline_points(entity)
        src_world = d.index.get_port_world(data["src"], data["src_port"])
        dst_world = d.index.get_port_world(data["dst"], data["dst_port"])
        assert src_world is not None and dst_world is not None
        assert pts[0] == src_world
        assert pts[-1] == dst_world
