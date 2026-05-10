"""Small dialog and sorting helpers shared by the property panel.

Centralizes ``QMessageBox`` wrappers and the port-key sort order so the heavier
UI modules stay focused on widgets and LogicDiagram-facing updates.
"""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget

from logic_cad.core.model.port_key import parse_port_key


def show_property_panel_warning(parent: QWidget, title: str, message: str) -> None:
    """Show a standard warning dialog for property apply or validation failures.

    Keeps ``QMessageBox.warning`` usage in one place for consistent UX copy.

    Args:
        parent: Parent widget for the dialog (typically the property panel).
        title: Message box window title.
        message: Body text for the user.
    """
    QMessageBox.warning(parent, title, message)


def show_apply_warning(
    parent: QWidget,
    caption: str,
    ex: BaseException,
    *,
    fallback: str = "適用に失敗しました。",
) -> None:
    """Show the standard warning dialog after a caught exception during apply.

    Args:
        parent: Parent widget for the dialog (typically the property panel).
        caption: Message box window title.
        ex: Caught exception; ``str(ex)`` is shown when non-empty.
        fallback: Body text when ``str(ex)`` is blank.
    """
    show_property_panel_warning(parent, caption, str(ex) or fallback)


def port_sort_key(pk: str) -> tuple[int, str]:
    """Sort key for port keys: IN, INOUT, OUT, then unknown.

    Args:
        pk: Raw port key string from the diagram index.

    Returns:
        A tuple ``(group, pk)`` suitable for ``list.sort(key=...)``.
    """
    parsed = parse_port_key(pk)
    if parsed is None:
        return (3, pk)
    if parsed.direction == "IN":
        return (0, pk)
    if parsed.direction == "INOUT":
        return (1, pk)
    if parsed.direction == "OUT":
        return (2, pk)
    return (3, pk)
