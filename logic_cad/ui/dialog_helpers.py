"""Helpers for common Qt dialog patterns (OK/Cancel shells, Yes/No questions, modeless focus)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)


def create_ok_cancel_dialog(
    parent: QWidget | None,
    title: str,
) -> tuple[QDialog, QVBoxLayout, QDialogButtonBox]:
    """Build a titled modal shell: ``QDialog`` with an empty vertical layout and wired OK/Cancel box.

    The button box is **not** inserted into the layout; callers append their widgets to the layout
    first, then ``layout.addWidget(buttons)`` so the footer stays at the bottom.

    Args:
        parent: Optional owning widget for window modality.
        title: Window title for the dialog.

    Returns:
        ``(dialog, outer_layout, button_box)`` with ``accepted`` / ``rejected`` already connected
        to :meth:`~PySide6.QtWidgets.QDialog.accept` / :meth:`~PySide6.QtWidgets.QDialog.reject`.
    """
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    outer = QVBoxLayout(dlg)
    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    return dlg, outer, buttons


def question_yes_no(
    parent: QWidget | None,
    title: str,
    text: str,
    *,
    default_no: bool = True,
) -> bool:
    """Show a standard Yes/No question and report whether **Yes** was chosen.

    Args:
        parent: Optional parent for modality and placement.
        title: Dialog window title.
        text: Question body (supports newlines).
        default_no: When True, **No** is the default button (Escape maps to No).

    Returns:
        ``True`` if the user clicked **Yes**, ``False`` for **No** or dismiss.
    """
    default = (
        QMessageBox.StandardButton.No if default_no else QMessageBox.StandardButton.Yes
    )
    ret = QMessageBox.question(
        parent,
        title,
        text,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        default,
    )
    return ret == QMessageBox.StandardButton.Yes


def raise_modeless(widget: QWidget) -> None:
    """Show a non-modal window and bring it to the front (toolbar/menu helpers).

    Args:
        widget: Window or panel that should be visible and active.

    Returns:
        None
    """
    widget.show()
    widget.raise_()
    widget.activateWindow()


def dialog_exec_accepted(dlg: QDialog) -> bool:
    """Run a modal dialog and report whether it finished as accepted.

    Args:
        dlg: Modal dialog whose :meth:`~PySide6.QtWidgets.QDialog.exec` should run.

    Returns:
        ``True`` if :meth:`~PySide6.QtWidgets.QDialog.exec` returns
        :attr:`~PySide6.QtWidgets.QDialog.DialogCode.Accepted`, else ``False``.
    """
    return dlg.exec() == QDialog.DialogCode.Accepted
