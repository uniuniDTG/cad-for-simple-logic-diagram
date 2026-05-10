"""Tests for AND/OR layout ``GATE_INPUT_STUB_ARROW`` LW polylines."""

from __future__ import annotations

from ezdxf.document import Drawing

from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.core.model.constants import (
    ENTITY_TYPE_GATE_INPUT_STUB_ARROW,
    GATE_STUB_ARROW_PARENT_XDATA,
    LAYER_SYMBOL,
)
from logic_cad.core.model.xdata import get_type, read_ld_app_dict
from logic_cad.core.paper_layout_access import paper_layout_block


def _stub_arrows_for_gate(doc: Drawing, layout_name: str, gate_uid: str) -> list:
    """Collect ``GATE_INPUT_STUB_ARROW`` LW entities parented to *gate_uid* on *layout_name*.

    Args:
        doc: Drawing under test.
        layout_name: Paperspace layout name.
        gate_uid: Logical AND/OR INSERT uid.

    Returns:
        Matching LWPOLYLINE entities.
    """
    blk = paper_layout_block(doc, layout_name)
    assert blk is not None
    out = []
    for e in blk:
        if e.dxftype() != "LWPOLYLINE":
            continue
        if str(e.dxf.layer) != LAYER_SYMBOL:
            continue
        if get_type(e) != ENTITY_TYPE_GATE_INPUT_STUB_ARROW:
            continue
        xd = read_ld_app_dict(e)
        if str(xd.get(GATE_STUB_ARROW_PARENT_XDATA) or "").strip() == gate_uid:
            out.append(e)
    return out


def test_gate_stub_arrow_sync_creates_and_removes_lwpolyline() -> None:
    d = LogicDiagram.new()
    uid = d.place_and_gate(2, (40.0, 50.0))

    d.set_gate_show_input_stub_in_arrow(uid, True)
    arrows = _stub_arrows_for_gate(d.doc, d.current_layout_name, uid)
    assert len(arrows) == 2
    for ent in arrows:
        rows = list(ent.get_points("xy"))
        assert len(rows) == 3

    d.set_gate_show_input_stub_in_arrow(uid, False)
    assert _stub_arrows_for_gate(d.doc, d.current_layout_name, uid) == []


def test_gate_stub_arrows_follow_rotation() -> None:
    d = LogicDiagram.new()
    uid = d.place_and_gate(2, (10.0, 10.0))
    d.set_gate_show_input_stub_in_arrow(uid, True)

    arrows_before = _stub_arrows_for_gate(d.doc, d.current_layout_name, uid)
    assert len(arrows_before) == 2
    v0 = list(arrows_before[0].get_points("xy"))[0]

    ok = d.rotate_symbol(uid, 90.0)
    assert ok is True

    arrows_after = _stub_arrows_for_gate(d.doc, d.current_layout_name, uid)
    assert len(arrows_after) == 2
    v1 = list(arrows_after[0].get_points("xy"))[0]
    assert abs(float(v0[0]) - float(v1[0])) > 0.05 or abs(float(v0[1]) - float(v1[1])) > 0.05


def test_delete_gate_removes_stub_arrow_geometry() -> None:
    d = LogicDiagram.new()
    uid = d.place_and_gate(2, (15.0, 15.0))
    d.set_gate_show_input_stub_in_arrow(uid, True)
    assert len(_stub_arrows_for_gate(d.doc, d.current_layout_name, uid)) == 2

    d.delete_by_uid(uid)
    assert _stub_arrows_for_gate(d.doc, d.current_layout_name, uid) == []


def test_change_gate_input_count_refreshes_arrow_count() -> None:
    d = LogicDiagram.new()
    uid = d.place_and_gate(2, (20.0, 20.0))
    d.set_gate_show_input_stub_in_arrow(uid, True)
    assert len(_stub_arrows_for_gate(d.doc, d.current_layout_name, uid)) == 2

    d.change_gate_inputs(uid, 3)
    assert len(_stub_arrows_for_gate(d.doc, d.current_layout_name, uid)) == 3


def test_validate_accepts_synced_gate_arrows() -> None:
    d = LogicDiagram.new()
    uid = d.place_and_gate(2, (5.0, 5.0))
    d.set_gate_show_input_stub_in_arrow(uid, True)
    issues = d.validate()
    gate_arrow_msgs = [x for x in issues if "GATE_INPUT_STUB_ARROW" in x]
    assert gate_arrow_msgs == []
