"""Layout rename updates PAGE_REF targets."""

from logic_cad.core.model.constants import TARGET_LAYOUT_XDATA
from logic_cad.core.dxf.dxf_repository import new_document
from logic_cad.core.pages.page_labels import page_ref_link_label, page_symbol_label
from logic_cad.core.pages.page_ref import page_link_picker_label
from logic_cad.core.services.layout_service import LayoutService
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

