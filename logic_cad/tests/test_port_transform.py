"""Port world coordinates under INSERT transform."""

import ezdxf
from ezdxf.math import Vec3

from logic_cad.core.model.index_store import IndexStore


def test_port_world_after_translation():
    doc = ezdxf.new()
    from logic_cad.core.dxf.dxf_repository import ensure_standard_layers
    from logic_cad.core.model.xdata import ensure_regapp

    ensure_standard_layers(doc)
    ensure_regapp(doc)
    blk = doc.blocks.new("T")
    blk.add_point((1, 0), dxfattribs={"layer": "LD_PORT_OUT0_LOGIC"})
    layout = doc.layouts.get("Layout1")
    br = layout.block_record_name
    msp = doc.blocks.get(br)
    ins = msp.add_blockref("T", (10, 20))
    from logic_cad.core.model.xdata import build_ld_app_tags, new_uid, set_entity_xdata

    uid = new_uid()
    set_entity_xdata(ins, build_ld_app_tags("1", uid, "SYMBOL"))

    ix = IndexStore(doc, "Layout1")
    ix.rebuild(doc, "Layout1")
    p = ix.get_port_world(uid, "OUT0_LOGIC")
    assert p is not None
    m = ins.matrix44()
    w = m.transform(Vec3(1.0, 0.0, 0.0))
    assert abs(p[0] - w.x) < 1e-6
    assert abs(p[1] - w.y) < 1e-6
