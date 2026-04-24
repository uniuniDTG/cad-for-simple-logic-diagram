"""P4: parallel offset of interior Manhattan wire segments."""

import pytest

from logic_cad.core.model.constants import BRIDGE_RADIUS
from logic_cad.core.routing import apply_vertical_semijumps_to_xyb
from logic_cad.core.routing.wire_polyline_geometry import (
    offset_polyline_segment_parallel,
    segment_eligible_for_parallel_offset,
)


def test_segment_eligible_only_interior():
    # L-shape corners: only the vertical run is interior (both bends).
    pts = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (20.0, 10.0)]
    assert not segment_eligible_for_parallel_offset(pts, 0)
    assert segment_eligible_for_parallel_offset(pts, 1)
    assert not segment_eligible_for_parallel_offset(pts, 2)


def test_parallel_offset_horizontal_segment():
    # Horizontal middle segment with vertical legs (Manhattan preserved when offsetting in Y).
    pts = [(0.0, 10.0), (10.0, 10.0), (10.0, 0.0), (20.0, 0.0), (20.0, -10.0)]
    out = offset_polyline_segment_parallel(pts, 2, 5.0)
    assert out is not None
    assert out[2][:2] == (10.0, 5.0)
    assert out[3][:2] == (20.0, 5.0)


def test_parallel_offset_vertical_segment():
    pts = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (20.0, 10.0), (20.0, 20.0), (30.0, 20.0)]
    out = offset_polyline_segment_parallel(pts, 1, 3.0)
    assert out is not None
    assert out[1][:2] == (13.0, 0.0)
    assert out[2][:2] == (13.0, 10.0)


def test_parallel_offset_vertical_run_moves_entire_colinear_including_bulge():
    base_xy = [(10.0, 0.0), (10.0, 20.0)]
    xyb = apply_vertical_semijumps_to_xyb(base_xy, [(10.0, 10.0, True)], BRIDGE_RADIUS)
    assert len(xyb) == 4
    out = offset_polyline_segment_parallel(xyb, 1, 2.0)
    assert out is not None
    for row in out:
        assert row[0] == pytest.approx(12.0)
    assert abs(out[1][2]) > 0.5


def test_parallel_offset_zero_delta_identity():
    pts = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (20.0, 10.0)]
    out = offset_polyline_segment_parallel(pts, 1, 0.0)
    assert out is not None
    assert len(out) == len(pts)
    exp_z = [(float(x), float(y), 0.0) for x, y in pts]
    assert all(
        abs(a[0] - c[0]) < 1e-9 and abs(a[1] - c[1]) < 1e-9 and abs(a[2] - c[2]) < 1e-9
        for a, c in zip(out, exp_z)
    )
