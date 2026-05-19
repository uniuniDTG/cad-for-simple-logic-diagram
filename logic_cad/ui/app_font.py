"""Resolve a single UI font family for Qt widgets (avoids repeated missing-TTF lookups)."""

from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase

# Japanese-capable UI fonts first; Segoe UI last among common Windows UI faces.
_UI_APP_FONT_CANDIDATES: tuple[str, ...] = (
    "Yu Gothic UI",
    "Yu Gothic",
    "Meiryo",
    "MS Gothic",
    "Helvetica Neue",
    "Arial",
    "Liberation Sans",
    "DejaVu Sans",
    "Noto Sans",
    "Segoe UI",
    "sans-serif",
)

_resolved_app_ui_font_family: str | None = None


def resolve_app_ui_font_family() -> str:
    """Return the first installed family from :data:`_UI_APP_FONT_CANDIDATES`.

    Result is cached for the process. Uses ``QFontDatabase.hasFamily`` so Qt does not
    repeatedly try to open missing ``segoeui.ttf`` paths when only the family name works.

    Returns:
        Installed font family name, or ``sans-serif`` when none match.
    """
    global _resolved_app_ui_font_family
    if _resolved_app_ui_font_family is not None:
        return _resolved_app_ui_font_family
    for fam in _UI_APP_FONT_CANDIDATES:
        if fam == "sans-serif" or QFontDatabase.hasFamily(fam):
            _resolved_app_ui_font_family = fam
            return fam
    _resolved_app_ui_font_family = "sans-serif"
    return _resolved_app_ui_font_family


def application_ui_font() -> QFont:
    """Build the default ``QFont`` for :meth:`QApplication.setFont`.

    Returns:
        Font using :func:`resolve_app_ui_font_family`.
    """
    font = QFont()
    font.setFamily(resolve_app_ui_font_family())
    font.setPointSize(9)
    return font
