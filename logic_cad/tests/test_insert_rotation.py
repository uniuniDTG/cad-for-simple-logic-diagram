"""INSERT rotation: ezdxf uses degrees on dxf.rotation; app must match matrix44()."""

from ezdxf.math import Vec3

import ezdxf

from logic_cad.core.logic_diagram import LogicDiagram


def test_rotate_insert_relative_deg_adds_degrees() -> None:
    d = LogicDiagram.new()
    with d.begin("p"):
        uid = d.place_symbol("NOT", (10.0, 20.0))
    ins = d.index.inserts_by_uid[uid]
    assert abs(float(ins.dxf.rotation)) < 1e-9
    d.symbols.rotate_insert_relative_deg(d.current_layout_name, uid, 90.0)
    assert abs(float(ins.dxf.rotation) - 90.0) < 1e-6
    d.symbols.rotate_insert_relative_deg(d.current_layout_name, uid, -30.0)
    assert abs(float(ins.dxf.rotation) - 60.0) < 1e-6


def test_insert_dxf_rotation_degrees_matches_matrix44() -> None:
    doc = ezdxf.new()
    doc.blocks.new("R").add_line((0, 0), (1, 0))
    layout = doc.layouts.get("Layout1")
    msp = doc.blocks.get(layout.block_record_name)
    ins = msp.add_blockref("R", (5.0, 5.0))
    ins.dxf.rotation = 90.0
    m = ins.matrix44()
    dx = m.transform_direction(Vec3(1.0, 0.0, 0.0))
    assert abs(dx.x) < 1e-5
    assert abs(dx.y - 1.0) < 1e-5
