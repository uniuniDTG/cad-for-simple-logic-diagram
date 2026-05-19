"""Tests for block_paint font face resolution (avoid broken TTF/TTC paths)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PySide6.QtGui import QFontDatabase

from logic_cad.tests.support.qt_offscreen import ensure_qapplication_offscreen
from logic_cad.ui.app_font import resolve_app_ui_font_family
from logic_cad.ui.block_paint import _qfont_from_font_face


def test_qfont_prefers_has_family_over_missing_font_file() -> None:
    """When family is installed, use hasFamily instead of opening a missing font file."""
    ensure_qapplication_offscreen()
    family = resolve_app_ui_font_family()
    if family == "sans-serif" or not QFontDatabase.hasFamily(family):
        pytest.skip("No concrete UI font family available in this environment")
    face = MagicMock()
    face.filename = r"C:\Windows\Fonts\msgothic.ttc"
    face.family = family
    font = _qfont_from_font_face(face, font_family="Arial")
    assert font.family() == family
