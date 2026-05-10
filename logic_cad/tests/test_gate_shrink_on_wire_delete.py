"""AND/OR input count shrinks when wires to gate inputs are removed."""

from logic_cad.core.logic_diagram import LogicDiagram

from logic_cad.tests.support.and_or_gates import and_or_gate_input_count_for_symbol_uid


def test_delete_wire_keeps_and2_when_min_two_inputs():
    d = LogicDiagram.new()
    with d.begin("place"):
        left0 = d.place_and_gate(1, (10.0, 10.0))
        left1 = d.place_and_gate(1, (10.0, 16.0))
        g = d.place_and_gate(2, (30.0, 10.0))
    d.rebuild_index()
    with d.begin("w"):
        d.connect_ports(left0, "OUT0_LOGIC", g, "IN0_LOGIC")
        w2 = d.connect_ports(left1, "OUT0_LOGIC", g, "IN1_LOGIC")
    d.rebuild_index()
    assert and_or_gate_input_count_for_symbol_uid(d, g) == 2
    with d.begin("del"):
        d.delete_by_uid(w2)
    assert and_or_gate_input_count_for_symbol_uid(d, g) == 2


def test_disconnect_keeps_min_two_gate():
    d = LogicDiagram.new()
    with d.begin("place"):
        left = d.place_and_gate(1, (10.0, 10.0))
        g = d.place_and_gate(2, (30.0, 10.0))
    d.rebuild_index()
    with d.begin("w"):
        wuid = d.connect_ports(left, "OUT0_LOGIC", g, "IN0_LOGIC")
    d.rebuild_index()
    assert and_or_gate_input_count_for_symbol_uid(d, g) == 2
    with d.begin("disc"):
        d.disconnect(wuid)
    assert and_or_gate_input_count_for_symbol_uid(d, g) == 2


def test_delete_middle_inputs_shrinks_by_compaction():
    """Deleting IN1 and IN2 leaves holes; compaction then shrink yields AND_3."""
    d = LogicDiagram.new()
    with d.begin("place"):
        sources = [d.place_and_gate(1, (5.0, 10.0 + 6.0 * i)) for i in range(5)]
        g = d.place_and_gate(5, (50.0, 22.0))
    d.rebuild_index()
    wires: list[str] = []
    with d.begin("w"):
        for i, s in enumerate(sources):
            wires.append(d.connect_ports(s, "OUT0_LOGIC", g, f"IN{i}_LOGIC"))
    d.rebuild_index()
    assert and_or_gate_input_count_for_symbol_uid(d, g) == 5
    with d.begin("del"):
        d.delete_by_uid(wires[1])
        d.delete_by_uid(wires[2])
    d.rebuild_index()
    assert and_or_gate_input_count_for_symbol_uid(d, g) == 3


def test_delete_low_inputs_leaving_high_indices_shrinks_to_wire_count():
    """After deleting IN0–IN2, remaining wires on IN3/IN4 compact to IN0/IN1 and gate shrinks to AND_2."""
    d = LogicDiagram.new()
    with d.begin("place"):
        sources = [d.place_and_gate(1, (5.0, 10.0 + 6.0 * i)) for i in range(5)]
        g = d.place_and_gate(5, (50.0, 22.0))
    d.rebuild_index()
    wires: list[str] = []
    with d.begin("w"):
        for i, s in enumerate(sources):
            wires.append(d.connect_ports(s, "OUT0_LOGIC", g, f"IN{i}_LOGIC"))
    d.rebuild_index()
    assert and_or_gate_input_count_for_symbol_uid(d, g) == 5
    with d.begin("del"):
        d.delete_by_uid(wires[0])
        d.delete_by_uid(wires[1])
        d.delete_by_uid(wires[2])
    d.rebuild_index()
    assert and_or_gate_input_count_for_symbol_uid(d, g) == 2


def test_delete_highest_input_shrinks_by_one():
    d = LogicDiagram.new()
    with d.begin("place"):
        s0 = d.place_and_gate(1, (5.0, 10.0))
        s1 = d.place_and_gate(1, (5.0, 16.0))
        s2 = d.place_and_gate(1, (5.0, 22.0))
        g = d.place_and_gate(3, (45.0, 16.0))
    d.rebuild_index()
    with d.begin("w"):
        d.connect_ports(s0, "OUT0_LOGIC", g, "IN0_LOGIC")
        d.connect_ports(s1, "OUT0_LOGIC", g, "IN1_LOGIC")
        w2 = d.connect_ports(s2, "OUT0_LOGIC", g, "IN2_LOGIC")
    d.rebuild_index()
    assert and_or_gate_input_count_for_symbol_uid(d, g) == 3
    with d.begin("del"):
        d.delete_by_uid(w2)
    assert and_or_gate_input_count_for_symbol_uid(d, g) == 2


def test_delete_wire_branch_insert_shrinks_gate():
    d = LogicDiagram.new()
    with d.begin("place"):
        a = d.place_and_gate(1, (5.0, 10.0))
        b = d.place_and_gate(1, (30.0, 10.0))
        s0 = d.place_and_gate(1, (5.0, 20.0))
        s1 = d.place_and_gate(1, (5.0, 26.0))
        g = d.place_and_gate(3, (45.0, 16.0))
    d.rebuild_index()
    with d.begin("br"):
        hub = d.place_wire_branch((18.0, 10.0))
    with d.begin("w"):
        d.connect_ports(a, "OUT0_LOGIC", hub, "INOUT0_MULTI")
        d.connect_ports(hub, "INOUT0_MULTI", b, "IN0_LOGIC")
        d.connect_ports(s0, "OUT0_LOGIC", g, "IN0_LOGIC")
        d.connect_ports(s1, "OUT0_LOGIC", g, "IN1_LOGIC")
        d.connect_ports(hub, "INOUT0_MULTI", g, "IN2_LOGIC")
    d.rebuild_index()
    assert and_or_gate_input_count_for_symbol_uid(d, g) == 3
    with d.begin("del"):
        d.delete_by_uid(hub)
    d.rebuild_index()
    assert and_or_gate_input_count_for_symbol_uid(d, g) == 2


def test_delete_feeder_wire_to_branch_shrinks_gate():
    """Deleting the wire into WIRE_BRANCH removes fanout to the gate; touched endpoints shrink AND3."""
    d = LogicDiagram.new()
    with d.begin("place"):
        a = d.place_and_gate(1, (5.0, 10.0))
        b = d.place_and_gate(1, (30.0, 10.0))
        s0 = d.place_and_gate(1, (5.0, 22.0))
        s1 = d.place_and_gate(1, (5.0, 28.0))
        g = d.place_and_gate(3, (50.0, 18.0))
    d.rebuild_index()
    with d.begin("br"):
        hub = d.place_wire_branch((18.0, 10.0))
    with d.begin("w"):
        d.connect_ports(a, "OUT0_LOGIC", hub, "INOUT0_MULTI")
        d.connect_ports(hub, "INOUT0_MULTI", b, "IN0_LOGIC")
        d.connect_ports(s0, "OUT0_LOGIC", g, "IN0_LOGIC")
        d.connect_ports(s1, "OUT0_LOGIC", g, "IN2_LOGIC")
        w_hub_leg = d.connect_ports(hub, "INOUT0_MULTI", g, "IN1_LOGIC")
    d.rebuild_index()
    assert and_or_gate_input_count_for_symbol_uid(d, g) == 3
    with d.begin("del"):
        d.delete_by_uid(w_hub_leg)
    d.rebuild_index()
    assert and_or_gate_input_count_for_symbol_uid(d, g) == 2


def test_connect_ports_full_and2_then_third_wire_expands_to_and3():
    """Regression: bundle optimize must not raise (else undo rolls back change_gate_inputs)."""
    d = LogicDiagram.new()
    with d.begin("place"):
        s0 = d.place_and_gate(1, (5.0, 10.0))
        s1 = d.place_and_gate(1, (5.0, 16.0))
        g = d.place_and_gate(2, (40.0, 14.0))
    d.rebuild_index()
    with d.begin("w0"):
        d.connect_ports(s0, "OUT0_LOGIC", g, "IN0_LOGIC")
    with d.begin("w1"):
        d.connect_ports(s1, "OUT0_LOGIC", g, "IN1_LOGIC")
    assert and_or_gate_input_count_for_symbol_uid(d, g) == 2
    s2 = d.place_and_gate(1, (5.0, 22.0))
    d.rebuild_index()
    with d.begin("w2"):
        d.connect_ports(s2, "OUT0_LOGIC", g, "IN0_LOGIC")
    assert and_or_gate_input_count_for_symbol_uid(d, g) == 3
