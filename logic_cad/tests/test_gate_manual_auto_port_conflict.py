"""Manual (skip) gate wires must not collide with auto-assigned IN indices after optimize."""

from logic_cad.core.logic_diagram import LogicDiagram

from logic_cad.tests.support.and_or_gates import and_or_gate_input_count_for_symbol_uid


def _input_ports_to_gate(diagram: LogicDiagram, gate_uid: str) -> list[str]:
    out: list[str] = []
    for _e, _wu, meta in diagram.wires.iter_wire_meta(diagram.current_layout_name):
        if meta.get("dst") != gate_uid:
            continue
        dp = meta.get("dst_port") or ""
        if dp.startswith("IN") and "LOGIC" in dp:
            out.append(str(dp))
    return sorted(out)


def test_optimize_assigns_auto_only_to_free_ins_when_manual_occupies_in1():
    d = LogicDiagram.new()
    with d.begin("place"):
        m = d.place_and_gate(1, (10.0, 10.0))
        a = d.place_and_gate(1, (10.0, 20.0))
        b = d.place_and_gate(1, (10.0, 30.0))
        g = d.place_and_gate(3, (50.0, 20.0))
    d.rebuild_index()
    p0 = d.index.get_port_world(m, "OUT0_LOGIC")
    p1 = d.index.get_port_world(g, "IN1_LOGIC")
    assert p0 is not None and p1 is not None
    bends = [(p0[0], p1[1])]
    if abs(p0[0] - p1[0]) < 1e-9 or abs(p0[1] - p1[1]) < 1e-9:
        bends = []
    with d.begin("wm"):
        d.connect_ports_manual(m, "OUT0_LOGIC", g, "IN1_LOGIC", bends)
    with d.begin("wa"):
        d.connect_ports(a, "OUT0_LOGIC", g, "IN0_LOGIC")
        d.connect_ports(b, "OUT0_LOGIC", g, "IN2_LOGIC")
    d.optimize_and_or_input_ports(g)
    ports = _input_ports_to_gate(d, g)
    assert len(ports) == 3
    assert len(set(ports)) == 3
    assert set(ports) == {"IN0_LOGIC", "IN1_LOGIC", "IN2_LOGIC"}


def test_fourth_auto_wire_expands_after_manual_plus_two_auto():
    d = LogicDiagram.new()
    with d.begin("place"):
        m = d.place_and_gate(1, (10.0, 10.0))
        a = d.place_and_gate(1, (10.0, 20.0))
        b = d.place_and_gate(1, (10.0, 30.0))
        c = d.place_and_gate(1, (10.0, 40.0))
        g = d.place_and_gate(3, (50.0, 22.0))
    d.rebuild_index()
    p0 = d.index.get_port_world(m, "OUT0_LOGIC")
    p1 = d.index.get_port_world(g, "IN1_LOGIC")
    assert p0 is not None and p1 is not None
    bends = [(p0[0], p1[1])]
    if abs(p0[0] - p1[0]) < 1e-9 or abs(p0[1] - p1[1]) < 1e-9:
        bends = []
    with d.begin("wm"):
        d.connect_ports_manual(m, "OUT0_LOGIC", g, "IN1_LOGIC", bends)
    with d.begin("wa"):
        d.connect_ports(a, "OUT0_LOGIC", g, "IN0_LOGIC")
        d.connect_ports(b, "OUT0_LOGIC", g, "IN2_LOGIC")
    d.rebuild_index()
    assert and_or_gate_input_count_for_symbol_uid(d, g) == 3
    with d.begin("w4"):
        d.connect_ports(c, "OUT0_LOGIC", g, "IN0_LOGIC")
    assert and_or_gate_input_count_for_symbol_uid(d, g) == 4
    ports = _input_ports_to_gate(d, g)
    assert len(ports) == 4
    assert len(set(ports)) == 4
