"""Tests for symbol block edit session, port helpers, scratch undo."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.core.model.port_key import PortKey, format_port_layer, parse_port_layer
from logic_cad.core.model.constants import (
    BLOCK_EDIT_AUX_GRID_DEFAULT_PITCH_MM,
    BLOCK_EDIT_SNAP_PITCH_MM,
    ENTITY_TYPE_USER_CIRCLE,
    ENTITY_TYPE_USER_LINE,
    GRID_PITCH,
    LAYER_SYMBOL,
    LAYER_TEXT,
)
from logic_cad.core.model.xdata import get_type, get_uid
from logic_cad.core.services.block_edit_helpers import (
    add_attdef_to_block,
    add_user_circle_to_block,
    add_user_line_to_block,
    make_port_layer_name,
    port_layer_is_taken,
    replace_main_block_from_scratch,
    scratch_block_attdef_tag_taken,
    update_scratch_attdef_fields,
)
from logic_cad.core.undo.history import find_entity_by_uid
from logic_cad.core.services.block_edit_session import BlockEditSession
from logic_cad.ui.snap_utils import dxf_from_scene_pos, scene_pos_from_dxf
from logic_cad.ui.symbol_block_editor.scene import AttdefEditItem, SymbolBlockEditScene
from logic_cad.core.services.block_edit_clipboard import (
    decode_entity_clipboard,
    encode_entity_payloads,
    paste_entity_clipboard_root,
)
from logic_cad.core.undo.scratch_transaction import ScratchUndoDiagram, scratch_undo
from logic_cad.core.undo.entity_serialize import serialize_entity


def test_scratch_user_line_on_ld_symbol() -> None:
    d = LogicDiagram.new()
    if "NOT" not in d.doc.blocks:
        pytest.skip("NOT block missing from library")
    sess = BlockEditSession.open_existing(d.doc, "NOT")
    blk = sess.scratch_block()
    uid = add_user_line_to_block(blk, (0.0, 0.0), (5.0, 0.0), "CENTER")
    e = find_entity_by_uid(sess.scratch_doc, uid)
    assert e is not None
    assert e.dxftype() == "LINE"
    assert str(e.dxf.layer) == LAYER_SYMBOL
    assert get_type(e) == ENTITY_TYPE_USER_LINE


def test_scratch_user_circle_on_ld_symbol() -> None:
    d = LogicDiagram.new()
    if "NOT" not in d.doc.blocks:
        pytest.skip("NOT block missing from library")
    sess = BlockEditSession.open_existing(d.doc, "NOT")
    blk = sess.scratch_block()
    uid = add_user_circle_to_block(blk, (1.0, -2.0), 4.0, "DASHED")
    e = find_entity_by_uid(sess.scratch_doc, uid)
    assert e is not None
    assert e.dxftype() == "CIRCLE"
    assert str(e.dxf.layer) == LAYER_SYMBOL
    assert get_type(e) == ENTITY_TYPE_USER_CIRCLE


def test_update_scratch_attdef_horizontal_align() -> None:
    """Tag/text/halign apply keeps anchor and sets DXF halign 0–2."""

    d = LogicDiagram.new()
    if "NOT" not in d.doc.blocks:
        pytest.skip("NOT block missing from library")
    sess = BlockEditSession.open_existing(d.doc, "NOT")
    blk = sess.scratch_block()
    h = add_attdef_to_block(blk, "LABEL0", (5.0, -3.0), "ABC", height_mm=2.0)
    ent = next(x for x in blk if str(getattr(x.dxf, "handle", "") or "") == h)
    assert int(getattr(ent.dxf, "halign", 0) or 0) == 0
    with sess.begin("prop"):
        update_scratch_attdef_fields(
            blk,
            h,
            tag="LABEL0",
            default_text="XYZ",
            halign=2,
            height_mm=5.0,
        )
    assert str(ent.dxf.text) == "XYZ"
    assert int(ent.dxf.halign) == 2
    assert float(ent.dxf.height) == 5.0
    assert float(ent.dxf.insert.x) == 5.0 and float(ent.dxf.insert.y) == -3.0
    assert float(ent.dxf.align_point.x) == 5.0 and float(ent.dxf.align_point.y) == -3.0


def test_scratch_block_attdef_tag_taken_ignores_same_handle() -> None:
    d = LogicDiagram.new()
    if "NOT" not in d.doc.blocks:
        pytest.skip("NOT block missing from library")
    sess = BlockEditSession.open_existing(d.doc, "NOT")
    blk = sess.scratch_block()
    h1 = add_attdef_to_block(blk, "LABEL0", (0.0, 0.0), "a", height_mm=2.0)
    h2 = add_attdef_to_block(blk, "LABEL1", (1.0, 1.0), "b", height_mm=2.0)
    assert scratch_block_attdef_tag_taken(blk, "LABEL0") is True
    assert scratch_block_attdef_tag_taken(blk, "label0") is True
    assert scratch_block_attdef_tag_taken(blk, "LABEL0", ignore_handle=h1) is False
    assert scratch_block_attdef_tag_taken(blk, "LABEL0", ignore_handle=h2) is True


def test_update_scratch_attdef_rename_to_duplicate_tag_raises() -> None:
    d = LogicDiagram.new()
    if "NOT" not in d.doc.blocks:
        pytest.skip("NOT block missing from library")
    sess = BlockEditSession.open_existing(d.doc, "NOT")
    blk = sess.scratch_block()
    _ = add_attdef_to_block(blk, "LABEL0", (0.0, 0.0), "a", height_mm=2.0)
    h1 = add_attdef_to_block(blk, "LABEL1", (1.0, 1.0), "b", height_mm=2.0)
    ent1 = next(x for x in blk if str(getattr(x.dxf, "handle", "") or "") == h1)
    with pytest.raises(ValueError, match="すでに"):
        with sess.begin("x"):
            update_scratch_attdef_fields(
                blk,
                h1,
                tag="LABEL0",
                default_text=str(ent1.dxf.text),
                halign=0,
                height_mm=2.0,
            )


def test_add_attdef_rejects_duplicate_tag() -> None:
    sess = BlockEditSession.open_new("TMP_ATTDEF_DUP_TEST")
    blk = sess.scratch_block()
    assert blk is not None
    add_attdef_to_block(blk, "LABEL5", (0.0, 0.0), "a", height_mm=2.0)
    with pytest.raises(ValueError, match="すでに"):
        add_attdef_to_block(blk, "LABEL5", (5.0, 5.0), "b", height_mm=2.0)


def test_add_attdef_ld_text() -> None:
    d = LogicDiagram.new()
    if "NOT" not in d.doc.blocks:
        pytest.skip("NOT block missing from library")
    sess = BlockEditSession.open_existing(d.doc, "NOT")
    blk = sess.scratch_block()
    h = add_attdef_to_block(blk, "LABEL0", (0.5, -0.5), "ABC", height_mm=2.0)
    assert h
    ent = next(x for x in blk if str(getattr(x.dxf, "handle", "") or "") == h)
    assert ent.dxftype() == "ATTDEF"
    assert str(ent.dxf.layer) == LAYER_TEXT


def test_block_session_is_dirty_only_after_transaction() -> None:
    d = LogicDiagram.new()
    if "NOT" not in d.doc.blocks:
        pytest.skip("NOT block missing from library")
    sess = BlockEditSession.open_existing(d.doc, "NOT")
    assert not sess.is_dirty()
    blk = sess.scratch_block()
    with sess.begin("mark"):
        add_user_line_to_block(blk, (0.0, 0.0), (1.0, 1.0), "CONTINUOUS")
    assert sess.is_dirty()


def test_auxiliary_grid_toggle_updates_snap_pitch() -> None:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    scene = SymbolBlockEditScene(
        get_session=lambda: None,
        request_port_layer=lambda: None,
        sketch_line_linetype=lambda: "CONTINUOUS",
    )
    assert scene.snap_pitch_mm == pytest.approx(GRID_PITCH)

    scene.set_auxiliary_grid_visible(False)
    assert scene.snap_pitch_mm == pytest.approx(GRID_PITCH)

    scene.set_auxiliary_grid_visible(True)
    assert scene.snap_pitch_mm == pytest.approx(BLOCK_EDIT_AUX_GRID_DEFAULT_PITCH_MM)
    assert scene.snap_pitch_mm == pytest.approx(BLOCK_EDIT_SNAP_PITCH_MM)


def test_auxiliary_snap_pitch_can_be_switched() -> None:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    scene = SymbolBlockEditScene(
        get_session=lambda: None,
        request_port_layer=lambda: None,
        sketch_line_linetype=lambda: "CONTINUOUS",
    )
    scene.set_auxiliary_snap_pitch_mm(0.2)
    scene.set_auxiliary_grid_visible(True)
    assert scene.snap_pitch_mm == pytest.approx(0.2)

    scene.set_auxiliary_grid_visible(False)
    assert scene.snap_pitch_mm == pytest.approx(GRID_PITCH)


def test_attdef_edit_item_snaps_to_auxiliary_pitch_when_minor_grid_on() -> None:
    """ATTDEF position snaps to scene.snap_pitch_mm when auxiliary grid / pitch is active."""

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    sess = BlockEditSession.open_new("TMP_ATTDEF_AUX_SNAP_TEST")
    blk = sess.scratch_block()
    assert blk is not None
    _ = add_attdef_to_block(blk, "LABEL0", (1.03, -2.07), "x", height_mm=2.0)

    scene = SymbolBlockEditScene(
        get_session=lambda: sess,
        request_port_layer=lambda: None,
        sketch_line_linetype=lambda: "CONTINUOUS",
    )
    scene.set_auxiliary_snap_pitch_mm(0.2)
    scene.set_auxiliary_grid_visible(True)
    scene.refresh_from_session()

    ad = next(i for i in scene.items() if isinstance(i, AttdefEditItem))
    ad.setPos(scene_pos_from_dxf(1.11, -2.13))
    ix, iy = dxf_from_scene_pos(ad.scenePos())
    assert ix == pytest.approx(1.2)
    assert iy == pytest.approx(-2.2)


def test_format_port_layer_roundtrip() -> None:
    pk = PortKey(direction="IN", index=2, unit="LOGIC")
    layer = format_port_layer(pk)
    assert layer == "LD_PORT_IN2_LOGIC"
    assert parse_port_layer(layer) == pk


def test_make_port_layer_name() -> None:
    assert make_port_layer_name("OUT", 0, "MULTI") == "LD_PORT_OUT0_MULTI"


def test_port_layer_duplicate_forbidden_in_scratch() -> None:
    d = LogicDiagram.new()
    if "NOT" not in d.doc.blocks:
        pytest.skip("NOT block missing from library")
    sess = BlockEditSession.open_existing(d.doc, "NOT")
    blk = sess.scratch_block()
    layer = make_port_layer_name("IN", 42, "LOGIC")
    with sess.begin("add"):
        blk.add_point((1.0, 1.0), dxfattribs={"layer": layer})
    assert port_layer_is_taken(blk, layer)


def test_scratch_undo_removes_port() -> None:
    d = LogicDiagram.new()
    if "NOT" not in d.doc.blocks:
        pytest.skip("NOT block missing from library")
    sess = BlockEditSession.open_existing(d.doc, "NOT")
    blk = sess.scratch_block()
    layer = make_port_layer_name("IN", 88, "LOGIC")
    with sess.begin("add"):
        blk.add_point((3.0, 3.0), dxfattribs={"layer": layer})
    assert any(
        e.dxftype() == "POINT" and str(e.dxf.layer).upper() == layer for e in blk
    )
    assert scratch_undo(ScratchUndoDiagram(sess.scratch_doc), sess.block_history)
    blk2 = sess.scratch_block()
    assert not any(
        e.dxftype() == "POINT" and str(e.dxf.layer).upper() == layer for e in blk2
    )


def test_apply_block_does_not_push_main_undo_stack() -> None:
    d = LogicDiagram.new()
    if "NOT" not in d.doc.blocks:
        pytest.skip("NOT block missing from library")
    sess = BlockEditSession.open_existing(d.doc, "NOT")
    blk = sess.scratch_block()
    with sess.begin("add"):
        blk.add_point((0.0, 5.0), dxfattribs={"layer": make_port_layer_name("OUT", 9, "LOGIC")})
    n_undo = len(d.history.undo_stack)
    sess.apply_to(d)
    assert len(d.history.undo_stack) == n_undo


def test_replace_main_preserves_block_name() -> None:
    d = LogicDiagram.new()
    if "NOT" not in d.doc.blocks:
        pytest.skip("NOT block missing from library")
    sess = BlockEditSession.open_existing(d.doc, "NOT")
    with sess.begin("mark"):
        sess.scratch_block().add_point(
            (2.0, 2.0), dxfattribs={"layer": make_port_layer_name("INOUT", 0, "MULTI")}
        )
    replace_main_block_from_scratch(d.doc, sess.scratch_doc, "NOT")
    blk = d.doc.blocks.get("NOT")
    assert any(
        e.dxftype() == "POINT"
        and parse_port_layer(str(e.dxf.layer)) is not None
        and float(e.dxf.location.x) == 2.0
        for e in blk
    )


def test_scratch_undo_port_move_no_duplicate_point() -> None:
    d = LogicDiagram.new()
    if "NOT" not in d.doc.blocks:
        pytest.skip("NOT block missing from library")
    sess = BlockEditSession.open_existing(d.doc, "NOT")
    blk = sess.scratch_block()
    layer = make_port_layer_name("IN", 77, "LOGIC")
    with sess.begin("add"):
        blk.add_point((1.0, 2.0), dxfattribs={"layer": layer})
    ent = next(
        e
        for e in blk
        if e.dxftype() == "POINT" and str(e.dxf.layer).upper() == layer.upper()
    )
    with sess.begin("move"):
        ent.dxf.location = (10.0, 20.0, 0.0)
    assert scratch_undo(ScratchUndoDiagram(sess.scratch_doc), sess.block_history)
    blk2 = sess.scratch_block()
    matches = [
        e
        for e in blk2
        if e.dxftype() == "POINT" and str(e.dxf.layer).upper() == layer.upper()
    ]
    assert len(matches) == 1
    assert abs(float(matches[0].dxf.location.x) - 1.0) < 1e-9
    assert abs(float(matches[0].dxf.location.y) - 2.0) < 1e-9


def test_block_edit_clipboard_paste_offsets_user_line() -> None:
    """Paste shifts USER_LINE by (paste_anchor - copy_anchor)."""
    d = LogicDiagram.new()
    if "NOT" not in d.doc.blocks:
        pytest.skip("NOT block missing from library")
    sess = BlockEditSession.open_existing(d.doc, "NOT")
    blk = sess.scratch_block()
    uid = add_user_line_to_block(blk, (1.0, 2.0), (4.0, 2.0), "CONTINUOUS")
    ent = find_entity_by_uid(sess.scratch_doc, uid)
    assert ent is not None
    pl = serialize_entity(sess.scratch_doc, ent)
    raw = encode_entity_payloads([pl])
    assert raw is not None
    root = decode_entity_clipboard(raw)
    assert root is not None
    n_before = sum(1 for e in blk if e.dxftype() == "LINE" and get_type(e) == ENTITY_TYPE_USER_LINE)
    handles = paste_entity_clipboard_root(sess, root, (10.0, 20.0))
    assert len(handles) == 1
    blk = sess.scratch_block()
    n_after = sum(1 for e in blk if e.dxftype() == "LINE" and get_type(e) == ENTITY_TYPE_USER_LINE)
    assert n_after == n_before + 1
    new_e = next(x for x in blk if str(getattr(x.dxf, "handle", "") or "") == handles[0])
    assert get_uid(new_e) != uid
    assert abs(float(new_e.dxf.start.x) - 8.5) < 1e-6
    assert abs(float(new_e.dxf.start.y) - 20.0) < 1e-6
    assert abs(float(new_e.dxf.end.x) - 11.5) < 1e-6
    assert abs(float(new_e.dxf.end.y) - 20.0) < 1e-6


def test_block_edit_clipboard_duplicate_attdef_renames_on_paste() -> None:
    d = LogicDiagram.new()
    if "NOT" not in d.doc.blocks:
        pytest.skip("NOT block missing from library")
    sess = BlockEditSession.open_existing(d.doc, "NOT")
    blk = sess.scratch_block()
    h0 = add_attdef_to_block(blk, "DUPTAG", (0.0, 0.0), "a", height_mm=2.0)
    ent0 = next(x for x in blk if str(getattr(x.dxf, "handle", "") or "") == h0)
    pl = serialize_entity(sess.scratch_doc, ent0)
    raw = encode_entity_payloads([pl])
    assert raw is not None
    root = decode_entity_clipboard(raw)
    assert root is not None
    paste_entity_clipboard_root(sess, root, (0.0, 0.0))
    blk = sess.scratch_block()
    tags = [str(e.dxf.tag) for e in blk if e.dxftype() == "ATTDEF"]
    assert any(t.upper() == "DUPTAG" for t in tags)
    assert any(t.upper().startswith("DUPTAG_") for t in tags)
