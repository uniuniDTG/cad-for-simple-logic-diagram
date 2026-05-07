"""Copy / paste symbol and user-sketch selection."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

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
from logic_cad.core.services.block_edit_clipboard import (
    BLOCK_EDIT_ENTITIES_MIME,
    collect_serialized_entities_from_block,
    decode_entity_clipboard,
    encode_entity_payloads,
    paste_entity_clipboard_root,
)
from logic_cad.ui.items.user_geometry_items import UserCircleItem, UserCloudItem, UserLineItem, UserTextItem
from logic_cad.ui.symbol_block_editor.scene import ITEM_KIND_ATTDEF, ITEM_KIND_GEOM, ITEM_KIND_PORT

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


def _block_edit_selection_keys(scene) -> list[tuple[str, str]]:
    """Stable de-duplicated (kind, key) pairs: handle or USER sketch uid."""
    refs: list[tuple[str, str]] = []
    for it in scene.selectedItems():
        kind = str(it.data(1) or "")
        h = str(it.data(0) or "")
        if kind in (ITEM_KIND_PORT, ITEM_KIND_GEOM, ITEM_KIND_ATTDEF) and h:
            refs.append(("handle", h))
        elif isinstance(it, UserLineItem):
            refs.append(("uid", it.sketch_uid))
        elif isinstance(it, UserCircleItem):
            refs.append(("uid", it.sketch_uid))
    seen: set[str] = set()
    ordered: list[tuple[str, str]] = []
    for kind, key in sorted(refs, key=lambda t: (t[0], t[1])):
        sig = f"{kind}:{key}"
        if sig in seen:
            continue
        seen.add(sig)
        ordered.append((kind, key))
    return ordered


def _block_edit_clipboard_from_system() -> dict[str, Any] | None:
    """Return decoded block-edit clipboard root from ``QClipboard``, if present."""
    app = QApplication.instance()
    if app is None:
        return None
    md = app.clipboard().mimeData()
    if md is None or not md.hasFormat(BLOCK_EDIT_ENTITIES_MIME):
        return None
    raw = md.data(BLOCK_EDIT_ENTITIES_MIME)
    blob = bytes(raw) if raw is not None else b""
    return decode_entity_clipboard(blob)


def copy_block_edit_selection(win: MainWindow) -> None:
    """Copy selected entities from the block editor to the block-edit clipboard MIME.

    Args:
        win: Main window (block tab, active session, non-empty selection).
    """
    sess = win._block_panel.session()
    if sess is None:
        return
    blk = sess.scratch_block()
    if blk is None:
        return
    keys = _block_edit_selection_keys(win._block_scene)
    if not keys:
        return
    payloads = collect_serialized_entities_from_block(sess.scratch_doc, blk, keys)
    raw = encode_entity_payloads(payloads)
    if not raw:
        return
    win._block_edit_entity_clipboard = raw
    app = QApplication.instance()
    if app is not None:
        md = QMimeData()
        md.setData(BLOCK_EDIT_ENTITIES_MIME, QByteArray(raw))
        app.clipboard().setMimeData(md)


def paste_block_edit_clipboard(win: MainWindow) -> None:
    """Paste block-edit clipboard at the cursor anchor and select new items.

    Args:
        win: Main window with active block session.
    """
    sess = win._block_panel.session()
    if sess is None:
        return
    root = _block_edit_clipboard_from_system()
    if root is None:
        fb = win._block_edit_entity_clipboard
        if not fb:
            return
        root = decode_entity_clipboard(fb)
    if root is None:
        return
    anchor = win._block_view.last_scene_pos_dxf()
    handles = paste_entity_clipboard_root(sess, root, anchor)
    win._block_scene.refresh_from_session()
    win._block_scene.clearSelection()
    hs = set(handles)
    for it in win._block_scene.items():
        h = str(it.data(0) or "")
        if h and h in hs:
            it.setSelected(True)
    win._block_scene.edited.emit()


def copy_symbol_selection(win: MainWindow) -> None:
    if win._page_tabs.currentIndex() == 2:
        copy_block_edit_selection(win)
        return
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
    if win._page_tabs.currentIndex() == 2:
        paste_block_edit_clipboard(win)
        return
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
