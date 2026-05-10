"""Modal dialog for placing DXF single-line TEXT (string + cap height)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QWidget,
)

from logic_cad.ui.dialog_helpers import (
    create_ok_cancel_dialog,
    dialog_exec_accepted,
)


def prompt_dxf_text_string_and_height(
    parent: QWidget | None,
    *,
    window_title: str,
    empty_text_warning_title: str,
    default_height_mm: float,
    line_placeholder: str = "表示文字列",
    height_min_mm: float = 0.25,
    height_max_mm: float = 80.0,
    height_step_mm: float = 0.25,
) -> tuple[str, float] | None:
    """Show a modal dialog to enter display text and cap height in mm.

    Used for block-editor ``TEXT`` on ``LD_TEXT`` and main-canvas user annotation text.

    Args:
        parent: Optional parent widget for modality.
        window_title: Dialog title.
        empty_text_warning_title: Title for the warning when the user confirms with blank text.
        default_height_mm: Initial value for the height spin box.
        line_placeholder: Placeholder on the line edit.
        height_min_mm: Minimum allowed height (mm).
        height_max_mm: Maximum allowed height (mm).
        height_step_mm: Step for the height spin box.

    Returns:
        ``(text, height_mm)`` when accepted with non-blank text, else ``None``.
    """

    dlg, layout, buttons = create_ok_cancel_dialog(parent, window_title)
    form = QFormLayout()
    te = QLineEdit()
    te.setPlaceholderText(line_placeholder)
    hsp = QDoubleSpinBox()
    hsp.setRange(float(height_min_mm), float(height_max_mm))
    hsp.setSingleStep(float(height_step_mm))
    hsp.setSuffix(" mm")
    hsp.setValue(float(default_height_mm))
    form.addRow("文字列", te)
    form.addRow("文字高さ", hsp)
    layout.addLayout(form)
    layout.addWidget(buttons)
    if not dialog_exec_accepted(dlg):
        return None
    txt = te.text()
    if not str(txt).strip():
        QMessageBox.warning(
            parent,
            empty_text_warning_title,
            "文字列が空です。",
        )
        return None
    return str(txt), float(hsp.value())
