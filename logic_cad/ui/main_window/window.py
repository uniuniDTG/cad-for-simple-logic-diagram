"""Main window: compose scene, view, panels; delegate actions to submodules."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence, QShortcut, QShowEvent
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QLabel, QMainWindow, QMenu, QMessageBox, QStatusBar

from logic_cad.core.logic_diagram import LogicDiagram
from . import (
    clipboard_actions,
    document_actions,
    edit_actions,
    layout,
    menus,
    page_actions,
    palette_drop,
    pdf_export,
    selection_props,
)
from .tool_bridge import WireSketchToolBridge
from logic_cad.ui.panels.manual_dialog import ManualDialog
from logic_cad.ui.panels.page_panel import PagePanel
from logic_cad.ui.panels.palette_panel import PalettePanel
from logic_cad.ui.panels.property_panel import PropertyPanel
from logic_cad.ui.panels.wire_sketch_tool_buttons import create_wire_sketch_tool_buttons
from logic_cad.ui.scene import DiagramScene
from logic_cad.ui.layer_lineweight_dialog import LayerLineweightDialog
from logic_cad.ui.styles import APP_STYLESHEET
from logic_cad.ui.toast import show_toast
from logic_cad.ui.views.diagram_view import DiagramView
from logic_cad.ui.app_user_settings import AppUserSettings, load_app_user_settings, save_app_user_settings
from logic_cad.ui.panels.symbol_library_dialog import SymbolLibraryDialog
from logic_cad.ui.user_settings_dialog import run_user_settings_dialog
from logic_cad.ui.find_replace_dialog import FindReplaceDialog
from logic_cad.core.services.layout_service import apply_frame_template_from_path
from logic_cad.core.services.layout_service import reload_symbol_library

class MainWindow(QMainWindow):
    _page_tabs: object

    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet(APP_STYLESHEET)
        self._diagram = LogicDiagram.new()

        _tb = create_wire_sketch_tool_buttons(self)
        self._btn_auto_wire = _tb.auto_wire
        self._btn_manual_wire = _tb.manual_wire
        self._btn_sk_line = _tb.sk_line
        self._btn_sk_circle = _tb.sk_circle
        self._btn_sk_cloud = _tb.sk_cloud
        self._btn_sk_text = _tb.sk_text

        self._scene = DiagramScene(self._diagram)
        self._tool_bridge = WireSketchToolBridge(
            self._scene,
            self._btn_auto_wire,
            self._btn_manual_wire,
            self._btn_sk_line,
            self._btn_sk_circle,
            self._btn_sk_cloud,
            self._btn_sk_text,
        )
        self._scene.set_navigate_page_callback(self._navigate_to_page_link)
        self._scene.set_navigate_inpage_peer_callback(self._navigate_to_inpage_peer)
        self._scene.set_reroute_failed_callback(self._on_reroute_after_geometry_failed)
        self._scene.set_wire_error_callback(self._on_wire_error_message)
        self._scene.set_hit_wire_clear_tools_callback(self._tool_bridge.clear_wire_routing_tools)
        self._scene.set_clipboard_callbacks(self._copy_symbol_selection, self._paste_symbol_clipboard)
        self._scene.selectionChanged.connect(self._on_selection_changed)

        self._btn_auto_wire.toggled.connect(self._tool_bridge.on_auto_wire_toggled)
        self._btn_manual_wire.toggled.connect(self._tool_bridge.on_manual_wire_toggled)
        self._btn_sk_line.toggled.connect(self._tool_bridge.on_any_sketch_toggled)
        self._btn_sk_circle.toggled.connect(self._tool_bridge.on_any_sketch_toggled)
        self._btn_sk_cloud.toggled.connect(self._tool_bridge.on_any_sketch_toggled)
        self._btn_sk_text.toggled.connect(self._tool_bridge.on_any_sketch_toggled)

        self._btn_sk_line.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._btn_sk_line.customContextMenuRequested.connect(self._on_sk_line_linetype_menu)
        self._refresh_sk_line_button_tooltip()

        self._app_user_settings: AppUserSettings = load_app_user_settings()
        self._view = DiagramView()
        self._view.setScene(self._scene)
        self._view.apply_user_settings(self._app_user_settings)
        self._view.set_escape_clear_wire_tools_callback(self._tool_bridge.clear_wire_routing_tools)
        self._view.set_escape_clear_sketch_tools_callback(self._tool_bridge.uncheck_sketch_tools)
        self._view.setAcceptDrops(True)
        self._view.dragEnterEvent = lambda e: palette_drop.view_drag_enter(self, e)  # type: ignore[method-assign]
        self._view.dragMoveEvent = lambda e: palette_drop.view_drag_move(self, e)  # type: ignore[method-assign]
        self._view.dropEvent = lambda e: palette_drop.view_drop(self, e)  # type: ignore[method-assign]

        self._palette = PalettePanel()
        self._refresh_palette()
        self._page_bar = PagePanel(lambda: self._diagram, self._on_page_change)
        self._page_bar.propertiesRequested.connect(self._on_page_properties)
        self._page_bar.deletePageRequested.connect(self._on_delete_page)
        self._page_bar.duplicatePageRequested.connect(self._on_duplicate_page)
        self._page_bar.addPageRequested.connect(self._show_add_page_dialog)
        self._page_bar.regenerateTocRequested.connect(self._regenerate_toc)
        self._props = PropertyPanel(
            lambda: self._diagram,
            self._refresh_scene,
            on_align_selected=self._scene.request_align_selected,
        )
        self._scene.set_after_delete_callback(self._props.clear_selection)
        self._props.setMinimumWidth(200)
        self._symbol_clipboard = None
        self._symbol_library_dialog = None
        self._manual_dialog = None
        self._find_dialog: FindReplaceDialog | None = None

        sc_find_next = QShortcut(QKeySequence("F3"), self)
        sc_find_next.setContext(Qt.ShortcutContext.WindowShortcut)
        sc_find_next.activated.connect(self._on_find_f3_global)
        sc_find_prev = QShortcut(QKeySequence("Shift+F3"), self)
        sc_find_prev.setContext(Qt.ShortcutContext.WindowShortcut)
        sc_find_prev.activated.connect(self._on_find_shift_f3_global)

        self.setCentralWidget(layout.build_central_widget(self))

        self._status_cursor = QLabel("—")
        self._status_cursor.setObjectName("statusCursorCoords")
        _sb = QStatusBar()
        _sb.addPermanentWidget(self._status_cursor)
        self.setStatusBar(_sb)
        self._view.cursor_dxf_mm_changed.connect(self._on_cursor_dxf_mm)

        menus.build_file_edit_menus(self)
        menus.build_project_settings_menu(self)
        menus.build_template_menu(self)
        menus.build_view_menu(self)
        self._page_bar.sync_from_diagram()
        document_actions.update_window_title(self)

    def _on_cursor_dxf_mm(self, dxf: object) -> None:
        if dxf is None:
            self._status_cursor.setText("—")
            return
        x, y = dxf  # type: ignore[misc]
        self._status_cursor.setText(f"X: {float(x):.2f} mm  Y: {float(y):.2f} mm")

    def _update_window_title(self) -> None:
        document_actions.update_window_title(self)

    def _refresh_sk_line_button_tooltip(self) -> None:
        """Set the line sketch button tooltip to show the current default linetype.

        Returns:
            None
        """
        lt = self._scene.user_sketch_line_default_linetype()
        label = {"CONTINUOUS": "実線", "DASHED": "点線", "CENTER": "中心線"}.get(lt, lt)
        self._btn_sk_line.setToolTip(
            "直線ツール: 2点で描画（グリッド）。Shift で水平/垂直に拘束。\n"
            f"次の線種: {label}（{lt}）。右クリックで変更。配置後はプロパティでも変更可。"
        )

    def _on_sk_line_linetype_menu(self, pos: QPoint) -> None:
        """Show a context menu to pick CONTINUOUS / DASHED / CENTER for the next user line.

        Args:
            pos: Local position on the line tool button (from ``customContextMenuRequested``).
        """
        menu = QMenu(self)
        cur = self._scene.user_sketch_line_default_linetype()
        key_by_action: dict[QAction, str] = {}
        for key, title in (
            ("CONTINUOUS", "実線 (CONTINUOUS)"),
            ("DASHED", "点線 (DASHED)"),
            ("CENTER", "中心線 (CENTER)"),
        ):
            act = menu.addAction(title)
            act.setCheckable(True)
            act.setChecked(key == cur)
            key_by_action[act] = key
        chosen = menu.exec(self._btn_sk_line.mapToGlobal(pos))
        if chosen is not None and chosen in key_by_action:
            self._scene.set_user_sketch_line_default_linetype(key_by_action[chosen])
            self._refresh_sk_line_button_tooltip()

    def _prompt_save_if_dirty(self) -> bool:
        return document_actions.prompt_save_if_dirty(self)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._prompt_save_if_dirty():
            event.accept()
        else:
            event.ignore()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if getattr(self, "_first_show", True):
            self._first_show = False
            QTimer.singleShot(0, self._view.fit_a4_page)

    def _on_reroute_after_geometry_failed(self, disp_uuid: str) -> None:
        show_toast(
            f"{disp_uuid} 再配線できませんでした。シンボルを元の位置に戻しました。",
            parent_window=self,
            duration=8000,
        )

    def _on_wire_error_message(self, message: str) -> None:
        show_toast(message, parent_window=self, duration=8000)

    def _copy_symbol_selection(self) -> None:
        clipboard_actions.copy_symbol_selection(self)

    def _paste_symbol_clipboard(self) -> None:
        clipboard_actions.paste_symbol_clipboard(self)

    def _on_page_tab_bar_context(self, pos) -> None:
        page_actions.on_page_tab_bar_context(self, pos)

    def _refresh_scene(self) -> None:
        self._scene.rebuild()
        self._page_bar.sync_from_diagram()
        self._update_window_title()

    def _refresh_palette(self) -> None:
        self._palette.refresh_from_document(self._diagram.doc)

    def _apply_frame_template(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "図枠テンプレート DXF を選択",
            "",
            "DXF (*.dxf);;All Files (*)",
        )
        if not path_str:
            return
        path = Path(path_str)
        ret = QMessageBox.question(
            self,
            "図枠テンプレートを適用",
            f"選択したファイルの図枠（ブロック定義と各用紙ページの図枠）に置き換えます。\n\n{path.name}\n\n続行しますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return

        try:
            apply_frame_template_from_path(self._diagram.doc, path)
        except Exception as ex:
            show_toast(
                f"図枠テンプレートの適用に失敗しました: {ex}",
                parent_window=self,
                duration=6000,
            )
            return
        self._diagram.mark_modified()
        self._refresh_palette()
        if self._symbol_library_dialog is not None:
            self._symbol_library_dialog.refresh_from_document()
        self._refresh_scene()
        show_toast("図枠テンプレートを適用しました。", parent_window=self)

    def _load_symbol_library_from_dxf(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "シンボルライブラリ DXF を選択",
            "",
            "DXF (*.dxf);;All Files (*)",
        )
        if not path_str:
            return
        path = Path(path_str)
        ret = QMessageBox.question(
            self,
            "シンボルライブラリを読み込み",
            f"選択した DXF からブロック定義を取り込み直します。\n"
            f"同名ブロックはライブラリの内容で置き換わります。\n\n{path.name}\n\n続行しますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        try:
            reload_symbol_library(self._diagram.doc, path=path)
        except Exception as ex:
            show_toast(
                f"シンボルライブラリの再読み込みに失敗しました: {ex}",
                parent_window=self,
                duration=6000,
            )
            return
        self._diagram.mark_modified()
        self._refresh_palette()
        if self._symbol_library_dialog is not None:
            self._symbol_library_dialog.refresh_from_document()
        self._refresh_scene()
        show_toast(f"シンボルライブラリを読み込みました: {path.name}", parent_window=self)

    def _show_symbol_library(self) -> None:


        if self._symbol_library_dialog is None:
            self._symbol_library_dialog = SymbolLibraryDialog(lambda: self._diagram.doc, parent=self)
        self._symbol_library_dialog.refresh_from_document()
        self._symbol_library_dialog.show()
        self._symbol_library_dialog.raise_()
        self._symbol_library_dialog.activateWindow()

    def _show_manual(self) -> None:
        if self._manual_dialog is None:
            self._manual_dialog = ManualDialog(parent=self)
        self._manual_dialog.refresh()
        self._manual_dialog.show()
        self._manual_dialog.raise_()
        self._manual_dialog.activateWindow()

    def _reload_symbol_library(self) -> None:
        ret = QMessageBox.question(
            self,
            "シンボルライブラリを再読み込み",
            "logic_cad/assets/symbol_library.dxf からブロック定義を取り込み直します。\n"
            "同名ブロックはライブラリの内容で置き換わります。続行しますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return


        try:
            reload_symbol_library(self._diagram.doc)
        except Exception as ex:
            show_toast(
                f"シンボルライブラリの再読み込みに失敗しました: {ex}",
                parent_window=self,
                duration=6000,
            )
            return
        self._diagram.mark_modified()
        self._refresh_palette()
        if self._symbol_library_dialog is not None:
            self._symbol_library_dialog.refresh_from_document()
        self._refresh_scene()
        show_toast("シンボルライブラリを再読み込みしました。", parent_window=self)

    def _edit_layer_lineweight(self) -> None:
        dlg = LayerLineweightDialog(self._diagram, self)
        if dlg.exec() == dlg.DialogCode.Accepted and dlg.changed():
            self._update_window_title()
            self._refresh_scene()

    def _ensure_find_dialog(self) -> FindReplaceDialog:
        """Single modeless find panel; sync diagram after New/Open. Search state stays in memory only (not in DXF)."""
        if self._find_dialog is None:
            self._find_dialog = FindReplaceDialog(
                self, self._diagram, self._refresh_scene, mode="find", main_window=self
            )
        self._find_dialog.set_diagram(self._diagram)
        return self._find_dialog

    def _on_find_f3_global(self) -> None:
        """F3: next search when the main window (or embedded view) has focus; find panel may be hidden."""
        self._ensure_find_dialog().trigger_next_search()

    def _on_find_shift_f3_global(self) -> None:
        """Shift+F3: previous search when the find panel is hidden (main window shortcut)."""
        self._ensure_find_dialog().trigger_prev_search()

    def _show_find(self) -> None:
        """Open modeless find: jump to hits while keeping the canvas editable (Ctrl+F)."""
        dlg = self._ensure_find_dialog()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _show_replace(self) -> None:
        """Open find/replace for SYM/LABEL* and user annotation text."""
        dlg = FindReplaceDialog(self, self._diagram, self._refresh_scene, mode="replace")
        dlg.exec()

    def _new_doc(self) -> None:
        document_actions.new_document(self)

    def _open_doc(self) -> None:
        document_actions.open_document(self)

    def _save_doc(self) -> None:
        document_actions.save_document(self)

    def _save_as_doc(self) -> None:
        document_actions.save_document_as(self)

    def _export_pdf(self) -> None:
        pdf_export.run_export_pdf(self)

    def _drawing_properties(self) -> None:
        document_actions.drawing_properties(self)

    def _preferred_font_settings(self) -> None:
        document_actions.preferred_font_settings(self)

    def _user_settings(self) -> None:
        """Open application user settings (crosshair); persist on accept."""
        result = run_user_settings_dialog(self, self._app_user_settings)
        if result is None:
            return
        self._app_user_settings = result
        save_app_user_settings(self._app_user_settings)
        self._view.apply_user_settings(self._app_user_settings)

    def _undo(self) -> None:
        edit_actions.undo(self)

    def _redo(self) -> None:
        edit_actions.redo(self)

    def _delete_selection(self) -> None:
        edit_actions.delete_selection(self)

    def _delete_all_user_clouds(self) -> None:
        edit_actions.delete_all_user_clouds(self)

    def _show_add_page_dialog(self) -> None:
        page_actions.show_add_page_dialog(self)

    def _on_duplicate_page(self, source_name: str) -> None:
        page_actions.on_duplicate_page(self, source_name)

    def _on_delete_page(self, name: str) -> None:
        page_actions.on_delete_page(self, name)

    def _on_page_properties(self, layout_name: str) -> None:
        page_actions.on_page_properties(self, layout_name)

    def _regenerate_toc(self) -> None:
        page_actions.regenerate_toc(self)

    def _on_page_change(self, name: str) -> None:
        page_actions.on_page_change(self, name)

    def _navigate_to_page_link(self, page_name: str) -> None:
        page_actions.navigate_to_page_link(self, page_name)

    def _navigate_to_inpage_peer(self, peer_uid: str) -> None:
        page_actions.navigate_to_inpage_peer(self, peer_uid)

    def _on_selection_changed(self) -> None:
        selection_props.on_selection_changed(self)
