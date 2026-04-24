"""Orthogonal wire semicircle jumps (vertical LWPOLYLINE bulge)."""

import math

import pytest

from logic_cad.core.model.constants import BRIDGE_RADIUS
from logic_cad.core.routing import (
    apply_vertical_semijumps_to_xyb,
    horizontal_segment_goes_east,
    orthogonal_segments_crossing_relaxed,
    strip_wire_xyb_semijumps,
)


def test_orthogonal_crossing_relaxed_interior() -> None:
    h0, h1 = (0.0, 5.0), (10.0, 5.0)
    v0, v1 = (5.0, 0.0), (5.0, 10.0)
    r = orthogonal_segments_crossing_relaxed(h0, h1, v0, v1)
    assert r is not None
    pt, hseg, vseg = r
    assert pt == (5.0, 5.0)
    assert hseg == (h0, h1)
    assert vseg == (v0, v1)


def test_orthogonal_crossing_rejects_t_junction_vertical_end_on_horizontal() -> None:
    h0, h1 = (0.0, 5.0), (10.0, 5.0)
    v0, v1 = (5.0, 5.0), (5.0, 10.0)
    assert orthogonal_segments_crossing_relaxed(h0, h1, v0, v1) is None


def test_horizontal_segment_goes_east() -> None:
    assert horizontal_segment_goes_east((0.0, 0.0), (3.0, 0.0)) is True
    assert horizontal_segment_goes_east((3.0, 0.0), (0.0, 0.0)) is False


def test_apply_semijump_inserts_vertical_bulge() -> None:
    base = [(5.0, 0.0), (5.0, 20.0)]
    xyb = apply_vertical_semijumps_to_xyb(base, [(5.0, 10.0, True)], BRIDGE_RADIUS)
    assert len(xyb) == 4
    assert abs(xyb[1][2]) == pytest.approx(1.0)
    assert xyb[1][0] == pytest.approx(5.0)
    assert xyb[2][0] == pytest.approx(5.0)
    assert abs(xyb[1][1] - xyb[2][1]) == pytest.approx(2 * BRIDGE_RADIUS)


def test_strip_roundtrip_restores_straight_vertical() -> None:
    base = [(5.0, 0.0), (5.0, 20.0)]
    xyb = apply_vertical_semijumps_to_xyb(base, [(5.0, 10.0, True)], BRIDGE_RADIUS)
    stripped = strip_wire_xyb_semijumps(xyb)
    xy = [(x, y) for x, y, _ in stripped]
    assert len(xy) == 2
    assert xy[0][0] == pytest.approx(5.0)
    assert xy[1][0] == pytest.approx(5.0)
    assert xy[0][1] == pytest.approx(0.0)
    assert xy[1][1] == pytest.approx(20.0)
    assert all(abs(b) < 1e-9 for *_, b in stripped)


def test_two_jumps_unified_orient_same_bulge_sign() -> None:
    base = [(10.0, 0.0), (10.0, 50.0)]
    xyb = apply_vertical_semijumps_to_xyb(
        base,
        [(10.0, 12.0, True), (10.0, 28.0, True), (10.0, 38.0, True)],
        BRIDGE_RADIUS,
    )
    bulges = [row[2] for row in xyb if abs(row[2]) > 0.5]
    assert len(bulges) == 3
    assert all(b == bulges[0] for b in bulges)


def test_two_jumps_mixed_orient_alternates_bulge_sign() -> None:
    """Without service-layer unification, opposite want_east flips bulge between jumps."""
    base = [(10.0, 0.0), (10.0, 40.0)]
    xyb = apply_vertical_semijumps_to_xyb(
        base, [(10.0, 12.0, True), (10.0, 28.0, False)], BRIDGE_RADIUS
    )
    bulges = [row[2] for row in xyb if abs(row[2]) > 0.5]
    assert len(bulges) == 2
    assert bulges[0] == -bulges[1]


def test_semijump_bulge_matches_half_circle_geometry() -> None:
    from ezdxf.math import Vec2, bulge_to_arc

    base = [(0.0, 0.0), (0.0, 20.0)]
    xyb = apply_vertical_semijumps_to_xyb(base, [(0.0, 10.0, True)], 0.7)
    b0 = xyb[1][2]
    c, sa, ea, r = bulge_to_arc(Vec2(0.0, xyb[1][1]), Vec2(0.0, xyb[2][1]), b0)
    assert r == pytest.approx(0.7, rel=1e-5)
    assert abs(sa - ea) == pytest.approx(math.pi, rel=1e-5)


def test_negative_bulge_tessellation_ends_at_chord_endpoint() -> None:
    """Match WireItem: swap sa/ea when bulge < 0 so t=1 lands on (x1,y1), not (x0,y0)."""
    import math

    from ezdxf.math import Vec2, bulge_to_arc

    base = [(5.0, 0.0), (5.0, 20.0)]
    xyb = apply_vertical_semijumps_to_xyb(base, [(5.0, 10.0, True)], BRIDGE_RADIUS)
    x0, y0, b0 = xyb[1][0], xyb[1][1], xyb[1][2]
    x1, y1 = xyb[2][0], xyb[2][1]
    assert b0 < 0

    center, sa, ea, r = bulge_to_arc(Vec2(x0, y0), Vec2(x1, y1), b0)
    sa, ea = ea, sa
    t_last = 1.0
    ang = sa + t_last * (ea - sa)
    cx, cy = float(center.x), float(center.y)
    xe = cx + r * math.cos(ang)
    ye = cy + r * math.sin(ang)
    assert xe == pytest.approx(x1, abs=1e-5)
    assert ye == pytest.approx(y1, abs=1e-5)
