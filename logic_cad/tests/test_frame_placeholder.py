"""Paper frame block (LD_PAPER_FRAME) refresh and placeholder expansion."""

from __future__ import annotations

import ezdxf

from logic_cad.core.model.constants import (
    BLOCK_PAPER_FRAME,
    ENTITY_TYPE_PAPER_FRAME,
    LAYER_FRAME,
    LAYER_FRAME_TEXT,
    LAYER_TEXT,
)
from logic_cad.core.dxf.dxf_repository import ensure_regapp, ensure_standard_layers
from logic_cad.core.pages.page_layout_meta import merge_layout_page_xdata
from logic_cad.core.services.toc_frame_service import expand_frame_placeholders, refresh_frame_for_layout
from logic_cad.core.model.xdata import build_ld_app_tags, new_uid, set_entity_xdata


def test_expand_frame_placeholders() -> None:
    s = expand_frame_placeholders(
        "{{DWG_NO}} / {{PAGE_NAME}}",
        {"DWG_NO": "A-001", "PAGE_NAME": "P1"},
    )
    assert s == "A-001 / P1"
    assert expand_frame_placeholders(
        "{{PAGE_NUM}} / {{PAGE_TOTAL}}",
        {"PAGE_NUM": "2", "PAGE_TOTAL": "15"},
    ) == "2 / 15"
    assert expand_frame_placeholders("{{MISS}}", {}) == ""


def _add_paper_frame_insert(doc: ezdxf.Drawing, *, with_custom: bool = False) -> None:
    ensure_standard_layers(doc)
    ensure_regapp(doc)
    layout = doc.layouts.get("Layout1")
    blk = doc.blocks.get(layout.block_record_name)
    pb = doc.blocks.new(BLOCK_PAPER_FRAME)
    pb.add_lwpolyline([(0, 0), (50, 0), (50, 40), (0, 40)], close=True, dxfattribs={"layer": LAYER_FRAME})
    pb.add_attdef(
        tag="DWG_NO",
        text="{{DWG_NO}}",
        insert=(5.0, 10.0),
        height=2.5,
        dxfattribs={"layer": LAYER_FRAME_TEXT},
    )
    pb.add_attdef(
        tag="PAGE_NAME",
        text="{{PAGE_NUM}}/{{PAGE_TOTAL}} {{PAGE_NAME}}",
        insert=(5.0, 8.0),
        height=2.5,
        dxfattribs={"layer": LAYER_FRAME_TEXT},
    )
    if with_custom:
        pb.add_attdef(
            tag="CUSTOM",
            text="Static",
            insert=(5.0, 6.0),
            height=2.5,
            dxfattribs={"layer": LAYER_FRAME_TEXT},
        )
    auto: dict[str, str] = {
        "DWG_NO": "{{DWG_NO}}",
        "PAGE_NAME": "{{PAGE_NUM}}/{{PAGE_TOTAL}} {{PAGE_NAME}}",
    }
    if with_custom:
        auto["CUSTOM"] = "Static"
    ins = blk.add_blockref(BLOCK_PAPER_FRAME, (0.0, 0.0, 0.0))
    ins.add_auto_attribs(auto)
    set_entity_xdata(ins, build_ld_app_tags("1", new_uid(), ENTITY_TYPE_PAPER_FRAME))


def test_refresh_updates_paper_frame_attribs() -> None:
    doc = ezdxf.new("R2010", setup=False, units=4)
    _add_paper_frame_insert(doc, with_custom=False)

    doc.header["$PROJECTNAME"] = "DWG-99"
    merge_layout_page_xdata(doc, "Layout1", page_desc="Hello", page_rev="1.0")
    refresh_frame_for_layout(doc, "Layout1")

    layout = doc.layouts.get("Layout1")
    blk = doc.blocks.get(layout.block_record_name)
    ins = next(e for e in blk if e.dxftype() == "INSERT" and str(e.dxf.name) == BLOCK_PAPER_FRAME)
    by_tag = {str(a.dxf.tag): str(a.dxf.text or "") for a in ins.attribs}
    assert by_tag["DWG_NO"] == "DWG-99"
    assert by_tag["PAGE_NAME"] == "1/1 Layout1"


def test_refresh_page_num_respects_user_header() -> None:
    doc = ezdxf.new("R2010", setup=False, units=4)
    _add_paper_frame_insert(doc, with_custom=False)
    doc.header["$PROJECTNAME"] = "X"
    doc.header["$USERI1"] = 4
    doc.header["$USERI2"] = 9
    merge_layout_page_xdata(doc, "Layout1", page_desc="", page_rev="")
    refresh_frame_for_layout(doc, "Layout1")
    layout = doc.layouts.get("Layout1")
    blk = doc.blocks.get(layout.block_record_name)
    ins = next(e for e in blk if e.dxftype() == "INSERT" and str(e.dxf.name) == BLOCK_PAPER_FRAME)
    by_tag = {str(a.dxf.tag): str(a.dxf.text or "") for a in ins.attribs}
    assert by_tag["PAGE_NAME"] == "4/9 Layout1"


def test_refresh_leaves_unknown_attrib_unchanged() -> None:
    doc = ezdxf.new("R2010", setup=False, units=4)
    _add_paper_frame_insert(doc, with_custom=True)
    refresh_frame_for_layout(doc, "Layout1")
    layout = doc.layouts.get("Layout1")
    blk = doc.blocks.get(layout.block_record_name)
    ins = next(e for e in blk if e.dxftype() == "INSERT" and str(e.dxf.name) == BLOCK_PAPER_FRAME)
    by_tag = {str(a.dxf.tag): str(a.dxf.text or "") for a in ins.attribs}
    assert by_tag["CUSTOM"] == "Static"


def test_refresh_without_paper_frame_insert_is_noop() -> None:
    doc = ezdxf.new("R2010", setup=False, units=4)
    if LAYER_TEXT not in doc.layers:
        doc.layers.add(LAYER_TEXT)
    blk = doc.blocks.get(doc.layouts.get("Layout1").block_record_name)
    mt = blk.add_mtext(
        "KEEP",
        dxfattribs={
            "layer": LAYER_TEXT,
            "char_height": 2.0,
            "insert": (1.0, 2.0, 0.0),
        },
    )
    refresh_frame_for_layout(doc, "Layout1")
    assert str(mt.dxf.text) == "KEEP"
