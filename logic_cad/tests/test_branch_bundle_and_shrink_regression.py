"""Regression: gate-input bundle with WIRE_BRANCH fan-in + AND/OR shrink."""

from logic_cad.core.logic_diagram import LogicDiagram

from logic_cad.tests.support.and_or_gates import and_or_gate_input_count_for_symbol_uid
from logic_cad.tests.support.diagram_entities import ld_app_dict_for_uid


def test_gate_input_bundle_includes_wires_from_wire_branch():
    d = LogicDiagram.new()
    layout = d.current_layout_name
    with d.begin("place"):
        driver = d.place_and_gate(1, (10.0, 10.0))
        gate = d.place_and_gate(2, (48.0, 12.0))
    d.rebuild_index()
    with d.begin("br"):
        hub = d.place_wire_branch((28.0, 12.0))
    with d.begin("w"):
        d.connect_ports(driver, "OUT0_LOGIC", hub, "INOUT0_MULTI")
        leg0 = d.connect_ports(hub, "INOUT0_MULTI", gate, "IN0_LOGIC")
        leg1 = d.connect_ports(hub, "INOUT0_MULTI", gate, "IN1_LOGIC")
    d.rebuild_index()
    all_rows = d.wires._gate_input_rows_all(layout, gate)
    bundle_rows = d.wires._gate_input_rows(layout, gate)
    assert len(all_rows) == 2
    assert len(bundle_rows) == 2
    assert ld_app_dict_for_uid(d.doc, leg0).get("dst_port") == "IN0_LOGIC"
    assert ld_app_dict_for_uid(d.doc, leg1).get("dst_port") == "IN1_LOGIC"


def test_optimize_gate_ports_with_wire_branch_fanin():
    d = LogicDiagram.new()
    layout = d.current_layout_name
    with d.begin("place"):
        driver = d.place_and_gate(1, (10.0, 10.0))
        gate = d.place_and_gate(2, (48.0, 12.0))
    d.rebuild_index()
    hub = d.place_wire_branch((28.0, 12.0))
    with d.begin("w"):
        d.connect_ports(driver, "OUT0_LOGIC", hub, "INOUT0_MULTI")
        leg_uid = d.connect_ports(hub, "INOUT0_MULTI", gate, "IN1_LOGIC")
        trunk_uid = d.connect_ports(hub, "INOUT0_MULTI", gate, "IN0_LOGIC")
    d.rebuild_index()
    assert d.optimize_and_or_input_ports(gate)
    d.rebuild_index()
    assert {
        ld_app_dict_for_uid(d.doc, leg_uid).get("dst_port"),
        ld_app_dict_for_uid(d.doc, trunk_uid).get("dst_port"),
    } == {"IN0_LOGIC", "IN1_LOGIC"}


def test_delete_middle_input_shrink_keeps_branch_leg_dst_port():
    d = LogicDiagram.new()
    with d.begin("place"):
        driver = d.place_and_gate(1, (10.0, 10.0))
        s2 = d.place_and_gate(1, (10.0, 26.0))
        s3 = d.place_and_gate(1, (10.0, 32.0))
        gate = d.place_and_gate(2, (48.0, 18.0))
    d.rebuild_index()
    hub = d.place_wire_branch((28.0, 18.0))
    with d.begin("w0"):
        d.connect_ports(driver, "OUT0_LOGIC", hub, "INOUT0_MULTI")
        leg_uid = d.connect_ports(hub, "INOUT0_MULTI", gate, "IN1_LOGIC")
        d.connect_ports(hub, "INOUT0_MULTI", gate, "IN0_LOGIC")
    d.rebuild_index()
    leg_port = ld_app_dict_for_uid(d.doc, leg_uid).get("dst_port")
    assert leg_port in ("IN0_LOGIC", "IN1_LOGIC")
    with d.begin("grow"):
        d.change_gate_inputs(gate, 4)
    d.rebuild_index()
    with d.begin("w12"):
        w_s2 = d.connect_ports(s2, "OUT0_LOGIC", gate, "IN2_LOGIC")
        d.connect_ports(s3, "OUT0_LOGIC", gate, "IN3_LOGIC")
    d.rebuild_index()
    assert ld_app_dict_for_uid(d.doc, leg_uid).get("dst_port") == leg_port
    assert and_or_gate_input_count_for_symbol_uid(d, gate) == 4
    with d.begin("del"):
        d.delete_by_uid(w_s2)
    d.rebuild_index()
    assert ld_app_dict_for_uid(d.doc, leg_uid).get("dst_port") == leg_port
    assert and_or_gate_input_count_for_symbol_uid(d, gate) == 3


def test_full_layout_shrink_pass_reduces_oversized_gate():
    d = LogicDiagram.new()
    with d.begin("place"):
        s0 = d.place_and_gate(1, (5.0, 10.0))
        s1 = d.place_and_gate(1, (5.0, 16.0))
        g = d.place_and_gate(2, (45.0, 16.0))
    d.rebuild_index()
    with d.begin("w"):
        d.connect_ports(s0, "OUT0_LOGIC", g, "IN0_LOGIC")
        d.connect_ports(s1, "OUT0_LOGIC", g, "IN1_LOGIC")
    d.rebuild_index()
    assert and_or_gate_input_count_for_symbol_uid(d, g) == 2
    with d.begin("grow"):
        d.change_gate_inputs(g, 3)
    d.rebuild_index()
    assert and_or_gate_input_count_for_symbol_uid(d, g) == 3
    d._shrink_all_and_or_gates_to_required()
    assert and_or_gate_input_count_for_symbol_uid(d, g) == 2
