"""LOGIC_CAD_ROUTING_* env and RoutingProfile phase flags for route_manhattan_ovg_layers."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import patch

import pytest

from logic_cad.core.model.constants import GRID_PITCH
from logic_cad.core.routing.constrained_router import route_manhattan_ovg_layers
from logic_cad.core.routing.polyline import snap_to_grid
from logic_cad.core.routing.profile import (
    DEFAULT_ROUTING_PROFILE,
    ENV_ROUTING_FIXED,
    ENV_ROUTING_OVG,
    RoutingProfile,
    apply_routing_env_overrides,
)

from logic_cad.tests.support.routing_geometry import snapped_segment_default_diagonal


def test_apply_routing_env_overrides_no_env_unchanged():
    p = RoutingProfile(max_search_states=12345)
    assert apply_routing_env_overrides(p) is p


def test_apply_routing_env_overrides_fixed_off(monkeypatch: pytest.MonkeyPatch):
    p = DEFAULT_ROUTING_PROFILE
    monkeypatch.setenv(ENV_ROUTING_FIXED, "0")
    out = apply_routing_env_overrides(p)
    assert out.use_fixed_manhattan is False
    assert out.use_ovg_multi is True
    assert out.max_search_states == p.max_search_states


def test_apply_routing_env_overrides_ovg_off(monkeypatch: pytest.MonkeyPatch):
    p = DEFAULT_ROUTING_PROFILE
    monkeypatch.setenv(ENV_ROUTING_OVG, "0")
    out = apply_routing_env_overrides(p)
    assert out.use_fixed_manhattan is True
    assert out.use_ovg_multi is False


def test_apply_routing_env_overrides_preserves_other_fields(monkeypatch: pytest.MonkeyPatch):
    p = replace(DEFAULT_ROUTING_PROFILE, max_search_states=999, gate_cleanup_pass=False)
    monkeypatch.setenv(ENV_ROUTING_FIXED, "false")
    monkeypatch.setenv(ENV_ROUTING_OVG, "no")
    out = apply_routing_env_overrides(p)
    assert out.max_search_states == 999
    assert out.gate_cleanup_pass is False
    assert out.use_fixed_manhattan is False
    assert out.use_ovg_multi is False


def test_route_manhattan_ovg_layers_both_phases_disabled_raises():
    bad = replace(DEFAULT_ROUTING_PROFILE, use_fixed_manhattan=False, use_ovg_multi=False)
    p0 = snap_to_grid(0.0, 0.0, GRID_PITCH)
    p1 = snap_to_grid(10.0, 10.0, GRID_PITCH)
    with pytest.raises(ValueError, match="両方が無効"):
        route_manhattan_ovg_layers(p0, p1, [], profile=bad, skip_first_leg_hard_obstacle_check=True)


def test_route_manhattan_ovg_layers_ovg_only_profile_runs_ovg():
    pitch = GRID_PITCH
    p0, p1 = snapped_segment_default_diagonal(pitch)
    prof = replace(DEFAULT_ROUTING_PROFILE, use_fixed_manhattan=False, use_ovg_multi=True)
    path = route_manhattan_ovg_layers(
        p0,
        p1,
        [],
        pitch=pitch,
        profile=prof,
        skip_first_leg_hard_obstacle_check=True,
    )
    assert len(path) >= 2
    assert path[0] == p0
    assert path[-1] == p1


def test_route_manhattan_ovg_layers_manhattan_only_skips_ovg():
    pitch = GRID_PITCH
    p0, p1 = snapped_segment_default_diagonal(pitch)
    prof = replace(DEFAULT_ROUTING_PROFILE, use_fixed_manhattan=True, use_ovg_multi=False)

    def ovg_must_not_run(*_a, **_k):
        raise AssertionError("OVG must not run when use_ovg_multi is False")

    with patch(
        "logic_cad.core.routing.constrained_router.route_ovg_multi_start",
        side_effect=ovg_must_not_run,
    ):
        path = route_manhattan_ovg_layers(
            p0,
            p1,
            [],
            pitch=pitch,
            profile=prof,
            skip_first_leg_hard_obstacle_check=True,
        )
    assert len(path) >= 2
    assert path[0] == p0
    assert path[-1] == p1


def test_route_manhattan_ovg_layers_env_ovg_off_skips_ovg(monkeypatch: pytest.MonkeyPatch):
    pitch = GRID_PITCH
    p0, p1 = snapped_segment_default_diagonal(pitch)
    monkeypatch.setenv(ENV_ROUTING_OVG, "0")
    monkeypatch.delenv(ENV_ROUTING_FIXED, raising=False)

    def ovg_must_not_run(*_a, **_k):
        raise AssertionError("OVG must not run when env disables OVG")

    with patch(
        "logic_cad.core.routing.constrained_router.route_ovg_multi_start",
        side_effect=ovg_must_not_run,
    ):
        path = route_manhattan_ovg_layers(
            p0,
            p1,
            [],
            pitch=pitch,
            skip_first_leg_hard_obstacle_check=True,
        )
    assert len(path) >= 2
    assert path[-1] == p1


def test_route_manhattan_ovg_layers_env_ovg_on_runs_ovg(monkeypatch: pytest.MonkeyPatch):
    pitch = GRID_PITCH
    p0, p1 = snapped_segment_default_diagonal(pitch)
    monkeypatch.setenv(ENV_ROUTING_OVG, "1")
    monkeypatch.setenv(ENV_ROUTING_FIXED, "0")
    called = {"ovg": False}

    def ovg_called(*_a, **_k):
        called["ovg"] = True
        return [p0, p1]

    with patch(
        "logic_cad.core.routing.constrained_router.route_ovg_multi_start",
        side_effect=ovg_called,
    ):
        path = route_manhattan_ovg_layers(
            p0,
            p1,
            [],
            pitch=pitch,
            skip_first_leg_hard_obstacle_check=True,
        )
    assert called["ovg"] is True
    assert path[-1] == p1
