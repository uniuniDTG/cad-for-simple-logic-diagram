"""Page link display labels and picker text."""

from logic_cad.core.model.constants import TOC_LAYOUT_NAME
from logic_cad.core.pages.page_labels import page_index_to_letters, page_ref_link_label, page_symbol_label


def test_page_index_to_letters():
    assert page_index_to_letters(0) == "A"
    assert page_index_to_letters(25) == "Z"
    assert page_index_to_letters(26) == "AA"
    assert page_index_to_letters(27) == "AB"


def test_page_symbol_label_same_suffix_a_for_all_non_toc():
    pages = ["101", "102", "103"]
    assert page_symbol_label("101", pages) == "101 A"
    assert page_symbol_label("102", pages) == "102 A"
    assert page_symbol_label("103", pages) == "103 A"


def test_page_symbol_label_mixed_names_all_use_a():
    pages = ["Alpha", "Layout1", "Zeta"]
    assert page_symbol_label("Alpha", pages) == "Alpha A"
    assert page_symbol_label("Layout1", pages) == "Layout1 A"
    assert page_symbol_label("Zeta", pages) == "Zeta A"


def test_page_ref_link_label_ordinals_and_space():
    assert page_ref_link_label("102", 0) == "102 A"
    assert page_ref_link_label("102", 1) == "102 B"
    assert page_ref_link_label("102", 2) == "102 C"
    assert page_ref_link_label("102", 25) == "102 Z"
    assert page_ref_link_label("102", 26) == "102 AA"


def test_page_symbol_label_toc_names_unchanged():
    pages = [TOC_LAYOUT_NAME, "101"]
    assert page_symbol_label(TOC_LAYOUT_NAME, pages) == TOC_LAYOUT_NAME
    assert page_symbol_label("101", pages) == "101 A"
