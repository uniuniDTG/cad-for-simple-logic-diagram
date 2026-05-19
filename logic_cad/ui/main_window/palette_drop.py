"""Palette drag-and-drop onto the diagram view."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox

from logic_cad.core.debug.debug_log import logic_cad_log
from logic_cad.ui.dialogs.inpage_link_place_dialog import run_inpage_link_place_dialog
from logic_cad.ui.dialogs.page_link_place_dialog import run_page_link_place_dialog
from logic_cad.ui.panels.palette_panel import MIME_PALETTE
from logic_cad.ui.snap_utils import snap_dxf_pos

if TYPE_CHECKING:
    from logic_cad.ui.main_window.window import MainWindow


def view_drag_enter(win: MainWindow, event) -> None:
    if event.mimeData().hasFormat(MIME_PALETTE):
        event.acceptProposedAction()
    else:
        event.ignore()


def view_drag_move(win: MainWindow, event) -> None:
    if event.mimeData().hasFormat(MIME_PALETTE):
        event.acceptProposedAction()
    else:
        event.ignore()


def view_drop(win: MainWindow, event) -> None:
    if not event.mimeData().hasFormat(MIME_PALETTE):
        event.ignore()
        return
    raw = bytes(event.mimeData().data(MIME_PALETTE)).decode("utf-8")
    scene_pos = win._view.mapToScene(event.position().toPoint())
    x, y = snap_dxf_pos(scene_pos.x(), -scene_pos.y())
    kind, _, name = raw.partition(":")
    logic_cad_log("drop", f"mime={raw!r} kind={kind!r} name={name!r} dxf_pos=({x}, {y})")
    if kind == "page_link":
        others = [p for p in win._diagram.list_pages() if p != win._diagram.current_layout_name]
        if not others:
            QMessageBox.information(
                win,
                "ページ跨ぎ",
                "リンク先にできる他ページがありません。ページを追加してください。",
            )
            event.ignore()
            return
        picked = run_page_link_place_dialog(win)
        if picked is None:
            event.ignore()
            return
        target, sym_ord = picked
        try:
            with win._diagram.begin("page_link"):
                win._diagram.place_page_link_pair_ranked((x, y), target, sym_ord)
        except Exception as ex:
            QMessageBox.warning(win, "ページ跨ぎ", str(ex))
            event.ignore()
            return
        event.acceptProposedAction()
        win._refresh_scene()
        return
    if kind == "inpage_link":
        picked = run_inpage_link_place_dialog(win)
        if picked is None:
            event.ignore()
            return
        try:
            with win._diagram.begin("inpage_link"):
                uid_from = win._diagram.place_inpage_link((x, y))
                win._diagram.place_inpage_link_peer(uid_from, (x + 28.0, y + 22.0))
                if not picked.link_name_auto:
                    win._diagram.set_inpage_ref_link_display(
                        uid_from,
                        link_name_auto=False,
                        display_text=picked.display_text,
                    )
        except Exception as ex:
            QMessageBox.warning(win, "インページリンク", str(ex))
            event.ignore()
            return
        event.acceptProposedAction()
        win._refresh_scene()
        return
    if kind == "kind" and name == "WIRE_BRANCH":
        try:
            with win._diagram.begin("wire_branch"):
                win._diagram.place_wire_branch((x, y))
        except Exception as ex:
            QMessageBox.warning(win, "配線分岐", str(ex))
            event.ignore()
            return
        event.acceptProposedAction()
        win._refresh_scene()
        return
    with win._diagram.begin("drop"):
        if kind == "kind" and name == "AND":
            win._diagram.place_and_gate(2, (x, y))
        elif kind == "kind" and name == "OR":
            win._diagram.place_or_gate(2, (x, y))
        elif kind == "kind" and name == "CHECKPOINT":
            win._diagram.place_checkpoint((x, y))
        elif kind == "block":
            win._diagram.place_symbol(name, (x, y))
    event.acceptProposedAction()
    win._refresh_scene()
