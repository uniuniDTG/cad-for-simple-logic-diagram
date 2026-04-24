"""DocumentDelta undo/redo."""

from logic_cad.core.model.xdata import get_type
from logic_cad.core.undo.entity_serialize import restore_entity_from_payload, serialize_entity
from logic_cad.core.undo.history import destroy_entity
from logic_cad.core.logic_diagram import LogicDiagram


def test_serialize_insert_roundtrip_preserves_attrib_invisible() -> None:
    """Undo/redo restores INSERT via payload; SYM hidden flag must survive add_auto_attribs."""
    d = LogicDiagram.new()
    layout = d.current_layout_name
    uid = d.place_symbol("NOT", (10.0, 10.0), "N1")
    ins = d.symbols.insert_by_uid(layout, uid)
    assert ins is not None
    for a in ins.attribs:
        if str(a.dxf.tag) == "SYM":
            a.dxf.invisible = 1
            break
    else:
        raise AssertionError("NOT block should have SYM attrib")
    payload = serialize_entity(d.doc, ins)
    destroy_entity(d.doc, ins)
    restored = restore_entity_from_payload(d.doc, payload)
    assert restored is not None
    sym = next((a for a in restored.attribs if str(a.dxf.tag) == "SYM"), None)
    assert sym is not None
    assert int(sym.dxf.invisible) == 1


def test_undo_redo_place_and_wire():
    d = LogicDiagram.new()
    with d.begin("t1"):
        u1 = d.place_and_gate(2, (10, 10))
        u2 = d.place_symbol("NOT", (30, 10), "N1")
    w = None
    with d.begin("t2"):
        w = d.connect_ports(u2, "OUT0_LOGIC", u1, "IN0_LOGIC")
    assert w is not None
    assert d.index.wire_by_uid.get(w)
    assert d.undo()
    assert d.index.wire_by_uid.get(w) is None
    assert d.redo()
    assert d.index.wire_by_uid.get(w)


def test_undo_drop_gate_then_place_again_restores_block_geometry() -> None:
    """Undo of first drop removes block-definition entities, leaving a hollow AND_n; ensure must rebuild."""
    d = LogicDiagram.new()
    layout = d.current_layout_name
    with d.begin("drop"):
        d.place_and_gate(2, (10.0, 10.0))
    assert d.undo()
    u = d.place_and_gate(2, (20.0, 20.0))
    ins = d.symbols.insert_by_uid(layout, u)
    assert ins is not None
    assert len(list(ins.attribs)) >= 1
    static = next((a for a in ins.attribs if str(a.dxf.tag) == "STATIC_LABEL0"), None)
    assert static is not None
    assert str(static.dxf.text or "").strip() == "&"
    assert get_type(ins) == "AND"
    assert d.index.get_port_world(u, "OUT0_LOGIC") is not None


def test_undo_drop_or_gate_then_place_again_restores_block_geometry() -> None:
    """Same hollow-block case for OR_n."""
    d = LogicDiagram.new()
    layout = d.current_layout_name
    with d.begin("drop"):
        d.place_or_gate(2, (10.0, 10.0))
    assert d.undo()
    u = d.place_or_gate(2, (20.0, 20.0))
    ins = d.symbols.insert_by_uid(layout, u)
    assert ins is not None
    assert len(list(ins.attribs)) >= 1
    static = next((a for a in ins.attribs if str(a.dxf.tag) == "STATIC_LABEL0"), None)
    assert static is not None
    assert str(static.dxf.text or "").strip() == "≥1"
    assert get_type(ins) == "OR"
    assert d.index.get_port_world(u, "OUT0_LOGIC") is not None
