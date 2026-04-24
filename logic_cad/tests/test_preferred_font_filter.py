"""Tests for project preferred font candidate filtering (no Qt required)."""

from __future__ import annotations

from logic_cad.ui.preferred_font_dialog import filter_font_candidates_by_availability


def test_filter_font_candidates_by_availability_order() -> None:
    """Filtered list keeps candidate order and drops missing families."""

    cands = ("A", "B", "C", "D")

    def has_family(name: str) -> bool:
        return name in {"B", "D"}

    assert filter_font_candidates_by_availability(cands, has_family) == ["B", "D"]
