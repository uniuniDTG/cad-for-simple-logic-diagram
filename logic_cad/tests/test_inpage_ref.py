"""INPAGE_REF pairing and ※n labels on one layout."""

from logic_cad.core.dxf.dxf_repository import new_document
from logic_cad.core.model.constants import (
    ENTITY_TYPE_INPAGE_REF,
    INPAGE_LINK_NAME_AUTO_XDATA,
    INPAGE_SYM_HEIGHT_XDATA,
    PEER_UID_XDATA,
)
from logic_cad.core.model.xdata import get_type, get_uid, read_ld_app_dict
from logic_cad.core.pages.inpage_ref import inpage_ref_label, refresh_inpage_ref_syms_on_layout
from logic_cad.core.services.dynamic_gate_factory import DynamicGateFactory
from logic_cad.core.services.layout_service import LayoutService
from logic_cad.core.services.symbol_service import SymbolService
from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.core.undo.history import find_entity_by_uid


def _sym(uid: str, ss: SymbolService, layout: str) -> str:
    ins = ss.insert_by_uid(layout, uid)
    assert ins is not None
    xd = read_ld_app_dict(ins)
    for a in ins.attribs:
        if str(a.dxf.tag).upper() == "SYM":
            return str(a.dxf.text or "")
    return str(xd.get("sym") or "")


def test_inpage_ref_label_helper() -> None:
    assert inpage_ref_label(1) == "※1"
    assert inpage_ref_label(12) == "※12"


def test_pair_shares_sym_and_peer_xdata() -> None:
    doc = new_document()
    names = [L.name for L in doc.layouts if not L.is_modelspace]
    layout = names[0]
    ss = SymbolService(doc, DynamicGateFactory())
    u_from = ss.place_inpage_ref(layout, (10.0, 20.0), outgoing=True, peer_uid="")
    u_to = ss.place_inpage_ref(layout, (40.0, 22.0), outgoing=False, peer_uid=u_from)
    ss.link_inpage_ref_pair(layout, u_from, u_to)
    assert _sym(u_from, ss, layout) == "※1"
    assert _sym(u_to, ss, layout) == "※1"
    ins_f = ss.insert_by_uid(layout, u_from)
    ins_t = ss.insert_by_uid(layout, u_to)
    assert ins_f is not None and ins_t is not None
    assert read_ld_app_dict(ins_f).get(PEER_UID_XDATA) == u_to
    assert read_ld_app_dict(ins_t).get(PEER_UID_XDATA) == u_from
    assert read_ld_app_dict(ins_f).get("type") == ENTITY_TYPE_INPAGE_REF


def test_set_inpage_sym_height_updates_xdata_and_attrib() -> None:
    doc = new_document()
    layout = [L.name for L in doc.layouts if not L.is_modelspace][0]
    ss = SymbolService(doc, DynamicGateFactory())
    uid = ss.place_inpage_ref(layout, (10.0, 20.0), outgoing=True, peer_uid="")
    ss.set_inpage_sym_height(layout, uid, 5.5)
    ins = ss.insert_by_uid(layout, uid)
    assert ins is not None
    xd = read_ld_app_dict(ins)
    assert float(xd.get(INPAGE_SYM_HEIGHT_XDATA) or 0.0) == 5.5
    sym_heights = [float(a.dxf.height) for a in ins.attribs if str(a.dxf.tag).upper() == "SYM"]
    assert sym_heights == [5.5]
    ss.set_inpage_sym_height(layout, uid, 0.1)
    ins2 = ss.insert_by_uid(layout, uid)
    assert ins2 is not None
    assert float(read_ld_app_dict(ins2).get(INPAGE_SYM_HEIGHT_XDATA) or 0.0) == 0.25
    ss.set_inpage_sym_height(layout, uid, 100.0)
    ins3 = ss.insert_by_uid(layout, uid)
    assert ins3 is not None
    assert float(read_ld_app_dict(ins3).get(INPAGE_SYM_HEIGHT_XDATA) or 0.0) == 80.0


def test_two_pairs_renumbered() -> None:
    doc = new_document()
    layout = [L.name for L in doc.layouts if not L.is_modelspace][0]
    ss = SymbolService(doc, DynamicGateFactory())
    a0 = ss.place_inpage_ref(layout, (5.0, 50.0), outgoing=True, peer_uid="")
    b0 = ss.place_inpage_ref(layout, (25.0, 50.0), outgoing=False, peer_uid=a0)
    ss.link_inpage_ref_pair(layout, a0, b0)
    a1 = ss.place_inpage_ref(layout, (5.0, 30.0), outgoing=True, peer_uid="")
    b1 = ss.place_inpage_ref(layout, (25.0, 30.0), outgoing=False, peer_uid=a1)
    ss.link_inpage_ref_pair(layout, a1, b1)
    # Sort key uses ``-insert.y`` ascending (same as PAGE_REF): larger y → smaller −y → listed first.
    assert _sym(a0, ss, layout) == "※1"
    assert _sym(b0, ss, layout) == "※1"
    assert _sym(a1, ss, layout) == "※2"
    assert _sym(b1, ss, layout) == "※2"


def test_delete_by_uid_removes_partner() -> None:
    doc = new_document()
    layout = [L.name for L in doc.layouts if not L.is_modelspace][0]
    d = LogicDiagram(doc, layout)
    u0 = d.place_inpage_link((10.0, 20.0))
    u1 = d.place_inpage_link_peer(u0, (30.0, 22.0))
    assert find_entity_by_uid(doc, u0) is not None
    assert find_entity_by_uid(doc, u1) is not None
    d.delete_by_uid(u0)
    assert find_entity_by_uid(doc, u0) is None
    assert find_entity_by_uid(doc, u1) is None


def test_duplicate_page_remaps_peer_uid() -> None:
    doc = new_document()
    ls = LayoutService(doc)
    pages = ls.list_pages()
    src = pages[0]
    dest = "InpageDupDest"
    ss = SymbolService(doc, DynamicGateFactory())
    u_from = ss.place_inpage_ref(src, (12.0, 18.0), outgoing=True, peer_uid="")
    u_to = ss.place_inpage_ref(src, (33.0, 19.0), outgoing=False, peer_uid=u_from)
    ss.link_inpage_ref_pair(src, u_from, u_to)
    ls.duplicate_paper_layout(src, dest)
    blk = doc.blocks.get(doc.layouts.get(dest).block_record_name)
    uids: list[str] = []
    for e in blk:
        if e.dxftype() != "INSERT":
            continue
        if get_type(e) == ENTITY_TYPE_INPAGE_REF:
            uids.append(get_uid(e) or "")
    assert len(uids) == 2
    ins0 = ss.insert_by_uid(dest, uids[0])
    ins1 = ss.insert_by_uid(dest, uids[1])
    assert ins0 is not None and ins1 is not None
    p0 = read_ld_app_dict(ins0).get(PEER_UID_XDATA)
    p1 = read_ld_app_dict(ins1).get(PEER_UID_XDATA)
    assert {p0, p1} == {uids[0], uids[1]}
    assert p0 != p1


def test_manual_link_label_survives_refresh() -> None:
    doc = new_document()
    layout = [L.name for L in doc.layouts if not L.is_modelspace][0]
    ss = SymbolService(doc, DynamicGateFactory())
    u_from = ss.place_inpage_ref(layout, (10.0, 40.0), outgoing=True, peer_uid="")
    u_to = ss.place_inpage_ref(layout, (40.0, 40.0), outgoing=False, peer_uid=u_from)
    ss.link_inpage_ref_pair(layout, u_from, u_to)
    ss.set_inpage_ref_link_display(layout, u_from, link_name_auto=False, display_text="Alpha")
    refresh_inpage_ref_syms_on_layout(doc, layout)
    assert _sym(u_from, ss, layout) == "Alpha"
    assert _sym(u_to, ss, layout) == "Alpha"
    for u in (u_from, u_to):
        xd = read_ld_app_dict(ss.insert_by_uid(layout, u))
        assert xd.get(INPAGE_LINK_NAME_AUTO_XDATA) == "0"


def test_mixed_manual_auto_ordinals_skip_gaps() -> None:
    """Manual pair first in sort order: auto pair still gets ※1 (policy A)."""
    doc = new_document()
    layout = [L.name for L in doc.layouts if not L.is_modelspace][0]
    ss = SymbolService(doc, DynamicGateFactory())
    a0 = ss.place_inpage_ref(layout, (5.0, 50.0), outgoing=True, peer_uid="")
    b0 = ss.place_inpage_ref(layout, (25.0, 50.0), outgoing=False, peer_uid=a0)
    ss.link_inpage_ref_pair(layout, a0, b0)
    a1 = ss.place_inpage_ref(layout, (5.0, 30.0), outgoing=True, peer_uid="")
    b1 = ss.place_inpage_ref(layout, (25.0, 30.0), outgoing=False, peer_uid=a1)
    ss.link_inpage_ref_pair(layout, a1, b1)
    ss.set_inpage_ref_link_display(layout, a0, link_name_auto=False, display_text="M")
    assert _sym(a0, ss, layout) == "M"
    assert _sym(b0, ss, layout) == "M"
    assert _sym(a1, ss, layout) == "※1"
    assert _sym(b1, ss, layout) == "※1"


def test_revert_manual_to_auto_renumbers() -> None:
    doc = new_document()
    layout = [L.name for L in doc.layouts if not L.is_modelspace][0]
    ss = SymbolService(doc, DynamicGateFactory())
    u_from = ss.place_inpage_ref(layout, (10.0, 40.0), outgoing=True, peer_uid="")
    u_to = ss.place_inpage_ref(layout, (40.0, 40.0), outgoing=False, peer_uid=u_from)
    ss.link_inpage_ref_pair(layout, u_from, u_to)
    ss.set_inpage_ref_link_display(layout, u_from, link_name_auto=False, display_text="Z")
    ss.set_inpage_ref_link_display(layout, u_from, link_name_auto=True, display_text="")
    assert _sym(u_from, ss, layout) == "※1"
    assert _sym(u_to, ss, layout) == "※1"
