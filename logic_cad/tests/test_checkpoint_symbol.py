"""CHECKPOINT insert: two-wire relay and capacity rules."""

from __future__ import annotations

import pytest

from logic_cad.core.model.constants import BLOCK_CHECKPOINT, ENTITY_TYPE_CHECKPOINT, ROUTE_ESCAPE_MM
from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.core.model.xdata import get_type

from logic_cad.tests.support.diagram_entities import ld_app_dict_for_uid


def test_place_checkpoint_sets_entity_type_and_block():
    d = LogicDiagram.new()
    cp = d.place_checkpoint((20.0, 30.0))
    d.rebuild_index()
    ins = d.symbols.insert_by_uid(d.current_layout_name, cp)
    assert ins is not None
    assert ins.dxf.name == BLOCK_CHECKPOINT
    assert get_type(ins) == ENTITY_TYPE_CHECKPOINT


def test_checkpoint_accepts_two_wires_then_rejects_third_input():
    d = LogicDiagram.new()
    with d.begin("place"):
        n = d.place_symbol("NOT", (10.0, 10.0))
        n2 = d.place_symbol("NOT", (10.0, 22.0))
        g = d.place_and_gate(2, (40.0, 10.0))
        cp = d.place_checkpoint((25.0, 10.0))
    d.rebuild_index()
    d.connect_ports(n, "OUT0_LOGIC", cp, "IN0_MULTI")
    d.connect_ports(cp, "OUT0_MULTI", g, "IN0_LOGIC")
    with pytest.raises(ValueError, match="入力は1本まで"):
        d.connect_ports(n2, "OUT0_LOGIC", cp, "IN0_MULTI")


def test_checkpoint_rejects_second_output():
    d = LogicDiagram.new()
    with d.begin("place"):
        n = d.place_symbol("NOT", (10.0, 10.0))
        g = d.place_and_gate(2, (50.0, 10.0))
        g2 = d.place_and_gate(2, (50.0, 20.0))
        cp = d.place_checkpoint((30.0, 10.0))
    d.rebuild_index()
    d.connect_ports(n, "OUT0_LOGIC", cp, "IN0_MULTI")
    d.connect_ports(cp, "OUT0_MULTI", g, "IN0_LOGIC")
    with pytest.raises(ValueError, match="出力は1本まで"):
        d.connect_ports(cp, "OUT0_MULTI", g2, "IN0_LOGIC")


def test_checkpoint_out_into_wire_branch_fanout():
    """CHECKPOINT の1本の OUT を WIRE_BRANCH に入れ、複数 OUT で扇状に出せる。"""
    d = LogicDiagram.new()
    with d.begin("place"):
        n = d.place_symbol("NOT", (10.0, 10.0))
        g1 = d.place_and_gate(2, (50.0, 10.0))
        g2 = d.place_and_gate(2, (50.0, 22.0))
        g3 = d.place_and_gate(2, (50.0, 34.0))
        cp = d.place_checkpoint((30.0, 10.0))
    d.rebuild_index()
    hub = d.place_wire_branch((40.0, 12.0))
    d.connect_ports(n, "OUT0_LOGIC", cp, "IN0_MULTI")
    d.connect_ports(cp, "OUT0_MULTI", hub, "IN0_MULTI")
    d.connect_ports(hub, "OUT0_MULTI", g1, "IN0_LOGIC")
    d.connect_ports(hub, "OUT0_MULTI", g2, "IN0_LOGIC")
    d.connect_ports(hub, "OUT0_MULTI", g3, "IN0_LOGIC")


def test_checkpoint_wrong_clicked_hub_port_normalized_when_gate_drives():
    """Hub-first normalize: gate OUT→checkpoint ignores the clicked hub port name."""
    d = LogicDiagram.new()
    with d.begin("place"):
        n = d.place_symbol("NOT", (10.0, 10.0))
        cp = d.place_checkpoint((25.0, 10.0))
    d.rebuild_index()
    wid = d.connect_ports(n, "OUT0_LOGIC", cp, "OUT0_MULTI")
    d.rebuild_index()
    meta = ld_app_dict_for_uid(d.doc, wid)
    assert meta.get("dst") == cp
    assert meta.get("dst_port") == "IN0_MULTI"


def test_checkpoint_out_port_escape_prefers_toward_direction():
    d = LogicDiagram.new()
    cp = d.place_checkpoint((100.0, 100.0))
    d.rebuild_index()
    esc = d.index.port_first_escape_world(
        d.doc, cp, "OUT0_MULTI", ROUTE_ESCAPE_MM, toward=(100.0, 130.0)
    )
    assert esc is not None
    assert abs(esc[0] - 100.0) < 0.6
    assert esc[1] > 100.0


def test_connect_to_checkpoint_when_src_is_east_of_cp():
    """Regression: CP had one-sided port cutout; routing from east could ovg no_path."""
    d = LogicDiagram.new()
    with d.begin("place"):
        n = d.place_symbol("NOT", (125.0, 160.0))
        cp = d.place_checkpoint((80.0, 118.0))
    d.rebuild_index()
    d.connect_ports(n, "OUT0_LOGIC", cp, "IN0_MULTI")
