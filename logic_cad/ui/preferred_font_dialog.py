"""Project preferred font dialog (プロジェクト設定)."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
)

from logic_cad.core.text.layout_resolver import font_family_candidates


def filter_font_candidates_by_availability(
    candidates: Sequence[str],
    has_family: Callable[[str], bool],
) -> list[str]:
    """Return *candidates* in order, keeping only names accepted by *has_family*.

    Args:
        candidates: Ordered font family names (e.g. from :func:`font_family_candidates`).
        has_family: Predicate matching Qt / OS availability (e.g. ``QFontDatabase.hasFamily``).

    Returns:
        Filtered list in the same relative order as *candidates*.
    """

    return [c for c in candidates if has_family(c)]


def installed_project_font_combo_entries() -> list[str]:
    """Return :func:`font_family_candidates` entries that exist on this system (Qt)."""

    return filter_font_candidates_by_availability(font_family_candidates(), QFontDatabase.hasFamily)


def _fill_preferred_font_combo(combo: QComboBox, current: str | None, installed: list[str]) -> None:
    """Populate combo: 「既定」, optional saved-but-not-installed family, then *installed*."""

    combo.clear()
    combo.addItem("既定", None)
    cur = str(current or "").strip() or None
    if cur and cur not in installed:
        combo.addItem(cur, cur)
    for fam in installed:
        combo.addItem(fam, fam)


def _select_combo_data(combo: QComboBox, data: str | None) -> None:
    """Select the row whose ``itemData`` equals *data* (``None`` for 既定)."""

    for i in range(combo.count()):
        if combo.itemData(i) == data:
            combo.setCurrentIndex(i)
            return
    combo.setCurrentIndex(0)


def run_preferred_font_dialog(parent, diagram) -> bool:
    """Show the preferred font dialog; apply on accept.

    Args:
        parent: Parent widget (typically main window).
        diagram: :class:`~logic_cad.core.logic_diagram.LogicDiagram` instance.

    Returns:
        ``True`` if the user accepted and settings were applied.
    """

    dlg = QDialog(parent)
    dlg.setWindowTitle("優先フォント")
    layout = QVBoxLayout(dlg)
    form = QFormLayout()
    combo = QComboBox()
    installed = installed_project_font_combo_entries()
    current = diagram.get_project_preferred_font_family()
    _fill_preferred_font_combo(combo, current, installed)
    _select_combo_data(combo, current)
    form.addRow("優先フォント", combo)
    layout.addLayout(form)
    hint = QLabel(
        "図面内テキストのフォント解決順の先頭に置きます（既定のときは DXF スタイル優先のまま）。"
        "\n一覧は環境にインストール済みの候補のみです。"
    )
    hint.setObjectName("hint")
    hint.setWordWrap(True)
    layout.addWidget(hint)
    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    layout.addWidget(buttons)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return False
    raw = combo.currentData()
    chosen: str | None
    if raw is None:
        chosen = None
    else:
        chosen = str(raw).strip() or None
    diagram.set_project_preferred_font_family(chosen)
    return True
