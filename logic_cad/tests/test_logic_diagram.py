"""Facade smoke."""

import pytest

from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.core.model.constants import FIRST_PAGE_NAME

from logic_cad.tests.support.wire_meta import (
    assert_wire_meta_canonical_out_to_in,
    count_wires_from_src_port,
)


def test_new_list_pages():
    d = LogicDiagram.new()
    pages = d.list_pages()
    assert pages
    assert d.current_layout_name in pages


def test_new_first_page_uses_first_page_name_constant() -> None:
    """新規ドキュメントの唯一の紙レイアウトは ezdxf 既定名ではなく FIRST_PAGE_NAME に揃える。"""
    d = LogicDiagram.new()
    assert d.current_layout_name == FIRST_PAGE_NAME
    assert d.list_pages() == [FIRST_PAGE_NAME]


def test_delete_page_removes_layout() -> None:
    d = LogicDiagram.new()
    with d.begin("add"):
        d.add_page("P2")
    assert "P2" in d.list_pages()
    with d.begin("del"):
        d.delete_page("P2")
    assert "P2" not in d.list_pages()


def test_delete_page_last_raises() -> None:
    d = LogicDiagram.new()
    only = d.list_pages()[0]
    with pytest.raises(ValueError, match="最後"):
        with d.begin("x"):
            d.delete_page(only)


def test_delete_page_switches_current_when_deleting_active() -> None:
    d = LogicDiagram.new()
    first = d.current_layout_name
    with d.begin("add"):
        d.add_page("P2")
    d.current_layout_name = "P2"
    with d.begin("del"):
        d.delete_page("P2")
    assert d.current_layout_name == first


def test_connect_same_ports_twice_raises():
    d = LogicDiagram.new()
    with d.begin("a"):
        u0 = d.place_symbol("NOT", (20.0, 40.0), "n0")
        u1 = d.place_symbol("NOT", (60.0, 40.0), "n1")
    d.rebuild_index()
    with d.begin("w1"):
        d.connect_ports(u0, "OUT0_LOGIC", u1, "IN0_LOGIC")
    with pytest.raises(ValueError, match="既に存在"):
        with d.begin("w2"):
            d.connect_ports(u0, "OUT0_LOGIC", u1, "IN0_LOGIC")


def test_second_direct_wire_from_same_out_raises():
    d = LogicDiagram.new()
    with d.begin("a"):
        src = d.place_symbol("NOT", (20.0, 40.0), "n0")
        dst0 = d.place_symbol("NOT", (60.0, 36.0), "n1")
        dst1 = d.place_symbol("NOT", (60.0, 44.0), "n2")
    d.rebuild_index()
    with d.begin("w1"):
        d.connect_ports(src, "OUT0_LOGIC", dst0, "IN0_LOGIC")
    with pytest.raises(ValueError, match="直接配線"):
        with d.begin("w2"):
            d.connect_ports(src, "OUT0_LOGIC", dst1, "IN0_LOGIC")


def test_second_wire_to_same_in_raises():
    d = LogicDiagram.new()
    with d.begin("a"):
        s0 = d.place_symbol("NOT", (20.0, 36.0), "a")
        s1 = d.place_symbol("NOT", (20.0, 44.0), "b")
        dst = d.place_symbol("NOT", (60.0, 40.0), "c")
    d.rebuild_index()
    with d.begin("w1"):
        d.connect_ports(s0, "OUT0_LOGIC", dst, "IN0_LOGIC")
    with pytest.raises(ValueError, match="すでに配線"):
        with d.begin("w2"):
            d.connect_ports(s1, "OUT0_LOGIC", dst, "IN0_LOGIC")


def test_checkpoint_to_wire_branch_multi_fanout():
    """CHECKPOINT single OUT into WIRE_BRANCH, then multiple OUT0_MULTI legs (no ``from_branch``)."""
    d = LogicDiagram.new()
    with d.begin("place"):
        a = d.place_and_gate(1, (6.0, 10.0))
        b = d.place_and_gate(1, (56.0, 14.0))
        c = d.place_and_gate(1, (34.0, 26.0))
        d_gate = d.place_and_gate(1, (34.0, 4.0))
        cp = d.place_checkpoint((18.0, 10.0))
    d.rebuild_index()
    with d.begin("br"):
        hub = d.place_wire_branch((34.0, 14.0))
    with d.begin("wire"):
        d.connect_ports(a, "OUT0_LOGIC", cp, "IN0_MULTI")
        d.connect_ports(cp, "OUT0_MULTI", hub, "IN0_MULTI")
        d.connect_ports(hub, "OUT0_MULTI", b, "IN0_LOGIC")
        d.connect_ports(hub, "OUT0_MULTI", c, "IN0_LOGIC")
        d.connect_ports(hub, "OUT0_MULTI", d_gate, "IN0_LOGIC")
    d.rebuild_index()
    n = count_wires_from_src_port(d, d.current_layout_name, hub, "OUT0_MULTI")
    assert n == 3


def test_connect_ports_reverse_in_out_normalizes_to_out_in():
    """IN* then OUT* click order → swap so XDATA stays canonical OUT* → IN*."""
    d = LogicDiagram.new()
    with d.begin("place"):
        a = d.place_and_gate(1, (10.0, 10.0))
        wb = d.place_wire_branch((30.0, 10.0))
    d.rebuild_index()
    with d.begin("wire"):
        d.connect_ports(a, "IN0_LOGIC", wb, "OUT0_MULTI")
    d.rebuild_index()
    metas = [m for _e, _wu, m in d.wires.iter_wire_meta(d.current_layout_name)]
    assert len(metas) == 1
    assert_wire_meta_canonical_out_to_in(metas[0])
    assert metas[0]["src"] == wb
    assert metas[0]["src_port"] == "OUT0_MULTI"
    assert metas[0]["dst"] == a
    assert metas[0]["dst_port"] == "IN0_LOGIC"


def test_connect_ports_both_in_raises():
    d = LogicDiagram.new()
    with d.begin("place"):
        n0 = d.place_symbol("NOT", (20.0, 40.0), "n0")
        n1 = d.place_symbol("NOT", (60.0, 40.0), "n1")
    d.rebuild_index()
    with pytest.raises(ValueError, match="両端がINポート"):
        with d.begin("w"):
            d.connect_ports(n0, "IN0_LOGIC", n1, "IN0_LOGIC")


def test_connect_ports_both_out_raises():
    d = LogicDiagram.new()
    with d.begin("place"):
        n0 = d.place_symbol("NOT", (20.0, 40.0), "n0")
        n1 = d.place_symbol("NOT", (60.0, 40.0), "n1")
    d.rebuild_index()
    with pytest.raises(ValueError, match="両端がOUTポート"):
        with d.begin("w"):
            d.connect_ports(n0, "OUT0_LOGIC", n1, "OUT0_LOGIC")


def test_connect_ports_in_in_with_hub_not_orientation_error():
    """Scene can yield gate IN + hub IN; do not raise 両端がINポート (defer to wire rules / repair)."""
    d = LogicDiagram.new()
    with d.begin("place"):
        a = d.place_and_gate(1, (10.0, 10.0))
        wb = d.place_wire_branch((30.0, 10.0))
    d.rebuild_index()
    try:
        with d.begin("w"):
            d.connect_ports(a, "IN0_LOGIC", wb, "IN0_MULTI")
    except ValueError as e:
        assert "両端がINポート" not in str(e)


def test_connect_ports_out_out_with_hub_not_orientation_error():
    """OUT–OUT with a hub endpoint skips orientation error (may fail later in wire service)."""
    d = LogicDiagram.new()
    with d.begin("place"):
        wb = d.place_wire_branch((30.0, 10.0))
        n = d.place_symbol("NOT", (10.0, 10.0))
    d.rebuild_index()
    try:
        with d.begin("w"):
            d.connect_ports(wb, "OUT0_MULTI", n, "OUT0_LOGIC")
    except ValueError as e:
        assert "両端がOUTポート" not in str(e)
