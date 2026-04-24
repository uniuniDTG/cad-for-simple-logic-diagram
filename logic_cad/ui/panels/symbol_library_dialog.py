"""Graphical block library: thumbnails with drag to canvas (same MIME as palette)."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QByteArray, QMimeData, Qt
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGridLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ezdxf.document import Drawing

from logic_cad.core.services.layout_service import list_palette_block_names
from logic_cad.ui.palette_drag_preview import palette_drag_pixmap_and_hotspot
from logic_cad.ui.panels.palette_panel import MIME_PALETTE


class _DraggableTile(QWidget):
    """Single library cell: thumbnail + label; starts QDrag with palette MIME."""

    def __init__(
        self,
        doc: Drawing,
        display_name: str,
        payload: str,
        *,
        thumb_px: int = 72,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._doc = doc
        self._display_name = display_name
        self._payload = payload
        self._thumb_px = thumb_px
        self._press_pos = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(2)

        self._pix_label = QLabel()
        self._pix_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pix_label.setFixedSize(thumb_px + 8, thumb_px + 8)
        self._pix_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._pix_label.setFrameShape(QFrame.Shape.StyledPanel)
        self._pix_label.setScaledContents(False)

        cap = QLabel(display_name)
        cap.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        cap.setWordWrap(True)
        cap.setMaximumWidth(thumb_px + 32)

        outer.addWidget(self._pix_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        outer.addWidget(cap, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._apply_pixmap()

    def _apply_pixmap(self) -> None:
        pm, _ = palette_drag_pixmap_and_hotspot(
            self._doc,
            self._payload,
            list_label=self._display_name,
            max_side_px=self._thumb_px,
        )
        if pm is not None:
            self._pix_label.setPixmap(pm)
        else:
            self._pix_label.setText("—")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if not (event.buttons() & Qt.MouseButton.LeftButton) or self._press_pos is None:
            super().mouseMoveEvent(event)
            return
        if (event.position().toPoint() - self._press_pos).manhattanLength() < QApplication.startDragDistance():
            super().mouseMoveEvent(event)
            return
        self._start_drag()
        self._press_pos = None
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._press_pos = None
        super().mouseReleaseEvent(event)

    def _start_drag(self) -> None:
        md = QMimeData()
        md.setData(MIME_PALETTE, QByteArray(self._payload.encode("utf-8")))
        drag = QDrag(self)
        drag.setMimeData(md)
        pix, hot = palette_drag_pixmap_and_hotspot(
            self._doc, self._payload, list_label=self._display_name, max_side_px=88
        )
        if pix is not None:
            drag.setPixmap(pix)
            drag.setHotSpot(hot)
        drag.exec(Qt.DropAction.CopyAction, Qt.DropAction.CopyAction)


class SymbolLibraryDialog(QDialog):
    """Non-modal gallery of palette entries; drag onto the diagram view to place."""

    _COLS = 4

    def __init__(self, get_doc: Callable[[], Drawing], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("シンボルライブラリ")
        self.setModal(False)
        self._get_doc = get_doc
        self._tiles: list[_DraggableTile] = []

        root = QVBoxLayout(self)
        hint = QLabel("サムネイルをキャンバスへドラッグして配置します。")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self._grid_widget = QWidget()
        self._grid = QGridLayout(self._grid_widget)
        self._grid.setContentsMargins(4, 4, 4, 4)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._grid_widget)
        root.addWidget(scroll, 1)
        self.resize(520, 420)

    def refresh_from_document(self) -> None:
        doc = self._get_doc()
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._tiles.clear()

        fixed: list[tuple[str, str]] = [
            ("NOT", "block:NOT"),
            ("AND", "kind:AND"),
            ("OR", "kind:OR"),
            ("チェックポイント", "kind:CHECKPOINT"),
            ("配線分岐", "kind:WIRE_BRANCH"),
            ("ページリンク", "page_link:"),
            ("インページリンク", "inpage_link:"),
        ]
        row = 0
        col = 0
        for text, payload in fixed:
            tile = _DraggableTile(doc, text, payload, parent=self._grid_widget)
            self._grid.addWidget(tile, row, col)
            self._tiles.append(tile)
            col += 1
            if col >= self._COLS:
                col = 0
                row += 1

        blocks = list_palette_block_names(doc)
        for name in blocks:
            if name.upper() == "NOT":
                continue
            payload = f"block:{name}"
            tile = _DraggableTile(doc, name, payload, parent=self._grid_widget)
            self._grid.addWidget(tile, row, col)
            self._tiles.append(tile)
            col += 1
            if col >= self._COLS:
                col = 0
                row += 1

        stretch_row = row if col == 0 else row + 1
        self._grid.setRowStretch(stretch_row, 1)
