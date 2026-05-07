"""Synthetic tests for port_src_dst_solver assert_* helpers; wire_connection_health gap snapshot."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from logic_cad.core.graph.port_src_dst_solver import (
    assert_checkpoint_wire_capacity,
    assert_ld_port_direct_wiring_rules,
)
from logic_cad.core.graph.wire_graph_deps import WireGraphDeps
from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.core.model.constants import ENTITY_TYPE_WIRE_BRANCH
from logic_cad.core.model.xdata import build_ld_app_tags, set_entity_xdata

from logic_cad.tests.support.diagram_entities import entity_and_ld_app_dict_for_uid


LAYOUT = "active"


def _iter_from_rows(rows: list[dict]) -> Iterator[tuple[object, str, dict]]:
    def iter_wire_meta(layout_name: str):
        assert layout_name == LAYOUT
        for row in rows:
            wu = str(row["wire_uid"])
            meta = {k: v for k, v in row.items() if k != "wire_uid"}
            yield None, wu, meta

    return iter_wire_meta


def test_assert_checkpoint_wb_requires_inout_port():
    wb = "wb-1"
    rows = [
        {
            "wire_uid": "w1",
            "src": "a",
            "src_port": "OUT0_LOGIC",
            "dst": wb,
            "dst_port": "IN0_MULTI",
        }
    ]
    iter_wm = _iter_from_rows(rows)
    types = {wb: ENTITY_TYPE_WIRE_BRANCH, "a": "NOT"}

    def sym_type(uid: str) -> str | None:
        return types.get(uid)

    deps = WireGraphDeps(iter_wire_meta=iter_wm, symbol_entity_type_fn=sym_type)
    with pytest.raises(ValueError, match="INOUT0_MULTI"):
        assert_checkpoint_wire_capacity(
            LAYOUT,
            "b",
            "OUT0_LOGIC",
            wb,
            "IN0_MULTI",
            deps=deps,
        )


def test_assert_checkpoint_cp_out_full():
    cp = "cp-1"
    rows = [
        {
            "wire_uid": "w1",
            "src": cp,
            "src_port": "OUT0_MULTI",
            "dst": "g",
            "dst_port": "IN0_LOGIC",
        }
    ]
    iter_wm = _iter_from_rows(rows)
    from logic_cad.core.model.constants import ENTITY_TYPE_CHECKPOINT

    types = {cp: ENTITY_TYPE_CHECKPOINT, "g": "AND_2"}

    def sym_type(uid: str) -> str | None:
        return types.get(uid)

    deps = WireGraphDeps(iter_wire_meta=iter_wm, symbol_entity_type_fn=sym_type)
    with pytest.raises(ValueError, match="チェックポイントの出力は1本まで"):
        assert_checkpoint_wire_capacity(
            LAYOUT,
            cp,
            "OUT0_MULTI",
            "h",
            "IN0_LOGIC",
            deps=deps,
        )


def test_assert_ld_duplicate_dst_port():
    g = "gate-1"
    rows = [
        {
            "wire_uid": "w1",
            "src": "a",
            "src_port": "OUT0_LOGIC",
            "dst": g,
            "dst_port": "IN0_LOGIC",
        }
    ]
    iter_wm = _iter_from_rows(rows)

    def sym_type(_uid: str) -> str | None:
        return "AND_2"

    deps = WireGraphDeps(iter_wire_meta=iter_wm, symbol_entity_type_fn=sym_type)
    with pytest.raises(ValueError, match="すでに配線が1本"):
        assert_ld_port_direct_wiring_rules(
            LAYOUT,
            "b",
            "OUT0_LOGIC",
            g,
            "IN0_LOGIC",
            deps=deps,
        )


def test_assert_ld_allows_second_wire_from_wb_inout():
    wb = "wb-1"
    rows = [
        {
            "wire_uid": "w1",
            "src": wb,
            "src_port": "INOUT0_MULTI",
            "dst": "a",
            "dst_port": "IN0_LOGIC",
        }
    ]
    iter_wm = _iter_from_rows(rows)

    def sym_type(uid: str) -> str | None:
        return ENTITY_TYPE_WIRE_BRANCH if uid == wb else "NOT"

    deps = WireGraphDeps(iter_wire_meta=iter_wm, symbol_entity_type_fn=sym_type)
    # Second fan-out from same INOUT0_MULTI is allowed
    assert_ld_port_direct_wiring_rules(
        LAYOUT,
        wb,
        "INOUT0_MULTI",
        "b",
        "IN0_LOGIC",
        deps=deps,
    )


def test_assert_ld_rejects_second_wire_on_inout_dst_even_if_existing_is_src():
    node = "io-1"
    rows = [
        {
            "wire_uid": "w1",
            "src": node,
            "src_port": "INOUT0_LOGIC",
            "dst": "a",
            "dst_port": "IN0_LOGIC",
        }
    ]
    iter_wm = _iter_from_rows(rows)

    def sym_type(_uid: str) -> str | None:
        return "SYMBOL"

    deps = WireGraphDeps(iter_wire_meta=iter_wm, symbol_entity_type_fn=sym_type)
    with pytest.raises(ValueError, match="すでに配線が1本"):
        assert_ld_port_direct_wiring_rules(
            LAYOUT,
            "b",
            "OUT0_LOGIC",
            node,
            "INOUT0_LOGIC",
            deps=deps,
        )


def test_assert_ld_rejects_second_wire_on_inout_src_even_if_existing_is_dst():
    node = "io-1"
    rows = [
        {
            "wire_uid": "w1",
            "src": "a",
            "src_port": "OUT0_LOGIC",
            "dst": node,
            "dst_port": "INOUT0_LOGIC",
        }
    ]
    iter_wm = _iter_from_rows(rows)

    def sym_type(_uid: str) -> str | None:
        return "SYMBOL"

    deps = WireGraphDeps(iter_wire_meta=iter_wm, symbol_entity_type_fn=sym_type)
    with pytest.raises(ValueError, match="直接配線はすでに1本"):
        assert_ld_port_direct_wiring_rules(
            LAYOUT,
            node,
            "INOUT0_LOGIC",
            "b",
            "IN0_LOGIC",
            deps=deps,
        )


def test_wire_connection_health_true_for_out_out_xdata_snapshot():
    """Document: logical_ok may stay True when XDATA is OUT–OUT; direction is not validated yet."""
    d = LogicDiagram.new()
    with d.begin("p"):
        n0 = d.place_symbol("NOT", (10.0, 10.0))
        n1 = d.place_symbol("NOT", (50.0, 10.0))
    d.rebuild_index()
    with d.begin("w"):
        wid = d.connect_ports(n0, "OUT0_LOGIC", n1, "IN0_LOGIC")
    d.rebuild_index()
    e, xd = entity_and_ld_app_dict_for_uid(d.doc, wid)
    corrupted = {
        "unit": xd.get("unit", "LOGIC"),
        "src": n0,
        "src_port": "OUT0_LOGIC",
        "dst": n1,
        "dst_port": "OUT0_LOGIC",
    }
    set_entity_xdata(e, build_ld_app_tags("1", wid, "WIRE", corrupted))
    d.rebuild_index()
    log_ok, geo_ok = d.wire_connection_health(wid)
    # Geometry may fail (polyline ends not at OUT ports); logical can still be True with compatible units
    assert log_ok is True
    assert geo_ok is False
