"""IndexStore.connected_endpoint_ports mirrors wire XDATA endpoints."""

from logic_cad.core.logic_diagram import LogicDiagram


def test_connected_endpoint_ports_lists_both_wire_endpoints():
    d = LogicDiagram.new()
    with d.begin("t"):
        wb = d.place_wire_branch((0.0, 0.0))
        a = d.place_and_gate(2, (12.0, 0.0))
        d.connect_ports(a, "OUT0_LOGIC", wb, "IN0_MULTI")
    d.rebuild_index()
    idx = d.index
    assert (wb, "IN0_MULTI") in idx.connected_endpoint_ports
    assert (a, "OUT0_LOGIC") in idx.connected_endpoint_ports
    assert (wb, "OUT0_MULTI") not in idx.connected_endpoint_ports


def test_connected_endpoint_ports_wire_branch_in_and_out():
    d = LogicDiagram.new()
    with d.begin("t"):
        wb = d.place_wire_branch((0.0, 0.0))
        src = d.place_and_gate(2, (-12.0, 0.0))
        dst = d.place_and_gate(2, (12.0, 0.0))
        d.connect_ports(src, "OUT0_LOGIC", wb, "IN0_MULTI")
        d.connect_ports(wb, "OUT0_MULTI", dst, "IN0_LOGIC")
    d.rebuild_index()
    idx = d.index
    assert (wb, "IN0_MULTI") in idx.connected_endpoint_ports
    assert (wb, "OUT0_MULTI") in idx.connected_endpoint_ports
