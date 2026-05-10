"""ATTDEF tag helpers."""

from logic_cad.core.attrib_tags import (
    is_supported_attdef_tag,
    list_editable_text_attdef_tags,
    symbol_editor_attdef_tag_choices_for_block,
    symbol_editor_attdef_tag_choices_unused_in_block,
)
from logic_cad.core.dxf.dxf_repository import new_document
from logic_cad.core.model.constants import BLOCK_PAGE_FROM, BLOCK_PAGE_TO, LAYER_TEXT


def test_is_supported_attdef_tag():
    assert is_supported_attdef_tag("SYM")
    assert is_supported_attdef_tag("sym")
    assert is_supported_attdef_tag("STATIC_LABEL0")
    assert is_supported_attdef_tag("STATIC_LABEL1")
    assert is_supported_attdef_tag("LABEL0")
    assert is_supported_attdef_tag("LABEL12")
    assert is_supported_attdef_tag("PAGE_NAME")
    assert is_supported_attdef_tag("page_desc")
    assert not is_supported_attdef_tag("SRC")
    assert not is_supported_attdef_tag("LABEL")
    assert not is_supported_attdef_tag("STATIC_LABEL")


def test_list_editable_text_attdef_tags_returns_label_and_static_label_tags():
    doc = new_document()
    blk = doc.blocks.new("ALARM_OPTIONAL")
    blk.add_attdef(tag="STATIC_LABEL1", text="S1", insert=(0.0, 2.0), height=0.25)
    blk.add_attdef(tag="LABEL2", text="L2", insert=(0.0, 1.0), height=0.25)
    blk.add_attdef(tag="STATIC_LABEL0", text="S0", insert=(0.0, 3.0), height=0.25)
    blk.add_attdef(tag="LABEL0", text="L0", insert=(0.0, 0.0), height=0.25)

    assert list_editable_text_attdef_tags(doc, "ALARM_OPTIONAL") == [
        "STATIC_LABEL0",
        "STATIC_LABEL1",
        "LABEL0",
        "LABEL2",
    ]


def test_symbol_editor_attdef_tag_choices_unused_in_block_excludes_existing() -> None:
    doc = new_document()
    blk = doc.blocks.new("X")
    blk.add_attdef(tag="SYM", text="", insert=(0.0, 0.0), height=2.5, dxfattribs={"layer": LAYER_TEXT})
    free = symbol_editor_attdef_tag_choices_unused_in_block(blk)
    assert "SYM" not in free
    assert "LABEL0" in free


def test_symbol_editor_page_link_extra_tags_when_editing_page_blocks() -> None:
    ch = symbol_editor_attdef_tag_choices_for_block(BLOCK_PAGE_FROM)
    assert "PAGE_NAME" in ch
    assert "PAGE_DESC" in ch
    assert ch[0] == "SYM"
    assert ch[1] == "PAGE_NAME"
    assert ch[2] == "PAGE_DESC"
    doc = new_document()
    blk = doc.blocks.new("P")
    free = symbol_editor_attdef_tag_choices_unused_in_block(blk, block_name=BLOCK_PAGE_TO)
    assert "PAGE_NAME" in free
    assert "PAGE_DESC" in free
