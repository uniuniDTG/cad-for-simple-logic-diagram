"""Sorted page names (natural order + TOC first), tab order on save."""

from pathlib import Path
import tempfile

from logic_cad.core.model.constants import TOC_LAYOUT_NAME
from logic_cad.core.dxf.dxf_repository import new_document, readfile, saveas
from logic_cad.core.pages.page_order import (
    is_reserved_toc_page_id,
    is_toc_layout_name,
    list_paper_layout_names_sorted,
    sort_paper_layout_names,
    toc_page_id_for_slot,
)
from logic_cad.core.pages.page_layout_meta import read_page_meta
from logic_cad.core.services.layout_service import LayoutService


def test_list_pages_sorted_by_name() -> None:
    doc = new_document()
    ls = LayoutService(doc)
    ls.add_page("Zeta")
    ls.add_page("Alpha")
    assert ls.list_pages() == ["Alpha", "Layout1", "Zeta"]


def test_list_pages_natural_numeric_order() -> None:
    doc = new_document()
    ls = LayoutService(doc)
    ls.add_page("11")
    ls.add_page("2")
    ls.add_page("10")
    assert ls.list_pages() == ["2", "10", "11", "Layout1"]


def test_sort_paper_layout_names_natural() -> None:
    assert sort_paper_layout_names(["10", "2", "foo10", "foo2"]) == ["2", "10", "foo2", "foo10"]


def test_is_toc_layout_name() -> None:
    assert is_toc_layout_name(TOC_LAYOUT_NAME)
    assert is_toc_layout_name("0A")
    assert is_toc_layout_name("0B")
    assert not is_toc_layout_name("Layout1")
    assert not is_toc_layout_name("01")


def test_toc_page_id_slots() -> None:
    assert toc_page_id_for_slot(0) == "0"
    assert toc_page_id_for_slot(1) == "0A"
    assert toc_page_id_for_slot(2) == "0B"


def test_reserved_toc_page_id_pattern() -> None:
    assert is_reserved_toc_page_id("0")
    assert is_reserved_toc_page_id("0A")
    assert is_reserved_toc_page_id("0AA")
    assert not is_reserved_toc_page_id("10")
    assert not is_reserved_toc_page_id("01")


def test_toc_layout_names_sort_slot_order() -> None:
    doc = new_document()
    ls = LayoutService(doc)
    for n in ("0B", "0", "0A"):
        doc.layouts.new(n)
        ls.ensure_minimal_page(n)
    toc = [n for n in list_paper_layout_names_sorted(doc) if is_toc_layout_name(n)]
    assert toc == ["0", "0A", "0B"]
    assert "page_id" not in read_page_meta(doc, "0")


def test_saveas_sets_taborder_by_name() -> None:
    doc = new_document()
    ls = LayoutService(doc)
    ls.add_page("Z")
    ls.add_page("A")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.dxf"
        saveas(doc, p)
        doc2 = readfile(p)
    order = doc2.layouts.names_in_taborder()
    assert order[0] == "Model"
    paper = [n for n in order if n != "Model"]
    assert paper == list_paper_layout_names_sorted(doc2)
