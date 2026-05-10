"""Unit tests for shared L1 (Manhattan) distance helpers."""

from __future__ import annotations

import pytest

from logic_cad.core.geometry.manhattan_metrics import (
    manhattan_distance,
    manhattan_distance_via,
    points_close_xy,
    segment_is_axis_aligned,
    segment_is_horizontal,
    segment_is_vertical,
    truncated_grid_steps_sum,
)


def test_manhattan_distance_same_point() -> None:
    """Zero distance when both arguments are identical."""

    assert manhattan_distance((0.0, 0.0), (0.0, 0.0)) == 0.0
    assert manhattan_distance((-3.5, 12.0), (-3.5, 12.0)) == 0.0


def test_manhattan_distance_axis_aligned_segments() -> None:
    """Matches ``abs(dx)+abs(dy)`` for cardinal steps and mixed signs."""

    assert manhattan_distance((0.0, 0.0), (3.0, 4.0)) == 7.0
    assert manhattan_distance((1.0, -2.0), (-1.0, 3.0)) == 7.0


def test_manhattan_distance_via_is_sum_of_legs() -> None:
    """Two-leg path length equals sum of two Manhattan segments."""

    a, via, b = (0.0, 0.0), (10.0, 0.0), (10.0, 7.0)
    assert manhattan_distance_via(a, via, b) == manhattan_distance(a, via) + manhattan_distance(via, b)
    assert manhattan_distance_via(a, via, b) == 17.0


def test_points_close_xy_matches_pairwise_abs() -> None:
    """``points_close_xy`` mirrors the prior routing ``abs(dx)<eps and abs(dy)<eps`` pattern."""

    assert points_close_xy((1.0, 2.0), (1.0, 2.0))
    assert points_close_xy((1.0, 2.0), (1.0 + 5e-10, 2.0 - 5e-10), eps=1e-9)
    assert not points_close_xy((0.0, 0.0), (0.002, 0.0), eps=1e-9)


def test_segment_orientation_helpers() -> None:
    """Axis / horizontal / vertical predicates match grid-aligned expectations."""

    a, b = (0.0, 0.0), (3.0, 0.0)
    assert segment_is_horizontal(a, b)
    assert segment_is_vertical(a, b) is False
    assert segment_is_axis_aligned(a, b)

    c, d = (1.0, 5.0), (1.0, -2.0)
    assert segment_is_vertical(c, d)
    assert segment_is_horizontal(c, d) is False
    assert segment_is_axis_aligned(c, d)

    assert segment_is_axis_aligned((0.0, 0.0), (0.0, 0.0))


def test_truncated_grid_steps_sum_not_same_as_l1_quotient() -> None:
    """Per-axis truncation can differ from ``int(L1 / pitch)`` (documented pitfall)."""

    pitch = 3.0
    a, b = (0.0, 0.0), (5.0, 5.0)
    assert truncated_grid_steps_sum(a, b, pitch) == int(5 / 3) + int(5 / 3) == 1 + 1 == 2
    assert int(manhattan_distance(a, b) / pitch) == int(10 / 3) == 3

    with pytest.raises(ValueError):
        truncated_grid_steps_sum(a, b, 0.0)
