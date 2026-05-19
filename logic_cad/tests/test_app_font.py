"""Tests for application UI font resolution."""

from __future__ import annotations

from logic_cad.tests.support.qt_offscreen import ensure_qapplication_offscreen
from logic_cad.ui.app_font import resolve_app_ui_font_family


def test_resolve_app_ui_font_family_returns_non_empty() -> None:
    """Resolved UI font is cached and not empty."""
    ensure_qapplication_offscreen()
    first = resolve_app_ui_font_family()
    second = resolve_app_ui_font_family()
    assert first
    assert first == second
