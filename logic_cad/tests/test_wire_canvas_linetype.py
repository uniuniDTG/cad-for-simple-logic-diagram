"""Tests for WIRE stroke linetype on the main diagram canvas."""

from __future__ import annotations

from PySide6.QtCore import Qt

from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.core.model.constants import LAYER_WIRE_VALUE
from logic_cad.core.model.xdata import build_ld_app_tags, new_uid, set_entity_xdata
from logic_cad.core.paper_layout_access import paper_layout_block
from logic_cad.tests.support.qt_offscreen import ensure_qapplication_offscreen
from logic_cad.ui.items.wire_item import WireItem
from logic_cad.ui.scene import DiagramScene


def test_wire_on_value_layer_bylayer_renders_dashed_pen() -> None:
    """WIRE with implicit ByLayer on ``LD_WIRE_VALUE`` uses the layer dash style on canvas.

    PDF/DXF resolve ByLayer from the layer table; ``DiagramScene.rebuild`` must do the same so
    VALUE routing wires are not drawn solid when entity linetype is unset.
    """
    ensure_qapplication_offscreen()
    d = LogicDiagram.new()
    layout_name = d.current_layout_name
    blk = paper_layout_block(d.doc, layout_name)
    assert blk is not None
    uid = new_uid()
    lw = blk.add_lwpolyline([(0.0, 0.0), (30.0, 0.0)], dxfattribs={"layer": LAYER_WIRE_VALUE})
    set_entity_xdata(lw, build_ld_app_tags("1", uid, "WIRE", {"unit": "VALUE"}))

    scene = DiagramScene(d)
    scene.rebuild()
    wires = [it for it in scene.items() if isinstance(it, WireItem)]
    assert len(wires) == 1
    pen = wires[0].pen()
    assert pen.style() in (Qt.PenStyle.DashLine, Qt.PenStyle.CustomDashLine)
    assert len(pen.dashPattern()) > 0
