"""WIRE_BRANCH as INSERT endpoint node (IN0_MULTI / OUT0_MULTI) and wire lifecycle."""

import math

from logic_cad.core.model.constants import ENTITY_TYPE_WIRE_BRANCH, GRID_PITCH
from logic_cad.core.undo.history import find_entity_by_uid
from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.core.routing.wire_polyline_geometry import (
    clamp_branch_arc_fraction_t,
    closest_point_on_polyline_xy,
    distance_from_polyline_start_to_closest_point_xy,
    point_on_polyline_at_arc_length_xy,
    polyline_chain_length_xy,
)
from logic_cad.core.model.xdata import get_type

from logic_cad.tests.support.diagram_entities import (
    insert_world_xy,
    ld_app_dict_for_uid,
    lwpolyline_first_vertex_xy,
)
from logic_cad.tests.support.wire_meta import count_wires_from_src_port


def test_closest_point_on_polyline_xy_segment_and_corner():
    q = closest_point_on_polyline_xy(1.0, 0.5, [(0.0, 0.0), (2.0, 0.0)])
    assert abs(q[0] - 1.0) < 1e-9 and abs(q[1]) < 1e-9
    q2 = closest_point_on_polyline_xy(2.5, 1.0, [(0.0, 0.0), (2.0, 0.0), (2.0, 4.0)])
    assert abs(q2[0] - 2.0) < 1e-9 and abs(q2[1] - 1.0) < 1e-9


def test_place_wire_branch_creates_insert():
    d = LogicDiagram.new()
    with d.begin("branch"):
        bid = d.place_wire_branch((20.0, 12.0))
    ins = find_entity_by_uid(d.doc, bid)
    assert ins is not None and ins.dxftype() == "INSERT"
    assert get_type(ins) == ENTITY_TYPE_WIRE_BRANCH


def test_fanout_from_branch_three_outputs():
    d = LogicDiagram.new()
    with d.begin("place"):
        a = d.place_and_gate(1, (6.0, 10.0))
        b = d.place_and_gate(1, (56.0, 14.0))
        c = d.place_and_gate(1, (34.0, 26.0))
        d_gate = d.place_and_gate(1, (34.0, 4.0))
    d.rebuild_index()
    with d.begin("branch"):
        # Slightly above d_gate obstacle top (margin) so IN port is not on bbox edge.
        br = d.place_wire_branch((34.0, 14.0))
    with d.begin("wire"):
        d.connect_ports(a, "OUT0_LOGIC", br, "IN0_MULTI")
        d.connect_ports(br, "OUT0_MULTI", b, "IN0_LOGIC")
        d.connect_ports(br, "OUT0_MULTI", c, "IN0_LOGIC")
        d.connect_ports(br, "OUT0_MULTI", d_gate, "IN0_LOGIC")
    d.rebuild_index()
    n = count_wires_from_src_port(d, d.current_layout_name, br, "OUT0_MULTI")
    assert n == 3


def test_delete_trunk_segment_wire_leaves_branch_and_other_wires():
    """Removing one segment wire does not delete the WIRE_BRANCH INSERT."""
    d = LogicDiagram.new()
    with d.begin("place"):
        a = d.place_and_gate(1, (10.0, 10.0))
        b = d.place_and_gate(1, (40.0, 14.0))
        c = d.place_and_gate(1, (24.0, 40.0))
    d.rebuild_index()
    with d.begin("branch"):
        br = d.place_wire_branch((24.0, 12.0))
    with d.begin("wire"):
        w_ab = d.connect_ports(a, "OUT0_LOGIC", br, "IN0_MULTI")
        d.connect_ports(br, "OUT0_MULTI", b, "IN0_LOGIC")
        w_leg = d.connect_ports(br, "OUT0_MULTI", c, "IN0_LOGIC")
    assert find_entity_by_uid(d.doc, br) is not None
    with d.begin("del"):
        d.delete_by_uid(w_ab)
    assert find_entity_by_uid(d.doc, br) is not None
    assert find_entity_by_uid(d.doc, w_leg) is not None


def test_connect_ports_branch_to_gate_health():
    d = LogicDiagram.new()
    with d.begin("place"):
        a = d.place_and_gate(1, (10.0, 10.0))
        b = d.place_and_gate(1, (40.0, 14.0))
        c = d.place_and_gate(1, (24.0, 40.0))
    d.rebuild_index()
    with d.begin("branch"):
        br = d.place_wire_branch((24.0, 12.0))
    with d.begin("wire"):
        d.connect_ports(a, "OUT0_LOGIC", br, "IN0_MULTI")
        d.connect_ports(br, "OUT0_MULTI", b, "IN0_LOGIC")
        nw = d.connect_ports(br, "OUT0_MULTI", c, "IN0_LOGIC")
    xd = ld_app_dict_for_uid(d.doc, nw)
    assert xd.get("src") == br
    assert xd.get("src_port") == "OUT0_MULTI"
    assert "from_branch" not in xd
    d.rebuild_index()
    lo, geo = d.wire_connection_health(nw)
    assert lo and geo


def test_symbol_move_reroutes_wires_to_branch():
    d = LogicDiagram.new()
    with d.begin("place"):
        a = d.place_and_gate(1, (10.0, 10.0))
        b = d.place_and_gate(1, (40.0, 14.0))
        c = d.place_and_gate(1, (24.0, 40.0))
    d.rebuild_index()
    with d.begin("branch"):
        br = d.place_wire_branch((24.0, 12.0))
    with d.begin("wire"):
        d.connect_ports(a, "OUT0_LOGIC", br, "IN0_MULTI")
        d.connect_ports(br, "OUT0_MULTI", b, "IN0_LOGIC")
        nw = d.connect_ports(br, "OUT0_MULTI", c, "IN0_LOGIC")
    d.rebuild_index()
    bx, by = insert_world_xy(d.doc, br)
    fp0 = lwpolyline_first_vertex_xy(d.doc, nw)
    assert math.hypot(fp0[0] - bx, fp0[1] - by) < 0.35
    with d.begin("move"):
        d.symbols.move_insert(d.current_layout_name, a, (12.0, 10.0))
        assert d.reroute_wires_after_symbol_moves({a})
    d.rebuild_index()
    bx2, by2 = insert_world_xy(d.doc, br)
    fp1 = lwpolyline_first_vertex_xy(d.doc, nw)
    assert math.hypot(fp1[0] - bx2, fp1[1] - by2) < 0.35


def test_move_wire_branch_reroutes_outgoing_wires():
    d = LogicDiagram.new()
    with d.begin("place"):
        a = d.place_and_gate(1, (6.0, 10.0))
        b = d.place_and_gate(1, (56.0, 14.0))
        c = d.place_and_gate(1, (34.0, 40.0))
    d.rebuild_index()
    with d.begin("branch"):
        br = d.place_wire_branch((34.0, 12.0))
    with d.begin("wire"):
        d.connect_ports(a, "OUT0_LOGIC", br, "IN0_MULTI")
        d.connect_ports(br, "OUT0_MULTI", b, "IN0_LOGIC")
        nw = d.connect_ports(br, "OUT0_MULTI", c, "IN0_LOGIC")
    d.rebuild_index()
    cx, cy = insert_world_xy(d.doc, br)
    assert d.move_wire_branch(br, (cx + GRID_PITCH, cy))
    d.rebuild_index()
    ncx, ncy = insert_world_xy(d.doc, br)
    fp = lwpolyline_first_vertex_xy(d.doc, nw)
    assert math.hypot(fp[0] - ncx, fp[1] - ncy) < 0.35
    assert abs(ncx - cx) + abs(ncy - cy) > 1e-6


def test_clamp_branch_arc_fraction_t_insets_from_ends():
    L = 100.0
    eps = 0.005
    assert abs(clamp_branch_arc_fraction_t(0.0, L) - eps) < 1e-9
    assert abs(clamp_branch_arc_fraction_t(1.0, L) - (1.0 - eps)) < 1e-9
    assert abs(clamp_branch_arc_fraction_t(0.5, L) - 0.5) < 1e-9


def test_polyline_arc_length_helpers_basic():
    pts = [(0.0, 0.0), (4.0, 0.0), (4.0, 3.0)]
    assert abs(polyline_chain_length_xy(pts) - 7.0) < 1e-9
    q = point_on_polyline_at_arc_length_xy(pts, 5.0)
    assert abs(q[0] - 4.0) < 1e-9 and abs(q[1] - 1.0) < 1e-9
    s, L, qc = distance_from_polyline_start_to_closest_point_xy(4.0, 1.0, pts)
    assert abs(L - 7.0) < 1e-9 and abs(s - 5.0) < 1e-9
    assert abs(qc[0] - 4.0) < 1e-9 and abs(qc[1] - 1.0) < 1e-9


def test_delete_branch_removes_insert_and_incident_wires():
    d = LogicDiagram.new()
    with d.begin("place"):
        a = d.place_and_gate(1, (10.0, 10.0))
        c = d.place_and_gate(1, (24.0, 40.0))
    d.rebuild_index()
    with d.begin("branch"):
        br = d.place_wire_branch((24.0, 12.0))
    with d.begin("wire"):
        w0 = d.connect_ports(a, "OUT0_LOGIC", br, "IN0_MULTI")
        w1 = d.connect_ports(br, "OUT0_MULTI", c, "IN0_LOGIC")
    with d.begin("del"):
        d.delete_by_uid(br)
    assert find_entity_by_uid(d.doc, br) is None
    assert find_entity_by_uid(d.doc, w0) is None
    assert find_entity_by_uid(d.doc, w1) is None
