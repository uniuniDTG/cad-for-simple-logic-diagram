"""Routing: OVG with axis-aligned first hops from port; optional preferred first_escape_src."""

import pytest

from logic_cad.core.model.constants import GRID_PITCH
from logic_cad.core.routing import route_manhattan_with_escape
from logic_cad.core.routing.overlap import path_has_collinear_overlap


def test_escape_inserts_axis_aligned_first_leg():
    pts = route_manhattan_with_escape((0, 0), (10, 8), [], first_escape_src=None)
    assert len(pts) >= 2
    assert pts[0] == (0, 0)
    d1 = abs(pts[1][0] - pts[0][0]) + abs(pts[1][1] - pts[0][1])
    assert d1 >= GRID_PITCH * 0.5
    assert pts[0][0] == pts[1][0] or pts[0][1] == pts[1][1]


def test_dual_axis_initial_escape_can_use_y_first_leg_when_aligned():
    """API flag ignored; four axis first hops always considered."""
    pts = route_manhattan_with_escape(
        (30.0, 50.0),
        (30.0, 72.0),
        [],
        first_escape_src=None,
        dual_axis_initial_escape=True,
    )
    assert len(pts) >= 2
    assert pts[0] == (30.0, 50.0)
    assert abs(pts[1][1] - 50.0) >= GRID_PITCH * 0.5 or abs(pts[1][0] - 30.0) >= GRID_PITCH * 0.5


def test_escape_avoids_collinear_overlap_with_existing_trunk():
    long_h = [((0.0, 0.0), (200.0, 0.0))]
    pts = route_manhattan_with_escape(
        (10.0, 0.0),
        (50.0, 0.0),
        [],
        first_escape_src=(20.0, 0.0),
        existing_wire_segments=long_h,
    )
    assert len(pts) >= 2
    assert not path_has_collinear_overlap(pts, long_h)
