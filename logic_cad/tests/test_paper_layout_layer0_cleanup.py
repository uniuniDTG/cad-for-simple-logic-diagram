"""configure_paper_layout_a4_landscape removes default layer-0 printable-area decoy rects."""

from __future__ import annotations

import ezdxf

from logic_cad.core.model.constants import (
    A4_LANDSCAPE_HEIGHT_MM,
    A4_LANDSCAPE_PRINTABLE_80_H_MM,
    A4_LANDSCAPE_PRINTABLE_80_W_MM,
    A4_LANDSCAPE_WIDTH_MM,
)
from logic_cad.core.services.layout_service import configure_paper_layout_a4_landscape


def test_configure_removes_80_percent_layer0_rectangle() -> None:
    doc = ezdxf.new("R2010", setup=False)
    layout = doc.layouts.get("Layout1")
    blk = doc.blocks.get(layout.block_record_name)
    m = (A4_LANDSCAPE_WIDTH_MM - A4_LANDSCAPE_PRINTABLE_80_W_MM) / 2
    my = (A4_LANDSCAPE_HEIGHT_MM - A4_LANDSCAPE_PRINTABLE_80_H_MM) / 2
    w, h = A4_LANDSCAPE_PRINTABLE_80_W_MM, A4_LANDSCAPE_PRINTABLE_80_H_MM
    blk.add_lwpolyline(
        [(m, my), (m + w, my), (m + w, my + h), (m, my + h)],
        close=True,
        dxfattribs={"layer": "0"},
    )
    assert sum(1 for e in blk if str(e.dxf.layer) == "0" and e.dxftype() == "LWPOLYLINE") == 1

    configure_paper_layout_a4_landscape(doc, "Layout1")

    assert sum(1 for e in blk if str(e.dxf.layer) == "0" and e.dxftype() == "LWPOLYLINE") == 0
