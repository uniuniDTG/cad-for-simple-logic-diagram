"""New / open / save / drawing metadata and window title."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
)

from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.core.pages.page_layout_meta import (
    read_drawing_number,
    read_drawing_page_start,
    read_drawing_page_total_override,
)

if TYPE_CHECKING:
    from logic_cad.ui.main_window.window import MainWindow


def update_window_title(win: MainWindow) -> None:
    dn = read_drawing_number(win._diagram.doc).strip()
    common = dn if dn else "（図面番号なし）"
    p = win._diagram.path
    try:
        path_s = str(Path(p).resolve()) if p else "未保存"
    except OSError:
        path_s = str(p) if p else "未保存"
    star = "*" if win._diagram.is_dirty() else ""
    win.setWindowTitle(f"{star}Logic CAD {common} - {path_s}")


def prompt_save_if_dirty(win: MainWindow) -> bool:
    if not win._diagram.is_dirty():
        return True
    mb = QMessageBox(win)
    mb.setWindowTitle("Logic CAD")
    mb.setText("変更が保存されていません。保存しますか？")
    mb.setIcon(QMessageBox.Icon.Question)
    mb.setStandardButtons(
        QMessageBox.StandardButton.Save
        | QMessageBox.StandardButton.Discard
        | QMessageBox.StandardButton.Cancel
    )
    mb.setDefaultButton(QMessageBox.StandardButton.Save)
    bs = mb.button(QMessageBox.StandardButton.Save)
    if bs is not None:
        bs.setText("保存")
    bd = mb.button(QMessageBox.StandardButton.Discard)
    if bd is not None:
        bd.setText("保存しない")
    bc = mb.button(QMessageBox.StandardButton.Cancel)
    if bc is not None:
        bc.setText("キャンセル")
    ret = QMessageBox.StandardButton(mb.exec())
    if ret == QMessageBox.StandardButton.Cancel:
        return False
    if ret == QMessageBox.StandardButton.Discard:
        return True
    win._save_doc()
    return not win._diagram.is_dirty()


def new_document(win: MainWindow) -> None:
    if not prompt_save_if_dirty(win):
        return
    win._diagram = LogicDiagram.new()
    win._scene.set_diagram(win._diagram)
    if win._find_dialog is not None:
        win._find_dialog.set_diagram(win._diagram)
    win._view.setScene(win._scene)
    win._page_bar.sync_from_diagram()
    win._props.clear_selection()
    win._symbol_clipboard = None
    win._refresh_palette()
    win._tool_bridge.reset_routing_and_sketch_tools()
    QTimer.singleShot(0, win._view.fit_a4_page)
    update_window_title(win)


def open_document(win: MainWindow) -> None:
    if not prompt_save_if_dirty(win):
        return
    path, _ = QFileDialog.getOpenFileName(win, "DXF を開く", "", "DXF (*.dxf)")
    if not path:
        return
    try:
        win._diagram = LogicDiagram.open(path)
    except Exception as ex:
        QMessageBox.warning(win, "開く", str(ex))
        return
    win._scene.set_diagram(win._diagram)
    if win._find_dialog is not None:
        win._find_dialog.set_diagram(win._diagram)
    win._view.setScene(win._scene)
    win._page_bar.sync_from_diagram()
    win._refresh_palette()
    win._symbol_clipboard = None
    win._tool_bridge.reset_routing_and_sketch_tools()
    QTimer.singleShot(0, win._view.fit_a4_page)
    update_window_title(win)


def save_document(win: MainWindow) -> None:
    if not win._diagram.path:
        save_document_as(win)
        return
    try:
        win._diagram.save()
    except Exception as ex:
        QMessageBox.warning(win, "保存", str(ex))
        return
    update_window_title(win)


def save_document_as(win: MainWindow) -> None:
    path, _ = QFileDialog.getSaveFileName(win, "DXF として保存", "", "DXF (*.dxf)")
    if not path:
        return
    try:
        win._diagram.save(path)
    except Exception as ex:
        QMessageBox.warning(win, "保存", str(ex))
        return
    update_window_title(win)


def preferred_font_settings(win: MainWindow) -> None:
    """Open project preferred font dialog (LD_DOC XDATA)."""

    from logic_cad.ui.preferred_font_dialog import run_preferred_font_dialog

    if run_preferred_font_dialog(win, win._diagram):
        win._refresh_scene()


def drawing_properties(win: MainWindow) -> None:
    cur = read_drawing_number(win._diagram.doc)
    dlg = QDialog(win)
    dlg.setWindowTitle("図面プロパティ")
    layout = QVBoxLayout(dlg)
    form = QFormLayout()
    ed_no = QLineEdit(cur)
    form.addRow("図面番号（全ページの {{DWG_NO}} / $PROJECTNAME）", ed_no)
    ed_start = QSpinBox()
    ed_start.setRange(1, 99999)
    ed_start.setValue(read_drawing_page_start(win._diagram.doc))
    ed_start.setStyleSheet("QSpinBox { padding-right: 15px; }")
    form.addRow("開始ページ番号（{{PAGE_NUM}} の先頭シート）", ed_start)
    ed_total = QSpinBox()
    ed_total.setRange(0, 99999)
    ed_total.setSpecialValueText("自動")
    tot_ov = read_drawing_page_total_override(win._diagram.doc)
    ed_total.setValue(tot_ov if tot_ov is not None else 0)
    ed_total.setStyleSheet("QSpinBox { padding-right: 15px; }")
    form.addRow("総ページ数（{{PAGE_TOTAL}}、0=自動）", ed_total)
    layout.addLayout(form)
    n_layouts = len(win._diagram.list_pages())
    hint = QLabel(
        "図枠の {{DWG_NO}} は $PROJECTNAME、{{PAGE_NUM}} / {{PAGE_TOTAL}} は $USERI1 / $USERI2（開発者向け "
        f"docs/developer.md 参照）。総ページを自動にした場合は現在の用紙枚数（目次含む）: {n_layouts}。"
    )
    hint.setObjectName("hint")
    hint.setWordWrap(True)
    layout.addWidget(hint)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    layout.addWidget(buttons)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return
    total_pages: int | None
    if ed_total.value() == 0:
        total_pages = None
    else:
        total_pages = ed_total.value()
    try:
        with win._diagram.begin("drawing_meta"):
            win._diagram.set_drawing_number(ed_no.text())
            win._diagram.set_drawing_page_numbering(start_page=ed_start.value(), total_pages=total_pages)
    except Exception as ex:
        QMessageBox.warning(win, "図面プロパティ", str(ex))
        return
    win._refresh_scene()
