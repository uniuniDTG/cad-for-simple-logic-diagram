"""Symbol-only obstacle routing when ``min_cost_across_wire_obstacle_passes`` is True (per-WIRE option)."""

from __future__ import annotations

from dataclasses import replace

from logic_cad.core.model.constants import GRID_PITCH, WIRE_XDATA_ALLOW_ORTHOGONAL_CROSS
from logic_cad.core.model.wire_port_helpers import wire_allows_orthogonal_cross
from logic_cad.core.routing.constrained_router import route_manhattan_ovg_layers
from logic_cad.core.routing.profile import DEFAULT_ROUTING_PROFILE
from logic_cad.core.routing.scoring import path_length


def test_allow_orthogonal_routes_with_symbol_only_obstacles_straight_line() -> None:
    """With flag True, only relaxed obstacles run — empty relaxed set yields straight segment."""
    pitch = GRID_PITCH
    p0 = (0.0, 0.0)
    p1 = (20.0, 0.0)
    # Blocks the direct horizontal run (axis-aligned segment on y=0 through x in [8,12]).
    obs_full: list[tuple[float, float, float, float]] = [(8.0, -1.0, 12.0, 1.0)]
    obs_relaxed: list[tuple[float, float, float, float]] = []
    prof = replace(DEFAULT_ROUTING_PROFILE, min_cost_across_wire_obstacle_passes=True)
    path = route_manhattan_ovg_layers(
        p0,
        p1,
        obs_full,
        pitch=pitch,
        profile=prof,
        obstacles_relaxed=obs_relaxed,
        skip_first_leg_hard_obstacle_check=True,
    )
    assert path[0] == p0
    assert path[-1] == p1
    # Relaxed straight line has length 20; any detour around the block is longer.
    assert path_length(path) <= 20.0 + 1e-6


def test_early_return_first_pass_when_min_cost_off() -> None:
    """Legacy: first successful pass wins (may be longer than relaxed would be)."""
    pitch = GRID_PITCH
    p0 = (0.0, 0.0)
    p1 = (20.0, 0.0)
    obs_full = [(8.0, -1.0, 12.0, 1.0)]
    obs_relaxed: list[tuple[float, float, float, float]] = []
    prof = replace(DEFAULT_ROUTING_PROFILE, min_cost_across_wire_obstacle_passes=False)
    path = route_manhattan_ovg_layers(
        p0,
        p1,
        obs_full,
        pitch=pitch,
        profile=prof,
        obstacles_relaxed=obs_relaxed,
        skip_first_leg_hard_obstacle_check=True,
    )
    assert path[0] == p0
    assert path[-1] == p1
    assert path_length(path) > 20.0 + 1e-6


def test_wire_allows_orthogonal_cross_default_false() -> None:
    assert not wire_allows_orthogonal_cross({})
    assert not wire_allows_orthogonal_cross({"allow_orthogonal_cross": "0"})


def test_wire_allows_orthogonal_cross_truthy() -> None:
    assert wire_allows_orthogonal_cross({WIRE_XDATA_ALLOW_ORTHOGONAL_CROSS: "1"})
    assert wire_allows_orthogonal_cross({WIRE_XDATA_ALLOW_ORTHOGONAL_CROSS: "true"})
