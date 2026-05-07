"""Reorder PAGE_REF corridor (current sheet → picked target layout) via Up/Down on uid list."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from logic_cad.core.model.constants import PEER_UID_XDATA
from logic_cad.core.model.xdata import get_uid, read_ld_app_dict
from logic_cad.core.pages.page_ref import page_ref_target_layouts_on_sheet, sorted_page_refs_by_target

if TYPE_CHECKING:
    from logic_cad.ui.main_window.window import MainWindow


def run_page_ref_reorder_dialog(win: MainWindow) -> None:
    diag = win._diagram
    doc = diag.doc
    src = diag.current_layout_name
    tgts = page_ref_target_layouts_on_sheet(doc, src)
    if not tgts:
        QMessageBox.information(win, "ページ跨ぎ", "並べ替えできるページリンクがありません。")
        return
    dlg = QDialog(win)
    dlg.setWindowTitle("ページ跨ぎリンクの順序")
    vb = QVBoxLayout(dlg)
    vb.addWidget(QLabel("リンク先レイアウト:"))
    cb = QComboBox()
    for t in tgts:
        cb.addItem(t, userData=t)
    vb.addWidget(cb)
    lw = QListWidget()
    vb.addWidget(lw)

    def refill() -> None:
        lw.clear()
        tgt = str(cb.currentData() or "").strip()
        if not tgt:
            return
        blk = doc.blocks.get(doc.layouts.get(src).block_record_name)
        for ins in sorted_page_refs_by_target(blk, tgt):
            d = read_ld_app_dict(ins)
            u = str(d.get("uid") or get_uid(ins) or "")
            if not u:
                continue
            peer = str(d.get(PEER_UID_XDATA) or "").strip() or "—"
            it = QListWidgetItem(f"{u}  （相手 uid: {peer}）")
            it.setData(Qt.ItemDataRole.UserRole, u)
            lw.addItem(it)

    cb.currentIndexChanged.connect(lambda _idx: refill())
    refill()

    row = QHBoxLayout()
    btn_up = QPushButton("上へ")
    btn_dn = QPushButton("下へ")
    row.addWidget(btn_up)
    row.addWidget(btn_dn)
    vb.addLayout(row)

    ok = QPushButton("OK")
    cancel = QPushButton("キャンセル")
    row2 = QHBoxLayout()
    row2.addWidget(ok)
    row2.addWidget(cancel)
    vb.addLayout(row2)

    def move_delta(delta: int) -> None:
        r = lw.currentRow()
        if r < 0:
            return
        n = lw.count()
        r2 = r + delta
        if r2 < 0 or r2 >= n:
            return
        it = lw.takeItem(r)
        lw.insertItem(r2, it)
        lw.setCurrentRow(r2)

    btn_up.clicked.connect(lambda: move_delta(-1))
    btn_dn.clicked.connect(lambda: move_delta(1))

    cancel.clicked.connect(dlg.reject)
    ok.clicked.connect(dlg.accept)

    if dlg.exec() != QDialog.DialogCode.Accepted:
        return
    tgt_final = str(cb.currentData() or "").strip()
    if not tgt_final:
        return
    ordered_uids: list[str] = []
    for j in range(lw.count()):
        it = lw.item(j)
        u = str(it.data(Qt.ItemDataRole.UserRole) or "").strip()
        if u:
            ordered_uids.append(u)
    try:
        with diag.begin("page_ref_reorder"):
            diag.reorder_page_refs_on_corridor(tgt_final, ordered_uids)
    except Exception as ex:
        QMessageBox.warning(win, "ページ跨ぎ", str(ex) or "並べ替えに失敗しました。")
        return
    win._refresh_scene()
