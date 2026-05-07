"""Single-step PAGE_REF placement: target layout and vacant sym ordinal in one dialog."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from logic_cad.core.pages.page_labels import page_index_to_letters
from logic_cad.core.pages.page_ref import vacant_page_ref_sym_ordinals

if TYPE_CHECKING:
    from logic_cad.ui.main_window.window import MainWindow


def run_page_link_place_dialog(win: MainWindow) -> tuple[str, int] | None:
    """Pick a cross-page link target and letter rank before placing PAGE_REF on the sheet.

    Args:
        win: Main window; supplies the active diagram, document, and parent widget.

    Returns:
        ``(target_layout, sym_ordinal)`` when the user accepts, or ``None`` if there is
        no other page to link to or the user cancels.
    """
    doc = win._diagram.doc
    src = win._diagram.current_layout_name
    pages = [p for p in win._diagram.list_pages() if p != src]
    if not pages:
        return None
    dlg = QDialog(win)
    dlg.setWindowTitle("ページ跨ぎ")
    outer = QVBoxLayout(dlg)

    outer.addWidget(QLabel("リンク先ページ:"))
    cb_page = QComboBox()
    for p in pages:
        cb_page.addItem(p, userData=p)
    outer.addWidget(cb_page)

    outer.addWidget(QLabel("付番（アルファベット）：使用済みは表示されません"))
    lbl_hint = QLabel()
    outer.addWidget(lbl_hint)
    cb_rank = QComboBox()
    outer.addWidget(cb_rank)

    nav = QHBoxLayout()
    btn_place = QPushButton("配置")
    btn_cancel = QPushButton("キャンセル")
    nav.addWidget(btn_place)
    nav.addWidget(btn_cancel)
    outer.addLayout(nav)

    result: dict[str, object] = {"target": "", "rank": -1}

    def _fill_rank_combo(target_layout: str) -> bool:
        cb_rank.blockSignals(True)
        cb_rank.clear()
        vacant = vacant_page_ref_sym_ordinals(doc, src, target_layout)
        for v in vacant:
            cb_rank.addItem(page_index_to_letters(v), userData=v)
        cb_rank.blockSignals(False)
        if not vacant:
            lbl_hint.setText("この回廊には空き付番がありません。")
            lbl_hint.show()
            return False
        first = vacant[0]
        lbl_hint.setText(f"推奨: {page_index_to_letters(first)}")
        lbl_hint.show()
        cb_rank.setCurrentIndex(0)
        return True

    def _sync_rank_from_page(_index: int = 0) -> None:
        tgt = str(cb_page.currentData() or "").strip()
        if not tgt:
            btn_place.setEnabled(False)
            return
        btn_place.setEnabled(_fill_rank_combo(tgt))

    def _place() -> None:
        ri = cb_rank.currentData()
        if ri is None:
            return
        result["target"] = str(cb_page.currentData() or "").strip()
        result["rank"] = int(ri)
        dlg.accept()

    cb_page.currentIndexChanged.connect(_sync_rank_from_page)
    btn_place.clicked.connect(_place)
    btn_cancel.clicked.connect(dlg.reject)

    _sync_rank_from_page()

    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None
    t = str(result["target"] or "").strip()
    r = int(result["rank"])
    if not t or r < 0:
        return None
    return t, r
