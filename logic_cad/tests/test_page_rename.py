"""Layout rename updates PAGE_REF targets."""

from logic_cad.core.model.constants import (
    PAGE_REF_SHOW_PAGE_DESC_XDATA,
    PAGE_REF_SHOW_PAGE_NAME_XDATA,
    PAGE_REF_SHOW_TARGET_INFO_XDATA,
    TARGET_LAYOUT_XDATA,
)
from logic_cad.core.dxf.dxf_repository import new_document
from logic_cad.core.pages.page_layout_meta import merge_layout_page_xdata
from logic_cad.core.pages.page_labels import (
    letters_to_page_index,
    page_index_to_letters,
    page_ref_link_label,
    page_symbol_label,
)
from logic_cad.core.pages.page_ref import (
    apply_ordered_page_ref_ranks_with_peers,
    page_link_picker_label,
    refresh_all_page_ref_syms,
    refresh_page_ref_syms_on_layout,
)
from logic_cad.core.services.layout_service import LayoutService, ensure_cross_page_reference_blocks
from logic_cad.core.services.symbol_service import SymbolService
from logic_cad.core.services.dynamic_gate_factory import DynamicGateFactory
from logic_cad.core.model.xdata import read_ld_app_dict


def test_rename_page_updates_page_ref_target() -> None:
    doc = new_document()
    names = [L.name for L in doc.layouts if not L.is_modelspace]
    first = names[0]
    ls = LayoutService(doc)
    ls.add_page("B")
    pages = ls.list_pages()
    assert "B" in pages
    ss = SymbolService(doc, DynamicGateFactory())
    uid = ss.place_page_link(first, (20.0, 30.0), "B", pages)
    ins = ss.insert_by_uid(first, uid)
    assert ins is not None
    assert read_ld_app_dict(ins).get(TARGET_LAYOUT_XDATA) == "B"
    ls.rename_page("B", "Page2")
    assert "Page2" in ls.list_pages()
    assert "B" not in ls.list_pages()
    ins2 = ss.insert_by_uid(first, uid)
    assert ins2 is not None
    xd = read_ld_app_dict(ins2)
    assert xd.get(TARGET_LAYOUT_XDATA) == "Page2"
    sym = None
    for a in ins2.attribs:
        if a.dxf.tag == "SYM":
            sym = a.dxf.text
            break
    assert sym == page_symbol_label("Page2", ls.list_pages())
    assert sym == page_ref_link_label("Page2", 0)


def test_two_page_refs_same_target_sym_a_b() -> None:
    doc = new_document()
    names = [L.name for L in doc.layouts if not L.is_modelspace]
    first = names[0]
    ls = LayoutService(doc)
    ls.add_page("102")
    pages = ls.list_pages()
    ss = SymbolService(doc, DynamicGateFactory())
    u0 = ss.place_page_link(first, (10.0, 20.0), "102", pages)
    u1 = ss.place_page_link(first, (30.0, 20.0), "102", pages)

    def _sym(uid: str) -> str | None:
        ins = ss.insert_by_uid(first, uid)
        assert ins is not None
        xd = read_ld_app_dict(ins)
        for a in ins.attribs:
            if str(a.dxf.tag).upper() == "SYM":
                return str(a.dxf.text or "")
        return xd.get("sym")

    assert _sym(u0) == "102 A"
    assert _sym(u1) == "102 B"


def _add_page_ref_target_attdefs(doc) -> None:
    ensure_cross_page_reference_blocks(doc)
    for block_name in ("PAGE_FROM", "PAGE_TO"):
        blk = doc.blocks.get(block_name)
        blk.add_attdef(tag="PAGE_NAME", text="", insert=(0.8, 1.8), height=0.28, dxfattribs={"layer": "LD_TEXT"})
        blk.add_attdef(tag="PAGE_DESC", text="", insert=(0.8, 1.2), height=0.28, dxfattribs={"layer": "LD_TEXT"})


def _attrib(ins, tag: str):
    want = str(tag).upper()
    for a in ins.attribs:
        if str(a.dxf.tag).upper() == want:
            return a
    return None


def test_page_ref_target_info_default_off_and_toggle_on() -> None:
    doc = new_document()
    _add_page_ref_target_attdefs(doc)
    names = [L.name for L in doc.layouts if not L.is_modelspace]
    first = names[0]
    ls = LayoutService(doc)
    ls.add_page("B")
    merge_layout_page_xdata(doc, "B", page_desc="Target page", page_rev="")
    ss = SymbolService(doc, DynamicGateFactory())
    uid = ss.place_page_link(first, (12.0, 10.0), "B", ls.list_pages())
    ins = ss.insert_by_uid(first, uid)
    assert ins is not None
    xd = read_ld_app_dict(ins)
    assert str(xd.get(PAGE_REF_SHOW_TARGET_INFO_XDATA) or "0") == "0"
    assert str(xd.get(PAGE_REF_SHOW_PAGE_NAME_XDATA) or "0") == "0"
    assert str(xd.get(PAGE_REF_SHOW_PAGE_DESC_XDATA) or "0") == "0"
    a_name = _attrib(ins, "PAGE_NAME")
    a_desc = _attrib(ins, "PAGE_DESC")
    assert a_name is not None
    assert a_desc is not None
    assert str(a_name.dxf.text or "") == "B"
    assert str(a_desc.dxf.text or "") == "Target page"
    assert bool(a_name.dxf.invisible)
    assert bool(a_desc.dxf.invisible)

    ss.set_page_ref_target_info_visibility(first, uid, show_page_name=True, show_page_desc=False)
    ins2 = ss.insert_by_uid(first, uid)
    assert ins2 is not None
    xd2 = read_ld_app_dict(ins2)
    assert str(xd2.get(PAGE_REF_SHOW_TARGET_INFO_XDATA) or "") == ""
    assert str(xd2.get(PAGE_REF_SHOW_PAGE_NAME_XDATA) or "") == "1"
    assert str(xd2.get(PAGE_REF_SHOW_PAGE_DESC_XDATA) or "") == "0"
    a_name2 = _attrib(ins2, "PAGE_NAME")
    a_desc2 = _attrib(ins2, "PAGE_DESC")
    assert a_name2 is not None
    assert a_desc2 is not None
    assert not bool(a_name2.dxf.invisible)
    assert bool(a_desc2.dxf.invisible)


def test_refresh_all_page_ref_syms_keeps_toggle_and_updates_desc() -> None:
    doc = new_document()
    _add_page_ref_target_attdefs(doc)
    names = [L.name for L in doc.layouts if not L.is_modelspace]
    first = names[0]
    ls = LayoutService(doc)
    ls.add_page("B")
    merge_layout_page_xdata(doc, "B", page_desc="Before", page_rev="")
    ss = SymbolService(doc, DynamicGateFactory())
    uid = ss.place_page_link(first, (18.0, 10.0), "B", ls.list_pages())
    ss.set_page_ref_target_info_visibility(first, uid, show_page_name=False, show_page_desc=True)

    merge_layout_page_xdata(doc, "B", page_desc="After", page_rev="")
    refresh_all_page_ref_syms(doc)

    ins = ss.insert_by_uid(first, uid)
    assert ins is not None
    xd = read_ld_app_dict(ins)
    assert str(xd.get(PAGE_REF_SHOW_TARGET_INFO_XDATA) or "") == ""
    assert str(xd.get(PAGE_REF_SHOW_PAGE_NAME_XDATA) or "") == "0"
    assert str(xd.get(PAGE_REF_SHOW_PAGE_DESC_XDATA) or "") == "1"
    a_desc = _attrib(ins, "PAGE_DESC")
    a_name = _attrib(ins, "PAGE_NAME")
    assert a_desc is not None
    assert a_name is not None
    assert str(a_desc.dxf.text or "") == "After"
    assert not bool(a_desc.dxf.invisible)
    assert bool(a_name.dxf.invisible)


def test_letters_inverse_roundtrip() -> None:
    for idx in range(160):
        s = page_index_to_letters(idx)
        assert letters_to_page_index(s) == idx


def test_page_link_picker_matches_geom_sym_letters_when_editing() -> None:
    doc = new_document()
    names = [L.name for L in doc.layouts if not L.is_modelspace]
    first = names[0]
    ls = LayoutService(doc)
    ls.add_page("102")
    pages = ls.list_pages()
    ss = SymbolService(doc, DynamicGateFactory())
    u0 = ss.place_page_link(first, (10.0, 20.0), "102", pages)
    u1 = ss.place_page_link(first, (30.0, 20.0), "102", pages)
    lbl0 = page_link_picker_label(doc, first, "102", exclude_uid=u0)
    lbl1 = page_link_picker_label(doc, first, "102", exclude_uid=u1)
    assert "(" + page_index_to_letters(0) + ")" in lbl0
    assert "(" + page_index_to_letters(1) + ")" in lbl1


def test_apply_ordered_ranks_swaps_symbols() -> None:
    doc = new_document()
    names = [L.name for L in doc.layouts if not L.is_modelspace]
    first = names[0]
    ls = LayoutService(doc)
    ls.add_page("102")
    pages = ls.list_pages()
    ss = SymbolService(doc, DynamicGateFactory())
    u0 = ss.place_page_link(first, (10.0, 20.0), "102", pages)
    u1 = ss.place_page_link(first, (30.0, 20.0), "102", pages)

    apply_ordered_page_ref_ranks_with_peers(doc, first, "102", [u1, u0])

    def _sym(uid: str) -> str | None:
        ins = ss.insert_by_uid(first, uid)
        assert ins is not None
        xd = read_ld_app_dict(ins)
        for a in ins.attribs:
            if str(a.dxf.tag).upper() == "SYM":
                return str(a.dxf.text or "")
        return xd.get("sym")

    assert _sym(u0) == "102 B"
    assert _sym(u1) == "102 A"


def test_place_peer_cross_layout_matching_suffix() -> None:
    doc = new_document()
    names = [L.name for L in doc.layouts if not L.is_modelspace]
    first = names[0]
    ls = LayoutService(doc)
    ls.add_page("ZPAGE")
    pages = ls.list_pages()
    ss = SymbolService(doc, DynamicGateFactory())
    rk = 4
    uf = ss.place_page_link(first, (5.0, 10.0), "ZPAGE", pages, defer_refresh=True, page_ref_rank=rk)
    ut = ss.place_page_link("ZPAGE", (5.0, 12.0), first, pages, outgoing=False, defer_refresh=True, page_ref_rank=rk)
    ss.link_page_ref_peers_cross_layout(first, uf, "ZPAGE", ut)
    refresh_page_ref_syms_on_layout(doc, first)
    refresh_page_ref_syms_on_layout(doc, "ZPAGE")
    xf = read_ld_app_dict(ss.insert_by_uid(first, uf))
    xt = read_ld_app_dict(ss.insert_by_uid("ZPAGE", ut))
    want_letter = page_index_to_letters(rk)
    assert xf.get("sym") == f"ZPAGE {want_letter}"
    assert xt.get("sym") == f"{first} {want_letter}"
