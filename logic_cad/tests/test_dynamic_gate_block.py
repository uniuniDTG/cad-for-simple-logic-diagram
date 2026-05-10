"""Dynamic AND/OR block structure."""

from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.core.model.constants import (
    GATE_STATIC_LABEL_AND,
    GATE_STATIC_LABEL_OR,
    GATE_STATIC_TEXT_HEIGHT_AND_MM,
    GATE_STATIC_TEXT_HEIGHT_OR_MM,
)
from logic_cad.core.services.dynamic_gate_factory import (
    GATE_LABEL0_TEXT_HEIGHT_MM,
    GATE_SYM_TEXT_HEIGHT_MM,
    gate_view_geometry_from_block_name,
)


def test_and_block_name_and_ports():
    d = LogicDiagram.new()
    name = d.gates.ensure_and_block(d.doc, 3)
    assert name == "AND_3"
    blk = d.doc.blocks.get("AND_3")
    assert not any(e.dxftype() == "ARC" for e in blk)
    layers = [e.dxf.layer for e in blk if e.dxftype() == "POINT"]
    assert "LD_PORT_IN0_LOGIC" in layers
    assert "LD_PORT_IN2_LOGIC" in layers
    assert "LD_PORT_OUT0_LOGIC" in layers
    static = [e for e in blk if e.dxftype() == "ATTDEF" and e.dxf.tag == "STATIC_LABEL0"]
    assert static and static[0].dxf.text == GATE_STATIC_LABEL_AND
    sym = [e for e in blk if e.dxftype() == "ATTDEF" and e.dxf.tag == "SYM"]
    assert sym and sym[0].dxf.text == "AND_3"
    assert float(sym[0].dxf.height) == GATE_SYM_TEXT_HEIGHT_MM
    st = static[0]
    assert float(st.dxf.height) == GATE_STATIC_TEXT_HEIGHT_AND_MM
    lbl = [e for e in blk if e.dxftype() == "ATTDEF" and e.dxf.tag == "LABEL0"]
    assert lbl and float(lbl[0].dxf.height) == GATE_LABEL0_TEXT_HEIGHT_MM


def test_or_block_reuse_and_topology():
    d = LogicDiagram.new()
    a = d.gates.ensure_or_block(d.doc, 2)
    b = d.gates.ensure_or_block(d.doc, 2)
    assert a == b == "OR_2"
    blk = d.doc.blocks.get("OR_2")
    layers = [e.dxf.layer for e in blk if e.dxftype() == "POINT"]
    assert "LD_PORT_IN0_LOGIC" in layers
    assert "LD_PORT_IN1_LOGIC" in layers
    assert "LD_PORT_OUT0_LOGIC" in layers
    static = [e for e in blk if e.dxftype() == "ATTDEF" and e.dxf.tag == "STATIC_LABEL0"]
    assert static and static[0].dxf.text == GATE_STATIC_LABEL_OR
    assert float(static[0].dxf.height) == GATE_STATIC_TEXT_HEIGHT_OR_MM
    sym = [e for e in blk if e.dxftype() == "ATTDEF" and e.dxf.tag == "SYM"]
    assert sym and sym[0].dxf.text == "OR_2"


def test_gate_view_geometry_matches_factory():
    g = gate_view_geometry_from_block_name("AND_2")
    assert g is not None
    assert g.xL == 2.0 and g.xR == 6.0 and g.x_out == 8.0
    assert g.yT == 6.0 and g.y_sq_B == 1.0 and g.y_sq_T == 5.0 and g.mid_y == 3.0
    assert g.stub_ys == (2.0, 4.0)
    assert g.sym_y == -0.38
    g3 = gate_view_geometry_from_block_name("AND_3")
    assert g3 is not None and g3.yT == 8.0 and g3.stub_ys == (2.0, 4.0, 6.0)
    assert gate_view_geometry_from_block_name("NOT") is None


def test_and_ports_at_stub_tips():
    d = LogicDiagram.new()
    d.gates.ensure_and_block(d.doc, 2)
    blk = d.doc.blocks.get("AND_2")
    pts_in = sorted(
        [(float(e.dxf.location.x), float(e.dxf.location.y)) for e in blk if e.dxftype() == "POINT" and "IN" in e.dxf.layer],
        key=lambda t: t[1],
    )
    assert len(pts_in) == 2
    assert all(p[0] == 0.0 for p in pts_in)
    out = next(e for e in blk if e.dxftype() == "POINT" and "OUT" in e.dxf.layer)
    assert float(out.dxf.location.x) == 8.0 and float(out.dxf.location.y) == 3.0


def test_place_and_gate_sets_sym_sequential_not_block_name():
    d = LogicDiagram.new()
    uid = d.place_and_gate(2, (10.0, 10.0))
    ins = d.symbols.insert_by_uid(d.current_layout_name, uid)
    assert ins is not None
    assert ins.dxf.name == "AND_2"
    sym = next(a.dxf.text for a in ins.attribs if a.dxf.tag == "SYM")
    assert sym == "AND_1"


def test_change_gate_inputs_preserves_out_world_position():
    d = LogicDiagram.new()
    uid = d.place_and_gate(2, (10.0, 10.0))
    out_before = d.index.get_port_world(uid, "OUT0_LOGIC")
    assert out_before is not None
    sym_before = next(a.dxf.text for a in d.symbols.insert_by_uid(d.current_layout_name, uid).attribs if a.dxf.tag == "SYM")
    d.change_gate_inputs(uid, 3)
    out_after = d.index.get_port_world(uid, "OUT0_LOGIC")
    assert out_after is not None
    assert abs(out_after[0] - out_before[0]) < 1e-6
    assert abs(out_after[1] - out_before[1]) < 1e-6
    ins = d.symbols.insert_by_uid(d.current_layout_name, uid)
    assert ins is not None
    assert ins.dxf.name == "AND_3"
    sym_after = next(a.dxf.text for a in ins.attribs if a.dxf.tag == "SYM")
    assert sym_after == sym_before == "AND_1"
