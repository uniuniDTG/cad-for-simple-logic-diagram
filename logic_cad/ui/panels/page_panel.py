"""Page (layout) list: layout name + ``page_desc``; extra detail in tooltip."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QMenu

from logic_cad.core.pages.page_layout_meta import read_page_meta

if TYPE_CHECKING:
    from logic_cad.core.logic_diagram import LogicDiagram

_PAGE_ROLE = Qt.ItemDataRole.UserRole


class PagePanel(QListWidget):
    propertiesRequested = Signal(str)
    deletePageRequested = Signal(str)
    duplicatePageRequested = Signal(str)
    addPageRequested = Signal()
    regenerateTocRequested = Signal()

    def __init__(self, get_diagram: Callable[[], LogicDiagram], on_change: Callable[[str], None], parent=None) -> None:
        super().__init__(parent)
        self._get_diagram = get_diagram
        self._on_change = on_change
        self.setSpacing(2)
        self.setAlternatingRowColors(False)
        self.itemSelectionChanged.connect(self._on_sel)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._ctx_menu)

    def sync_from_diagram(self) -> None:
        d = self._get_diagram()
        self.blockSignals(True)
        self.clear()
        pages = d.list_pages()
        cur = d.current_layout_name
        cur_row = 0
        for i, name in enumerate(pages):
            meta = read_page_meta(d.doc, name)
            desc = (meta.get("page_desc") or "").strip()
            label = f"[{name}]  {desc if desc else ''}"
            it = QListWidgetItem(label)
            it.setData(_PAGE_ROLE, name)
            rev = (meta.get("page_rev") or "").strip()
            tip_parts = [f"レイアウト名: {name}"]
            if rev:
                tip_parts.append(f"改訂: {rev}")
            if desc:
                tip_parts.append(f"説明: {desc}")
            it.setToolTip("\n".join(tip_parts))
            self.addItem(it)
            if name == cur:
                cur_row = i
        if self.count() > 0:
            self.setCurrentRow(cur_row)
        self.blockSignals(False)

    def _on_sel(self) -> None:
        it = self.currentItem()
        if it is None:
            return
        name = it.data(_PAGE_ROLE)
        if isinstance(name, str) and name:
            self._on_change(name)

    def _ctx_menu(self, pos: QPoint) -> None:
        it = self.itemAt(pos)
        menu = QMenu(self)
        if it is not None:
            name = it.data(_PAGE_ROLE)
            if isinstance(name, str) and name:
                menu.addAction("プロパティ…", lambda: self.propertiesRequested.emit(name))
                menu.addAction("ページを削除…", lambda: self.deletePageRequested.emit(name))
                menu.addAction("ページを複製…", lambda: self.duplicatePageRequested.emit(name))
                menu.addSeparator()
        menu.addAction("ページを追加…", lambda: self.addPageRequested.emit())
        menu.addAction("目次を再生成", lambda: self.regenerateTocRequested.emit())
        menu.exec(self.mapToGlobal(pos))
