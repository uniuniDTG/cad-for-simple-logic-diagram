"""ATTDEF tag helpers."""

from logic_cad.core.attrib_tags import is_supported_attdef_tag, list_editable_text_attdef_tags
from logic_cad.core.dxf.dxf_repository import new_document


def test_is_supported_attdef_tag():
    assert is_supported_attdef_tag("SYM")
    assert is_supported_attdef_tag("sym")
    assert is_supported_attdef_tag("STATIC_LABEL0")
    assert is_supported_attdef_tag("STATIC_LABEL1")
    assert is_supported_attdef_tag("LABEL0")
    assert is_supported_attdef_tag("LABEL12")
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
