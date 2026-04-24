"""WIRE_BRANCH chain: hub–hub tail reversal when adding a gate into a full WB IN.

Topology (50mm spacing):

    WB1 — WB2 — AND2   (after ① then ②; L1 reverses so AND2 drives WB2)

When the upstream hub already has a wire into its IN0_MULTI (e.g. a gate), reversing
the tail would create a double-IN on that hub — connection must fail (no hub-out fallback).

Multi-level flip (3+ WB chain):
    WB1 — WB2 — WB3 — AND2
    ② AND2→WB3 traverses all intermediate hub-hub segments and flips them all.
"""

from __future__ import annotations

import pytest

from logic_cad.core.logic_diagram import LogicDiagram

from logic_cad.tests.support.wire_meta import (
    assert_wire_meta_canonical_out_to_in,
    wire_meta_dicts_for_layout,
)


def _wire_between(metas: list[dict], a: str, b: str) -> dict | None:
    for m in metas:
        su, du = str(m.get("src")), str(m.get("dst"))
        if {su, du} == {a, b}:
            return m
    return None


def test_wb1_to_wb2_hub_wire_canonical():
    """① WB1 OUT → WB2 IN: single hub–hub segment (upstream WB has no IN wire)."""
    d = LogicDiagram.new()
    with d.begin("place"):
        wb1 = d.place_wire_branch((50.0, 10.0))
        wb2 = d.place_wire_branch((100.0, 10.0))
    d.rebuild_index()
    with d.begin("w1"):
        d.connect_ports(wb1, "OUT0_MULTI", wb2, "IN0_MULTI")
    d.rebuild_index()
    metas = wire_meta_dicts_for_layout(d, d.current_layout_name)
    assert len(metas) == 1
    m1 = _wire_between(metas, wb1, wb2)
    assert m1 is not None
    assert m1["src"] == wb1 and m1["src_port"] == "OUT0_MULTI"
    assert m1["dst"] == wb2 and m1["dst_port"] == "IN0_MULTI"
    assert_wire_meta_canonical_out_to_in(m1)


def test_and2_to_wb2_succeeds_after_reversing_hub_tail():
    """① WB1→WB2; ② AND2→WB2: reverse tail so AND2 drives WB2 (upstream WB1 IN was free)."""
    d = LogicDiagram.new()
    with d.begin("place"):
        wb1 = d.place_wire_branch((50.0, 10.0))
        wb2 = d.place_wire_branch((100.0, 10.0))
        and2 = d.place_and_gate(2, (150.0, 10.0))
    d.rebuild_index()
    with d.begin("w1"):
        d.connect_ports(wb1, "OUT0_MULTI", wb2, "IN0_MULTI")
    d.rebuild_index()
    with d.begin("w2"):
        d.connect_ports(and2, "OUT0_LOGIC", wb2, "IN0_MULTI")
    d.rebuild_index()
    metas = wire_meta_dicts_for_layout(d, d.current_layout_name)
    assert len(metas) == 2
    m_gate = _wire_between(metas, and2, wb2)
    assert m_gate is not None
    assert m_gate["src"] == and2 and m_gate["dst"] == wb2
    assert_wire_meta_canonical_out_to_in(m_gate)
    m_hh = _wire_between(metas, wb1, wb2)
    assert m_hh is not None
    assert m_hh["src"] == wb2 and m_hh["src_port"] == "OUT0_MULTI"
    assert m_hh["dst"] == wb1 and m_hh["dst_port"] == "IN0_MULTI"
    assert_wire_meta_canonical_out_to_in(m_hh)


def test_and2_to_wb2_raises_when_upstream_wb_in_used_by_gate():
    """① AND1→WB1→WB2; ② AND2→WB2 cannot reverse tail (WB1 IN already fed by gate)."""
    d = LogicDiagram.new()
    with d.begin("place"):
        and1 = d.place_and_gate(1, (0.0, 10.0))
        wb1 = d.place_wire_branch((50.0, 10.0))
        wb2 = d.place_wire_branch((100.0, 10.0))
        and2 = d.place_and_gate(2, (150.0, 10.0))
    d.rebuild_index()
    with d.begin("w1"):
        d.connect_ports(and1, "OUT0_LOGIC", wb1, "IN0_MULTI")
        d.connect_ports(wb1, "OUT0_MULTI", wb2, "IN0_MULTI")
    d.rebuild_index()
    with d.begin("w2"), pytest.raises(ValueError, match="配線分岐の入力は1本まで"):
        d.connect_ports(and2, "OUT0_LOGIC", wb2, "IN0_MULTI")


# ---------------------------------------------------------------------------
# New: AND1-WB1-WB2-AND2 full 4-step scenario (2-WB chain)
# ---------------------------------------------------------------------------


def test_and1_wb1_wb2_and2_four_steps():
    """Full 4-step scenario: AND1-(50)-WB1-(50)-WB2-(50)-AND2.

    ① WB1→WB2 (initial hub-hub wire)
    ② AND2(OUT)→WB2: 1-level flip → WB2(OUT)→WB1(IN), AND2→WB2(IN)
    ③ AND1(OUT)→WB1(IN): must FAIL (AND2 at WB2's IN blocks chain flip)
    ④ WB1(OUT)→AND1(IN): must succeed (WB1 fans out)
    """
    d = LogicDiagram.new()
    with d.begin("place"):
        and1 = d.place_and_gate(2, (0.0, 10.0))
        wb1 = d.place_wire_branch((50.0, 10.0))
        wb2 = d.place_wire_branch((100.0, 10.0))
        and2 = d.place_and_gate(2, (150.0, 10.0))
    d.rebuild_index()

    # ① WB1→WB2
    with d.begin("w1"):
        d.connect_ports(wb1, "OUT0_MULTI", wb2, "IN0_MULTI")
    d.rebuild_index()
    metas = wire_meta_dicts_for_layout(d, d.current_layout_name)
    assert len(metas) == 1
    m = _wire_between(metas, wb1, wb2)
    assert m is not None and m["src"] == wb1 and m["dst"] == wb2

    # ② AND2(OUT)→WB2: flips L1 so WB2→WB1
    with d.begin("w2"):
        d.connect_ports(and2, "OUT0_LOGIC", wb2, "IN0_MULTI")
    d.rebuild_index()
    metas = wire_meta_dicts_for_layout(d, d.current_layout_name)
    assert len(metas) == 2
    m_gate = _wire_between(metas, and2, wb2)
    assert m_gate is not None
    assert m_gate["src"] == and2 and m_gate["dst"] == wb2
    assert_wire_meta_canonical_out_to_in(m_gate)
    m_hh = _wire_between(metas, wb1, wb2)
    assert m_hh is not None
    assert m_hh["src"] == wb2 and m_hh["src_port"] == "OUT0_MULTI"
    assert m_hh["dst"] == wb1 and m_hh["dst_port"] == "IN0_MULTI"
    assert_wire_meta_canonical_out_to_in(m_hh)

    # ③ AND1(OUT)→WB1(IN): chain blocked by AND2 at WB2 — must raise
    with d.begin("w3"), pytest.raises(ValueError, match="配線分岐の入力は1本まで"):
        d.connect_ports(and1, "OUT0_LOGIC", wb1, "IN0_MULTI")
    d.rebuild_index()

    # ④ WB1(OUT)→AND1(IN): WB1 can fan-out, must succeed
    with d.begin("w4"):
        d.connect_ports(wb1, "OUT0_MULTI", and1, "IN0_LOGIC")
    d.rebuild_index()
    metas = wire_meta_dicts_for_layout(d, d.current_layout_name)
    assert len(metas) == 3
    m_fan = _wire_between(metas, wb1, and1)
    assert m_fan is not None
    assert m_fan["src"] == wb1 and m_fan["src_port"] == "OUT0_MULTI"
    assert m_fan["dst"] == and1
    assert_wire_meta_canonical_out_to_in(m_fan)


# ---------------------------------------------------------------------------
# New: AND1-WB1-WB2-WB3-AND2 multi-level flip (3-WB chain)
# ---------------------------------------------------------------------------


def test_and2_to_wb3_multi_level_flip_3wb_chain():
    """3-WB chain: ①WB1→WB2→WB3; ②AND2→WB3 triggers 2-level flip.

    AND1-(50)-WB1-(50)-WB2-(50)-WB3-(50)-AND2

    After ②: AND2→WB3(IN), WB3(OUT)→WB2(IN), WB2(OUT)→WB1(IN) — all canonical.
    ③ AND1(OUT)→WB1(IN): must FAIL (AND2 blocks the full chain).
    ④ WB1(OUT)→AND1(IN): must succeed.
    """
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
        d.connect_ports(wb1, "OUT0_MULTI", wb2, "IN0_MULTI")
        d.connect_ports(wb2, "OUT0_MULTI", wb3, "IN0_MULTI")
    d.rebuild_index()
    metas = wire_meta_dicts_for_layout(d, d.current_layout_name)
    assert len(metas) == 2
    assert _wire_between(metas, wb1, wb2) is not None
    assert _wire_between(metas, wb2, wb3) is not None

    # ② AND2(OUT)→WB3: 2-level flip reverses both WB2→WB3 and WB1→WB2
    with d.begin("w2"):
        d.connect_ports(and2, "OUT0_LOGIC", wb3, "IN0_MULTI")
    d.rebuild_index()
    metas = wire_meta_dicts_for_layout(d, d.current_layout_name)
    assert len(metas) == 3

    # AND2→WB3 canonical
    m_gate = _wire_between(metas, and2, wb3)
    assert m_gate is not None
    assert m_gate["src"] == and2 and m_gate["dst"] == wb3
    assert_wire_meta_canonical_out_to_in(m_gate)

    # WB2→WB3 segment reversed: WB3(OUT)→WB2(IN)
    m_wb3_wb2 = _wire_between(metas, wb2, wb3)
    assert m_wb3_wb2 is not None
    assert m_wb3_wb2["src"] == wb3 and m_wb3_wb2["src_port"] == "OUT0_MULTI"
    assert m_wb3_wb2["dst"] == wb2 and m_wb3_wb2["dst_port"] == "IN0_MULTI"
    assert_wire_meta_canonical_out_to_in(m_wb3_wb2)

    # WB1→WB2 segment reversed: WB2(OUT)→WB1(IN)
    m_wb2_wb1 = _wire_between(metas, wb1, wb2)
    assert m_wb2_wb1 is not None
    assert m_wb2_wb1["src"] == wb2 and m_wb2_wb1["src_port"] == "OUT0_MULTI"
    assert m_wb2_wb1["dst"] == wb1 and m_wb2_wb1["dst_port"] == "IN0_MULTI"
    assert_wire_meta_canonical_out_to_in(m_wb2_wb1)

    # ③ AND1(OUT)→WB1(IN): blocked by AND2 at end of chain — must raise
    with d.begin("w3"), pytest.raises(ValueError, match="配線分岐の入力は1本まで"):
        d.connect_ports(and1, "OUT0_LOGIC", wb1, "IN0_MULTI")
    d.rebuild_index()

    # ④ WB1(OUT)→AND1(IN): must succeed
    with d.begin("w4"):
        d.connect_ports(wb1, "OUT0_MULTI", and1, "IN0_LOGIC")
    d.rebuild_index()
    metas = wire_meta_dicts_for_layout(d, d.current_layout_name)
    assert len(metas) == 4
    m_fan = _wire_between(metas, wb1, and1)
    assert m_fan is not None
    assert m_fan["src"] == wb1 and m_fan["src_port"] == "OUT0_MULTI"
    assert_wire_meta_canonical_out_to_in(m_fan)


# ---------------------------------------------------------------------------
# New: 4-WB chain multi-level flip
# ---------------------------------------------------------------------------


def test_and2_to_wb4_multi_level_flip_4wb_chain():
    """4-WB chain: ①WB1→WB2→WB3→WB4; ②AND2→WB4 triggers 3-level flip."""
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
        d.connect_ports(wb1, "OUT0_MULTI", wb2, "IN0_MULTI")
        d.connect_ports(wb2, "OUT0_MULTI", wb3, "IN0_MULTI")
        d.connect_ports(wb3, "OUT0_MULTI", wb4, "IN0_MULTI")
    d.rebuild_index()

    # ② AND2(OUT)→WB4: 3-level flip
    with d.begin("w2"):
        d.connect_ports(and2, "OUT0_LOGIC", wb4, "IN0_MULTI")
    d.rebuild_index()

    metas = wire_meta_dicts_for_layout(d, d.current_layout_name)
    assert len(metas) == 4

    # AND2→WB4 canonical
    m_gate = _wire_between(metas, and2, wb4)
    assert m_gate is not None and m_gate["src"] == and2 and m_gate["dst"] == wb4
    assert_wire_meta_canonical_out_to_in(m_gate)

    # Each segment reversed: flow is AND2→WB4→WB3→WB2→WB1
    for upstream, downstream in [(wb4, wb3), (wb3, wb2), (wb2, wb1)]:
        m = _wire_between(metas, upstream, downstream)
        assert m is not None, f"wire between {upstream!r} and {downstream!r} not found"
        assert m["src"] == upstream and m["src_port"] == "OUT0_MULTI"
        assert m["dst"] == downstream and m["dst_port"] == "IN0_MULTI"
        assert_wire_meta_canonical_out_to_in(m)
