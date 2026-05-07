"""Left-tab controls for in-app symbol block (BEDIT-style) editing."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.core.model.constants import (
    BLOCK_EDIT_AUX_GRID_DEFAULT_PITCH_MM,
    BLOCK_EDIT_AUX_GRID_PITCH_OPTIONS_MM,
)
from logic_cad.core.model.user_sketch_layers import user_sketch_entity_linetype_for_display
from logic_cad.core.services.block_edit_helpers import (
    delete_block_definition_if_unused,
    duplicate_block_definition,
    make_port_layer_name,
    rename_block_definition,
)
from logic_cad.core.services.block_edit_session import BlockEditSession
from logic_cad.core.services.layout_service import list_palette_block_names

from logic_cad.ui.panels.block_sketch_tool_buttons import create_block_annotation_sketch_buttons
from logic_cad.ui.sketch_tool_icons import block_port_icon
from logic_cad.ui.symbol_block_editor import SymbolBlockEditScene

_SK_TOOL = QSize(24, 24)


class BlockEditPanel(QWidget):
    """West tab: block list only; canvas toolbar (see :meth:`tools_widget`) holds tools + apply."""

    session_changed = Signal()

    def __init__(
        self,
        get_diagram: Callable[[], LogicDiagram],
        *,
        on_applied: Callable[[], None],
        notify: Callable[[str], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("blockEditPanel")
        self._get_diagram = get_diagram
        self._on_applied = on_applied
        self._notify = notify
        self._session: BlockEditSession | None = None
        self._scene: SymbolBlockEditScene | None = None
        self._block_sk_line_linetype: str = "CONTINUOUS"
        self._aux_grid_pitch_mm: float = float(BLOCK_EDIT_AUX_GRID_DEFAULT_PITCH_MM)

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("ブロック一覧"))
        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._on_list_changed)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_block_list_context_menu)
        lay.addWidget(self._list, 1)

        self._tools_bar = self._make_tools_bar()

    def _make_tools_bar(self) -> QWidget:
        fr = QFrame()
        fr.setObjectName("blockEditToolsBar")
        outer = QVBoxLayout(fr)
        outer.setContentsMargins(6, 4, 6, 4)
        outer.setSpacing(6)

        row = QHBoxLayout()
        row.setSpacing(6)

        self._btn_tool_port = QPushButton(fr)
        self._btn_tool_port.setCheckable(True)
        self._btn_tool_port.setAutoDefault(False)
        self._btn_tool_port.setDefault(False)
        self._btn_tool_port.setObjectName("blockSketchToolPort")
        self._btn_tool_port.setIcon(block_port_icon())
        self._btn_tool_port.setIconSize(_SK_TOOL)
        self._btn_tool_port.setToolTip(
            "ポート（LD_PORT）: クリックで属性を決めて配置。グリッドにスナップ。配置ツール中はクリックが配置優先。"
        )
        self._btn_tool_port.setAccessibleName("ポート")

        self._ann_sk = create_block_annotation_sketch_buttons(fr)
        row.addWidget(self._btn_tool_port)
        row.addWidget(self._ann_sk.line)
        row.addWidget(self._ann_sk.circle)
        row.addWidget(self._ann_sk.text)
        self._chk_show_aux_grid = QCheckBox("補助スナップ", fr)
        self._chk_show_aux_grid.setChecked(False)
        self._refresh_aux_grid_tooltip()
        self._chk_show_aux_grid.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._chk_show_aux_grid.customContextMenuRequested.connect(self._on_aux_grid_context_menu)
        self._chk_show_aux_grid.stateChanged.connect(self._on_show_aux_grid_state_changed)
        row.addWidget(self._chk_show_aux_grid)
        row.addStretch()

        self._btn_apply = QPushButton("ブロック編集完了")
        self._btn_apply.setObjectName("blockApplyToMain")
        self._btn_apply.setToolTip("スクラッチの内容を本体の同名ブロック定義に上書きします。")
        self._btn_apply.clicked.connect(self._on_apply)
        row.addWidget(self._btn_apply)
        outer.addLayout(row)

        self._ann_sk.line.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._ann_sk.line.customContextMenuRequested.connect(self._on_block_sk_line_linetype_menu)
        self._refresh_block_sk_line_button_tooltip()

        self._placement_buttons: tuple[QPushButton, ...] = (
            self._btn_tool_port,
            self._ann_sk.line,
            self._ann_sk.circle,
            self._ann_sk.text,
        )
        self._btn_tool_port.toggled.connect(self._on_port_toggled)
        self._ann_sk.line.toggled.connect(self._on_sk_line_toggled)
        self._ann_sk.circle.toggled.connect(self._on_sk_circle_toggled)
        self._ann_sk.text.toggled.connect(self._on_sk_attdef_toggled)
        return fr

    def tools_widget(self) -> QWidget:
        return self._tools_bar

    def attach_scene(self, scene: SymbolBlockEditScene) -> None:
        self._scene = scene
        scene.set_auxiliary_snap_pitch_mm(self._aux_grid_pitch_mm)
        scene.set_auxiliary_grid_visible(self._chk_show_aux_grid.isChecked())

    def _on_show_aux_grid_state_changed(self, _state: int) -> None:
        if self._scene is not None:
            self._scene.set_auxiliary_snap_pitch_mm(self._aux_grid_pitch_mm)
            self._scene.set_auxiliary_grid_visible(self._chk_show_aux_grid.isChecked())

    def _refresh_aux_grid_tooltip(self) -> None:
        self._chk_show_aux_grid.setToolTip(
            f"補助グリッド表示を切り替えます（現在: {self._aux_grid_pitch_mm:g} mm）。"
            "オフ時はスナップも 1 mm 主グリッドです。"
            "右クリックで補助グリッド間隔を選択できます。"
        )

    def _on_aux_grid_context_menu(self, pos) -> None:
        menu = QMenu(self)
        pitch_by_action: dict[QAction, float] = {}
        for pitch in BLOCK_EDIT_AUX_GRID_PITCH_OPTIONS_MM:
            act = menu.addAction(f"{pitch:g} mm")
            act.setCheckable(True)
            act.setChecked(abs(self._aux_grid_pitch_mm - float(pitch)) <= 1e-12)
            pitch_by_action[act] = float(pitch)
        chosen = menu.exec(self._chk_show_aux_grid.mapToGlobal(pos))
        if chosen is None or chosen not in pitch_by_action:
            return
        next_pitch = pitch_by_action[chosen]
        if abs(self._aux_grid_pitch_mm - next_pitch) <= 1e-12:
            return
        self._aux_grid_pitch_mm = next_pitch
        self._refresh_aux_grid_tooltip()
        if self._scene is not None:
            self._scene.set_auxiliary_snap_pitch_mm(next_pitch)
            self._scene.set_auxiliary_grid_visible(self._chk_show_aux_grid.isChecked())

    def clear_block_list_selection(self) -> None:
        """Clear the list highlight without running :meth:`_on_list_changed` side effects."""

        self._list.blockSignals(True)
        self._list.clearSelection()
        self._list.setCurrentRow(-1)
        self._list.blockSignals(False)

    def current_list_block_name(self) -> str | None:
        it = self._list.currentItem()
        if it is None:
            return None
        name = str(it.text()).strip()
        return name if name else None

    def session(self) -> BlockEditSession | None:
        return self._session

    def request_port_layer_interactive(self) -> str | None:
        dlg = QDialog(self)
        dlg.setWindowTitle("ポート属性")
        form = QFormLayout(dlg)
        dir_c = QComboBox()
        dir_c.addItems(["IN", "OUT", "INOUT"])
        idx_s = QSpinBox()
        idx_s.setStyleSheet("QSpinBox { padding-right: 15px; }")
        idx_s.setRange(0, 99)
        idx_s.setValue(0)
        unit_c = QComboBox()
        unit_c.addItems(["LOGIC", "VALUE", "MULTI", "COM"])
        form.addRow("方向", dir_c)
        form.addRow("番号", idx_s)
        form.addRow("単位種別", unit_c)
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        form.addRow(bb)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        try:
            return make_port_layer_name(dir_c.currentText(), int(idx_s.value()), unit_c.currentText())
        except ValueError:
            return None

    def sketch_line_linetype(self) -> str:
        return user_sketch_entity_linetype_for_display(self._block_sk_line_linetype)

    def _refresh_block_sk_line_button_tooltip(self) -> None:
        lt = user_sketch_entity_linetype_for_display(self._block_sk_line_linetype)
        label = {"CONTINUOUS": "実線", "DASHED": "点線", "CENTER": "中心線"}.get(lt, lt)
        self._ann_sk.line.setToolTip(
            "直線（USER_LINE）: 2点で描画。グリッドにスナップ。Shiftで水平/垂直。レイヤは LD_SYMBOL。\n"
            "配置ツール中はクリックが配置優先（下に図形があっても同じ）。プレビュー中の右クリックで1点目キャンセル。\n"
            f"次の注釈の線種（直線・円の両方）: {label}（{lt}）。このボタンを右クリックで線種を変更。"
        )
        self._ann_sk.circle.setToolTip(
            "円（USER_CIRCLE）: 1点目で中心、2点目で半径。グリッドスナップ。レイヤ LD_SYMBOL。\n"
            "配置ツール中はクリックが配置優先。右クリックでキャンセル。\n"
            f"線種は直線ツールと共通（{label} / {lt}）。直線アイコンボタンを右クリックで変更。"
        )

    def _on_block_sk_line_linetype_menu(self, pos) -> None:
        menu = QMenu(self)
        cur = user_sketch_entity_linetype_for_display(self._block_sk_line_linetype)
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
        chosen = menu.exec(self._ann_sk.line.mapToGlobal(pos))
        if chosen is not None and chosen in key_by_action:
            self._block_sk_line_linetype = key_by_action[chosen]
            self._refresh_block_sk_line_button_tooltip()

    def _uncheck_other_placement(self, keep: QPushButton) -> None:
        for b in self._placement_buttons:
            if b is not keep:
                b.blockSignals(True)
                b.setChecked(False)
                b.blockSignals(False)

    def clear_placement_tools(self) -> None:
        for b in self._placement_buttons:
            b.blockSignals(True)
            b.setChecked(False)
            b.blockSignals(False)
        if self._scene is not None:
            self._scene.set_placement_tool(None)

    def _clear_placement_tools(self) -> None:
        self.clear_placement_tools()

    def _on_port_toggled(self, checked: bool) -> None:
        if self._scene is None:
            return
        if checked:
            self._uncheck_other_placement(self._btn_tool_port)
            self._scene.set_placement_tool("port")
        else:
            self._scene.set_placement_tool(None)

    def _on_sk_line_toggled(self, checked: bool) -> None:
        if self._scene is None:
            return
        if checked:
            self._uncheck_other_placement(self._ann_sk.line)
            self._scene.set_placement_tool("line")
        else:
            self._scene.set_placement_tool(None)

    def _on_sk_circle_toggled(self, checked: bool) -> None:
        if self._scene is None:
            return
        if checked:
            self._uncheck_other_placement(self._ann_sk.circle)
            self._scene.set_placement_tool("circle")
        else:
            self._scene.set_placement_tool(None)

    def _on_sk_attdef_toggled(self, checked: bool) -> None:
        if self._scene is None:
            return
        if checked:
            self._uncheck_other_placement(self._ann_sk.text)
            self._scene.set_placement_tool("attdef")
        else:
            self._scene.set_placement_tool(None)

    def _on_block_list_context_menu(self, pos) -> None:
        item = self._list.itemAt(pos)
        menu = QMenu(self)
        act_new = menu.addAction("新規ブロック…")
        act_new.triggered.connect(self._on_new_block)
        if item is not None:
            self._list.setCurrentItem(item)
            act_rename = menu.addAction("名前の変更…")
            act_rename.triggered.connect(self._on_rename_block)
            act_dup = menu.addAction("この定義から複製…")
            act_dup.triggered.connect(self._on_duplicate_block)
            act_del = menu.addAction("削除")
            act_del.triggered.connect(self._on_delete_block)
        menu.exec(self._list.mapToGlobal(pos))

    def _on_rename_block(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        old = str(item.text()).strip()
        if not old:
            return
        sess = self._session
        reopen_after = False
        if sess is not None and sess.block_name == old:
            if sess.is_dirty():
                QMessageBox.warning(
                    self,
                    "名前の変更",
                    "このブロックに未適用の変更があります。先に「ブロック編集完了」で適用するか、別ブロック選択で破棄してください。",
                )
                return
            self.discard_session()
            reopen_after = True
        new_nm, ok = QInputDialog.getText(self, "名前の変更", "新しいブロック名", text=old)
        if not ok:
            return
        new_nm = str(new_nm).strip()
        if not new_nm or new_nm.startswith("*"):
            QMessageBox.warning(self, "名前の変更", "ブロック名が無効です。")
            return
        if new_nm == old:
            return
        doc = self._get_diagram().doc
        if new_nm in doc.blocks:
            QMessageBox.warning(self, "名前の変更", f"{new_nm!r} は既に存在します。")
            return
        try:
            rename_block_definition(doc, old, new_nm)
        except ValueError as ex:
            QMessageBox.warning(self, "名前の変更", str(ex))
            return
        self._get_diagram().mark_modified()
        self.refresh_block_list()
        self._on_applied()
        self._notify(f"ブロック {old!r} を {new_nm!r} に名前変更しました。")
        self._select_list_block(new_nm)
        if reopen_after:
            self.start_session_existing(new_nm)

    def _on_duplicate_block(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        src = str(item.text()).strip()
        if not src:
            return
        if self._end_or_prompt_previous_session() == "cancel":
            return
        new_nm, ok = QInputDialog.getText(self, "ブロック複製", "新しいブロック名")
        if not ok:
            return
        new_nm = str(new_nm).strip()
        if not new_nm or new_nm.startswith("*"):
            QMessageBox.warning(self, "ブロック複製", "ブロック名が無効です。")
            return
        doc = self._get_diagram().doc
        if new_nm in doc.blocks:
            QMessageBox.warning(self, "ブロック複製", f"{new_nm!r} は既に存在します。")
            return
        try:
            duplicate_block_definition(doc, src, new_nm)
        except ValueError as ex:
            QMessageBox.warning(self, "ブロック複製", str(ex))
            return
        self._get_diagram().mark_modified()
        self.refresh_block_list()
        self._on_applied()
        self._notify(f"ブロック {src!r} から {new_nm!r} を作成しました。")
        self.start_session_existing(new_nm)
        self._select_list_block(new_nm)

    def refresh_block_list(self) -> None:
        cur = self._list.currentItem().text() if self._list.currentItem() else ""
        self._list.blockSignals(True)
        self._list.clear()
        doc = self._get_diagram().doc
        for name in list_palette_block_names(doc):
            self._list.addItem(name)
        if cur:
            for i in range(self._list.count()):
                if self._list.item(i).text() == cur:
                    self._list.setCurrentRow(i)
                    break
        self._list.blockSignals(False)

    def discard_session(self) -> None:
        if self._session is not None:
            self._session.clear_history()
        self._session = None
        self._clear_placement_tools()
        if self._scene is not None:
            self._scene.refresh_from_session()
        self.session_changed.emit()

    def clear_session_and_history(self) -> None:
        self.discard_session()

    def start_session_existing(self, block_name: str) -> None:
        diagram = self._get_diagram()
        self._session = BlockEditSession.open_existing(diagram.doc, block_name)
        if self._scene is not None:
            self._clear_placement_tools()
            self._scene.refresh_from_session()
        self.session_changed.emit()

    def start_session_new(self, block_name: str) -> None:
        self._session = BlockEditSession.open_new(block_name)
        if self._scene is not None:
            self._clear_placement_tools()
            self._scene.refresh_from_session()
        self._notify(f"新規ブロック {block_name}: キャンバス上の「本体へ適用」でドキュメントに追加されます。")
        self._list.blockSignals(True)
        self._list.clearSelection()
        self._list.blockSignals(False)
        self.session_changed.emit()

    def apply_session(self) -> None:
        if self._session is None:
            return
        diagram = self._get_diagram()
        name = self._session.block_name
        self._session.apply_to(diagram)
        self._session.clear_history()
        self._session = None
        self._clear_placement_tools()
        if self._scene is not None:
            self._scene.refresh_from_session()
        self.refresh_block_list()
        self._select_list_block(name)
        self._on_applied()
        self._notify("本体のブロック定義を上書きしました。一覧はそのまま・編集を続けられます。")
        self.start_session_existing(name)
        if self._scene is not None:
            self._scene.clearSelection()

    def _select_list_block(self, block_name: str) -> None:
        want = str(block_name).strip()
        if not want:
            return
        for i in range(self._list.count()):
            it = self._list.item(i)
            if it is not None and str(it.text()).strip() == want:
                self._list.setCurrentRow(i)
                return

    def _end_or_prompt_previous_session(self) -> str:
        if self._session is None:
            return "proceed"
        if not self._session.is_dirty():
            self.discard_session()
            return "proceed"
        r = self._prompt_switch_session()
        if r == "cancel":
            return "cancel"
        if r == "apply":
            self.apply_session()
        else:
            self.discard_session()
        return "proceed"

    def _on_list_changed(self, cur, prev) -> None:
        if cur is None:
            if self._session is not None:
                if self._end_or_prompt_previous_session() == "cancel":
                    self._list.blockSignals(True)
                    if prev is not None:
                        self._list.setCurrentItem(prev)
                    self._list.blockSignals(False)
                    return
            self.session_changed.emit()
            return
        name = cur.text()
        if (
            self._session is not None
            and self._session.block_name == name
            and not self._session.is_new_block
        ):
            return
        if self._end_or_prompt_previous_session() == "cancel":
            self._list.blockSignals(True)
            if prev is not None:
                self._list.setCurrentItem(prev)
            else:
                self._list.clearSelection()
            self._list.blockSignals(False)
            return
        self.start_session_existing(name)

    def _prompt_switch_session(self) -> str:
        mb = QMessageBox(self)
        mb.setWindowTitle("ブロック編集")
        mb.setText("別のブロックを選択しました。現在のスクラッチ編集をどうしますか？")
        apply_btn = mb.addButton("適用", QMessageBox.ButtonRole.AcceptRole)
        discard_btn = mb.addButton("破棄", QMessageBox.ButtonRole.DestructiveRole)
        mb.addButton("キャンセル", QMessageBox.ButtonRole.RejectRole)
        mb.exec()
        clicked = mb.clickedButton()
        if clicked == apply_btn:
            return "apply"
        if clicked == discard_btn:
            return "discard"
        return "cancel"

    def _on_new_block(self) -> None:
        name, ok = QInputDialog.getText(self, "新規ブロック", "ブロック名")
        if not ok:
            return
        name = str(name).strip()
        if not name or name.startswith("*"):
            QMessageBox.warning(self, "新規ブロック", "ブロック名が無効です。")
            return
        doc = self._get_diagram().doc
        if name in doc.blocks:
            QMessageBox.warning(self, "新規ブロック", f"{name!r} は既に本体に存在します。")
            return
        if self._end_or_prompt_previous_session() == "cancel":
            return
        self.start_session_new(name)

    def _on_delete_block(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        name = item.text()
        if self._session is not None and self._session.block_name == name:
            if self._session.is_dirty():
                mb = QMessageBox(self)
                mb.setWindowTitle("ブロック削除")
                mb.setIcon(QMessageBox.Icon.Warning)
                mb.setText(
                    f"「{name}」を編集中です。\n"
                    "未適用の変更を破棄して、このブロックを本体から削除してよろしいですか？"
                )
                mb.setStandardButtons(
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                mb.setDefaultButton(QMessageBox.StandardButton.No)
                if mb.exec() != QMessageBox.StandardButton.Yes:
                    return
            self.discard_session()
        try:
            delete_block_definition_if_unused(self._get_diagram().doc, name)
        except ValueError as ex:
            QMessageBox.warning(self, "削除", str(ex))
            return
        self._get_diagram().mark_modified()
        self.refresh_block_list()
        self._on_applied()
        self._notify(f"ブロック {name!r} を削除しました。")

    def _on_apply(self) -> None:
        if self._session is None:
            QMessageBox.information(self, "適用", "編集セッションがありません。一覧でブロックを開いてください。")
            return
        self.apply_session()

    def request_end_session_for_nav(self) -> bool:
        if self._session is None:
            return True
        if not self._session.is_dirty():
            self.discard_session()
            return True
        mb = QMessageBox(self)
        mb.setWindowTitle("ブロック編集")
        mb.setText("ブロック編集を終了しますか？未適用の変更は失われます。")
        apply_btn = mb.addButton("適用して終了", QMessageBox.ButtonRole.AcceptRole)
        discard_btn = mb.addButton("破棄", QMessageBox.ButtonRole.DestructiveRole)
        mb.addButton("キャンセル", QMessageBox.ButtonRole.RejectRole)
        mb.exec()
        clicked = mb.clickedButton()
        if clicked == apply_btn:
            self.apply_session()
            return True
        if clicked == discard_btn:
            self.discard_session()
            return True
        return False
