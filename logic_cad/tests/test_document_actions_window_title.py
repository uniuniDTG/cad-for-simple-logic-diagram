"""Tests for main window title text formatting."""

from __future__ import annotations

from pathlib import Path

from logic_cad.core.model.constants import APP_DISPLAY_NAME_WITH_VERSION
from logic_cad.ui.main_window.document_actions import build_window_title


def test_build_window_title_for_unsaved_dirty_diagram() -> None:
    """Unsaved dirty diagram title includes star, version and fallback labels."""
    title = build_window_title(
        drawing_number="",
        diagram_path=None,
        is_dirty=True,
    )
    assert title == f"*{APP_DISPLAY_NAME_WITH_VERSION} （図面番号なし） - 未保存"


def test_build_window_title_for_saved_clean_diagram() -> None:
    """Saved clean diagram title includes drawing number and absolute path."""
    path = str(Path("sample_title_test.dxf"))
    expected_path = str(Path(path).resolve())
    title = build_window_title(
        drawing_number="DWG-42",
        diagram_path=path,
        is_dirty=False,
    )
    assert title == f"{APP_DISPLAY_NAME_WITH_VERSION} DWG-42 - {expected_path}"
