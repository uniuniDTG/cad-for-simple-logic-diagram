"""Copy / paste symbol and user-sketch selection."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QByteArray, QMimeData
from PySide6.QtWidgets import QApplication, QMessageBox

from logic_cad.core.model.constants import (
    ENTITY_TYPE_PAPER_FRAME,
    ENTITY_TYPE_TOC_HEADER,
    ENTITY_TYPE_TOC_ROW,
)
from logic_cad.core.symbol_clipboard import SymbolClipboardPayload
from logic_cad.core.symbol_clipboard_codec import (
    SYMBOL_CLIPBOARD_MIME,
    decode_symbol_clipboard_payload_from_bytes,
    encode_symbol_clipboard_payload_to_bytes,
)
from logic_cad.ui.items.user_geometry_items import UserCircleItem, UserCloudItem, UserLineItem, UserTextItem

if TYPE_CHECKING:
    from logic_cad.ui.main_window.window import MainWindow


def _payload_from_system_clipboard() -> SymbolClipboardPayload | None:
    """Decode the logic_cad symbol payload from ``QClipboard`` if present.

    Invalid or unknown MIME payloads are ignored so paste can fall back to
    the in-memory buffer.

    Returns:
        Parsed payload with symbols or user sketches, or ``None`` if unavailable.
    """

    app = QApplication.instance()
    if app is None:
        return None
    md = app.clipboard().mimeData()
    if md is None or not md.hasFormat(SYMBOL_CLIPBOARD_MIME):
        return None
    raw = md.data(SYMBOL_CLIPBOARD_MIME)
    blob = bytes(raw) if raw is not None else b""
    if not blob:
        return None
    try:
        pl = decode_symbol_clipboard_payload_from_bytes(blob)
    except ValueError:
        return None
    if not pl.symbols and not pl.user_sketches:
        return None
    return pl


def copy_symbol_selection(win: MainWindow) -> None:
    from logic_cad.ui.items.symbol_item import SymbolItem

    sym_uids: list[str] = []
    sketch_uids: list[str] = []
    for it in win._scene.selectedItems():
        if isinstance(it, SymbolItem):
            if it.entity_type in (
                ENTITY_TYPE_PAPER_FRAME,
                ENTITY_TYPE_TOC_HEADER,
                ENTITY_TYPE_TOC_ROW,
            ):
                continue
            sym_uids.append(it.symbol_uid)
        elif isinstance(it, (UserLineItem, UserCircleItem, UserCloudItem, UserTextItem)):
            sketch_uids.append(it.sketch_uid)
    if not sym_uids and not sketch_uids:
        return
    sketch_uids = list(dict.fromkeys(sketch_uids))
    sym_uids = list(dict.fromkeys(sym_uids))
    payload = win._diagram.build_symbol_clipboard_payload(sym_uids, sketch_uids)
    if not payload.symbols and not payload.user_sketches:
        return
    win._symbol_clipboard = payload
    app = QApplication.instance()
    if app is not None:
        raw = encode_symbol_clipboard_payload_to_bytes(payload)
        md = QMimeData()
        md.setData(SYMBOL_CLIPBOARD_MIME, QByteArray(raw))
        app.clipboard().setMimeData(md)


def paste_symbol_clipboard(win: MainWindow) -> None:
    pl: SymbolClipboardPayload | None = _payload_from_system_clipboard()
    if pl is None:
        if win._symbol_clipboard is None:
            return
        pl = win._symbol_clipboard
    if not pl.symbols and not pl.user_sketches:
        return
    anchor = win._view.last_scene_pos_dxf()
    new_syms: list[str] = []
    new_sk: list[str] = []
    try:
        with win._diagram.begin("paste_symbols"):
            new_syms, new_sk = win._diagram.paste_symbol_clipboard_payload(pl, anchor)
    except Exception as ex:
        QMessageBox.warning(win, "貼り付け", str(ex) or "貼り付けに失敗しました。")
        return
    win._refresh_scene()
    if new_syms or new_sk:
        win._scene.select_pasted_items(set(new_syms), set(new_sk))
