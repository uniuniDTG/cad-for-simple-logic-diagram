"""Visibility tests for COM wire arrowheads in the scene."""

from __future__ import annotations

from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.core.model.constants import LINETYPE_COM
from logic_cad.tests.support.qt_offscreen import ensure_qapplication_offscreen
from logic_cad.ui.items.wire_arrow_item import WireArrowItem
from logic_cad.ui.scene import DiagramScene


def test_com_wire_arrow_remains_visible_in_scene() -> None:
    """COM wire arrowhead should not be forced transparent in DiagramScene."""
    ensure_qapplication_offscreen()
    d = LogicDiagram.new()
    with d.begin("place"):
        src = d.place_symbol("NOT", (20.0, 40.0), "SRC")
        dst = d.place_symbol("NOT", (60.0, 40.0), "DST")
    d.rebuild_index()
    with d.begin("wire"):
        wuid = d.connect_ports_manual(src, "OUT0_LOGIC", dst, "IN0_LOGIC", [])
        d.set_wire_linetype(wuid, LINETYPE_COM)
        d.set_wire_show_in_arrow(wuid, True)

    scene = DiagramScene(d)
    arrows = [item for item in scene.items() if isinstance(item, WireArrowItem)]
    assert len(arrows) == 1
    assert arrows[0].pen().color().alpha() > 0
