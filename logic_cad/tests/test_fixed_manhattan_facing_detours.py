"""Fixed Manhattan: port facing wraparound + expanded detour candidates (plan facing_detours)."""

from __future__ import annotations

from dataclasses import replace

from logic_cad.core.model.constants import GRID_PITCH
from logic_cad.core.routing.constrained_router import route_manhattan_ovg_layers
from logic_cad.core.routing.manhattan import collect_fixed_manhattan_polylines
from logic_cad.core.routing.profile import DEFAULT_ROUTING_PROFILE

from logic_cad.tests.support.routing_geometry import snapped_segment_default_diagonal


def test_collect_wraparound_adds_candidates_when_backward():
    pitch = 10.0
    base = collect_fixed_manhattan_polylines(
        0.0, 0.0, -80.0, 0.0, pitch, [], [], None, None
    )
    wrapped = collect_fixed_manhattan_polylines(
        0.0, 0.0, -80.0, 0.0, pitch, [], [], (1, 0), (-1, 0)
    )
    assert len(wrapped) > len(base)
    assert any(len(p) >= 4 for p in wrapped)


def test_collect_detour_includes_dst_y_offset_strip():
    pitch = 10.0
    x0, y0 = 0.0, 0.0
    x1, y1 = 50.0, 50.0
    obs = [(1.0, 1.0, 2.0, 2.0)]
    c = collect_fixed_manhattan_polylines(
        x0, y0, x1, y1, pitch, obs, [], None, None
    )
    ym_d = y1 + pitch
    assert any(
        len(p) >= 4 and p[1] == (x0, ym_d) and p[2] == (x1, ym_d) for p in c
    )


def test_collect_detour_includes_five_point_shapes():
    pitch = 10.0
    obs = [(1.0, 1.0, 2.0, 2.0)]
    c = collect_fixed_manhattan_polylines(
        0.0, 0.0, 50.0, 50.0, pitch, obs, [], None, None
    )
    assert any(len(p) == 5 for p in c)


def test_route_manhattan_ovg_layers_accepts_facing_kwargs():
    p0, p1 = snapped_segment_default_diagonal(GRID_PITCH)
    path = route_manhattan_ovg_layers(
        p0,
        p1,
        [],
        pitch=GRID_PITCH,
        src_facing=(1, 0),
        dst_facing=(0, 1),
        skip_first_leg_hard_obstacle_check=True,
    )
    assert len(path) >= 2
    assert path[0] == p0
    assert path[-1] == p1


def test_fixed_only_with_facing_still_routes_open_map():
    prof = replace(DEFAULT_ROUTING_PROFILE, use_ovg_multi=False)
    p0, p1 = snapped_segment_default_diagonal(GRID_PITCH)
    path = route_manhattan_ovg_layers(
        p0,
        p1,
        [],
        pitch=GRID_PITCH,
        profile=prof,
        src_facing=(1, 0),
        dst_facing=(0, 1),
        skip_first_leg_hard_obstacle_check=True,
    )
    assert len(path) >= 2
