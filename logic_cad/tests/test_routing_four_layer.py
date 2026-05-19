"""Four-layer routing: full hard (symbols+wires) then symbol-only hard fallback."""

import pytest

from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.core.model.constants import GRID_PITCH
from logic_cad.core.obstacles import build_routing_obstacles, build_symbol_only_routing_obstacles
from logic_cad.core.obstacles.from_document import _symbol_boxes
from logic_cad.core.routing import (
    RoutingProfile,
    path_hits_obstacles,
    route_manhattan,
    route_manhattan_with_escape,
)

from logic_cad.tests.support.routing_geometry import ROUTING_TEST_BLOCKING_WALL_MM


def test_route_manhattan_relaxed_empty_succeeds_when_full_hard_blocks_all_layers12():
    """A large hard rectangle blocks layers 1–2; symbol-only relaxed [] yields a direct segment (layer 3)."""
    pitch = GRID_PITCH
    # Bounding box covers typical detour grid around (0,0)–(4,0) at unit pitch.
    wall = ROUTING_TEST_BLOCKING_WALL_MM
    pts = route_manhattan(
        (0.0, 0.0),
        (4.0, 0.0),
        obstacles=[wall],
        pitch=pitch,
        obstacles_relaxed=[],
    )
    assert pts[0] == (0.0, 0.0)
    assert pts[-1] == (4.0, 0.0)
    assert path_hits_obstacles(pts, [wall])


def test_route_manhattan_no_relaxed_raises_when_only_full_used():
    with pytest.raises(ValueError, match="マンハッタン経路が見つかりません"):
        route_manhattan(
            (0.0, 0.0),
            (4.0, 0.0),
            obstacles=[ROUTING_TEST_BLOCKING_WALL_MM],
            pitch=GRID_PITCH,
            obstacles_relaxed=None,
        )


def test_route_manhattan_with_escape_passes_relaxed():
    wall = ROUTING_TEST_BLOCKING_WALL_MM
    pts = route_manhattan_with_escape(
        (0.0, 0.0),
        (4.0, 0.0),
        obstacles=[wall],
        pitch=GRID_PITCH,
        first_escape_src=(1.0, 0.0),
        obstacles_relaxed=[],
    )
    assert pts[0] == (0.0, 0.0)
    assert pts[-1] == (4.0, 0.0)


def test_build_symbol_only_is_subset_when_wires_exist():
    d = LogicDiagram.new()
    with d.begin("p"):
        a = d.place_and_gate(1, (10.0, 10.0))
        b = d.place_and_gate(1, (30.0, 10.0))
    with d.begin("w"):
        d.connect_ports(a, "OUT0_LOGIC", b, "IN0_LOGIC")
    d.rebuild_index()
    layout = d.current_layout_name
    full = build_routing_obstacles(d.doc, d.index, layout, set())
    sym = build_symbol_only_routing_obstacles(d.doc, d.index, layout, set())
    assert len(sym) <= len(full)
    assert len(full) > 0


def test_inpage_ref_symbol_boxes_stay_near_insert_not_wcs_origin() -> None:
    """POINT-only ``INPAGE_FROM`` must not widen routing hull toward WCS (0,0).

    Regression: degenerate port AABB merges with ``extents([INSERT])`` spanning origin and insert.

    Raises:
        AssertionError: Bounding hull is unrealistically pulled left/down or inflated.
    """
    d = LogicDiagram.new()
    ix_from = 100.0
    iy_from = 80.0
    with d.begin("inpage"):
        u_from = d.place_inpage_link((ix_from, iy_from))
        u_to = d.place_inpage_link_peer(u_from, (130.0, 82.0))
    d.rebuild_index()

    boxes_from = _symbol_boxes(d.doc, d.index, u_from)
    boxes_to = _symbol_boxes(d.doc, d.index, u_to)
    assert boxes_from
    assert boxes_to

    for uid in (u_from, u_to):
        ins = d.index.inserts_by_uid.get(uid)
        assert ins is not None
        ix = float(ins.dxf.insert.x)
        iy = float(ins.dxf.insert.y)
        boxes = boxes_from if uid == u_from else boxes_to
        x0 = min(b[0] for b in boxes)
        y0 = min(b[1] for b in boxes)
        x1 = max(b[2] for b in boxes)
        y1 = max(b[3] for b in boxes)

        assert x0 > ix * 0.5, f"{uid} min_x={x0} insert=({ix}, {iy})"
        assert y0 > iy * 0.5, f"{uid} min_y={y0} insert=({ix}, {iy})"

        port_xyz = [
            pw
            for (pu, _pk), pw in d.index.ports.items()
            if pu == uid
        ]
        assert port_xyz
        for px, py in port_xyz:
            assert x0 <= px <= x1, f"{uid} port ({px},{py}) x outside hull"
            assert y0 <= py <= y1, f"{uid} port ({px},{py}) y outside hull"

        width = x1 - x0
        height = y1 - y0
        assert width <= 96.0, f"{uid} width={width}"
        assert height <= 64.0, f"{uid} height={height}"


def test_profile_relax_wire_hard_layers_default_true():
    assert RoutingProfile().relax_wire_hard_layers is True


def test_profile_enable_and_or_crossing_swaps_default_false():
    assert RoutingProfile().enable_and_or_crossing_swaps is False
