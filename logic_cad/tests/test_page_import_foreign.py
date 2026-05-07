"""Tests for importing paper layouts from foreign DXF and PAGE_REF target helpers."""

from __future__ import annotations

from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.core.model.constants import PEER_UID_XDATA, TARGET_LAYOUT_XDATA
from logic_cad.core.model.xdata import get_type, read_ld_app_dict
from logic_cad.core.pages.page_ref import (
    find_page_ref_insert,
    page_layout_target_is_usable,
    page_ref_insert_broken_for_editor,
    page_ref_peers_mutual_ok,
    page_ref_insert_target_unresolved_for_editor,
)


def test_page_layout_target_usable_and_editor_unresolved() -> None:
    """Usable targets match existing paper layouts; blanks and unknown names fail."""
    d = LogicDiagram.new()
    p0 = d.list_pages()[0]
    assert page_layout_target_is_usable(d.doc, p0)
    assert not page_layout_target_is_usable(d.doc, "")
    assert not page_layout_target_is_usable(d.doc, "no_such_layout")
    assert page_ref_insert_target_unresolved_for_editor(d.doc, "")
    assert page_ref_insert_target_unresolved_for_editor(d.doc, "no_such_layout")
    assert not page_ref_insert_target_unresolved_for_editor(d.doc, p0)


def test_import_two_pages_keeps_target_and_reconnects_peers() -> None:
    """TARGET_LAYOUT stays literal; peer_uid maps to counterpart after multi-page import."""
    src = LogicDiagram.new()
    src.add_page("SheetB")
    p0 = "01"
    src.set_current_page(p0)
    src.place_page_link_pair_ranked((22.0, 40.0), "SheetB", 0)

    tgt = LogicDiagram.new()
    with tgt.begin("imp"):
        tgt.import_pages_from_foreign_drawing(src.doc, [(p0, "ImpA"), ("SheetB", "ImpB")])

    blk_from = tgt.doc.blocks.get(tgt.doc.layouts.get("ImpA").block_record_name)
    from_xd = None
    for ent in blk_from:
        if ent.dxftype() != "INSERT":
            continue
        if get_type(ent) != "PAGE_REF":
            continue
        from_xd = read_ld_app_dict(ent)
        break
    assert from_xd is not None
    tgt_layout = str(from_xd.get(TARGET_LAYOUT_XDATA) or "").strip()
    assert tgt_layout == "SheetB"

    peer = str(from_xd.get(PEER_UID_XDATA) or "").strip()
    assert peer
    peer_hit = find_page_ref_insert(tgt.doc, peer)
    assert peer_hit is not None
    ln_peer, _ = peer_hit
    assert ln_peer == "ImpB"
    assert page_ref_peers_mutual_ok(tgt.doc, dict(from_xd)) is True
    assert not page_ref_insert_broken_for_editor(tgt.doc, "ImpA", dict(from_xd))


def test_import_single_page_keeps_target_peer_unresolved_when_partner_missing() -> None:
    """Partial import keeps TARGET literal; dangling peer yields broken corridor for editor."""
    src = LogicDiagram.new()
    src.add_page("SheetB")
    p0 = "01"
    src.set_page_metadata("SheetB", description="UniqB", revision="0")
    src.set_current_page(p0)
    src.place_page_link_pair_ranked((22.0, 40.0), "SheetB", 0)

    tgt = LogicDiagram.new()
    tgt.add_page("Extra")
    tgt.set_page_metadata("Extra", description="OtherDesc", revision="0")

    with tgt.begin("imp"):
        tgt.import_pages_from_foreign_drawing(src.doc, [(p0, "ImpA")])

    blk = tgt.doc.blocks.get(tgt.doc.layouts.get("ImpA").block_record_name)
    xd_page_ref = None
    for ent in blk:
        if ent.dxftype() != "INSERT":
            continue
        if get_type(ent) != "PAGE_REF":
            continue
        xd_page_ref = read_ld_app_dict(ent)
        break
    assert xd_page_ref is not None
    found = str(xd_page_ref.get(TARGET_LAYOUT_XDATA) or "").strip()
    assert found == "SheetB"
    assert page_ref_insert_target_unresolved_for_editor(tgt.doc, found)
    assert page_ref_insert_broken_for_editor(tgt.doc, "ImpA", dict(xd_page_ref))
