"""Modal dialog for palette INPAGE_REF placement: manual display text or automatic ※ numbering."""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QWidget,
)

from logic_cad.core.model.constants import INPAGE_LINK_DISPLAY_MAX_LEN

from logic_cad.ui.dialog_helpers import (
    create_ok_cancel_dialog,
    dialog_exec_accepted,
)

if TYPE_CHECKING:
    from logic_cad.ui.main_window.window import MainWindow


class InpageLinkPlaceChoice(NamedTuple):
    """User choice from :func:`run_inpage_link_place_dialog`.

    Attributes:
        link_name_auto: When True, defer to :func:`refresh_inpage_ref_syms_on_layout` for ※1… order.
        display_text: Fixed label for both ends; must be empty when *link_name_auto* is True.
    """

    link_name_auto: bool
    display_text: str


def run_inpage_link_place_dialog(win: MainWindow) -> InpageLinkPlaceChoice | None:
    """Prompt for INPAGE_REF link label before inserting the FROM/TO pair from the palette.

    Manual mode persists ``inpage_link_name_auto`` to ``\"0\"`` so geometry sort cannot re-assign ※n.

    Args:
        win: Main window (dialog parent).

    Returns:
        The user's choice when accepted; ``None`` when the dialog was cancelled.
    """

    dlg, layout, buttons = create_ok_cancel_dialog(win, "インページリンク")
    hint = QLabel(
        "手動では表示が固定されます。自動採番オンにすると配置後も幾何順で ※ の番号が変わり得ます。"
    )
    hint.setWordWrap(True)
    layout.addWidget(hint)

    chk_auto = QCheckBox("自動採番（※1, ※2, …）")
    chk_auto.setChecked(False)

    row = QFormLayout()
    te = QLineEdit()
    te.setMaxLength(INPAGE_LINK_DISPLAY_MAX_LEN)
    te.setPlaceholderText(
        "手動でも *n 形式にもどちらにもできます（自動採番オフのみ）",
    )

    row.addRow(chk_auto)
    row.addRow("リンク表示文字", te)
    layout.addLayout(row)

    def _toggle_edit(checked: bool) -> None:
        te.setEnabled(not checked)

    chk_auto.toggled.connect(_toggle_edit)
    _toggle_edit(chk_auto.isChecked())
    layout.addWidget(buttons)

    if not dialog_exec_accepted(dlg):
        return None

    use_auto = chk_auto.isChecked()
    if use_auto:
        return InpageLinkPlaceChoice(link_name_auto=True, display_text="")

    txt = te.text().strip()
    if not txt:
        QMessageBox.warning(
            win,
            "インページリンク",
            "手動モードでは表示文字を入力してください。",
        )
        return None

    max_len = int(INPAGE_LINK_DISPLAY_MAX_LEN)
    if len(txt) > max_len:
        QMessageBox.warning(
            win,
            "インページリンク",
            f"表示文字は {max_len} 文字以内にしてください（現在 {len(txt)} 文字）。",
        )
        return None

    return InpageLinkPlaceChoice(link_name_auto=False, display_text=txt)
