"""apply_frame_template_from_path: replace frame without duplicate inserts."""

from __future__ import annotations

from pathlib import Path

import ezdxf

from logic_cad.core.dxf.dxf_repository import ensure_regapp, ensure_standard_layers, new_document
from logic_cad.core.model.constants import (
    BLOCK_PAPER_FRAME,
    ENTITY_TYPE_PAPER_FRAME,
    LAYER_FRAME,
    LAYER_FRAME_TEXT,
)
from logic_cad.core.pages.page_order import list_paper_layout_names_sorted
from logic_cad.core.services.layout_service import apply_frame_template_from_path


def _write_minimal_frame_template(path: Path, dwg_attdef_text: str) -> None:
    """Minimal template: frame block definitions only (no modelspace entities)."""
    doc = ezdxf.new("R2010", setup=["styles"], units=4)
    ensure_standard_layers(doc)
    ensure_regapp(doc)
    pb = doc.blocks.new(BLOCK_PAPER_FRAME)
    pb.add_lwpolyline(
        [(0, 0), (200, 0), (200, 120), (0, 120)],
        close=True,
        dxfattribs={"layer": LAYER_FRAME},
    )
    pb.add_attdef(
        tag="DWG_NO",
        text=dwg_attdef_text,
        insert=(14.0, 22.0),
        height=2.5,
        dxfattribs={"layer": LAYER_FRAME_TEXT},
    )
    doc.saveas(str(path))


def _count_paper_frame_inserts(doc: ezdxf.Drawing) -> int:
    from logic_cad.core.model.xdata import get_type

    n = 0
    for layout in doc.layouts:
        if layout.is_modelspace:
            continue
        blk = doc.blocks.get(layout.block_record_name)
        for e in blk:
            if e.dxftype() == "INSERT" and get_type(e) == ENTITY_TYPE_PAPER_FRAME:
                n += 1
    return n


def _dwg_no_attdef_text(doc: ezdxf.Drawing) -> str:
    blk = doc.blocks.get(BLOCK_PAPER_FRAME)
    assert blk is not None
    for e in blk:
        if e.dxftype() == "ATTDEF" and str(e.dxf.tag) == "DWG_NO":
            return str(e.dxf.text)
    raise AssertionError("DWG_NO ATTDEF missing")


def test_apply_frame_template_replaces_block_and_avoids_duplicate_inserts(tmp_path: Path) -> None:
    t1 = tmp_path / "frame_v1.dxf"
    t2 = tmp_path / "frame_v2.dxf"
    _write_minimal_frame_template(t1, "LABEL_A")
    _write_minimal_frame_template(t2, "LABEL_B")

    doc = new_document()
    assert list_paper_layout_names_sorted(doc)

    apply_frame_template_from_path(doc, t1)
    assert _dwg_no_attdef_text(doc) == "LABEL_A"
    n_after_first = _count_paper_frame_inserts(doc)
    assert n_after_first == len(list_paper_layout_names_sorted(doc))

    apply_frame_template_from_path(doc, t2)
    assert _dwg_no_attdef_text(doc) == "LABEL_B"
    n_after_second = _count_paper_frame_inserts(doc)
    assert n_after_second == len(list_paper_layout_names_sorted(doc))
