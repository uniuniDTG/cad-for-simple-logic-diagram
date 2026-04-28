"""COM wire marker regeneration tests."""

from __future__ import annotations

from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.core.model.constants import (
    LAYER_WIRE_COM_SEGMENT,
    LAYER_WIRE_COM_MARKER,
    LINETYPE_COM,
    LINETYPE_LOGIC,
    WIRE_COM_DASH_MM,
    WIRE_COM_MARKER_RADIUS_MM,
)

from logic_cad.tests.support.diagram_entities import wire_polyline_points


def _marker_circles_in_current_layout(diagram: LogicDiagram) -> list[object]:
    layout = diagram.doc.layouts.get(diagram.current_layout_name)
    blk = diagram.doc.blocks.get(layout.block_record_name)
    return [
        e
        for e in blk
        if e.dxftype() == "CIRCLE" and str(getattr(e.dxf, "layer", "")).upper() == LAYER_WIRE_COM_MARKER.upper()
    ]


def _segment_lines_in_current_layout(diagram: LogicDiagram) -> list[object]:
    layout = diagram.doc.layouts.get(diagram.current_layout_name)
    blk = diagram.doc.blocks.get(layout.block_record_name)
    return [
        e
        for e in blk
        if e.dxftype() == "LINE" and str(getattr(e.dxf, "layer", "")).upper() == LAYER_WIRE_COM_SEGMENT.upper()
    ]


def test_com_linetype_generates_segment_restarted_bead_markers() -> None:
    d = LogicDiagram.new()
    with d.begin("place"):
        src = d.place_symbol("NOT", (20.0, 40.0), "SRC")
        dst = d.place_symbol("NOT", (60.0, 40.0), "DST")
    d.rebuild_index()
    with d.begin("wire"):
        wuid = d.connect_ports_manual(src, "OUT0_LOGIC", dst, "IN0_LOGIC", [])
        d.set_wire_linetype(wuid, LINETYPE_COM)

    pts = wire_polyline_points(d.doc, wuid)
    assert len(pts) == 2
    p0, p1 = pts[0], pts[1]
    assert abs(p0[1] - p1[1]) < 1e-6
    seg_len = abs(p1[0] - p0[0])
    assert seg_len > (WIRE_COM_DASH_MM * 2.0 + WIRE_COM_MARKER_RADIUS_MM * 2.0)

    circles = _marker_circles_in_current_layout(d)
    lines = _segment_lines_in_current_layout(d)
    assert circles, "COM wire should place bead markers"
    assert lines, "COM wire should place helper line segments"
    centers = sorted(float(c.dxf.center.x) for c in circles)

    # Beads restart per segment and never occupy the terminal side.
    max_center = centers[-1]
    tail_len = float(p1[0]) - (max_center + WIRE_COM_MARKER_RADIUS_MM)
    assert tail_len >= -1e-6
    assert tail_len <= WIRE_COM_DASH_MM + 1e-6

    if len(centers) >= 2:
        period = WIRE_COM_DASH_MM + WIRE_COM_MARKER_RADIUS_MM * 2.0
        assert abs((centers[1] - centers[0]) - period) < 1e-6


def test_marker_centers_place_one_circle_for_exact_11mm_segment() -> None:
    d = LogicDiagram.new()
    centers = d.wires._com_marker_centers_for_polyline([(0.0, 0.0), (11.0, 0.0)])
    assert len(centers) == 1


def test_com_visuals_restart_from_5mm_at_each_corner() -> None:
    d = LogicDiagram.new()
    with d.begin("place"):
        src = d.place_symbol("NOT", (20.0, 40.0), "SRC")
        dst = d.place_symbol("NOT", (60.0, 20.0), "DST")
    d.rebuild_index()
    with d.begin("wire"):
        wuid = d.connect_ports_manual(src, "OUT0_LOGIC", dst, "IN0_LOGIC", [(40.0, 40.0), (40.0, 20.0)])
        d.set_wire_linetype(wuid, LINETYPE_COM)

    lines = _segment_lines_in_current_layout(d)
    assert lines
    starts = {(round(float(e.dxf.start.x), 3), round(float(e.dxf.start.y), 3)) for e in lines}
    path = wire_polyline_points(d.doc, wuid)
    seg_starts = {(round(float(x), 3), round(float(y), 3)) for x, y in path[:-1]}
    # First helper line must start from each segment corner (phase reset).
    assert seg_starts.issubset(starts)


def test_switching_away_from_com_linetype_clears_markers() -> None:
    d = LogicDiagram.new()
    with d.begin("place"):
        src = d.place_symbol("NOT", (20.0, 40.0), "SRC")
        dst = d.place_symbol("NOT", (60.0, 40.0), "DST")
    d.rebuild_index()
    with d.begin("wire"):
        wuid = d.connect_ports_manual(src, "OUT0_LOGIC", dst, "IN0_LOGIC", [])
        d.set_wire_linetype(wuid, LINETYPE_COM)
    assert _marker_circles_in_current_layout(d)

    with d.begin("wire-style"):
        d.set_wire_linetype(wuid, LINETYPE_LOGIC)

    assert _marker_circles_in_current_layout(d) == []
