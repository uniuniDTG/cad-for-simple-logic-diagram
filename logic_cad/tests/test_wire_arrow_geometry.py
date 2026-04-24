"""Tests for IN-side wire arrow wing geometry."""

from __future__ import annotations

import math

import pytest

from logic_cad.core.routing.wire_arrow_geometry import wire_in_arrow_wing_points_xyb
from logic_cad.core.services.dynamic_gate_factory import STUB_MM


def test_and_or_input_stub_polyline_in_at_symbol_root() -> None:
    """Stub tip (0,y) to vertical bar (STUB_MM,y): IN vertex P is the symbol-side root."""
    yi = 3.0
    xyb = [(0.0, yi, 0.0), (STUB_MM, yi, 0.0)]
    a, p, b = wire_in_arrow_wing_points_xyb(xyb, back_mm=2.0, side_mm=0.6)
    assert p == (STUB_MM, yi)


def test_straight_horizontal_incoming() -> None:
    """Last segment along +X; wings symmetric about the wire."""
    xyb = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0)]
    a, p, b = wire_in_arrow_wing_points_xyb(xyb, back_mm=2.0, side_mm=0.7)
    assert p == (10.0, 0.0)
    assert a == pytest.approx((8.0, 0.7))
    assert b == pytest.approx((8.0, -0.7))


def test_straight_vertical_incoming() -> None:
    xyb = [(0.0, 0.0, 0.0), (0.0, 5.0, 0.0)]
    a, p, b = wire_in_arrow_wing_points_xyb(xyb, back_mm=2.0, side_mm=0.7)
    assert p == (0.0, 5.0)
    assert a == pytest.approx((-0.7, 3.0))
    assert b == pytest.approx((0.7, 3.0))


def test_degenerate_segment_returns_none() -> None:
    xyb = [(1.0, 2.0, 0.0), (1.0, 2.0, 0.0)]
    assert wire_in_arrow_wing_points_xyb(xyb) is None


def test_terminal_duplicate_points_use_last_non_degenerate_direction() -> None:
    xyb = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (10.0, 0.0, 0.0)]
    a, p, b = wire_in_arrow_wing_points_xyb(xyb, back_mm=2.0, side_mm=0.7)
    assert p == (10.0, 0.0)
    assert a == pytest.approx((8.0, 0.7))
    assert b == pytest.approx((8.0, -0.7))


def test_too_few_vertices_raises() -> None:
    with pytest.raises(ValueError):
        wire_in_arrow_wing_points_xyb([(0.0, 0.0, 0.0)])


def test_arc_last_segment_unit_length() -> None:
    """Bulge non-zero: wing tips are *back_mm* along -t and ±*side_mm* from P."""
    xyb = [(0.0, 0.0, 0.5), (4.0, 0.0, 0.0)]
    tri = wire_in_arrow_wing_points_xyb(xyb, back_mm=2.0, side_mm=0.7)
    assert tri is not None
    a, p, b = tri
    for wing in (a, b):
        dx = wing[0] - p[0]
        dy = wing[1] - p[1]
        assert math.hypot(dx, dy) == pytest.approx(math.hypot(2.0, 0.7))
