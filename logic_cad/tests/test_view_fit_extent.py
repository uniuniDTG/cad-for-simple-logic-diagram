"""Tests for middle-double-click view framing (diagram A4 floor; block editor padding)."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtWidgets import QGraphicsRectItem

from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.core.model.constants import (
    A4_LANDSCAPE_HEIGHT_MM,
    A4_LANDSCAPE_WIDTH_MM,
    BLOCK_EDIT_INITIAL_VIEW_HALF_MM,
)
from logic_cad.tests.support.qt_offscreen import ensure_qapplication_offscreen
from logic_cad.ui.scene import DiagramScene
from logic_cad.ui.symbol_block_editor.scene import SymbolBlockEditScene
from logic_cad.ui.view_fit_rect import DEFAULT_DIAGRAM_VIEW_FIT_MARGIN_MM, default_a4_fit_rect_mm


def test_default_a4_fit_rect_matches_landscape_sheet_and_margin() -> None:
    """Landscape A4 dimensions plus uniform margin match manual composition."""

    m = DEFAULT_DIAGRAM_VIEW_FIT_MARGIN_MM
    r = default_a4_fit_rect_mm()
    assert r.left() == -m
    assert r.top() == -A4_LANDSCAPE_HEIGHT_MM - m
    assert r.width() == A4_LANDSCAPE_WIDTH_MM + 2 * m
    assert r.height() == A4_LANDSCAPE_HEIGHT_MM + 2 * m


def test_diagram_scene_extent_floor_when_items_bounds_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """When ``itemsBoundingRect`` is empty, extent is exactly the default A4 rectangle."""

    ensure_qapplication_offscreen()
    scene = DiagramScene(LogicDiagram.new())

    def _empty_bounds() -> QRectF:
        return QRectF()

    monkeypatch.setattr(scene, "itemsBoundingRect", _empty_bounds)
    assert scene.extent_rect_for_view_fit() == default_a4_fit_rect_mm()


def test_diagram_scene_extent_unions_padded_items_with_a4_floor() -> None:
    """Bounds include diagram content plus the injected rect; padded hull unites with A4."""

    ensure_qapplication_offscreen()
    scene = DiagramScene(LogicDiagram.new())
    tiny = QGraphicsRectItem(5000.0, -3000.0, 3.0, 4.0)
    scene.addItem(tiny)
    m = DEFAULT_DIAGRAM_VIEW_FIT_MARGIN_MM
    br_all = scene.itemsBoundingRect()
    padded = br_all.adjusted(-m, -m, m, m)
    assert scene.extent_rect_for_view_fit() == padded.united(default_a4_fit_rect_mm())


def test_block_edit_extent_uses_margin_without_min_floor() -> None:
    """Small block geometry fits tightly with DEFAULT_DIAGRAM_VIEW_FIT_MARGIN_MM only."""

    ensure_qapplication_offscreen()
    sc = SymbolBlockEditScene(lambda: None, lambda: None, lambda: "CONTINUOUS")
    it = QGraphicsRectItem(5.0, 6.0, 2.0, 3.0)
    sc.addItem(it)
    br = it.sceneBoundingRect()
    pad = float(DEFAULT_DIAGRAM_VIEW_FIT_MARGIN_MM)
    assert sc.extent_rect_for_view_fit() == br.adjusted(-pad, -pad, pad, pad)


def test_block_edit_extent_empty_matches_initial_view_with_margin() -> None:
    """Empty block scene falls back to initial insertion framing plus margin."""

    ensure_qapplication_offscreen()
    sc = SymbolBlockEditScene(lambda: None, lambda: None, lambda: "CONTINUOUS")
    half = float(BLOCK_EDIT_INITIAL_VIEW_HALF_MM)
    base = sc.initial_view_scene_rect()
    pad = float(DEFAULT_DIAGRAM_VIEW_FIT_MARGIN_MM)
    ext = sc.extent_rect_for_view_fit()
    assert ext == base.adjusted(-pad, -pad, pad, pad)
    assert ext.width() == 2 * half + 2 * pad
