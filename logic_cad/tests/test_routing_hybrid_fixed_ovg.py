"""Fixed-candidate phase before OVG; shared segment_policy rules."""

from unittest.mock import patch

import pytest

from logic_cad.core.model.constants import GRID_PITCH
from logic_cad.core.routing.constrained_router import route_manhattan_ovg_layers
from logic_cad.core.routing.obstacles import obstacle_rects_inflated
from logic_cad.core.routing.occupancy import Cardinal
from logic_cad.core.routing.ovg import _build_ovg_edges, _build_ovg_nodes
from logic_cad.core.routing.polyline import snap_to_grid
from logic_cad.core.routing.segment_policy import (
    first_axis_leg_clear,
    segment_blocks_hard_and_collinear,
)

from logic_cad.tests.support.routing_geometry import snapped_segment_default_diagonal


def test_segment_blocks_blocks_same_cases_as_ovg_would_skip_edge():
    pitch = GRID_PITCH
    a = snap_to_grid(0.0, 0.0, pitch)
    b = snap_to_grid(50.0, 0.0, pitch)
    obs = [(20.0, -5.0, 30.0, 5.0)]
    hard = obstacle_rects_inflated(obs)
    assert segment_blocks_hard_and_collinear(a, b, hard, None)

    a2 = snap_to_grid(0.0, 0.0, pitch)
    b2 = snap_to_grid(0.0, 50.0, pitch)
    assert not segment_blocks_hard_and_collinear(a2, b2, hard, None)


def test_first_axis_leg_clear_matches_skip_flag():
    pitch = GRID_PITCH
    src = snap_to_grid(0.0, 0.0, pitch)
    fh = snap_to_grid(15.0, 0.0, pitch)
    # Entirely inside the port cutout (step_free ≈ ROUTE_ESCAPE_MM + pitch): skipped when flag True.
    near_port = [(0.2, -0.5, 0.8, 0.5)]
    hard_near = obstacle_rects_inflated(near_port)
    assert first_axis_leg_clear(
        src,
        fh,
        hard_near,
        None,
        pitch,
        max(1.0, pitch),
        skip_first_leg_hard_obstacle_check=True,
    )
    assert not first_axis_leg_clear(
        src,
        fh,
        hard_near,
        None,
        pitch,
        max(1.0, pitch),
        skip_first_leg_hard_obstacle_check=False,
    )
    # Tail after cutout still checked: obstacle on the remainder blocks even with skip True.
    hard_tail = obstacle_rects_inflated([(5.0, -2.0, 8.0, 2.0)])
    assert not first_axis_leg_clear(
        src,
        fh,
        hard_tail,
        None,
        pitch,
        max(1.0, pitch),
        skip_first_leg_hard_obstacle_check=True,
    )


def test_fixed_phase_does_not_call_ovg_when_simple_l_exists():
    pitch = GRID_PITCH
    p0, p1 = snapped_segment_default_diagonal(pitch)

    def ovg_shOULD_not_run(*_a, **_k):
        raise AssertionError("OVG must not run when fixed Manhattan is valid")

    with patch(
        "logic_cad.core.routing.constrained_router.route_ovg_multi_start",
        side_effect=ovg_shOULD_not_run,
    ):
        path = route_manhattan_ovg_layers(
            p0,
            p1,
            [],
            pitch=pitch,
            skip_first_leg_hard_obstacle_check=True,
        )
    assert len(path) >= 2
    assert path[0] == p0
    assert path[-1] == p1


def test_ovg_runs_when_fixed_phase_returns_nothing():
    pitch = GRID_PITCH
    p0, p1 = snapped_segment_default_diagonal(pitch)
    ovg_calls: list[int] = []

    def fake_fixed(*_a, **_k):
        return None

    real_multi = __import__(
        "logic_cad.core.routing.constrained_router", fromlist=["route_ovg_multi_start"]
    ).route_ovg_multi_start

    def counting_ovg(*a, **k):
        ovg_calls.append(1)
        return real_multi(*a, **k)

    with patch(
        "logic_cad.core.routing.constrained_router._try_fixed_manhattan_escape_phase",
        fake_fixed,
    ), patch(
        "logic_cad.core.routing.constrained_router.route_ovg_multi_start",
        side_effect=counting_ovg,
    ):
        path = route_manhattan_ovg_layers(
            p0,
            p1,
            [],
            pitch=pitch,
            skip_first_leg_hard_obstacle_check=True,
        )
    assert ovg_calls == [1]
    assert len(path) >= 2


def test_ovg_adjacency_uses_segment_blocks():
    """Regression: every OVG graph edge must pass the same rule as segment_policy."""
    pitch = GRID_PITCH
    src = (0.0, 0.0)
    dst = (100.0, 0.0)
    obs: list[tuple[float, float, float, float]] = []
    nodes = _build_ovg_nodes(src, dst, obs, pitch, None, dense_corridor=False)
    hard: list[tuple[float, float, float, float]] = []
    existing = [((40.0, 0.0), (60.0, 0.0))]
    adj = _build_ovg_edges(nodes, hard, pitch, existing)
    for i, nbs in adj.items():
        for j, _dist in nbs:
            a, b = nodes[i], nodes[j]
            assert not segment_blocks_hard_and_collinear(a, b, hard, existing)


def test_banned_all_cardinals_raises():
    pitch = GRID_PITCH
    p0 = snap_to_grid(0.0, 0.0, pitch)
    p1 = snap_to_grid(50.0, 40.0, pitch)
    banned: set[Cardinal] = {(1, 0), (-1, 0), (0, 1), (0, -1)}
    with pytest.raises(ValueError):
        route_manhattan_ovg_layers(
            p0,
            p1,
            [],
            pitch=pitch,
            banned_src_cardinals=banned,
            skip_first_leg_hard_obstacle_check=True,
        )
