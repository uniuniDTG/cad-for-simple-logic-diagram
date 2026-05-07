"""Symbol palette with drag."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QMimeData, Qt
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from ezdxf.document import Drawing

from logic_cad.core.debug.debug_log import logic_cad_log
from logic_cad.core.debug.debug_symlib import symlib_log
from logic_cad.core.services.layout_service import list_palette_block_names
from logic_cad.ui.palette_drag_preview import palette_drag_pixmap_and_hotspot

MIME_PALETTE = "application/x-logic-cad-palette"


class PalettePanel(QListWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("symbolPalette")
        self.setDragEnabled(True)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)
        self._doc: Drawing | None = None

    def refresh_from_document(self, doc: Drawing) -> None:
        """Rebuild entries from doc block table (keep built‑in rows + library blocks)."""
        self._doc = doc
        self.clear()
        fixed = [
            ("AND", "kind:AND"),
            ("OR", "kind:OR"),
            ("チェックポイント", "kind:CHECKPOINT"),
            ("配線分岐", "kind:WIRE_BRANCH"),
            ("ページリンク", "page_link:"),
            ("インページリンク", "inpage_link:"),
        ]
        for text, payload in fixed:
            it = QListWidgetItem(text)
            it.setData(Qt.ItemDataRole.UserRole, payload)
            self.addItem(it)

        blocks = list_palette_block_names(doc)
        symlib_log(f"palette refresh: {len(blocks)} block rows -> {blocks}")
        logic_cad_log("palette", f"refresh {len(blocks)} library rows: {blocks}")
        for name in blocks:
            it = QListWidgetItem(name)
            it.setData(Qt.ItemDataRole.UserRole, f"block:{name}")
            self.addItem(it)

    def startDrag(self, supportedActions) -> None:
        item = self.currentItem()
        if not item:
            return
        payload = item.data(Qt.ItemDataRole.UserRole)
        if not payload:
            return
        md = QMimeData()
        md.setData(MIME_PALETTE, QByteArray(payload.encode("utf-8")))
        drag = QDrag(self)
        drag.setMimeData(md)
        pix, hot = palette_drag_pixmap_and_hotspot(self._doc, str(payload), list_label=item.text())
        if pix is not None:
            drag.setPixmap(pix)
            drag.setHotSpot(hot)
        drag.exec(Qt.DropAction.CopyAction, Qt.DropAction.CopyAction)
