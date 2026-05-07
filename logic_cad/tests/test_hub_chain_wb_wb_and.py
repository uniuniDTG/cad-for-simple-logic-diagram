"""WIRE_BRANCH chain behavior with INOUT0_MULTI single-port hubs."""

from __future__ import annotations

from logic_cad.core.logic_diagram import LogicDiagram

from logic_cad.tests.support.wire_meta import (
    wire_meta_dicts_for_layout,
)


def _wire_between(metas: list[dict], a: str, b: str) -> dict | None:
    for m in metas:
        su, du = str(m.get("src")), str(m.get("dst"))
        if {su, du} == {a, b}:
            return m
    return None


def test_wb1_to_wb2_hub_wire_keeps_click_order():
    d = LogicDiagram.new()
    with d.begin("place"):
        wb1 = d.place_wire_branch((50.0, 10.0))
        wb2 = d.place_wire_branch((100.0, 10.0))
    d.rebuild_index()
    with d.begin("w1"):
        d.connect_ports(wb1, "INOUT0_MULTI", wb2, "INOUT0_MULTI")
    d.rebuild_index()
    metas = wire_meta_dicts_for_layout(d, d.current_layout_name)
    assert len(metas) == 1
    m1 = _wire_between(metas, wb1, wb2)
    assert m1 is not None
    assert m1["src"] == wb1 and m1["src_port"] == "INOUT0_MULTI"
    assert m1["dst"] == wb2 and m1["dst_port"] == "INOUT0_MULTI"


def test_and2_to_wb2_adds_second_wire_without_reversal():
    d = LogicDiagram.new()
    with d.begin("place"):
        wb1 = d.place_wire_branch((50.0, 10.0))
        wb2 = d.place_wire_branch((100.0, 10.0))
        and2 = d.place_and_gate(2, (150.0, 10.0))
    d.rebuild_index()
    with d.begin("w1"):
        d.connect_ports(wb1, "INOUT0_MULTI", wb2, "INOUT0_MULTI")
    d.rebuild_index()
    with d.begin("w2"):
        d.connect_ports(and2, "OUT0_LOGIC", wb2, "INOUT0_MULTI")
    d.rebuild_index()
    metas = wire_meta_dicts_for_layout(d, d.current_layout_name)
    assert len(metas) == 2
    m_gate = _wire_between(metas, and2, wb2)
    assert m_gate is not None
    assert m_gate["src"] == and2 and m_gate["dst"] == wb2
    m_hh = _wire_between(metas, wb1, wb2)
    assert m_hh is not None
    assert m_hh["src"] == wb1 and m_hh["src_port"] == "INOUT0_MULTI"
    assert m_hh["dst"] == wb2 and m_hh["dst_port"] == "INOUT0_MULTI"


def test_and2_to_wb2_allows_multiple_incoming_edges():
    d = LogicDiagram.new()
    with d.begin("place"):
        and1 = d.place_and_gate(1, (0.0, 10.0))
        wb1 = d.place_wire_branch((50.0, 10.0))
        wb2 = d.place_wire_branch((100.0, 10.0))
        and2 = d.place_and_gate(2, (150.0, 10.0))
    d.rebuild_index()
    with d.begin("w1"):
        d.connect_ports(and1, "OUT0_LOGIC", wb1, "INOUT0_MULTI")
        d.connect_ports(wb1, "INOUT0_MULTI", wb2, "INOUT0_MULTI")
    d.rebuild_index()
    with d.begin("w2"):
        d.connect_ports(and2, "OUT0_LOGIC", wb2, "INOUT0_MULTI")
    d.rebuild_index()
    assert len(wire_meta_dicts_for_layout(d, d.current_layout_name)) == 3


# ---------------------------------------------------------------------------
# New: AND1-WB1-WB2-AND2 full 4-step scenario (2-WB chain)
# ---------------------------------------------------------------------------


def test_and1_wb1_wb2_and2_four_steps():
    """INOUT hub chain accepts incremental links in click order."""
    d = LogicDiagram.new()
    with d.begin("place"):
        and1 = d.place_and_gate(2, (0.0, 10.0))
        wb1 = d.place_wire_branch((50.0, 10.0))
        wb2 = d.place_wire_branch((100.0, 10.0))
        and2 = d.place_and_gate(2, (150.0, 10.0))
    d.rebuild_index()

    # ① WB1→WB2
    with d.begin("w1"):
        d.connect_ports(wb1, "INOUT0_MULTI", wb2, "INOUT0_MULTI")
    d.rebuild_index()
    metas = wire_meta_dicts_for_layout(d, d.current_layout_name)
    assert len(metas) == 1
    m = _wire_between(metas, wb1, wb2)
    assert m is not None and m["src"] == wb1 and m["dst"] == wb2

    # ② AND2(OUT)→WB2
    with d.begin("w2"):
        d.connect_ports(and2, "OUT0_LOGIC", wb2, "INOUT0_MULTI")
    d.rebuild_index()
    metas = wire_meta_dicts_for_layout(d, d.current_layout_name)
    assert len(metas) == 2
    m_gate = _wire_between(metas, and2, wb2)
    assert m_gate is not None
    assert m_gate["src"] == and2 and m_gate["dst"] == wb2
    m_hh = _wire_between(metas, wb1, wb2)
    assert m_hh is not None
    assert m_hh["src"] == wb1 and m_hh["src_port"] == "INOUT0_MULTI"
    assert m_hh["dst"] == wb2 and m_hh["dst_port"] == "INOUT0_MULTI"

    # ③ AND1(OUT)→WB1
    with d.begin("w3"):
        d.connect_ports(and1, "OUT0_LOGIC", wb1, "INOUT0_MULTI")
    d.rebuild_index()

    # ④ WB1→AND1(IN): WB1 can fan-out
    with d.begin("w4"):
        d.connect_ports(wb1, "INOUT0_MULTI", and1, "IN0_LOGIC")
    d.rebuild_index()
    metas = wire_meta_dicts_for_layout(d, d.current_layout_name)
    assert len(metas) == 4
    assert any(
        m.get("src") == wb1
        and m.get("src_port") == "INOUT0_MULTI"
        and m.get("dst") == and1
        for m in metas
    )


# ---------------------------------------------------------------------------
# New: AND1-WB1-WB2-WB3-AND2 multi-level flip (3-WB chain)
# ---------------------------------------------------------------------------


def test_and2_to_wb3_multi_level_flip_3wb_chain():
    """3-WB chain keeps hub-hub direction in click order."""
    d = LogicDiagram.new()
    with d.begin("place"):
        and1 = d.place_and_gate(2, (0.0, 10.0))
        wb1 = d.place_wire_branch((50.0, 10.0))
        wb2 = d.place_wire_branch((100.0, 10.0))
        wb3 = d.place_wire_branch((150.0, 10.0))
        and2 = d.place_and_gate(2, (200.0, 10.0))
    d.rebuild_index()

    # ① Connect WB chain WB1→WB2→WB3
    with d.begin("w1"):
        d.connect_ports(wb1, "INOUT0_MULTI", wb2, "INOUT0_MULTI")
        d.connect_ports(wb2, "INOUT0_MULTI", wb3, "INOUT0_MULTI")
    d.rebuild_index()
    metas = wire_meta_dicts_for_layout(d, d.current_layout_name)
    assert len(metas) == 2
    assert _wire_between(metas, wb1, wb2) is not None
    assert _wire_between(metas, wb2, wb3) is not None

    # ② AND2(OUT)→WB3
    with d.begin("w2"):
        d.connect_ports(and2, "OUT0_LOGIC", wb3, "INOUT0_MULTI")
    d.rebuild_index()
    metas = wire_meta_dicts_for_layout(d, d.current_layout_name)
    assert len(metas) == 3

    # AND2→WB3 canonical
    m_gate = _wire_between(metas, and2, wb3)
    assert m_gate is not None
    assert m_gate["src"] == and2 and m_gate["dst"] == wb3
    # WB2→WB3 remains WB2→WB3
    m_wb3_wb2 = _wire_between(metas, wb2, wb3)
    assert m_wb3_wb2 is not None
    assert m_wb3_wb2["src"] == wb2 and m_wb3_wb2["src_port"] == "INOUT0_MULTI"
    assert m_wb3_wb2["dst"] == wb3 and m_wb3_wb2["dst_port"] == "INOUT0_MULTI"

    # WB1→WB2 remains WB1→WB2
    m_wb2_wb1 = _wire_between(metas, wb1, wb2)
    assert m_wb2_wb1 is not None
    assert m_wb2_wb1["src"] == wb1 and m_wb2_wb1["src_port"] == "INOUT0_MULTI"
    assert m_wb2_wb1["dst"] == wb2 and m_wb2_wb1["dst_port"] == "INOUT0_MULTI"

    # ③ AND1(OUT)→WB1
    with d.begin("w3"):
        d.connect_ports(and1, "OUT0_LOGIC", wb1, "INOUT0_MULTI")
    d.rebuild_index()

    # ④ WB1→AND1(IN)
    with d.begin("w4"):
        d.connect_ports(wb1, "INOUT0_MULTI", and1, "IN0_LOGIC")
    d.rebuild_index()
    metas = wire_meta_dicts_for_layout(d, d.current_layout_name)
    assert len(metas) == 5
    assert any(
        m.get("src") == wb1
        and m.get("src_port") == "INOUT0_MULTI"
        and m.get("dst") == and1
        for m in metas
    )


# ---------------------------------------------------------------------------
# New: 4-WB chain multi-level flip
# ---------------------------------------------------------------------------


def test_and2_to_wb4_multi_level_flip_4wb_chain():
    """4-WB chain accepts additional gate input without hub reversal."""
    d = LogicDiagram.new()
    with d.begin("place"):
        wb1 = d.place_wire_branch((50.0, 10.0))
        wb2 = d.place_wire_branch((100.0, 10.0))
        wb3 = d.place_wire_branch((150.0, 10.0))
        wb4 = d.place_wire_branch((200.0, 10.0))
        and2 = d.place_and_gate(2, (250.0, 10.0))
    d.rebuild_index()

    # ① Connect chain WB1→WB2→WB3→WB4
    with d.begin("w1"):
        d.connect_ports(wb1, "INOUT0_MULTI", wb2, "INOUT0_MULTI")
        d.connect_ports(wb2, "INOUT0_MULTI", wb3, "INOUT0_MULTI")
        d.connect_ports(wb3, "INOUT0_MULTI", wb4, "INOUT0_MULTI")
    d.rebuild_index()

    # ② AND2(OUT)→WB4
    with d.begin("w2"):
        d.connect_ports(and2, "OUT0_LOGIC", wb4, "INOUT0_MULTI")
    d.rebuild_index()

    metas = wire_meta_dicts_for_layout(d, d.current_layout_name)
    assert len(metas) == 4

    # AND2→WB4 canonical
    m_gate = _wire_between(metas, and2, wb4)
    assert m_gate is not None and m_gate["src"] == and2 and m_gate["dst"] == wb4
    # Hub-hub segments stay in initial click direction.
    for upstream, downstream in [(wb1, wb2), (wb2, wb3), (wb3, wb4)]:
        m = _wire_between(metas, upstream, downstream)
        assert m is not None, f"wire between {upstream!r} and {downstream!r} not found"
        assert m["src"] == upstream and m["src_port"] == "INOUT0_MULTI"
        assert m["dst"] == downstream and m["dst_port"] == "INOUT0_MULTI"
