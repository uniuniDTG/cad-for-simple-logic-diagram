"""Undo / redo / delete selection."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox

from logic_cad.ui.items.user_geometry_items import UserCircleItem, UserCloudItem, UserLineItem, UserTextItem

if TYPE_CHECKING:
    from logic_cad.ui.main_window.window import MainWindow


def undo(win: MainWindow) -> None:
    win._diagram.undo()
    win._refresh_scene()


def redo(win: MainWindow) -> None:
    win._diagram.redo()
    win._refresh_scene()


def delete_selection(win: MainWindow) -> None:
    from logic_cad.ui.items.symbol_item import SymbolItem
    from logic_cad.ui.items.wire_item import WireItem

    with win._diagram.begin("delete"):
        for it in list(win._scene.selectedItems()):
            if isinstance(it, SymbolItem):
                win._diagram.delete_by_uid(it.symbol_uid)
            elif isinstance(it, WireItem):
                win._diagram.delete_by_uid(it.wire_uid)
            elif isinstance(it, (UserLineItem, UserCircleItem, UserCloudItem, UserTextItem)):
                win._diagram.delete_by_uid(it.sketch_uid)
    win._props.clear_selection()
    win._refresh_scene()


def delete_all_user_clouds(win: MainWindow) -> None:
    """Show a confirmation dialog, then delete all revision clouds document-wide.

    Args:
        win: Main window holding the diagram and property panel.

    Returns:
        None
    """
    ret = QMessageBox.question(
        win,
        "雲マークをすべて削除",
        "すべての用紙ページ上の雲マーク（ユーザー下絵）を削除しますか？\n\n"
        "直線・円・テキストの下絵は削除されません。操作は取り消し（Undo）できます。",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if ret != QMessageBox.StandardButton.Yes:
        return
    with win._diagram.begin("delete_all_user_clouds"):
        win._diagram.delete_all_user_clouds_all_pages()
    win._props.clear_selection()
    win._refresh_scene()
