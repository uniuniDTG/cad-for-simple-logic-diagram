"""Central widget: splitter with page/edit tabs (palette), canvas, property panel."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from logic_cad.ui.main_window.window import MainWindow


def _section_header(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setObjectName("sectionHeader")
    return lbl


def _section_sep() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setObjectName("sectionSep")
    return sep


class _SymbolLibraryBanner(QWidget):
    """区切り線と「シンボル」見出しをまとめ、クリックでシンボルライブラリを開く領域。

    パレット一覧とは分離し、ドラッグ操作と競合しないようにする。

    Args:
        on_click: 左クリック時に呼ぶコールバック（通常は ``MainWindow._show_symbol_library``）。
        parent: 親ウィジェット。省略時は None。

    """

    def __init__(
        self,
        on_click: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_click = on_click
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("クリックでシンボルライブラリを表示")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(_section_sep())
        lay.addWidget(_section_header("シンボル"))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """左ボタンで ``on_click`` を実行する。

        Args:
            event: マウスイベント。

        """
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_click()
        super().mousePressEvent(event)


def build_central_widget(win: MainWindow) -> QWidget:
    right = QWidget()
    v = QVBoxLayout(right)
    v.setContentsMargins(0, 0, 0, 0)
    v.addWidget(win._center_stack, 1)

    palette_column = QWidget()
    palette_column.setObjectName("paletteColumn")
    palette_column.setMinimumWidth(220)
    pc_layout = QVBoxLayout(palette_column)
    pc_layout.setContentsMargins(6, 8, 6, 6)
    pc_layout.setSpacing(4)

    pc_layout.addWidget(_section_header("配線ツール"))
    pc_layout.addWidget(win._btn_auto_wire)
    pc_layout.addWidget(win._btn_manual_wire)

    pc_layout.addWidget(_section_sep())
    pc_layout.addWidget(_section_header("注釈（図形）"))
    pc_layout.addWidget(win._sketch_tools_widget)

    symbol_block = QWidget()
    _sb_lay = QVBoxLayout(symbol_block)
    _sb_lay.setContentsMargins(0, 0, 0, 0)
    _sb_lay.setSpacing(4)
    _sb_lay.addWidget(_SymbolLibraryBanner(lambda: win._show_symbol_library()))
    _sb_lay.addWidget(win._palette, 1)
    pc_layout.addWidget(symbol_block, 1)

    win._page_tabs = QTabWidget()
    win._page_tabs.setTabPosition(QTabWidget.TabPosition.West)
    win._page_tabs.setDocumentMode(True)
    _te = win._page_tabs.addTab(palette_column, "編集")
    win._page_tabs.setTabToolTip(_te, "配線・図形ツール / シンボルパレット")
    _ti = win._page_tabs.addTab(win._page_bar, "ページ")
    win._page_tabs.setTabToolTip(_ti, "ドキュメント / ページ一覧")
    _tb_block = win._page_tabs.addTab(win._block_panel, "ブロック編集")
    win._page_tabs.setTabToolTip(_tb_block, "シンボルブロック定義のポート編集")
    win._page_tabs.currentChanged.connect(win._on_main_tab_changed)
    _tb = win._page_tabs.tabBar()
    _tb.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    _tb.customContextMenuRequested.connect(win._on_page_tab_bar_context)

    left_pages = QWidget()
    _lpl = QVBoxLayout(left_pages)
    _lpl.setContentsMargins(0, 0, 0, 0)
    _lpl.addWidget(win._page_tabs)
    left_pages.setMinimumWidth(220)

    splitter = QSplitter(Qt.Orientation.Horizontal)
    splitter.addWidget(left_pages)
    splitter.addWidget(right)
    splitter.addWidget(win._props)
    splitter.setStretchFactor(0, 0)
    splitter.setStretchFactor(1, 1)
    splitter.setStretchFactor(2, 0)
    splitter.setSizes([250, 720, 250])

    central = QWidget()
    cv = QVBoxLayout(central)
    cv.setContentsMargins(0, 0, 0, 0)
    cv.addWidget(splitter, 1)
    return central
