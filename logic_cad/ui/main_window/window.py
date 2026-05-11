"""Main window: compose scene, view, panels; delegate actions to submodules."""

from __future__ import annotations

import logging
import math
from pathlib import Path

from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence, QShortcut, QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGraphicsEllipseItem,
    QLabel,
    QMainWindow,
    QMenu,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.core.model.constants import ENTITY_TYPE_USER_LINE
from logic_cad.core.model.user_sketch_layers import (
    normalize_user_sketch_linetype,
    user_sketch_display_linetype_for_entity,
)
from logic_cad.core.model.xdata import get_type
from logic_cad.core.services.layout_service import (
    apply_frame_template_from_path,
    reload_symbol_library,
    validate_frame_template_path,
)
from logic_cad.core.undo.history import find_entity_by_uid
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
from logic_cad.ui.panels.block_edit_panel import BlockEditPanel
from logic_cad.ui.symbol_block_editor import SymbolBlockEditScene, SymbolBlockEditView
from logic_cad.ui.symbol_block_editor.scene import (
    ITEM_KIND_ATTDEF,
    ITEM_KIND_BLOCK_MTEXT,
    ITEM_KIND_BLOCK_TEXT,
    ITEM_KIND_GEOM,
    ITEM_KIND_PORT,
    PORT_LAYER_TAKEN_MESSAGE,
)
from logic_cad.ui.scene import DiagramScene
from logic_cad.ui.dialog_helpers import dialog_exec_accepted, question_yes_no, raise_modeless
from logic_cad.ui.layer_lineweight_dialog import LayerLineweightDialog
from logic_cad.ui.styles import APP_STYLESHEET
from logic_cad.ui.toast import show_toast
from logic_cad.ui.views.diagram_view import DiagramView
from logic_cad.ui.app_user_settings import AppUserSettings, load_app_user_settings, save_app_user_settings
from logic_cad.ui.panels.symbol_library_dialog import SymbolLibraryDialog
from logic_cad.ui.panels.log_window_dialog import LogWindowDialog
from logic_cad.ui.user_settings_dialog import run_user_settings_dialog
from logic_cad.ui.find_replace_dialog import FindReplaceDialog
from logic_cad.ui.items.user_geometry_items import UserArcItem, UserCircleItem, UserLineItem

_TEMPLATE_VALIDATION_LOGGER = logging.getLogger("logic_cad.validation.template")

class MainWindow(QMainWindow):
    _page_tabs: object
    _center_stack: QStackedWidget
    _block_canvas_stack: QStackedWidget
    _block_panel: BlockEditPanel
    _block_scene: SymbolBlockEditScene
    _block_view: SymbolBlockEditView
    _sketch_tools_widget: QWidget

    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet(APP_STYLESHEET)
        self._diagram = LogicDiagram.new()

        _tb = create_wire_sketch_tool_buttons(self)
        self._btn_auto_wire = _tb.auto_wire
        self._btn_manual_wire = _tb.manual_wire
        self._sketch_tools_widget = _tb.sketch_tools_widget
        self._btn_sk_line = _tb.sk_line
        self._btn_sk_circle = _tb.sk_circle
        self._btn_sk_arc = _tb.sk_arc
        self._btn_sk_cloud = _tb.sk_cloud
        self._btn_sk_text = _tb.sk_text

        self._scene = DiagramScene(self._diagram)
        self._tool_bridge = WireSketchToolBridge(
            self._scene,
            self._btn_auto_wire,
            self._btn_manual_wire,
            self._btn_sk_line,
            self._btn_sk_circle,
            self._btn_sk_arc,
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

        self._tool_bridge.connect_toolbar_signals()

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

        self._block_panel = BlockEditPanel(
            lambda: self._diagram,
            on_applied=self._after_block_edit_applied,
            notify=lambda msg: show_toast(msg, parent_window=self),
        )
        self._block_scene = SymbolBlockEditScene(
            lambda: self._block_panel.session(),
            self._block_panel.request_port_layer_interactive,
            self._block_panel.sketch_line_linetype,
        )
        self._block_view = SymbolBlockEditView(self._block_scene)
        self._block_view.set_escape_callback(self._block_panel.handle_escape_key)
        self._block_scene.status_message.connect(self._on_block_edit_status_message)
        self._block_panel.attach_scene(self._block_scene)
        self._block_scene.selectionChanged.connect(self._on_block_selection_changed)
        self._block_panel.session_changed.connect(self._on_block_edit_session_changed)
        self._center_stack = QStackedWidget()
        self._center_stack.addWidget(self._view)
        self._block_empty_hint = QWidget()
        _bel = QVBoxLayout(self._block_empty_hint)
        _bel.addStretch()
        _bh = QLabel("左の一覧でブロックを選択すると、ここに編集キャンバスが表示されます。")
        _bh.setWordWrap(True)
        _bh.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _bel.addWidget(_bh)
        _bel.addStretch()
        self._block_editor_page = QWidget()
        _bcl = QVBoxLayout(self._block_editor_page)
        _bcl.setContentsMargins(0, 0, 0, 0)
        _bcl.setSpacing(4)
        _bcl.addWidget(self._block_panel.tools_widget())
        _bcl.addWidget(self._block_view, 1)
        self._block_canvas_stack = QStackedWidget()
        self._block_canvas_stack.addWidget(self._block_empty_hint)
        self._block_canvas_stack.addWidget(self._block_editor_page)
        self._center_stack.addWidget(self._block_canvas_stack)
        self._last_tab_index = 0

        self._palette = PalettePanel()
        self._refresh_palette()
        self._page_bar = PagePanel(lambda: self._diagram, self._on_page_change)
        self._page_bar.propertiesRequested.connect(self._on_page_properties)
        self._page_bar.deletePageRequested.connect(self._on_delete_page)
        self._page_bar.duplicatePageRequested.connect(self._on_duplicate_page)
        self._page_bar.addPageRequested.connect(self._show_add_page_dialog)
        self._page_bar.regenerateTocRequested.connect(self._regenerate_toc)
        self._page_bar.importPagesFromForeignRequested.connect(self._on_import_pages_from_foreign)
        self._props = PropertyPanel(
            lambda: self._diagram,
            self._refresh_scene,
            on_align_selected=self._scene.request_align_selected,
            get_block_edit_session=lambda: self._block_panel.session(),
            on_block_scratch_applied=self._on_block_scratch_property_applied,
        )
        self._scene.set_after_delete_callback(self._props.clear_selection)
        self._props.setMinimumWidth(200)
        self._symbol_clipboard = None
        self._block_edit_entity_clipboard: bytes | None = None
        self._symbol_library_dialog = None
        self._manual_dialog = None
        self._log_dialog: LogWindowDialog | None = None
        self._find_dialog: FindReplaceDialog | None = None

        sc_find_next = QShortcut(QKeySequence("F3"), self)
        sc_find_next.setContext(Qt.ShortcutContext.WindowShortcut)
        sc_find_next.activated.connect(self._on_find_f3_global)
        sc_find_prev = QShortcut(QKeySequence("Shift+F3"), self)
        sc_find_prev.setContext(Qt.ShortcutContext.WindowShortcut)
        sc_find_prev.activated.connect(self._on_find_shift_f3_global)

        self._shortcut_block_esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self._shortcut_block_esc.setContext(Qt.ShortcutContext.WindowShortcut)
        self._shortcut_block_esc.activated.connect(self._on_block_escape_key)

        self.setCentralWidget(layout.build_central_widget(self))
        self._update_block_escape_shortcut_enabled()

        self._status_cursor = QLabel("—")
        self._status_cursor.setObjectName("statusCursorCoords")
        _sb = QStatusBar()
        _sb.addPermanentWidget(self._status_cursor)
        self.setStatusBar(_sb)
        self._view.cursor_dxf_mm_changed.connect(self._on_main_cursor_dxf_mm)
        self._block_view.cursor_dxf_mm_changed.connect(self._on_block_cursor_dxf_mm)

        menus.build_file_edit_menus(self)
        menus.build_project_settings_menu(self)
        menus.build_template_menu(self)
        menus.build_view_menu(self)
        self._page_bar.sync_from_diagram()
        document_actions.update_window_title(self)

    def _on_block_scratch_property_applied(self) -> None:
        self._block_scene.refresh_from_session()
        QTimer.singleShot(0, self._on_block_selection_changed)

    def _sync_block_editor_canvas(self) -> None:
        if self._page_tabs.currentIndex() != 2:
            return
        if self._block_panel.session() is not None:
            self._block_canvas_stack.setCurrentIndex(1)
        else:
            self._block_canvas_stack.setCurrentIndex(0)
            self._block_panel.clear_block_list_selection()

    def _on_block_edit_session_changed(self) -> None:
        self._sync_block_editor_canvas()
        self._update_window_title()
        if self._page_tabs.currentIndex() == 2:
            QTimer.singleShot(0, self._fit_block_initial_view)

    def _fit_block_initial_view(self) -> None:
        if self._page_tabs.currentIndex() != 2:
            return
        self._block_view.fit_initial_view()

    def _on_block_edit_status_message(self, message: str) -> None:
        """Block-edit feedback: toast for port conflict; other hints on the status bar."""
        if message == PORT_LAYER_TAKEN_MESSAGE:
            show_toast(message, parent_window=self)
            return
        sb = self.statusBar()
        if sb is not None:
            sb.showMessage(message, 3000)

    def _on_main_cursor_dxf_mm(self, dxf: object) -> None:
        """Forward main diagram cursor DXF coords when not on the block tab."""
        if self._page_tabs.currentIndex() == 2:
            return
        self._on_cursor_dxf_mm(dxf)

    def _on_block_cursor_dxf_mm(self, dxf: object) -> None:
        """Forward block canvas cursor DXF coords only on the block tab."""
        if self._page_tabs.currentIndex() != 2:
            return
        self._on_cursor_dxf_mm(dxf)

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
            f"次の線種: {label}（{lt}）。右クリックで変更。円弧ツールも同じ線種を使用。\n"
            "配置後はプロパティでも変更可。"
        )
        self._btn_sk_arc.setToolTip(
            "円弧ツール: 開始→弧上の点→終了の3点（グリッド）。\n"
            f"線種は直線ツールと共通: {label}（{lt}）。直線ボタンを右クリックで変更。"
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
        if self._block_panel.session() is not None:
            if not self._block_panel.request_end_session_for_nav():
                event.ignore()
                return
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

    def _after_block_edit_applied(self) -> None:
        self._diagram.rebuild_index()
        self._refresh_palette()
        self._refresh_scene()

    def _on_block_escape_key(self) -> None:
        if self._page_tabs.currentIndex() != 2:
            return
        if QApplication.activeModalWidget() is not None:
            return
        self._block_panel.handle_escape_key()

    def _update_block_escape_shortcut_enabled(self) -> None:
        """Enable window-level Esc only on the block-edit tab.

        A ``WindowShortcut`` on Escape would otherwise consume the key on every tab,
        preventing :class:`DiagramView` from clearing wire/sketch previews and selection.
        """

        self._shortcut_block_esc.setEnabled(self._page_tabs.currentIndex() == 2)

    def _on_main_tab_changed(self, index: int) -> None:
        prev = self._last_tab_index
        if prev == 2 and index != 2:
            if not self._block_panel.request_end_session_for_nav():
                self._page_tabs.blockSignals(True)
                self._page_tabs.setCurrentIndex(2)
                self._page_tabs.blockSignals(False)
                return
        self._last_tab_index = index
        self._on_cursor_dxf_mm(None)
        if index == 2:
            self._scene.clearSelection()
            self._props.clear_selection()
            self._center_stack.setCurrentIndex(1)
            self._block_panel.refresh_block_list()
            self._block_scene.refresh_from_session()
            self._sync_block_editor_canvas()
            self._fit_block_initial_view()
            self._block_view.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        else:
            self._block_scene.clearSelection()
            self._center_stack.setCurrentIndex(0)
            self._view.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
            QTimer.singleShot(0, self._on_selection_changed)
        self._update_window_title()
        self._update_block_escape_shortcut_enabled()

    def _on_page_tab_bar_context(self, pos) -> None:
        page_actions.on_page_tab_bar_context(self, pos)

    def _refresh_scene(self) -> None:
        self._scene.rebuild()
        self._page_bar.sync_from_diagram()
        self._update_window_title()

    def _refresh_palette(self) -> None:
        self._palette.refresh_from_document(self._diagram.doc)

    def _apply_frame_template(self) -> None:
        if not self._block_panel.request_end_session_for_nav():
            return
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "図枠テンプレート DXF を選択",
            "",
            "DXF (*.dxf);;All Files (*)",
        )
        if not path_str:
            return
        path = Path(path_str)
        if not question_yes_no(
            self,
            "図枠テンプレートを適用",
            f"選択したファイルの図枠（ブロック定義と各用紙ページの図枠）に置き換えます。\n\n{path.name}\n\n続行しますか？",
        ):
            return

        try:
            issues = validate_frame_template_path(path)
        except Exception as ex:
            show_toast(
                f"図枠テンプレートの検証に失敗しました: {ex}",
                parent_window=self,
                duration=6000,
            )
            return
        if issues:
            for issue in issues:
                _TEMPLATE_VALIDATION_LOGGER.warning(issue)
            excerpt = "\n".join(f"- {msg}" for msg in issues[:8])
            if len(issues) > 8:
                excerpt += f"\n... 他 {len(issues) - 8} 件"
            if not question_yes_no(
                self,
                "図枠テンプレート検証",
                "テンプレート検証で問題が見つかりました。\n"
                "適用すると既存図面に不整合を持ち込む可能性があります。\n\n"
                f"{excerpt}\n\n"
                "警告を許容して続行しますか？",
            ):
                show_toast("図枠テンプレート適用をキャンセルしました。", parent_window=self)
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
        if not self._block_panel.request_end_session_for_nav():
            return
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "シンボルライブラリ DXF を選択",
            "",
            "DXF (*.dxf);;All Files (*)",
        )
        if not path_str:
            return
        path = Path(path_str)
        if not question_yes_no(
            self,
            "シンボルライブラリを読み込み",
            f"選択した DXF からブロック定義を取り込み直します。\n"
            f"同名ブロックはライブラリの内容で置き換わります。\n\n{path.name}\n\n続行しますか？",
        ):
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
        raise_modeless(self._symbol_library_dialog)

    def _show_manual(self) -> None:
        if self._manual_dialog is None:
            self._manual_dialog = ManualDialog(parent=self)
        self._manual_dialog.refresh()
        raise_modeless(self._manual_dialog)

    def _show_log_window(self) -> None:
        if self._log_dialog is None:
            self._log_dialog = LogWindowDialog(parent=self)
        raise_modeless(self._log_dialog)

    def _reload_symbol_library(self) -> None:
        if not self._block_panel.request_end_session_for_nav():
            return
        if not question_yes_no(
            self,
            "シンボルライブラリを再読み込み",
            "logic_cad/assets/symbol_library.dxf からブロック定義を取り込み直します。\n"
            "同名ブロックはライブラリの内容で置き換わります。続行しますか？",
        ):
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
        if dialog_exec_accepted(dlg) and dlg.changed():
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
        raise_modeless(self._ensure_find_dialog())

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

    def _on_import_pages_from_foreign(self) -> None:
        page_actions.run_import_pages_dialog(self)

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

    def _navigate_to_page_link(self, page_name: str, focus_peer_uid: str | None = None) -> None:
        page_actions.navigate_to_page_link(self, page_name, focus_peer_uid)

    def _navigate_to_inpage_peer(self, peer_uid: str) -> None:
        page_actions.navigate_to_inpage_peer(self, peer_uid)

    def _on_block_selection_changed(self) -> None:
        if self._page_tabs.currentIndex() != 2:
            return
        sess = self._block_panel.session()
        if sess is None:
            self._props.clear_selection()
            return
        blk = sess.scratch_block()
        if blk is None:
            self._props.clear_selection()
            return
        sel = self._block_scene.selectedItems()
        if len(sel) != 1:
            if not sel:
                self._props.clear_selection()
            else:
                self._props.show_multi(len(sel))
            return
        it = sel[0]
        bname = sess.scratch_definition_name()
        if isinstance(it, UserLineItem):
            ent = find_entity_by_uid(sess.scratch_doc, it.sketch_uid)
            if ent is None:
                self._props.clear_selection()
                return
            lt = user_sketch_display_linetype_for_entity(ent)
            det = (
                f"UUID: {it.sketch_uid}\n"
                f"表示線種: {lt}\n"
                f"{MainWindow._block_geom_property_detail(ent)}"
            )
            self._props.show_block_edit_geom(
                block_name=bname,
                handle=str(ent.dxf.handle),
                dxftype="USER_LINE",
                layer=str(ent.dxf.layer),
                detail=det,
                editable_linetype=lt,
                linetype_subject="user_sketch",
                sketch_uid=it.sketch_uid,
            )
            return

        if isinstance(it, UserCircleItem):
            ent = find_entity_by_uid(sess.scratch_doc, it.sketch_uid)
            if ent is None:
                self._props.clear_selection()
                return
            lt = user_sketch_display_linetype_for_entity(ent)
            det = (
                f"タイプ: USER_CIRCLE\n"
                f"UUID: {it.sketch_uid}\n"
                f"表示線種: {lt}\n"
                f"{MainWindow._block_geom_property_detail(ent)}"
            )
            self._props.show_block_edit_geom(
                block_name=bname,
                handle=str(ent.dxf.handle),
                dxftype="USER_CIRCLE",
                layer=str(ent.dxf.layer),
                detail=det,
                editable_linetype=lt,
                linetype_subject="user_sketch",
                sketch_uid=it.sketch_uid,
            )
            return

        if isinstance(it, UserArcItem):
            ent = find_entity_by_uid(sess.scratch_doc, it.sketch_uid)
            if ent is None:
                self._props.clear_selection()
                return
            lt = user_sketch_display_linetype_for_entity(ent)
            det = (
                f"タイプ: USER_ARC\n"
                f"UUID: {it.sketch_uid}\n"
                f"表示線種: {lt}\n"
                f"{MainWindow._block_geom_property_detail(ent)}"
            )
            self._props.show_block_edit_geom(
                block_name=bname,
                handle=str(ent.dxf.handle),
                dxftype="USER_ARC",
                layer=str(ent.dxf.layer),
                detail=det,
                editable_linetype=lt,
                linetype_subject="user_sketch",
                sketch_uid=it.sketch_uid,
            )
            return

        h = str(it.data(0) or "")
        kind = str(it.data(1) or "")
        ent = None
        for e in blk:
            if str(getattr(e.dxf, "handle", "") or "") == h:
                ent = e
                break
        if ent is None:
            self._props.clear_selection()
            return
        if kind == ITEM_KIND_PORT and isinstance(it, QGraphicsEllipseItem):
            layer = str(ent.dxf.layer)
            self._props.show_block_edit_port(
                block_name=bname,
                handle=h,
                layer=layer,
                x_mm=float(ent.dxf.location.x),
                y_mm=float(ent.dxf.location.y),
            )
            return
        if kind == ITEM_KIND_ATTDEF and ent.dxftype() == "ATTDEF":
            ha = int(getattr(ent.dxf, "halign", 0) or 0)
            self._props.show_block_edit_attdef(
                block_name=bname,
                handle=h,
                tag=str(ent.dxf.tag),
                default_text=str(ent.dxf.text or ""),
                halign=ha,
                height_mm=float(getattr(ent.dxf, "height", 2.5) or 2.5),
            )
            return
        if kind == ITEM_KIND_BLOCK_TEXT and ent.dxftype() == "TEXT":
            ha = int(getattr(ent.dxf, "halign", 0) or 0)
            self._props.show_block_edit_scratch_text(
                block_name=bname,
                handle=h,
                is_mtext=False,
                text=str(ent.dxf.text or ""),
                height_mm=float(getattr(ent.dxf, "height", 2.5) or 2.5),
                rotation_deg=float(getattr(ent.dxf, "rotation", 0.0) or 0.0),
                halign=ha,
            )
            return
        if kind == ITEM_KIND_BLOCK_MTEXT and ent.dxftype() == "MTEXT":
            try:
                body = ent.plain_text()
            except Exception:
                body = str(getattr(ent.dxf, "text", "") or "")
            if isinstance(body, list):
                body = "\n".join(str(x) for x in body)
            self._props.show_block_edit_scratch_text(
                block_name=bname,
                handle=h,
                is_mtext=True,
                text=str(body),
                height_mm=float(getattr(ent.dxf, "char_height", 2.5) or 2.5),
                rotation_deg=float(getattr(ent.dxf, "rotation", 0.0) or 0.0),
                width_mm=float(getattr(ent.dxf, "width", 0.0) or 0.0),
                attachment_point=int(getattr(ent.dxf, "attachment_point", 1) or 1),
            )
            return
        if kind == ITEM_KIND_GEOM:
            detail = MainWindow._block_geom_property_detail(ent)
            lt_val: str | None = None
            lt_subj = ""
            sk_uid: str | None = None
            if ent.dxftype() == "LINE" and get_type(ent) != ENTITY_TYPE_USER_LINE:
                lt_val = MainWindow._block_native_line_display_linetype(ent)
                lt_subj = "native_line"
            self._props.show_block_edit_geom(
                block_name=bname,
                handle=h,
                dxftype=str(ent.dxftype()),
                layer=str(ent.dxf.layer),
                detail=detail,
                editable_linetype=lt_val,
                linetype_subject=lt_subj,
                sketch_uid=sk_uid,
            )
            return
        self._props.clear_selection()

    @staticmethod
    def _block_native_line_display_linetype(ent: object) -> str:
        lt_raw = str(getattr(ent.dxf, "linetype", "") or "").strip()
        if not lt_raw or lt_raw.upper() in ("BYLAYER", "BYBLOCK"):
            return "CONTINUOUS"
        return normalize_user_sketch_linetype(lt_raw)

    @staticmethod
    def _block_geom_property_detail(ent: object) -> str:
        et = ent.dxftype()  # type: ignore[union-attr]
        if et == "LINE":
            x0, y0 = float(ent.dxf.start.x), float(ent.dxf.start.y)  # type: ignore[union-attr]
            x1, y1 = float(ent.dxf.end.x), float(ent.dxf.end.y)
            return f"長さ {math.hypot(x1 - x0, y1 - y0):.3f} mm"
        if et == "CIRCLE":
            return f"半径 {float(ent.dxf.radius):.3f} mm"  # type: ignore[union-attr]
        if et == "LWPOLYLINE":
            rows = list(ent.get_points("xy"))  # type: ignore[union-attr]
            closed = bool(ent.closed)  # type: ignore[union-attr]
            cl = "閉じた" if closed else "開いた"
            return f"頂点数 {len(rows)}（{cl}）"
        if et == "ARC":
            return f"半径 {float(ent.dxf.radius):.3f} mm"  # type: ignore[union-attr]
        return "—"

    def _on_selection_changed(self) -> None:
        selection_props.on_selection_changed(self)
