"""Page list, TOC, navigation, and page CRUD dialogs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, QRectF, QTimer, Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QInputDialog,
    QLineEdit,
    QMenu,
    QMessageBox,
    QVBoxLayout,
)

from logic_cad.core.pages.page_layout_meta import read_page_meta
from logic_cad.ui.dialogs.page_import_dialog import run_page_import_dialog
from logic_cad.ui.dialogs.page_ref_reorder_dialog import run_page_ref_reorder_dialog

if TYPE_CHECKING:
    from logic_cad.ui.main_window.window import MainWindow


PAGE_NAME_LABEL = "レイアウト名（CADタブ名）"
PAGE_DESC_LABEL = "説明（目次・枠に表示）"
PAGE_REV_LABEL = "改訂番号"


def _add_page_meta_rows(
    form: QFormLayout,
    *,
    name_editor: QLineEdit,
    desc_editor: QLineEdit,
    rev_editor: QLineEdit,
) -> None:
    """Add page metadata rows in canonical order.

    Args:
        form: Target form layout.
        name_editor: Editor for layout/page name.
        desc_editor: Editor for page description.
        rev_editor: Editor for page revision.
    """
    form.addRow(PAGE_NAME_LABEL, name_editor)
    form.addRow(PAGE_DESC_LABEL, desc_editor)
    form.addRow(PAGE_REV_LABEL, rev_editor)


def run_import_pages_dialog(win: MainWindow) -> None:
    """Open ``別ファイルからページを取り込み`` modal for *win*."""
    run_page_import_dialog(win)


def on_page_tab_bar_context(win: MainWindow, pos: QPoint) -> None:
    tab_bar = win._page_tabs.tabBar()
    idx = tab_bar.tabAt(pos)
    if idx < 0 or win._page_tabs.tabText(idx) != "ページ":
        return
    menu = QMenu(win)
    menu.addAction("ページを追加…", win._show_add_page_dialog)
    menu.addAction("別ファイルからページを取り込み…", lambda: run_import_pages_dialog(win))
    menu.addAction(
        "現在のページのプロパティ…",
        lambda: win._on_page_properties(win._diagram.current_layout_name),
    )
    menu.addAction("目次を再生成", win._regenerate_toc)
    menu.addAction("ページ跨ぎリンクの順序…", lambda: run_page_ref_reorder_dialog(win))
    menu.exec(tab_bar.mapToGlobal(pos))


def show_add_page_dialog(win: MainWindow) -> None:
    dlg = QDialog(win)
    dlg.setWindowTitle("ページを追加")
    form = QFormLayout()
    ed_name = QLineEdit()
    ed_rev = QLineEdit("0")
    ed_desc = QLineEdit()
    _add_page_meta_rows(
        form,
        name_editor=ed_name,
        desc_editor=ed_desc,
        rev_editor=ed_rev,
    )
    layout = QVBoxLayout(dlg)
    layout.addLayout(form)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    layout.addWidget(buttons)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return
    name = ed_name.text().strip()
    if not name:
        return
    rev = ed_rev.text().strip() or "0"
    try:
        with win._diagram.begin("add_page"):
            win._diagram.add_page(name)
            win._diagram.set_page_metadata(name, description=ed_desc.text(), revision=rev)
    except Exception as ex:
        QMessageBox.warning(win, "ページ", str(ex))
        return
    win._refresh_scene()


def on_duplicate_page(win: MainWindow, source_name: str) -> None:
    from logic_cad.core.pages.page_order import validate_paper_layout_name

    default = win._diagram.layouts.suggest_next_layout_name()
    name, ok = QInputDialog.getText(
        win,
        "ページを複製",
        "新しいレイアウト名:",
        text=default,
    )
    if not ok:
        return
    dest = name.strip()
    if not dest:
        return
    try:
        validate_paper_layout_name(dest)
    except ValueError as ex:
        QMessageBox.warning(win, "ページ", str(ex))
        return
    try:
        with win._diagram.begin("duplicate_page"):
            win._diagram.duplicate_page(source_name, dest)
    except Exception as ex:
        QMessageBox.warning(win, "ページ", str(ex))
        return
    win._diagram.set_current_page(dest)
    win._scene.set_diagram(win._diagram)
    win._page_bar.sync_from_diagram()
    win._props.clear_selection()
    win._refresh_scene()


def on_delete_page(win: MainWindow, name: str) -> None:
    ret = QMessageBox.question(
        win,
        "ページの削除",
        f"ページ「{name}」を削除しますか？\n\n"
        "このレイアウト上のシンボル・配線はすべて失われます。\n"
        "他のページからこのページへのページ跨ぎリンクも削除されます。",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if ret != QMessageBox.StandardButton.Yes:
        return
    try:
        with win._diagram.begin("delete_page"):
            win._diagram.delete_page(name)
    except ValueError as ex:
        QMessageBox.warning(win, "ページ", str(ex))
        return
    win._scene.set_diagram(win._diagram)
    win._props.clear_selection()
    win._refresh_scene()


def on_page_properties(win: MainWindow, layout_name: str) -> None:
    meta = read_page_meta(win._diagram.doc, layout_name)
    dlg = QDialog(win)
    dlg.setWindowTitle(f"ページのプロパティ — {layout_name}")
    layout = QVBoxLayout(dlg)
    form = QFormLayout()
    ed_name = QLineEdit(layout_name)
    ed_desc = QLineEdit(meta.get("page_desc", ""))
    ed_rev = QLineEdit(meta.get("page_rev", ""))
    _add_page_meta_rows(
        form,
        name_editor=ed_name,
        desc_editor=ed_desc,
        rev_editor=ed_rev,
    )
    layout.addLayout(form)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    layout.addWidget(buttons)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return
    new_name = ed_name.text().strip()
    if not new_name:
        QMessageBox.warning(win, "ページ", "レイアウト名が空です。")
        return
    try:
        with win._diagram.begin("page_properties"):
            if new_name != layout_name:
                win._diagram.rename_page(layout_name, new_name)
            win._diagram.set_page_metadata(
                new_name,
                description=ed_desc.text(),
                revision=ed_rev.text(),
            )
    except Exception as ex:
        QMessageBox.warning(win, "ページ", str(ex))
        return
    win._refresh_scene()


def regenerate_toc(win: MainWindow) -> None:
    try:
        with win._diagram.begin("toc"):
            win._diagram.regenerate_toc()
    except Exception as ex:
        QMessageBox.warning(win, "目次", str(ex))
        return
    win._refresh_scene()


def on_page_change(win: MainWindow, name: str) -> None:
    win._diagram.set_current_page(name)
    win._scene.set_diagram(win._diagram)
    win._props.clear_selection()
    center_view_on_current_page_content(win, prefer_page_refs=False)


def navigate_to_page_link(win: MainWindow, page_name: str, focus_peer_uid: str | None = None) -> None:
    if page_name not in win._diagram.list_pages():
        return
    win._diagram.set_current_page(page_name)
    win._scene.set_diagram(win._diagram)
    win._page_bar.sync_from_diagram()
    win._props.clear_selection()

    def _go() -> None:
        from logic_cad.ui.items.symbol_item import SymbolItem

        fp = (focus_peer_uid or "").strip()
        if fp:
            target: QRectF | None = None
            for it in win._scene.items():
                if isinstance(it, SymbolItem) and it.symbol_uid == fp:
                    target = it.sceneBoundingRect()
                    break
            if target is not None and not target.isEmpty() and target.isValid():
                br = target.adjusted(-10.0, -10.0, 10.0, 10.0)
                win._view.centerOn(br.center())
                return
        center_view_on_current_page_content(win, prefer_page_refs=True)

    QTimer.singleShot(0, _go)


def navigate_to_inpage_peer(win: MainWindow, peer_uid: str) -> None:
    """Pan the view so the INPAGE_REF partner (*peer_uid*) is visible on the current page."""

    def _go() -> None:
        from logic_cad.ui.items.symbol_item import SymbolItem

        if not peer_uid.strip():
            return
        target: QRectF | None = None
        for it in win._scene.items():
            if isinstance(it, SymbolItem) and it.symbol_uid == peer_uid:
                target = it.sceneBoundingRect()
                break
        if target is None or target.isEmpty() or not target.isValid():
            center_view_on_current_page_content(win, prefer_page_refs=False)
            return
        br = target.adjusted(-10.0, -10.0, 10.0, 10.0)
        win._view.centerOn(br.center())

    QTimer.singleShot(0, _go)


def center_view_on_current_page_content(win: MainWindow, *, prefer_page_refs: bool = False) -> None:
    """Keep zoom; pan so content is centered (PAGE_REF-only rect when jumping via link)."""

    def _go() -> None:
        from logic_cad.ui.items.symbol_item import SymbolItem

        br = win._scene.itemsBoundingRect()
        if prefer_page_refs:
            rects: list[QRectF] = []
            for it in win._scene.items():
                if isinstance(it, SymbolItem) and it.entity_type == "PAGE_REF":
                    rects.append(it.sceneBoundingRect())
            if rects:
                u = rects[0]
                for r in rects[1:]:
                    u = u.united(r)
                br = u
        if br.isEmpty() or not br.isValid():
            br = QRectF(0, -A4_LANDSCAPE_HEIGHT_MM, A4_LANDSCAPE_WIDTH_MM, A4_LANDSCAPE_HEIGHT_MM)
        else:
            br = br.adjusted(-10.0, -10.0, 10.0, 10.0)
        win._view.centerOn(br.center())

    QTimer.singleShot(0, _go)
