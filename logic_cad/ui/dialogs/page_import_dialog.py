"""Dialog: choose an external DXF and import selected paper layouts into the current diagram."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
)

from logic_cad.core.dxf.dxf_repository import readfile
from logic_cad.core.pages.page_layout_meta import read_page_meta
from logic_cad.core.pages.page_order import is_toc_layout_name, validate_paper_layout_name
from logic_cad.core.services.layout_service import LayoutService
from logic_cad.ui.dialog_helpers import (
    create_ok_cancel_dialog,
    dialog_exec_accepted,
)

if TYPE_CHECKING:
    from logic_cad.ui.main_window.window import MainWindow


def run_page_import_dialog(win: "MainWindow") -> None:
    """Let the user pick a DXF file and import checked paper layouts.

    Shows a preview table with default destination layout names when the source
    name conflicts with layouts already present in the current document.

    Args:
        win: Main window owning the active :class:`~logic_cad.core.logic_diagram.LogicDiagram`.
    """
    fd_path, _ = QFileDialog.getOpenFileName(
        win,
        "別ファイルからページを取り込み",
        str(Path.cwd()),
        "DXF files (*.dxf);;All files (*)",
    )
    if not fd_path:
        return
    try:
        foreign_doc = readfile(fd_path)
    except Exception as ex:
        QMessageBox.warning(win, "ページ取り込み", f"ファイルを読めません。\n\n{ex}")
        return

    foreign_pages = LayoutService(foreign_doc).list_pages()
    importable = [p for p in foreign_pages if not is_toc_layout_name(p)]
    if not importable:
        QMessageBox.information(
            win,
            "ページ取り込み",
            "ソースに取り込める用紙レイアウトがありません（目次のみ等）。",
        )
        return

    dlg, vb, buttons = create_ok_cancel_dialog(win, f"ページ取り込み — {fd_path}")

    vb.addWidget(QLabel(Path(fd_path).name))
    tbl = QTableWidget(len(importable), 3)
    tbl.setHorizontalHeaderLabels(["取り込む", "ソースレイアウト", "取り込み先レイアウト名"])
    tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
    tbl.verticalHeader().setVisible(False)
    tbl.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)

    ls_target = LayoutService(win._diagram.doc)
    for row, src_layout in enumerate(importable):
        ci = QTableWidgetItem()
        ci.setCheckState(Qt.CheckState.Unchecked)
        ci.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        tbl.setItem(row, 0, ci)

        src_item = QTableWidgetItem(src_layout)
        src_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        tbl.setItem(row, 1, src_item)

        meta = read_page_meta(foreign_doc, src_layout)
        tip = ""
        desc = str(meta.get("page_desc") or "").strip()
        rev = str(meta.get("page_rev") or "").strip()
        if desc:
            tip = f"説明: {desc}"
        if rev:
            tip = (tip + "\n") if tip else ""
            tip += f"改訂: {rev}"
        src_item.setToolTip(tip or src_layout)

        dest_default = ls_target.suggest_import_dest_layout_name(src_layout)
        le = QLineEdit(dest_default)
        le.setPlaceholderText(dest_default)
        tbl.setCellWidget(row, 2, le)

    vb.addWidget(tbl)
    vb.addWidget(buttons)

    if not dialog_exec_accepted(dlg):
        return

    migrations: list[tuple[str, str]] = []
    for row in range(tbl.rowCount()):
        ck = tbl.item(row, 0)
        if ck is None or ck.checkState() != Qt.CheckState.Checked:
            continue
        src_item = tbl.item(row, 1)
        w_dest = tbl.cellWidget(row, 2)
        if src_item is None or not isinstance(w_dest, QLineEdit):
            continue
        src_name = src_item.text().strip()
        dest_name = w_dest.text().strip()
        if not dest_name:
            QMessageBox.warning(win, "ページ取り込み", "取り込み先のレイアウト名が空の行があります。")
            return
        try:
            validate_paper_layout_name(dest_name)
        except ValueError as ex:
            QMessageBox.warning(win, "ページ取り込み", str(ex))
            return
        migrations.append((src_name, dest_name))

    if not migrations:
        QMessageBox.information(win, "ページ取り込み", "取り込むページを選択してください。")
        return

    dest_seen: set[str] = set()
    for _s, dst in migrations:
        if dst in dest_seen:
            QMessageBox.warning(
                win,
                "ページ取り込み",
                f"取り込み先レイアウト名 {dst!r} が重複しています。",
            )
            return
        dest_seen.add(dst)

    try:
        with win._diagram.begin("import_pages_foreign"):
            win._diagram.import_pages_from_foreign_drawing(foreign_doc, migrations)
    except Exception as ex:
        QMessageBox.warning(win, "ページ取り込み", str(ex))
        return

    dest_last = migrations[-1][1]
    win._diagram.set_current_page(dest_last)
    win._scene.set_diagram(win._diagram)
    win._page_bar.sync_from_diagram()
    win._props.clear_selection()
    win._refresh_scene()
