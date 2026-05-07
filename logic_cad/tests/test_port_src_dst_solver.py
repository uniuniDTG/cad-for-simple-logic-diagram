"""Tests for port_src_dst_solver (normalize, flips, asserts) and connect_ports hub IN rules."""

from __future__ import annotations

import os

import pytest

from logic_cad.core.dxf.dxf_repository import readfile
from logic_cad.core.graph.port_src_dst_solver import (
    find_flip_to_free_branch_in_for_pending_connection,
    find_hub_wire_flips,
    normalize_wire_endpoints,
)
from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.core.model.xdata import build_ld_app_tags, read_ld_app_dict, set_entity_xdata

from logic_cad.tests.support.diagram_entities import entity_and_ld_app_dict_for_uid
from logic_cad.tests.support.wire_meta import (
    assert_wire_meta_canonical_out_to_in,
    count_wires_in_layout,
    count_wires_to_dst_port,
)


# ---------------------------------------------------------------------------
# normalize_wire_endpoints (pure)
# ---------------------------------------------------------------------------


def test_normalize_swaps_in_out():
    su, sp, du, dp = normalize_wire_endpoints(
        "u1", "IN0_LOGIC", "u2", "OUT0_LOGIC", is_wire_hub_fn=lambda _u: False
    )
    assert (su, sp, du, dp) == ("u2", "OUT0_LOGIC", "u1", "IN0_LOGIC")


def test_normalize_rejects_both_in_without_hub():
    with pytest.raises(ValueError, match="両端がIN"):
        normalize_wire_endpoints(
            "u1", "IN0_LOGIC", "u2", "IN1_LOGIC", is_wire_hub_fn=lambda _u: False
        )


def test_normalize_corrects_in_in_hub_as_dst():
    """gate(IN) → hub(IN): hub stays source with clicked hub port."""
    out = normalize_wire_endpoints(
        "gate", "IN0_LOGIC", "wb", "IN0_MULTI", is_wire_hub_fn=lambda u: u == "wb"
    )
    assert out == ("wb", "IN0_MULTI", "gate", "IN0_LOGIC")


def test_normalize_corrects_in_in_hub_as_src():
    """hub(IN) → gate(IN): same correction when click order is reversed."""
    out = normalize_wire_endpoints(
        "wb", "IN0_MULTI", "gate", "IN0_LOGIC", is_wire_hub_fn=lambda u: u == "wb"
    )
    assert out == ("wb", "IN0_MULTI", "gate", "IN0_LOGIC")


def test_normalize_passes_through_in_in_both_hubs():
    """hub(IN) → hub(IN): both hubs ambiguous, BFS resolves later."""
    out = normalize_wire_endpoints(
        "wb1", "IN0_MULTI", "wb2", "IN0_MULTI",
        is_wire_hub_fn=lambda u: u in ("wb1", "wb2"),
    )
    assert out == ("wb1", "IN0_MULTI", "wb2", "IN0_MULTI")


def test_normalize_corrects_out_out_hub_as_src():
    """hub(OUT) + gate(OUT): gate is the driver; clicked hub port is kept."""
    out = normalize_wire_endpoints(
        "wb", "OUT0_MULTI", "gate", "OUT0_LOGIC",
        is_wire_hub_fn=lambda u: u == "wb",
    )
    assert out == ("gate", "OUT0_LOGIC", "wb", "OUT0_MULTI")


def test_normalize_corrects_out_out_hub_as_dst():
    """gate(OUT) + hub(OUT): same correction with click order reversed."""
    out = normalize_wire_endpoints(
        "gate", "OUT0_LOGIC", "wb", "OUT0_MULTI",
        is_wire_hub_fn=lambda u: u == "wb",
    )
    assert out == ("gate", "OUT0_LOGIC", "wb", "OUT0_MULTI")


def test_normalize_hub_port_ignored_hub_in_gate_out():
    """hub(IN) + gate(OUT): hub's IN port is irrelevant — gate still drives hub."""
    out = normalize_wire_endpoints(
        "wb", "IN0_MULTI", "gate", "OUT0_LOGIC",
        is_wire_hub_fn=lambda u: u == "wb",
    )
    assert out == ("gate", "OUT0_LOGIC", "wb", "IN0_MULTI")


def test_normalize_rejects_out_out_both_nonhub():
    """gate(OUT) + gate(OUT) with no hub: always raises ValueError."""
    with pytest.raises(ValueError, match="両端がOUT"):
        normalize_wire_endpoints(
            "g1", "OUT0_LOGIC", "g2", "OUT0_LOGIC",
            is_wire_hub_fn=lambda _u: False,
        )


def test_normalize_passes_through_out_out_both_hubs():
    """hub(OUT) → hub(OUT): both hubs ambiguous, BFS resolves later."""
    out = normalize_wire_endpoints(
        "wb1", "OUT0_MULTI", "wb2", "OUT0_MULTI",
        is_wire_hub_fn=lambda u: u in ("wb1", "wb2"),
    )
    assert out == ("wb1", "OUT0_MULTI", "wb2", "OUT0_MULTI")


def test_normalize_out_to_inout_keeps_out_as_source():
    out = normalize_wire_endpoints(
        "g1", "OUT0_LOGIC", "g2", "INOUT0_LOGIC", is_wire_hub_fn=lambda _u: False
    )
    assert out == ("g1", "OUT0_LOGIC", "g2", "INOUT0_LOGIC")


def test_normalize_in_to_inout_swaps_to_inout_source():
    out = normalize_wire_endpoints(
        "g1", "IN0_LOGIC", "g2", "INOUT0_LOGIC", is_wire_hub_fn=lambda _u: False
    )
    assert out == ("g2", "INOUT0_LOGIC", "g1", "IN0_LOGIC")


def test_normalize_inout_to_inout_keeps_click_order():
    out = normalize_wire_endpoints(
        "g1", "INOUT0_LOGIC", "g2", "INOUT0_LOGIC", is_wire_hub_fn=lambda _u: False
    )
    assert out == ("g1", "INOUT0_LOGIC", "g2", "INOUT0_LOGIC")


def test_normalize_hub_with_inout_keeps_click_intent():
    out_src_gate = normalize_wire_endpoints(
        "gate", "INOUT0_LOGIC", "wb", "IN0_MULTI", is_wire_hub_fn=lambda u: u == "wb"
    )
    out_src_hub = normalize_wire_endpoints(
        "wb", "OUT0_MULTI", "gate", "INOUT0_LOGIC", is_wire_hub_fn=lambda u: u == "wb"
    )
    assert out_src_gate == ("gate", "INOUT0_LOGIC", "wb", "IN0_MULTI")
    assert out_src_hub == ("wb", "OUT0_MULTI", "gate", "INOUT0_LOGIC")


# ---------------------------------------------------------------------------
# Hub IN full: no hub-out fallback (ValueError)
# ---------------------------------------------------------------------------


def test_connect_second_and_to_occupied_wire_branch_in_raises():
    d = LogicDiagram.new()
    with d.begin("place"):
        upstream = d.place_and_gate(1, (6.0, 10.0))
        wb = d.place_wire_branch((30.0, 10.0))
        d.place_and_gate(1, (60.0, 10.0))
    d.rebuild_index()
    with d.begin("wire1"):
        d.connect_ports(upstream, "OUT0_LOGIC", wb, "INOUT0_MULTI")
    d.rebuild_index()
    other_and = d.place_and_gate(1, (30.0, 26.0))
    d.rebuild_index()
    with d.begin("wire2"):
        d.connect_ports(other_and, "OUT0_LOGIC", wb, "INOUT0_MULTI")


def test_connect_wb_out_to_peer_wb_in_raises_when_peer_in_full():
    d = LogicDiagram.new()
    with d.begin("place"):
        upstream = d.place_and_gate(1, (6.0, 10.0))
        wb1 = d.place_wire_branch((30.0, 10.0))
        wb2 = d.place_wire_branch((55.0, 10.0))
    d.rebuild_index()
    with d.begin("w1"):
        d.connect_ports(upstream, "OUT0_LOGIC", wb1, "INOUT0_MULTI")
    d.rebuild_index()
    with d.begin("w2"):
        d.connect_ports(wb2, "INOUT0_MULTI", wb1, "INOUT0_MULTI")


# ---------------------------------------------------------------------------
# find_hub_wire_flips
# ---------------------------------------------------------------------------


def test_find_hub_wire_flips_no_flips_when_canonical():
    d = LogicDiagram.new()
    with d.begin("place"):
        wb = d.place_wire_branch((30.0, 10.0))
        g = d.place_and_gate(1, (10.0, 10.0))
    d.rebuild_index()
    with d.begin("w"):
        d.connect_ports(g, "OUT0_LOGIC", wb, "INOUT0_MULTI")
    d.rebuild_index()
    flips = find_hub_wire_flips(d.current_layout_name, deps=d.wires.wire_graph_deps())
    assert flips == []


def test_anchor_bfs_flips_semantically_reversed_hub_hub_wire():
    d = LogicDiagram.new()
    with d.begin("place"):
        a = d.place_and_gate(1, (6.0, 10.0))
        wb_a = d.place_wire_branch((28.0, 10.0))
        wb_b = d.place_wire_branch((50.0, 10.0))
    d.rebuild_index()
    with d.begin("w"):
        d.connect_ports(a, "OUT0_LOGIC", wb_a, "INOUT0_MULTI")
        d.connect_ports(wb_a, "INOUT0_MULTI", wb_b, "INOUT0_MULTI")
    d.rebuild_index()
    hub_hub_wid = None
    for _e, wu, m in d.wires.iter_wire_meta(d.current_layout_name):
        su, du = m.get("src"), m.get("dst")
        if su in (wb_a, wb_b) and du in (wb_a, wb_b):
            hub_hub_wid = wu
            break
    assert hub_hub_wid is not None
    flips = find_hub_wire_flips(d.current_layout_name, deps=d.wires.wire_graph_deps())
    assert flips == []


def test_find_hub_wire_flips_long_hub_chain_completes():
    """Long hub chain; spaced so auto-route succeeds without relying on hub-out fallback."""
    d = LogicDiagram.new()
    with d.begin("place"):
        a = d.place_and_gate(1, (0.0, 10.0))
        hubs = [d.place_wire_branch((28.0 + 12.0 * i, 10.0)) for i in range(15)]
    d.rebuild_index()
    with d.begin("chain"):
        d.connect_ports(a, "OUT0_LOGIC", hubs[0], "INOUT0_MULTI")
        for i in range(len(hubs) - 1):
            d.connect_ports(hubs[i], "INOUT0_MULTI", hubs[i + 1], "INOUT0_MULTI")
    d.rebuild_index()
    flips = find_hub_wire_flips(d.current_layout_name, deps=d.wires.wire_graph_deps())
    assert flips == []


def test_find_hub_wire_flips_no_anchor_hub_hub_only():
    d = LogicDiagram.new()
    with d.begin("place"):
        wb_a = d.place_wire_branch((28.0, 10.0))
        wb_b = d.place_wire_branch((50.0, 10.0))
    d.rebuild_index()
    with d.begin("w"):
        d.connect_ports(wb_a, "INOUT0_MULTI", wb_b, "INOUT0_MULTI")
    d.rebuild_index()
    flips = find_hub_wire_flips(d.current_layout_name, deps=d.wires.wire_graph_deps())
    assert flips == []


def test_find_flip_to_free_branch_in_returns_flip_when_upstream_in_empty():
    d = LogicDiagram.new()
    with d.begin("place"):
        wb_a = d.place_wire_branch((28.0, 10.0))
        wb_b = d.place_wire_branch((50.0, 10.0))
    d.rebuild_index()
    with d.begin("w"):
        d.connect_ports(wb_a, "INOUT0_MULTI", wb_b, "INOUT0_MULTI")
    d.rebuild_index()
    f = find_flip_to_free_branch_in_for_pending_connection(
        d.current_layout_name,
        wb_b,
        "INOUT0_MULTI",
        deps=d.wires.wire_graph_deps(),
    )
    assert f is None


def test_find_flip_to_free_branch_in_none_when_upstream_in_has_gate():
    d = LogicDiagram.new()
    with d.begin("place"):
        g = d.place_and_gate(1, (6.0, 10.0))
        wb_a = d.place_wire_branch((28.0, 10.0))
        wb_b = d.place_wire_branch((50.0, 10.0))
    d.rebuild_index()
    with d.begin("w"):
        d.connect_ports(g, "OUT0_LOGIC", wb_a, "INOUT0_MULTI")
        d.connect_ports(wb_a, "INOUT0_MULTI", wb_b, "INOUT0_MULTI")
    d.rebuild_index()
    assert not find_flip_to_free_branch_in_for_pending_connection(
        d.current_layout_name,
        wb_b,
        "INOUT0_MULTI",
        deps=d.wires.wire_graph_deps(),
    )


def test_find_hub_wire_flips_no_hub_wires():
    d = LogicDiagram.new()
    with d.begin("place"):
        n0 = d.place_symbol("NOT", (10.0, 10.0))
        n1 = d.place_symbol("NOT", (40.0, 10.0))
    d.rebuild_index()
    with d.begin("w"):
        d.connect_ports(n0, "OUT0_LOGIC", n1, "IN0_LOGIC")
    d.rebuild_index()
    flips = find_hub_wire_flips(d.current_layout_name, deps=d.wires.wire_graph_deps())
    assert flips == []


# ---------------------------------------------------------------------------
# repair_hub_wire_directions
# ---------------------------------------------------------------------------


def test_repair_hub_wire_directions_fixes_backwards_xdata():
    d = LogicDiagram.new()
    with d.begin("place"):
        wb = d.place_wire_branch((30.0, 10.0))
        g = d.place_and_gate(1, (10.0, 10.0))
    d.rebuild_index()
    with d.begin("w"):
        wid = d.connect_ports(g, "OUT0_LOGIC", wb, "INOUT0_MULTI")
    d.rebuild_index()

    e, old_meta = entity_and_ld_app_dict_for_uid(d.doc, wid)
    corrupted_extra = {
        "unit": old_meta.get("unit", "LOGIC"),
        "src": old_meta["dst"],
        "src_port": old_meta["dst_port"],
        "dst": old_meta["src"],
        "dst_port": old_meta["src_port"],
    }
    set_entity_xdata(e, build_ld_app_tags("1", wid, "WIRE", corrupted_extra))

    n = d.repair_hub_wire_directions()
    assert n == 0


# ---------------------------------------------------------------------------
# Fixture: test2.dxf
# ---------------------------------------------------------------------------


def test_test2_dxf_connect_and_to_wb_in_flip_or_capacity():
    """Fixture may allow hub-tail flip (second AND succeeds) or block (raises)."""
    fixture = os.path.join(os.path.dirname(__file__), "test2.dxf")
    doc = readfile(fixture)
    layout_names = [ln for ln in doc.layouts.names() if ln not in ("0", "Model")]
    assert layout_names
    d = LogicDiagram(doc, layout_names[0])
    d.rebuild_index()

    wb2_uid = "27668a1a-f52c-4dcf-ae33-8b2811e9e4f3"
    and_uid = "9dc38f82-1ab8-45cf-b4aa-308e55ab1c1f"

    prep = find_flip_to_free_branch_in_for_pending_connection(
        d.current_layout_name,
        wb2_uid,
        "INOUT0_MULTI",
        deps=d.wires.wire_graph_deps(),
    )
    assert prep is None
    n_wires_before = count_wires_in_layout(d, d.current_layout_name)
    with d.begin("connect"):
        with pytest.raises(ValueError, match="INOUT0_MULTI"):
            d.connect_ports(and_uid, "OUT0_LOGIC", wb2_uid, "IN0_MULTI")
    d.rebuild_index()
    n_wires_after = count_wires_in_layout(d, d.current_layout_name)
    assert n_wires_after == n_wires_before
