"""Obstacle sets for escape+mid routing and crossing heuristics."""

from dataclasses import replace

import pytest

from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.core.model.constants import GRID_PITCH, ROUTING_VERTICAL_LANE_SPACING_MM
from logic_cad.core.obstacles import wire_obstacles
from logic_cad.core.routing import (
    DEFAULT_ROUTING_PROFILE,
    apply_vertical_lane_stagger,
    path_hits_obstacles,
    route_manhattan,
    route_manhattan_with_escape,
)
from logic_cad.core.model.xdata import build_ld_app_tags, get_uid, set_entity_xdata

from logic_cad.tests.support.diagram_entities import entity_and_ld_app_dict_for_uid
from logic_cad.core.routing.wire_path_metrics import _count_segment_crossings_among, _polylines_cross


def test_wire_obstacles_skip_wires_whose_endpoints_are_not_in_index():
    """Deleting a gate leaves polylines pointing at a dead dst; they must not act as routing obstacles."""
    d = LogicDiagram.new()
    with d.begin("place"):
        left0 = d.place_and_gate(1, (20.0, 16.0))
        left1 = d.place_and_gate(1, (20.0, 32.0))
        right = d.place_and_gate(2, (72.0, 24.0))
    with d.begin("wire"):
        d.connect_ports(left0, "OUT0_LOGIC", right, "IN0_LOGIC")
        d.connect_ports(left1, "OUT0_LOGIC", right, "IN1_LOGIC")
    d.rebuild_index()
    legacy = len(wire_obstacles(d.doc, d.current_layout_name, index=None))
    indexed = len(wire_obstacles(d.doc, d.current_layout_name, index=d.index))
    assert legacy == indexed
    assert legacy > 0

    with d.begin("del-gate"):
        d.delete_by_uid(right)

    legacy_orphan = len(wire_obstacles(d.doc, d.current_layout_name, index=None))
    indexed_orphan = len(wire_obstacles(d.doc, d.current_layout_name, index=d.index))
    assert legacy_orphan > 0
    assert indexed_orphan == 0


def test_wire_obstacles_skip_wires_with_missing_src_or_dst_xdata():
    """Broken xdata must not leave fat segments in the routing obstacle set when index is used."""
    d = LogicDiagram.new()
    with d.begin("place"):
        a = d.place_and_gate(1, (10.0, 10.0))
        b = d.place_and_gate(1, (40.0, 10.0))
    with d.begin("wire"):
        wuid = d.connect_ports(a, "OUT0_LOGIC", b, "IN0_LOGIC")
    d.rebuild_index()
    e, xd = entity_and_ld_app_dict_for_uid(d.doc, wuid)
    wu = get_uid(e)
    assert wu
    bad = dict(xd)
    bad.pop("src", None)
    set_entity_xdata(e, build_ld_app_tags("1", wu, "WIRE", bad))
    d.rebuild_index()

    layout = d.current_layout_name
    assert len(wire_obstacles(d.doc, layout, index=None)) > 0
    assert len(wire_obstacles(d.doc, layout, index=d.index)) == 0


def test_mid_segment_respects_obstacles_after_escape():
    """Obstacles apply to ex→dst; path should not cut through a blocking rect on that leg."""
    p0 = (0.0, 0.0)
    dst = (10.0, 2.0)
    ex = (2.0, 0.0)
    obs = [(4.0, -1.0, 6.0, 1.0)]
    pts = route_manhattan_with_escape(
        p0,
        dst,
        obs,
        pitch=GRID_PITCH,
        first_escape_src=ex,
        skip_first_leg_hard_obstacle_check=False,
    )
    assert not path_hits_obstacles(pts, obs)


def test_segment_crossing_count_horizontal_vertical():
    a = [(0.0, 1.0), (4.0, 1.0)]
    b = [(2.0, 0.0), (2.0, 4.0)]
    assert _polylines_cross(a, b)
    assert _count_segment_crossings_among([a, b]) >= 1


def test_parallel_polylines_no_crossing():
    a = [(0.0, 0.0), (4.0, 0.0)]
    b = [(0.0, 2.0), (4.0, 2.0)]
    assert not _polylines_cross(a, b)
    assert _count_segment_crossings_among([a, b]) == 0


def test_apply_vertical_lane_stagger_offsets_longest_interior_vertical():
    pitch = GRID_PITCH
    # Longest interior vertical is (4,0)→(4,12) (first leg p0→p1 is not a candidate).
    x_col = 4.0
    pts = [(0.0, 0.0), (x_col, 0.0), (x_col, 12.0), (10.0, 12.0)]
    out = apply_vertical_lane_stagger(pts, 1, pitch)
    ox = round(ROUTING_VERTICAL_LANE_SPACING_MM / pitch) * pitch
    expected_x = x_col + ox
    assert any(abs(p[0] - expected_x) < 1e-6 for p in out)


def test_route_manhattan_relaxed_obstacles_unblock_long_horizontal_when_full_hard_blocks_ovg():
    """Move-time reroute uses symbol-only hard rects so layers 3–4 can cross existing wire hulls."""
    src = (-115.0, 292.0)
    dst = (-71.0, 292.0)
    obs = [(-120.0, 280.0, -65.0, 304.0)]
    profile = replace(DEFAULT_ROUTING_PROFILE, max_search_states=12_000)
    with pytest.raises(ValueError, match="マンハッタン経路が見つかりません"):
        route_manhattan(
            src,
            dst,
            obs,
            pitch=GRID_PITCH,
            profile=profile,
            obstacles_relaxed=None,
        )
    pts = route_manhattan(
        src,
        dst,
        obs,
        pitch=GRID_PITCH,
        profile=profile,
        obstacles_relaxed=[],
    )
    assert pts[0] == src
    assert pts[-1] == dst
    assert len(pts) == 2
