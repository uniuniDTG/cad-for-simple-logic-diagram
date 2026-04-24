"""Duplicate paper layout: new UIDs and remapped WIRE endpoints."""

from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.core.model.xdata import get_type, get_uid, read_ld_app_dict


def test_duplicate_page_remaps_wire_symbol_uids() -> None:
    d = LogicDiagram.new()
    layout = d.current_layout_name
    with d.begin("a"):
        u0 = d.place_symbol("NOT", (20.0, 40.0), "n0")
        u1 = d.place_symbol("NOT", (60.0, 40.0), "n1")
    d.rebuild_index()
    with d.begin("w"):
        d.connect_ports(u0, "OUT0_LOGIC", u1, "IN0_LOGIC")
    d.rebuild_index()

    blk = d.doc.blocks.get(d.doc.layouts.get(layout).block_record_name)
    w0 = None
    for e in blk:
        if e.dxftype() == "LWPOLYLINE" and get_type(e) == "WIRE":
            w0 = read_ld_app_dict(e)
            break
    assert w0 is not None
    assert w0.get("src") == u0
    assert w0.get("dst") == u1

    dest = "P_dup_test"
    while dest in d.doc.layouts:
        dest = dest + "x"

    with d.begin("dup"):
        d.duplicate_page(layout, dest)

    d.set_current_page(dest)
    d.rebuild_index()
    blk2 = d.doc.blocks.get(d.doc.layouts.get(dest).block_record_name)
    insert_uids = {get_uid(e) for e in blk2 if e.dxftype() == "INSERT" and get_uid(e)}
    wires = [
        read_ld_app_dict(e)
        for e in blk2
        if e.dxftype() == "LWPOLYLINE" and get_type(e) == "WIRE"
    ]
    assert len(wires) == 1
    w1 = wires[0]
    ns, nd = w1.get("src"), w1.get("dst")
    assert ns and nd
    assert ns not in (u0, u1)
    assert nd not in (u0, u1)
    assert ns in insert_uids
    assert nd in insert_uids
    assert w1.get("src_port") == w0.get("src_port")
    assert w1.get("dst_port") == w0.get("dst_port")


