"""Tests for ``logic_cad.core.geometry.arc_through_three_points``."""

from __future__ import annotations

import math

import pytest

from logic_cad.core.geometry.arc_through_three_points import (
    ValueCollinearPointsError,
    ValueDuplicatePointsError,
    circumcenter_xy,
    dxf_arc_from_three_points,
)


def test_circumcenter_unit_semicircle() -> None:
    """(1,0), (0,1), (-1,0) -> center (0,0)."""
    cx, cy = circumcenter_xy((1.0, 0.0), (0.0, 1.0), (-1.0, 0.0))
    assert abs(cx) < 1e-9 and abs(cy) < 1e-9


def test_dxf_arc_quadrant_ccw() -> None:
    """Start +X, mid +Y, end -X: CCW arc through upper half."""
    (cx, cy), r, sa, ea = dxf_arc_from_three_points((10.0, 0.0), (0.0, 10.0), (-10.0, 0.0))
    assert abs(cx) < 1e-6 and abs(cy) < 1e-6
    assert abs(r - 10.0) < 1e-6
    assert abs(sa - 0.0) < 1e-3 or abs(sa - 360.0) < 1e-3
    assert abs(ea - 180.0) < 1e-3


def test_dxf_arc_major_arc_mid_on_left() -> None:
    """Middle point on long way: start (1,0), mid (-1,0), end (0,1)."""
    (cx, cy), r, sa, ea = dxf_arc_from_three_points((1.0, 0.0), (-1.0, 0.0), (0.0, 1.0))
    assert abs(cx) < 1e-9 and abs(cy) < 1e-9
    assert abs(r - 1.0) < 1e-9
    # CCW from 90° to 0° (360°) passes through 180° (left point).
    assert abs(sa - 90.0) < 1e-3
    assert abs(ea - 0.0) < 1e-3 or abs(ea - 360.0) < 1e-3


def test_collinear_raises() -> None:
    with pytest.raises(ValueCollinearPointsError):
        dxf_arc_from_three_points((0.0, 0.0), (1.0, 0.0), (2.0, 0.0))


def test_duplicate_raises() -> None:
    with pytest.raises(ValueDuplicatePointsError):
        dxf_arc_from_three_points((1.0, 1.0), (1.0, 1.0), (0.0, 0.0))


def test_endpoints_on_circle() -> None:
    """Reconstructed arc passes through all three (numerical)."""
    # Radius 5 about (2, -1): three non-collinear points on the circle.
    (cx, cy), r, sa, ea = dxf_arc_from_three_points((7.0, -1.0), (2.0, 4.0), (-3.0, -1.0))
    pts = ((7.0, -1.0), (2.0, 4.0), (-3.0, -1.0))
    for px, py in pts:
        d = abs(math.hypot(px - cx, py - cy) - r)
        assert d < 1e-3
