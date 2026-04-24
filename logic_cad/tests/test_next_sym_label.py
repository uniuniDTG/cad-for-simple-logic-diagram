"""Incremental SYM labels on place_symbol (ref=None)."""

from logic_cad.core.logic_diagram import LogicDiagram


def test_place_symbol_auto_sym_not_sequence():
    d = LogicDiagram.new()
    layout = d.current_layout_name
    with d.begin("p"):
        u1 = d.place_symbol("NOT", (10.0, 10.0))
        u2 = d.place_symbol("NOT", (20.0, 10.0))
    assert u1 != u2
    ins1 = d.symbols.insert_by_uid(layout, u1)
    ins2 = d.symbols.insert_by_uid(layout, u2)
    assert ins1 is not None and ins2 is not None
    s1 = s2 = ""
    for a in ins1.attribs:
        if str(a.dxf.tag) == "SYM":
            s1 = str(a.dxf.text or "")
            break
    for a in ins2.attribs:
        if str(a.dxf.tag) == "SYM":
            s2 = str(a.dxf.text or "")
            break
    assert s1 == "NOT_1"
    assert s2 == "NOT_2"
    for ins in (ins1, ins2):
        for a in ins.attribs:
            if str(a.dxf.tag) == "SYM":
                assert int(getattr(a.dxf, "invisible", 0)) == 1
                break


def test_next_sym_label_uses_full_block_name():
    d = LogicDiagram.new()
    ss = d.symbols
    layout = d.current_layout_name
    assert ss.next_sym_label(layout, "NOT") == "NOT_1"
    with d.begin("p"):
        d.place_symbol("NOT", (10.0, 10.0))
    assert ss.next_sym_label(layout, "NOT") == "NOT_2"


def test_legacy_not_without_underscore_counts_toward_next() -> None:
    """Old SYM 'NOT1' still reserves numeric slot for new NOT_n style."""
    d = LogicDiagram.new()
    ss = d.symbols
    layout = d.current_layout_name
    with d.begin("p"):
        d.place_symbol("NOT", (10.0, 10.0), ref="NOT1")
    assert ss.next_sym_label(layout, "NOT") == "NOT_2"


def test_gate_sym_labels_sequential_per_kind() -> None:
    d = LogicDiagram.new()
    layout = d.current_layout_name
    with d.begin("g"):
        u_and2 = d.place_and_gate(2, (10.0, 10.0))
        u_and3 = d.place_and_gate(3, (20.0, 10.0))
        u_or = d.place_or_gate(2, (30.0, 10.0))
    def sym(uid: str) -> str:
        ins = d.symbols.insert_by_uid(layout, uid)
        assert ins is not None
        return next(a.dxf.text for a in ins.attribs if a.dxf.tag == "SYM")

    assert sym(u_and2) == "AND_1"
    assert sym(u_and3) == "AND_2"
    assert sym(u_or) == "OR_1"
