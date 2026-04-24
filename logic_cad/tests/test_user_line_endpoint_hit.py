"""Tests for ``UserLineItem.hit_endpoint_index`` (canvas endpoint drag)."""

from __future__ import annotations

from PySide6.QtCore import QPointF

from logic_cad.ui.items.user_geometry_items import UserLineItem
from logic_cad.ui.scene_item.hits import DEFAULT_SCENE_HIT_TOL_MM


def test_hit_endpoint_index_chooses_start_and_end() -> None:
    item = UserLineItem("a", 0.0, 0.0, 100.0, 0.0)
    assert item.hit_endpoint_index(QPointF(0.0, 0.0)) == 0
    assert item.hit_endpoint_index(QPointF(100.0, 0.0)) == 1


def test_hit_endpoint_index_fails_mid_axis() -> None:
    item = UserLineItem("a", 0.0, 0.0, 100.0, 0.0)
    assert item.hit_endpoint_index(QPointF(50.0, 0.0)) is None


def test_hit_endpoint_index_respects_tol_mm() -> None:
    item = UserLineItem("a", 0.0, 0.0, 10.0, 0.0)
    t = float(DEFAULT_SCENE_HIT_TOL_MM)
    assert item.hit_endpoint_index(QPointF(t - 0.5, 0.0), tol_mm=t) == 0
    assert item.hit_endpoint_index(QPointF(t + 0.5, 0.0), tol_mm=t) is None


def test_hit_endpoint_index_prefers_nearer_of_two() -> None:
    """If both ends are within *tol mm*, the closer one wins (includes very short lines)."""
    item = UserLineItem("a", 0.0, 0.0, 2.0, 0.0)
    t = 4.0
    assert item.hit_endpoint_index(QPointF(1.0, 0.0), tol_mm=t) == 0
    pos_closer_to_end = QPointF(1.6, 0.0)
    assert item.hit_endpoint_index(pos_closer_to_end, tol_mm=t) == 1
