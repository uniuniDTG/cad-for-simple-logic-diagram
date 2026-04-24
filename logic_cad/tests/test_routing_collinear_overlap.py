"""Collinear wire overlap exclusion in Manhattan routing."""

from __future__ import annotations

from logic_cad.core.model.constants import ROUTING_COLLINEAR_OVERLAP_MIN_MM
from logic_cad.core.routing.manhattan import route_manhattan
from logic_cad.core.routing.overlap import (
    path_has_collinear_overlap,
    segment_collinear_overlap_length,
    segment_overlaps_existing_collinear,
    wire_paths_to_flat_segments,
)


def test_segment_collinear_overlap_parallel_horizontal() -> None:
    assert segment_collinear_overlap_length((0.0, 0.0), (10.0, 0.0), (3.0, 0.0), (7.0, 0.0)) == 4.0
    assert segment_collinear_overlap_length((3.0, 0.0), (7.0, 0.0), (0.0, 0.0), (10.0, 0.0)) == 4.0


def test_segment_collinear_overlap_crossing_only() -> None:
    assert segment_collinear_overlap_length((0.0, 0.0), (10.0, 0.0), (5.0, -5.0), (5.0, 5.0)) == 0.0


def test_segment_collinear_touch_endpoint() -> None:
    assert (
        segment_collinear_overlap_length((0.0, 0.0), (5.0, 0.0), (5.0, 0.0), (10.0, 0.0)) <= ROUTING_COLLINEAR_OVERLAP_MIN_MM
    )


def test_segment_overlaps_skips_axis_mismatch() -> None:
    existing = wire_paths_to_flat_segments([[(0.0, 0.0), (10.0, 0.0)]])
    assert not segment_overlaps_existing_collinear((0.0, 5.0), (10.0, 5.0), existing)
    assert segment_overlaps_existing_collinear((2.0, 0.0), (8.0, 0.0), existing)


def test_path_has_collinear_overlap() -> None:
    existing = wire_paths_to_flat_segments([[(0.0, 0.0), (10.0, 0.0)]])
    assert path_has_collinear_overlap([(2.0, 0.0), (8.0, 0.0)], existing)
    assert not path_has_collinear_overlap([(2.0, 1.0), (8.0, 1.0)], existing)
    assert not path_has_collinear_overlap([(5.0, -2.0), (5.0, 2.0)], existing)


def test_route_manhattan_avoids_collinear_duplicate_horizontal() -> None:
    existing = wire_paths_to_flat_segments([[(2.0, 0.0), (8.0, 0.0)]])
    pts = route_manhattan((2.0, 0.0), (8.0, 0.0), obstacles=[], existing_wire_segments=existing)
    assert len(pts) >= 2
    assert not path_has_collinear_overlap(pts, existing)
    assert pts[0] == (2.0, 0.0)
    assert pts[-1] == (8.0, 0.0)


def test_route_manhattan_allows_orthogonal_crossing() -> None:
    existing = wire_paths_to_flat_segments([[(0.0, 0.0), (10.0, 0.0)]])
    pts = route_manhattan((5.0, -3.0), (5.0, 3.0), obstacles=[], existing_wire_segments=existing)
    assert pts[0] == (5.0, -3.0)
    assert pts[-1] == (5.0, 3.0)
    assert len(pts) == 2
