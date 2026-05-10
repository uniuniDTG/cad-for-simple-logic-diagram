"""Undo / redo / delete selection."""

from __future__ import annotations

from typing import TYPE_CHECKING

from logic_cad.core.undo.scratch_transaction import (
    ScratchUndoDiagram,
    scratch_redo,
    scratch_undo,
)
from logic_cad.ui.dialog_helpers import question_yes_no
from logic_cad.ui.items.symbol_item import SymbolItem
from logic_cad.ui.items.user_geometry_items import (
    UserArcItem,
    UserCircleItem,
    UserCloudItem,
    UserLineItem,
    UserTextItem,
)
from logic_cad.ui.items.wire_item import WireItem

if TYPE_CHECKING:
    from logic_cad.ui.main_window.window import MainWindow


def _block_edit_tab_active(win: MainWindow) -> bool:
    """True when the west tab bar is on *ブロック* (symbol block editor shell)."""

    return win._page_tabs.currentIndex() == 2


def undo(win: MainWindow) -> None:
    if _block_edit_tab_active(win):
        sess = win._block_panel.session()
        if sess is not None:
            if scratch_undo(ScratchUndoDiagram(sess.scratch_doc), sess.block_history):
                win._block_scene.refresh_from_session()
            return
    win._diagram.undo()
    win._refresh_scene()


def redo(win: MainWindow) -> None:
    if _block_edit_tab_active(win):
        sess = win._block_panel.session()
        if sess is not None:
            if scratch_redo(ScratchUndoDiagram(sess.scratch_doc), sess.block_history):
                win._block_scene.refresh_from_session()
            return
    win._diagram.redo()
    win._refresh_scene()


def delete_selection(win: MainWindow) -> None:
    if _block_edit_tab_active(win):
        win._block_scene.delete_selected_editor_items()
        return
    with win._diagram.begin("delete"):
        for it in list(win._scene.selectedItems()):
            if isinstance(it, SymbolItem):
                win._diagram.delete_by_uid(it.symbol_uid)
            elif isinstance(it, WireItem):
                win._diagram.delete_by_uid(it.wire_uid)
            elif isinstance(
                it, (UserLineItem, UserCircleItem, UserArcItem, UserCloudItem, UserTextItem)
            ):
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
    if not question_yes_no(
        win,
        "雲マークをすべて削除",
        "すべての用紙ページ上の雲マーク（ユーザー下絵）を削除しますか？\n\n"
        "直線・円・テキストの下絵は削除されません。操作は取り消し（Undo）できます。",
    ):
        return
    with win._diagram.begin("delete_all_user_clouds"):
        win._diagram.delete_all_user_clouds_all_pages()
    win._props.clear_selection()
    win._refresh_scene()
