"""Tests for symbol block edit session, port helpers, scratch undo."""

from __future__ import annotations

import ezdxf
import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from logic_cad.core.dxf.attrib_geometry_sync import sync_insert_attrib_geometry_for_block_name
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
    add_plain_text_to_block,
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
from logic_cad.core.text.layout_resolver import normalize_dxf_text_entity
from logic_cad.ui.snap_utils import dxf_from_scene_pos, scene_pos_from_dxf
from logic_cad.ui.symbol_block_editor.scene import AttdefEditItem, PortMarkerItem, SymbolBlockEditScene
from logic_cad.core.services.block_edit_clipboard import (
    decode_entity_clipboard,
    encode_entity_payloads,
    paste_entity_clipboard_root,
)
from logic_cad.core.undo.scratch_transaction import ScratchUndoDiagram, scratch_undo
from logic_cad.core.undo.entity_serialize import restore_entity_from_payload, serialize_entity


def test_block_edit_scratch_definition_name_matches_scratch_block() -> None:
    d = LogicDiagram.new()
    if d.doc.blocks.get("PAGE_FROM") is None:
        pytest.skip("PAGE_FROM missing from document")
    sess = BlockEditSession.open_existing(d.doc, "PAGE_FROM")
    assert sess.scratch_definition_name() == "PAGE_FROM"
    sb = sess.scratch_block()
    assert sb is not None
    assert str(sb.name) == "PAGE_FROM"


def test_attdef_edit_item_empty_default_text_shows_placeholder_bounds() -> None:
    """Empty ATTDEF default text yields non-trivial bounds via block-editor placeholder glyph."""
    if QApplication.instance() is None:
        _ = QApplication([])
    sess = BlockEditSession.open_new("TMP_ATTDEF_PLACE_BOUNDS")
    blk = sess.scratch_block()
    assert blk is not None
    h = add_attdef_to_block(blk, "LABEL0", (3.0, 4.0), "", height_mm=3.0)
    assert h

    def _session() -> BlockEditSession | None:
        return sess

    item = AttdefEditItem(_session, h, snap_pitch_mm=lambda: float(BLOCK_EDIT_SNAP_PITCH_MM))
    item.sync_pos_from_entity()
    br = item.boundingRect()
    assert br.height() > 1.5
    assert br.width() > 0.25
    assert str(next(e for e in blk if str(getattr(e.dxf, "handle", "") or "") == h).dxf.text or "") == ""


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


def test_apply_then_open_existing_preserves_user_line_ld_app() -> None:
    """Scratch reopened via serialize path must keep uid so USER_LINE stays editable in BEDIT."""

    d = LogicDiagram.new()
    if "NOT" not in d.doc.blocks:
        pytest.skip("NOT block missing from library")
    sess = BlockEditSession.open_existing(d.doc, "NOT")
    blk = sess.scratch_block()
    assert blk is not None
    uid = add_user_line_to_block(blk, (0.0, 0.0), (3.0, 0.0), "CONTINUOUS")
    assert find_entity_by_uid(sess.scratch_doc, uid) is not None
    sess.apply_to(d)
    sess2 = BlockEditSession.open_existing(d.doc, "NOT")
    e2 = find_entity_by_uid(sess2.scratch_doc, uid)
    assert e2 is not None
    assert e2.dxftype() == "LINE"
    assert str(e2.dxf.layer) == LAYER_SYMBOL
    assert get_type(e2) == ENTITY_TYPE_USER_LINE


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


def test_block_edit_refresh_keeps_off_grid_attdef_scene_pos() -> None:
    """Session rebuild must place ATTDEF at DXF anchor without rounding to snap grid."""

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    sess = BlockEditSession.open_new("TMP_OFFGRID_ATTDEF_POS")
    blk = sess.scratch_block()
    assert blk is not None
    h = add_attdef_to_block(blk, "LABEL0", (1.03, -2.07), "x", height_mm=2.0)
    ent = next(x for x in blk if str(getattr(x.dxf, "handle", "") or "") == h)
    lay = normalize_dxf_text_entity(ent)

    scene = SymbolBlockEditScene(
        get_session=lambda: sess,
        request_port_layer=lambda: None,
        sketch_line_linetype=lambda: "CONTINUOUS",
    )
    scene.refresh_from_session()

    ad = next(i for i in scene.items() if isinstance(i, AttdefEditItem))
    sx, sy = dxf_from_scene_pos(ad.scenePos())
    assert sx == pytest.approx(float(lay.anchor_x))
    assert sy == pytest.approx(float(lay.anchor_y))


def test_block_edit_refresh_keeps_off_grid_port_scene_pos() -> None:
    """Session rebuild must place port marker at DXF location without snap rounding."""

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    sess = BlockEditSession.open_new("TMP_OFFGRID_PORT_POS")
    blk = sess.scratch_block()
    assert blk is not None
    layer = make_port_layer_name("IN", 3, "LOGIC")
    x_pt, y_pt = 2.17, -4.53
    with sess.begin("add_port"):
        blk.add_point((x_pt, y_pt), dxfattribs={"layer": layer})

    scene = SymbolBlockEditScene(
        get_session=lambda: sess,
        request_port_layer=lambda: None,
        sketch_line_linetype=lambda: "CONTINUOUS",
    )
    scene.refresh_from_session()

    pm = next(i for i in scene.items() if isinstance(i, PortMarkerItem))
    px, py = dxf_from_scene_pos(pm.scenePos())
    assert px == pytest.approx(x_pt)
    assert py == pytest.approx(y_pt)


def test_commit_skips_attdef_and_port_when_not_dragged() -> None:
    """Commit paths must not alter ATTDEF/port DXF from pitch-vs-display rounding alone."""

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    sess = BlockEditSession.open_new("TMP_COMMIT_SKIP_OFFGRID")
    blk = sess.scratch_block()
    assert blk is not None
    h_att = add_attdef_to_block(blk, "LABEL0", (1.03, -2.07), "x", height_mm=2.0)
    layer = make_port_layer_name("OUT", 2, "LOGIC")
    x_pt, y_pt = 3.17, -1.53
    with sess.begin("add_port"):
        blk.add_point((x_pt, y_pt), dxfattribs={"layer": layer})

    scene = SymbolBlockEditScene(
        get_session=lambda: sess,
        request_port_layer=lambda: None,
        sketch_line_linetype=lambda: "CONTINUOUS",
    )
    scene.set_auxiliary_grid_visible(False)
    assert scene.snap_pitch_mm == pytest.approx(GRID_PITCH)
    scene.refresh_from_session()

    assert scene._commit_attdef_moves() is False
    assert scene._commit_port_moves() is False

    ent_att = next(x for x in blk if str(getattr(x.dxf, "handle", "") or "") == h_att)
    ent_pt = next(
        e
        for e in blk
        if e.dxftype() == "POINT" and str(e.dxf.layer).upper() == layer.upper()
    )
    assert float(ent_att.dxf.insert.x) == pytest.approx(1.03)
    assert float(ent_att.dxf.insert.y) == pytest.approx(-2.07)
    assert float(ent_pt.dxf.location.x) == pytest.approx(x_pt)
    assert float(ent_pt.dxf.location.y) == pytest.approx(y_pt)


def test_commit_ignores_stale_attdef_moved_without_drag_snapshot() -> None:
    """Spurious ``_moved`` alone must not commit ATTDEF if drag snapshot does not track this item."""

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    sess = BlockEditSession.open_new("TMP_COMMIT_ATTDEF_STALE_MOVE")
    blk = sess.scratch_block()
    assert blk is not None
    h_att = add_attdef_to_block(blk, "LABEL0", (1.03, -2.07), "x", height_mm=2.0)

    scene = SymbolBlockEditScene(
        get_session=lambda: sess,
        request_port_layer=lambda: None,
        sketch_line_linetype=lambda: "CONTINUOUS",
    )
    scene.refresh_from_session()
    ad = next(i for i in scene.items() if isinstance(i, AttdefEditItem))
    scene._drag_start_scene = {}
    ad._moved = True

    assert scene._commit_attdef_moves() is False
    assert ad._moved is False
    ent_att = next(x for x in blk if str(getattr(x.dxf, "handle", "") or "") == h_att)
    assert float(ent_att.dxf.insert.x) == pytest.approx(1.03)
    assert float(ent_att.dxf.insert.y) == pytest.approx(-2.07)


def test_commit_writes_attdef_when_moved_flag_set() -> None:
    """After a drag, ATTDEF insert commits at grid pitch."""

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    sess = BlockEditSession.open_new("TMP_COMMIT_ATTDEF_DRAG")
    blk = sess.scratch_block()
    assert blk is not None
    h_att = add_attdef_to_block(blk, "LABEL0", (0.0, 0.0), "x", height_mm=2.0)

    scene = SymbolBlockEditScene(
        get_session=lambda: sess,
        request_port_layer=lambda: None,
        sketch_line_linetype=lambda: "CONTINUOUS",
    )
    scene.refresh_from_session()
    ad = next(i for i in scene.items() if isinstance(i, AttdefEditItem))
    scene._drag_start_scene = {id(ad): QPointF(ad.scenePos())}

    ad._programmatic_pos_depth += 1
    try:
        ad.setPos(scene_pos_from_dxf(5.07, -6.08))
    finally:
        ad._programmatic_pos_depth -= 1
    ad._moved = True

    assert scene._commit_attdef_moves() is True
    ent_att = next(x for x in blk if str(getattr(x.dxf, "handle", "") or "") == h_att)
    assert float(ent_att.dxf.insert.x) == pytest.approx(5.0)
    assert float(ent_att.dxf.insert.y) == pytest.approx(-6.0)


def test_commit_writes_port_when_moved_flag_set() -> None:
    """After a drag, port POINT commits at grid pitch."""

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    sess = BlockEditSession.open_new("TMP_COMMIT_PORT_DRAG")
    blk = sess.scratch_block()
    assert blk is not None
    layer = make_port_layer_name("IN", 1, "LOGIC")
    with sess.begin("add_port"):
        blk.add_point((0.0, 0.0), dxfattribs={"layer": layer})

    scene = SymbolBlockEditScene(
        get_session=lambda: sess,
        request_port_layer=lambda: None,
        sketch_line_linetype=lambda: "CONTINUOUS",
    )
    scene.refresh_from_session()
    pm = next(i for i in scene.items() if isinstance(i, PortMarkerItem))
    scene._drag_start_scene = {id(pm): QPointF(pm.scenePos())}

    pm._programmatic_pos_depth += 1
    try:
        pm.setPos(scene_pos_from_dxf(9.06, -4.09))
    finally:
        pm._programmatic_pos_depth -= 1
    pm._pm_moved = True

    assert scene._commit_port_moves() is True
    ent_pt = next(
        e
        for e in blk
        if e.dxftype() == "POINT" and str(e.dxf.layer).upper() == layer.upper()
    )
    assert float(ent_pt.dxf.location.x) == pytest.approx(9.0)
    assert float(ent_pt.dxf.location.y) == pytest.approx(-4.0)


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


def test_add_plain_text_ld_text_layer() -> None:
    sess = BlockEditSession.open_new("TMP_PLAIN_TEXT1")
    blk = sess.scratch_block()
    assert blk is not None
    h = add_plain_text_to_block(blk, (3.0, -1.5), "Note", height_mm=2.25)
    ent = next(e for e in blk if str(getattr(e.dxf, "handle", "") or "") == h)
    assert ent.dxftype() == "TEXT"
    assert str(ent.dxf.layer).upper() == LAYER_TEXT.upper()
    assert abs(float(ent.dxf.insert.x) - 3.0) < 1e-9
    assert str(ent.dxf.text) == "Note"


def test_restore_mtext_from_payload_in_scratch_block() -> None:
    sess = BlockEditSession.open_new("TMP_MTEXT_SER")
    blk = sess.scratch_block()
    assert blk is not None
    with sess.begin("add"):
        mt = blk.add_mtext(
            r"line1\Pline2",
            dxfattribs={
                "layer": LAYER_TEXT,
                "char_height": 2.8,
                "width": 55.0,
                "insert": (9.0, -4.0, 0.0),
                "attachment_point": 3,
            },
        )
    pl = serialize_entity(sess.scratch_doc, mt)
    assert pl.get("dxftype") == "MTEXT"
    geom = pl.get("geometry") or {}
    assert "line1" in str(geom.get("text", ""))
    h_old = str(mt.dxf.handle)
    with sess.begin("del"):
        blk.delete_entity(mt)
    pl2 = dict(pl)
    pl2.pop("handle", None)
    pl2["owner"] = {"kind": "block", "name": sess.block_name}
    with sess.begin("restore"):
        ent2 = restore_entity_from_payload(sess.scratch_doc, pl2)
    assert ent2 is not None
    assert ent2.dxftype() == "MTEXT"
    assert str(getattr(ent2.dxf, "handle", "") or "") != h_old
    assert abs(float(ent2.dxf.insert.x) - 9.0) < 1e-9
    assert abs(float(ent2.dxf.char_height) - 2.8) < 1e-9
    assert abs(float(ent2.dxf.width) - 55.0) < 1e-9
    assert int(getattr(ent2.dxf, "attachment_point", 0) or 0) == 3


def test_add_attdef_to_block_sets_halign_and_align_point() -> None:
    """New ATTDEF from block editor helper gets explicit halign and align_point."""

    sess = BlockEditSession.open_new("TMP_ATTDEF_HALIGN_AP")
    blk = sess.scratch_block()
    assert blk is not None
    h = add_attdef_to_block(blk, "LABEL0", (2.5, -1.25), "x", height_mm=2.0)
    ent = next(e for e in blk if str(getattr(e.dxf, "handle", "") or "") == h)
    assert ent.dxftype() == "ATTDEF"
    assert int(ent.dxf.halign) == 0
    ins = ent.dxf.insert
    ap = ent.dxf.align_point
    assert abs(float(ins.x) - float(ap.x)) < 1e-9
    assert abs(float(ins.y) - float(ap.y)) < 1e-9
    assert abs(float(ins.z) - float(ap.z)) < 1e-9


def test_sync_insert_attrib_geometry_for_block_name_only_matching_inserts() -> None:
    """sync_insert_attrib_geometry_for_block_name updates only INSERTs of that block."""

    doc = ezdxf.new("R2010", setup=["styles"])
    sym_a = doc.blocks.new("BLOCK_A")
    ad_a = sym_a.add_attdef("T", (1.0, 2.0), "", dxfattribs={"height": 1.0, "halign": 1})
    ad_a.dxf.align_point = (1.0, 2.0, 0.0)
    sym_b = doc.blocks.new("BLOCK_B")
    ad_b = sym_b.add_attdef("T", (0.0, 0.0), "", dxfattribs={"height": 1.0, "halign": 0})
    ad_b.dxf.align_point = (0.0, 0.0, 0.0)

    lay = doc.layouts.get("Layout1")
    lb = doc.blocks.get(lay.block_record_name)
    ins_a = lb.add_blockref("BLOCK_A", (10.0, 20.0))
    ins_a.add_attrib("T", "hello", (99.0, 88.0), dxfattribs={"height": 0.1, "halign": 0})
    ins_a.attribs[0].dxf.invisible = 1
    ins_b = lb.add_blockref("BLOCK_B", (5.0, 5.0))
    ins_b.add_attrib("T", "other", (7.0, 8.0), dxfattribs={"height": 1.0, "halign": 0})

    n = sync_insert_attrib_geometry_for_block_name(doc, "BLOCK_A")
    assert n == 1
    a = ins_a.attribs[0]
    assert str(a.dxf.text) == "hello"
    assert int(a.dxf.invisible) == 1
    assert float(a.dxf.insert.x) == pytest.approx(1.0)
    assert float(a.dxf.insert.y) == pytest.approx(2.0)
    assert int(a.dxf.halign) == 1
    b = ins_b.attribs[0]
    assert float(b.dxf.insert.x) == pytest.approx(7.0)
    assert str(b.dxf.text) == "other"
