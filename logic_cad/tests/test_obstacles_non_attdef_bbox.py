"""Non-gate symbol routing hull uses block geometry without ATTDEF (matches UI geo pass)."""

import ezdxf

from logic_cad.core.obstacles import _non_attdef_insert_world_bbox


def test_non_attdef_insert_world_bbox_excludes_attdef_from_block_extents():
    doc = ezdxf.new("R2010")
    blk = doc.blocks.new("T_BLOCK")
    blk.add_line((0.0, 0.0), (4.0, 0.0), dxfattribs={"layer": "LD_SYMBOL"})
    blk.add_attdef(
        "LABEL",
        (100.0, 100.0),
        "FAR",
        dxfattribs={"layer": "LD_TEXT", "height": 0.25},
    )
    layout = doc.layouts.get("Model")
    lb = doc.blocks.get(layout.block_record_name)
    ins = lb.add_blockref("T_BLOCK", (7.0, 8.0))
    nb = _non_attdef_insert_world_bbox(doc, ins)
    assert nb is not None
    x0, y0, x1, y1 = nb
    assert abs(x0 - 7.0) < 1e-6 and abs(y0 - 8.0) < 1e-6
    assert abs(x1 - 11.0) < 1e-6 and abs(y1 - 8.0) < 1e-6
