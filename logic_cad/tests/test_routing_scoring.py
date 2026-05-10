"""Unit tests for routing path cost helpers in ``scoring``."""

from __future__ import annotations

from logic_cad.core.routing.scoring import path_turns


def test_path_turns_axis_aligned_straight_is_zero() -> None:
    """A single horizontal or vertical segment has no direction change."""

    assert path_turns([(0.0, 0.0), (10.0, 0.0)]) == 0
    assert path_turns([(2.0, 3.0), (2.0, -1.0)]) == 0


def test_path_turns_typical_manhattan_l_shape_counts_one_turn() -> None:
    """Two perpendicular axis-aligned legs form one 90° direction change."""

    pts = [(0.0, 0.0), (10.0, 0.0), (10.0, 7.0)]
    assert path_turns(pts) == 1


def test_path_turns_manhattan_staircase_counts_each_corner() -> None:
    """Each 90° bend on an axis-aligned polyline increments the turn count."""

    pts = [
        (0.0, 0.0),
        (1.0, 0.0),
        (1.0, 1.0),
        (2.0, 1.0),
    ]
    assert path_turns(pts) == 2


def test_path_turns_non_axis_aligned_segment_skipped_manhattan_only_product() -> None:
    """Diagonal (or other non-H/V) legs are ignored for turn counting.

    Post-refactor behavior: only horizontal/vertical segments participate. Diagonal
    segments neither increment turns nor reset the prior axis direction; the last
    axis-aligned ``prev_dir`` remains in effect across skipped segments.
    """

    # First leg establishes horizontal direction; diagonal is skipped; vertical leg
    # still compares against the stored horizontal direction → one counted turn.
    pts_skip_middle = [(0.0, 0.0), (1.0, 0.0), (2.0, 1.0), (2.0, 2.0)]
    assert path_turns(pts_skip_middle) == 1

    # Leading diagonal is skipped entirely, so the vertical leg is treated as the
    # first axis-aligned direction (no prior direction → no turn at the corner).
    pts_leading_diagonal = [(0.0, 0.0), (1.0, 1.0), (1.0, 2.0), (2.0, 2.0)]
    assert path_turns(pts_leading_diagonal) == 1


def test_path_turns_reverse_on_same_axis_counts_turn() -> None:
    """A 180° bend on the same axis (opposite direction) increments turns."""

    pts = [(0.0, 0.0), (10.0, 0.0), (5.0, 0.0)]
    assert path_turns(pts) == 1
