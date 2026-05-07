"""Contextual properties: only fields relevant to the current selection."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from logic_cad.core.attrib_tags import list_editable_text_attdef_tags, symbol_editor_attdef_tag_choices
from logic_cad.core.model.constants import (
    ENTITY_TYPE_INPAGE_REF,
    INPAGE_SYM_HEIGHT_MM,
    ENTITY_TYPE_USER_CIRCLE,
    ENTITY_TYPE_USER_CLOUD,
    ENTITY_TYPE_USER_LINE,
    ENTITY_TYPE_USER_TEXT,
    LINETYPE_COM,
    LINETYPE_LOGIC,
    LINETYPE_VALUE,
    WIRE_XDATA_SHOW_IN_ARROW,
)
from logic_cad.core.model.port_key import (
    is_inout_port_key,
    is_input_port_key,
    is_output_port_key,
    parse_port_key,
)
from logic_cad.core.undo.history import find_entity_by_uid
from logic_cad.core.pages.page_labels import page_index_to_letters, page_ref_link_label
from logic_cad.core.pages.page_layout_meta import read_page_meta
from logic_cad.core.pages.page_ref import (
    page_ref_allowed_sym_ordinals_for_property_edit,
    page_ref_ordinal_for_uid,
    page_ref_stored_rank,
)
from logic_cad.core.model.user_sketch_layers import user_sketch_display_linetype_for_entity
from logic_cad.core.model.wire_port_helpers import (
    wire_allows_orthogonal_cross,
    wire_skips_auto_reroute,
)
from logic_cad.core.uid_display import format_uid_display
from logic_cad.core.model.xdata import read_ld_app_dict

from logic_cad.core.model.port_key import parse_port_layer
from logic_cad.core.services.block_edit_helpers import (
    make_port_layer_name,
    set_native_line_linetype_in_block,
    set_scratch_user_sketch_linetype,
    update_scratch_attdef_fields,
    update_scratch_port_layer,
)

if TYPE_CHECKING:
    from logic_cad.core.logic_diagram import LogicDiagram
    from logic_cad.core.services.block_edit_session import BlockEditSession


def _port_sort_key(pk: str) -> tuple[int, str]:
    parsed = parse_port_key(pk)
    if parsed is None:
        return (3, pk)
    if parsed.direction == "IN":
        return (0, pk)
    if parsed.direction == "INOUT":
        return (1, pk)
    if parsed.direction == "OUT":
        return (2, pk)
    return (3, pk)


class PropertyPanel(QWidget):
    _NONE, _MULTI, _SYM, _GATE, _PAGE, _INPAGE, _WIRE, _WIRE_BRANCH, _USER_SK, _BLOCK_PORT, _BLOCK_GEOM, _BLOCK_ATTDEF = range(
        12
    )

    def __init__(
        self,
        get_diagram: Callable[[], LogicDiagram],
        on_applied: Callable[[], None],
        *,
        on_align_selected: Callable[[str], None] | None = None,
        get_block_edit_session: Callable[[], BlockEditSession | None] | None = None,
        on_block_scratch_applied: Callable[[], None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._get_diagram = get_diagram
        self._on_applied = on_applied
        self._on_align_selected = on_align_selected
        self._get_block_edit_session = get_block_edit_session
        self._on_block_scratch_applied = on_block_scratch_applied
        self._be_geom_lt_subject: str = ""
        self._be_geom_lt_handle: str = ""
        self._be_geom_lt_sketch_uid: str | None = None
        self._be_attdef_handle: str = ""
        self._be_port_edit_handle: str = ""
        self._uid: str | None = None
        self._wire_uid: str | None = None
        self._wire_branch_uid: str | None = None
        self._user_sk_uid: str | None = None
        self._user_sk_kind: str = ""

        self._stack = QStackedWidget()

        self._page_none = QWidget()
        ln = QVBoxLayout(self._page_none)
        ln.addWidget(QLabel("アイテムを1つ選択するとプロパティが表示されます。"))
        ln.addStretch()

        self._page_multi = QWidget()
        lm = QVBoxLayout(self._page_multi)
        self._multi_label = QLabel()
        lm.addWidget(self._multi_label)
        lm.addWidget(QLabel("整列・均等（シンボル2個以上）"))
        for label, mode in (
            ("左に揃える", "left"),
            ("水平中央に揃える", "hcenter"),
            ("右に揃える", "right"),
            ("上に揃える", "top"),
            ("垂直中央に揃える", "vcenter"),
            ("下に揃える", "bottom"),
            ("水平方向に均等配置", "hdistribute"),
            ("垂直方向に均等配置", "vdistribute"),
        ):
            b = QPushButton(label)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            b.clicked.connect(lambda *_, m=mode: self._emit_align(m))
            lm.addWidget(b)
        lm.addStretch()

        self._page_sym = QWidget()
        sym_outer = QVBoxLayout(self._page_sym)
        sym_outer.setContentsMargins(0, 0, 0, 0)
        fs = QFormLayout()
        self._sym_meta_uid = QLineEdit()
        self._sym_meta_uid.setReadOnly(True)
        self._sym_meta_block = QLineEdit()
        self._sym_meta_block.setReadOnly(True)
        self._sym_meta_type = QLineEdit()
        self._sym_meta_type.setReadOnly(True)
        fs.addRow("UUID", self._sym_meta_uid)
        fs.addRow("ブロック名", self._sym_meta_block)
        fs.addRow("タイプ", self._sym_meta_type)
        self._sym_only = QLineEdit()
        self._sym_show_only = QCheckBox()
        self._sym_show_only.setChecked(False)
        btn_sym = QPushButton("適用")
        btn_sym.clicked.connect(self._apply_symbol_only)
        fs.addRow("SYM", self._sym_only)
        fs.addRow("SYM を表示", self._sym_show_only)
        fs.addRow(btn_sym)
        sym_outer.addLayout(fs)
        sym_outer.addWidget(QLabel("ポート接続"))
        self._sym_ports_wrap = QWidget()
        self._sym_ports_form = QFormLayout(self._sym_ports_wrap)
        sym_outer.addWidget(self._sym_ports_wrap)
        self._sym_label_section = QWidget()
        self._sym_label_form = QFormLayout(self._sym_label_section)
        sym_outer.addWidget(QLabel("ラベル (ATTDEF: LABEL0 …)"))
        sym_outer.addWidget(self._sym_label_section)
        sym_outer.addStretch()

        self._page_gate = QWidget()
        gate_outer = QVBoxLayout(self._page_gate)
        gate_outer.setContentsMargins(0, 0, 0, 0)
        fg = QFormLayout()
        self._gate_meta_uid = QLineEdit()
        self._gate_meta_uid.setReadOnly(True)
        self._gate_meta_block = QLineEdit()
        self._gate_meta_block.setReadOnly(True)
        self._gate_meta_type = QLineEdit()
        self._gate_meta_type.setReadOnly(True)
        fg.addRow("UUID", self._gate_meta_uid)
        fg.addRow("ブロック名", self._gate_meta_block)
        fg.addRow("タイプ", self._gate_meta_type)
        self._sym_gate = QLineEdit()
        self._sym_show_gate = QCheckBox()
        self._sym_show_gate.setChecked(False)
        self._gate_stub_in_arrow = QCheckBox()
        self._gate_n_display = QLabel()
        self._gate_n_display.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        btn_gate = QPushButton("適用")
        btn_gate.clicked.connect(self._apply_gate)
        fg.addRow("SYM", self._sym_gate)
        fg.addRow("SYM を表示", self._sym_show_gate)
        fg.addRow("矢印 を表示", self._gate_stub_in_arrow)
        fg.addRow("入力ポート数", self._gate_n_display)
        fg.addRow(btn_gate)
        self._btn_optimize_inputs = QPushButton("入力ポートの配線を最適化")
        self._btn_optimize_inputs.setToolTip(
            "入力を割り当て直し配線を再計算します。"
        )
        self._btn_optimize_inputs.clicked.connect(self._optimize_gate_inputs)
        fg.addRow(self._btn_optimize_inputs)
        gate_outer.addLayout(fg)
        gate_outer.addWidget(QLabel("ポート接続"))
        self._gate_ports_wrap = QWidget()
        self._gate_ports_form = QFormLayout(self._gate_ports_wrap)
        gate_outer.addWidget(self._gate_ports_wrap)
        self._gate_label_section = QWidget()
        self._gate_label_form = QFormLayout(self._gate_label_section)
        gate_outer.addWidget(QLabel("ラベル (ATTDEF: LABEL0 …)"))
        gate_outer.addWidget(self._gate_label_section)
        gate_outer.addStretch()

        self._page_pref = QWidget()
        fp = QFormLayout(self._page_pref)
        self._page_meta_uid = QLineEdit()
        self._page_meta_uid.setReadOnly(True)
        self._page_meta_block = QLineEdit()
        self._page_meta_block.setReadOnly(True)
        self._page_meta_type = QLineEdit()
        self._page_meta_type.setReadOnly(True)
        fp.addRow("UUID", self._page_meta_uid)
        fp.addRow("ブロック名", self._page_meta_block)
        fp.addRow("タイプ", self._page_meta_type)
        self._page_ref_target_layout = ""
        self._page_target_label = QLabel()
        self._page_target_label.setWordWrap(True)
        self._page_target_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._page_ref_rank_combo = QComboBox()
        self._page_ref_rank_combo.currentIndexChanged.connect(self._on_page_ref_rank_combo_changed)
        self._sym_page = QLineEdit()
        self._sym_page.setReadOnly(True)
        self._page_show_page_name = QCheckBox()
        self._page_show_page_name.setChecked(False)
        self._page_show_page_desc = QCheckBox()
        self._page_show_page_desc.setChecked(False)
        btn_page = QPushButton("適用")
        btn_page.clicked.connect(self._apply_page_ref)
        fp.addRow("リンク先ページ", self._page_target_label)
        fp.addRow("付番", self._page_ref_rank_combo)
        fp.addRow("表示名（リンク先・自動）", self._sym_page)
        fp.addRow("PAGE_NAME を表示", self._page_show_page_name)
        fp.addRow("PAGE_DESC を表示", self._page_show_page_desc)
        fp.addRow(btn_page)

        self._page_inpage = QWidget()
        fin = QFormLayout(self._page_inpage)
        self._inpage_meta_uid = QLineEdit()
        self._inpage_meta_uid.setReadOnly(True)
        self._inpage_meta_block = QLineEdit()
        self._inpage_meta_block.setReadOnly(True)
        self._inpage_meta_type = QLineEdit()
        self._inpage_meta_type.setReadOnly(True)
        self._inpage_peer_uid = QLineEdit()
        self._inpage_peer_uid.setReadOnly(True)
        self._inpage_sym_display = QLineEdit()
        self._inpage_sym_display.setReadOnly(True)
        fin.addRow("UUID", self._inpage_meta_uid)
        fin.addRow("ブロック名", self._inpage_meta_block)
        fin.addRow("タイプ", self._inpage_meta_type)
        fin.addRow("相手 UUID", self._inpage_peer_uid)
        fin.addRow("表示（※n）", self._inpage_sym_display)
        self._inpage_sym_height_mm = QDoubleSpinBox()
        self._inpage_sym_height_mm.setRange(0.25, 80.0)
        self._inpage_sym_height_mm.setSingleStep(0.25)
        self._inpage_sym_height_mm.setDecimals(2)
        self._inpage_sym_height_mm.setSuffix(" mm")
        fin.addRow("文字高さ (SYM)", self._inpage_sym_height_mm)
        btn_inpage = QPushButton("適用")
        btn_inpage.clicked.connect(self._apply_inpage_ref)
        fin.addRow(btn_inpage)

        self._page_wire = QWidget()
        fw = QFormLayout(self._page_wire)
        self._wire_meta_uid = QLineEdit()
        self._wire_meta_uid.setReadOnly(True)
        self._wire_meta_type = QLineEdit()
        self._wire_meta_type.setReadOnly(True)
        fw.addRow("UUID", self._wire_meta_uid)
        fw.addRow("タイプ", self._wire_meta_type)
        self._wire_src_detail = QLabel()
        self._wire_src_detail.setWordWrap(True)
        self._wire_src_detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._wire_dst_detail = QLabel()
        self._wire_dst_detail.setWordWrap(True)
        self._wire_dst_detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        fw.addRow("始点 (SYM / UUID)", self._wire_src_detail)
        fw.addRow("終点 (SYM / UUID)", self._wire_dst_detail)
        self._wire_manual = QCheckBox("AND/OR 入力ポート固定")
        fw.addRow(self._wire_manual)
        self._wire_in_arrow = QCheckBox("終点に矢印（IN側）")
        fw.addRow(self._wire_in_arrow)
        self._wire_allow_orthogonal = QCheckBox("直交を許可")
        self._wire_allow_orthogonal.setToolTip(
            "オン時は他線の帯を跨ぐ直交が通りやすくなります。"
        )
        fw.addRow(self._wire_allow_orthogonal)
        self._wire_health = QLabel()
        self._wire_health.setWordWrap(True)
        fw.addRow("接続状態", self._wire_health)
        self._wire_lt = QComboBox()
        self._wire_lt.addItem("実線(Logic)", LINETYPE_LOGIC)
        self._wire_lt.addItem("点線(Value)", LINETYPE_VALUE)
        self._wire_lt.addItem("通信(COM)", LINETYPE_COM)
        btn_w = QPushButton("適用")
        btn_w.clicked.connect(self._apply_wire)
        fw.addRow("線種", self._wire_lt)
        fw.addRow(btn_w)

        self._page_wire_branch = QWidget()
        wb_outer = QVBoxLayout(self._page_wire_branch)
        wb_outer.setContentsMargins(0, 0, 0, 0)
        fwb = QFormLayout()
        self._wb_meta_uid = QLineEdit()
        self._wb_meta_uid.setReadOnly(True)
        self._wb_meta_type = QLineEdit()
        self._wb_meta_type.setReadOnly(True)
        self._wb_parent_wire_uid = QLineEdit()
        self._wb_parent_wire_uid.setReadOnly(True)
        fwb.addRow("UUID", self._wb_meta_uid)
        fwb.addRow("タイプ", self._wb_meta_type)
        self._wb_port_in_label = QLabel("IN0_MULTI（1本まで）")
        self._wb_port_in_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._wb_port_out_label = QLabel("OUT0_MULTI（複数可）")
        self._wb_port_out_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        fwb.addRow("入力ポート", self._wb_port_in_label)
        fwb.addRow("出力ポート", self._wb_port_out_label)
        wb_outer.addLayout(fwb)
        wb_outer.addWidget(QLabel("親配線（接続元）"))
        self._wb_parent_wrap = QWidget()
        fwb_parent = QFormLayout(self._wb_parent_wrap)
        fwb_parent.setContentsMargins(0, 0, 0, 0)
        fwb_parent.addRow("UUID", self._wb_parent_wire_uid)
        wb_outer.addWidget(self._wb_parent_wrap)
        wb_outer.addWidget(QLabel("子配線（接続先）"))
        self._wb_legs_wrap = QWidget()
        self._wb_legs_form = QFormLayout(self._wb_legs_wrap)
        wb_outer.addWidget(self._wb_legs_wrap)
        wb_outer.addStretch()

        self._page_user_sk = QWidget()
        fus = QVBoxLayout(self._page_user_sk)
        fus.setContentsMargins(0, 0, 0, 0)
        ff = QFormLayout()
        self._usk_meta_uid = QLineEdit()
        self._usk_meta_uid.setReadOnly(True)
        self._usk_meta_type = QLineEdit()
        self._usk_meta_type.setReadOnly(True)
        ff.addRow("UUID", self._usk_meta_uid)
        ff.addRow("タイプ", self._usk_meta_type)
        fus.addLayout(ff)
        self._usk_row_lt = QWidget()
        flt = QFormLayout(self._usk_row_lt)
        flt.setContentsMargins(0, 0, 0, 0)
        self._usk_lt = QComboBox()
        self._usk_lt.addItems(["CONTINUOUS", "DASHED", "CENTER"])
        flt.addRow("線種", self._usk_lt)
        fus.addWidget(self._usk_row_lt)
        self._usk_row_pitch = QWidget()
        fpitch = QFormLayout(self._usk_row_pitch)
        fpitch.setContentsMargins(0, 0, 0, 0)
        self._usk_pitch = QDoubleSpinBox()
        self._usk_pitch.setRange(0.001, 500.0)
        self._usk_pitch.setDecimals(3)
        self._usk_pitch.setSingleStep(0.25)
        self._usk_pitch.setSuffix(" mm")
        self._usk_pitch.setToolTip(
            "リビジョンクラウドのスカラップ間隔（おおよその線分長）です。"
            " 図面上の元の値と一致しない場合があります。"
        )
        fpitch.addRow("ピッチ", self._usk_pitch)
        fus.addWidget(self._usk_row_pitch)
        self._usk_row_pitch.hide()
        self._usk_row_txt = QWidget()
        ftx = QFormLayout(self._usk_row_txt)
        ftx.setContentsMargins(0, 0, 0, 0)
        self._usk_txt = QLineEdit()
        self._usk_h = QDoubleSpinBox()
        self._usk_h.setRange(0.25, 80.0)
        self._usk_h.setSingleStep(0.25)
        self._usk_h.setSuffix(" mm")
        self._usk_halign = QComboBox()
        self._usk_halign.addItem("左", 0)
        self._usk_halign.addItem("中央", 1)
        self._usk_halign.addItem("右", 2)
        ftx.addRow("文字列", self._usk_txt)
        ftx.addRow("文字高さ", self._usk_h)
        ftx.addRow("水平揃え", self._usk_halign)
        fus.addWidget(self._usk_row_txt)
        btn_usk = QPushButton("適用")
        btn_usk.clicked.connect(self._apply_user_sketch)
        fus.addWidget(btn_usk)
        fus.addStretch()

        self._page_block_port = QWidget()
        fbp = QFormLayout(self._page_block_port)
        self._be_port_block = QLineEdit()
        self._be_port_block.setReadOnly(True)
        self._be_port_handle = QLineEdit()
        self._be_port_handle.setReadOnly(True)
        self._be_port_layer_preview = QLabel("—")
        self._be_port_layer_preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._be_port_dir = QComboBox()
        self._be_port_dir.addItems(["IN", "OUT", "INOUT"])
        self._be_port_idx = QSpinBox()
        self._be_port_idx.setRange(0, 99)
        self._be_port_idx.setStyleSheet("QSpinBox { padding-right: 15px; }")
        self._be_port_unit = QComboBox()
        self._be_port_unit.addItems(["LOGIC", "VALUE", "MULTI", "COM"])
        self._be_port_dir.currentIndexChanged.connect(self._sync_be_port_layer_preview)
        self._be_port_idx.valueChanged.connect(self._sync_be_port_layer_preview)
        self._be_port_unit.currentIndexChanged.connect(self._sync_be_port_layer_preview)
        self._be_port_x = QLineEdit()
        self._be_port_x.setReadOnly(True)
        self._be_port_y = QLineEdit()
        self._be_port_y.setReadOnly(True)
        self._be_port_apply = QPushButton("ポート属性を適用")
        self._be_port_apply.clicked.connect(self._apply_block_edit_port)
        fbp.addRow("ブロック", self._be_port_block)
        fbp.addRow("ハンドル", self._be_port_handle)
        fbp.addRow("ポート方向", self._be_port_dir)
        fbp.addRow("ポート番号", self._be_port_idx)
        fbp.addRow("ポート単位", self._be_port_unit)
        fbp.addRow("レイヤ（適用結果）", self._be_port_layer_preview)
        fbp.addRow("X (mm)", self._be_port_x)
        fbp.addRow("Y (mm)", self._be_port_y)
        fbp.addRow(self._be_port_apply)

        self._page_block_geom = QWidget()
        fbg = QFormLayout(self._page_block_geom)
        self._be_geom_block = QLineEdit()
        self._be_geom_block.setReadOnly(True)
        self._be_geom_type = QLineEdit()
        self._be_geom_type.setReadOnly(True)
        self._be_geom_handle = QLineEdit()
        self._be_geom_handle.setReadOnly(True)
        self._be_geom_layer = QLineEdit()
        self._be_geom_layer.setReadOnly(True)
        self._be_geom_detail = QLabel()
        self._be_geom_detail.setWordWrap(True)
        self._be_geom_detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        fbg.addRow("ブロック", self._be_geom_block)
        fbg.addRow("図形", self._be_geom_type)
        fbg.addRow("ハンドル", self._be_geom_handle)
        fbg.addRow("レイヤ", self._be_geom_layer)
        fbg.addRow("内容", self._be_geom_detail)
        self._be_geom_lt_wrap = QWidget()
        flt_be = QFormLayout(self._be_geom_lt_wrap)
        flt_be.setContentsMargins(0, 0, 0, 0)
        self._be_geom_lt = QComboBox()
        self._be_geom_lt.addItems(["CONTINUOUS", "DASHED", "CENTER"])
        self._be_geom_lt_apply = QPushButton("線種を適用")
        self._be_geom_lt_apply.clicked.connect(self._apply_block_edit_linetype)
        flt_be.addRow("線種", self._be_geom_lt)
        flt_be.addRow(self._be_geom_lt_apply)
        fbg.addRow(self._be_geom_lt_wrap)
        self._be_geom_lt_wrap.hide()

        self._page_block_attdef = QWidget()
        fba = QFormLayout(self._page_block_attdef)
        self._be_att_block = QLineEdit()
        self._be_att_block.setReadOnly(True)
        self._be_att_handle = QLineEdit()
        self._be_att_handle.setReadOnly(True)
        self._be_att_tag = QComboBox()
        self._be_att_tag.setEditable(False)
        self._be_att_default = QLineEdit()
        self._be_att_h = QDoubleSpinBox()
        self._be_att_h.setRange(0.25, 80.0)
        self._be_att_h.setSingleStep(0.25)
        self._be_att_h.setSuffix(" mm")
        self._be_att_halign = QComboBox()
        self._be_att_halign.addItem("左", 0)
        self._be_att_halign.addItem("中央", 1)
        self._be_att_halign.addItem("右", 2)
        self._be_att_apply = QPushButton("適用")
        self._be_att_apply.clicked.connect(self._apply_block_edit_attdef)
        fba.addRow("ブロック", self._be_att_block)
        fba.addRow("ハンドル", self._be_att_handle)
        fba.addRow("タグ", self._be_att_tag)
        fba.addRow("既定テキスト", self._be_att_default)
        fba.addRow("文字高さ", self._be_att_h)
        fba.addRow("水平揃え", self._be_att_halign)
        fba.addRow(self._be_att_apply)

        for w in (
            self._page_none,
            self._page_multi,
            self._page_sym,
            self._page_gate,
            self._page_pref,
            self._page_inpage,
            self._page_wire,
            self._page_wire_branch,
            self._page_user_sk,
            self._page_block_port,
            self._page_block_geom,
            self._page_block_attdef,
        ):
            self._stack.addWidget(w)

        box = QGroupBox("プロパティ")
        bv = QVBoxLayout()
        bv.addWidget(self._stack)
        box.setLayout(bv)
        lay = QVBoxLayout(self)
        lay.addWidget(box)
        lay.addStretch()
        self._label_edits: dict[str, QLineEdit] = {}
        self.clear_selection()

    @staticmethod
    def _clear_port_form(form: QFormLayout) -> None:
        while form.rowCount() > 0:
            form.removeRow(0)

    @staticmethod
    def _clear_form(form: QFormLayout) -> None:
        while form.rowCount() > 0:
            form.removeRow(0)

    @staticmethod
    def _set_readonly_uid_field(edit: QLineEdit, full_uid: str) -> None:
        edit.setText(format_uid_display(full_uid))
        edit.setToolTip(full_uid)

    @staticmethod
    def _ld_port_starts_with_in(port: str) -> bool:
        return is_input_port_key(port)

    @staticmethod
    def _ld_port_starts_with_out(port: str) -> bool:
        return is_output_port_key(port)

    def _peer_display(self, d: "LogicDiagram", uid: str | None) -> tuple[str, str]:
        """(short multiline text, tooltip = full UUID or empty)."""
        if not uid:
            return "—", ""
        ins = d.symbols.insert_by_uid(d.current_layout_name, uid)
        short = format_uid_display(uid)
        if ins is None:
            return f"（INSERT なし）\nUUID: {short}", uid
        sym = ins.dxf.name
        for a in ins.attribs:
            if str(a.dxf.tag) == "SYM":
                sym = str(a.dxf.text or sym)
                break
        return f"SYM: {sym}\nUUID: {short}", uid

    def _populate_port_rows(self, form: QFormLayout, uid: str) -> None:
        self._clear_port_form(form)
        d = self._get_diagram()
        idx = d.index
        ports = [pk for (u, pk) in idx.ports if u == uid]
        ports.sort(key=_port_sort_key)
        for pk in ports:
            peer = d.wires.peer_for_symbol_port(d.current_layout_name, uid, pk)
            if peer:
                pu, pp = peer
                body, tip = self._peer_display(d, pu)
                if pp:
                    body = f"{body}\n相手ポート: {pp}"
            else:
                body, tip = "未接続", ""
            lab = QLabel(body)
            lab.setWordWrap(True)
            lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            if tip:
                lab.setToolTip(tip)
            form.addRow(pk, lab)

    def _emit_align(self, mode: str) -> None:
        if self._on_align_selected is not None:
            self._on_align_selected(mode)

    def clear_selection(self) -> None:
        self._uid = None
        self._wire_uid = None
        self._wire_branch_uid = None
        self._user_sk_uid = None
        self._user_sk_kind = ""
        self._clear_label_forms()
        self._clear_port_form(self._sym_ports_form)
        self._clear_port_form(self._gate_ports_form)
        self._clear_form(self._wb_legs_form)
        self._be_geom_lt_wrap.hide()
        self._be_geom_lt_subject = ""
        self._be_geom_lt_handle = ""
        self._be_geom_lt_sketch_uid = None
        self._be_attdef_handle = ""
        self._be_port_edit_handle = ""
        self._stack.setCurrentIndex(self._NONE)

    def show_multi(self, n: int) -> None:
        self._uid = None
        self._wire_uid = None
        self._wire_branch_uid = None
        self._user_sk_uid = None
        self._user_sk_kind = ""
        self._clear_label_forms()
        self._clear_port_form(self._sym_ports_form)
        self._clear_port_form(self._gate_ports_form)
        self._clear_form(self._wb_legs_form)
        self._be_geom_lt_wrap.hide()
        self._be_geom_lt_subject = ""
        self._be_geom_lt_handle = ""
        self._be_geom_lt_sketch_uid = None
        self._be_attdef_handle = ""
        self._be_port_edit_handle = ""
        self._multi_label.setText(f"{n} 個のアイテムが選択されています。")
        self._stack.setCurrentIndex(self._MULTI)

    def show_block_edit_port(
        self,
        *,
        block_name: str,
        handle: str,
        layer: str,
        x_mm: float,
        y_mm: float,
    ) -> None:
        self._uid = None
        self._wire_uid = None
        self._wire_branch_uid = None
        self._user_sk_uid = None
        self._user_sk_kind = ""
        self._clear_label_forms()
        self._clear_port_form(self._sym_ports_form)
        self._clear_port_form(self._gate_ports_form)
        self._clear_form(self._wb_legs_form)
        self._be_geom_lt_wrap.hide()
        self._be_geom_lt_subject = ""
        self._be_geom_lt_handle = ""
        self._be_geom_lt_sketch_uid = None
        self._be_attdef_handle = ""
        self._be_port_block.setText(block_name or "—")
        self._be_port_handle.setText(handle or "—")
        self._be_port_edit_handle = str(handle or "")
        pk = parse_port_layer(str(layer or ""))
        self._be_port_dir.blockSignals(True)
        self._be_port_idx.blockSignals(True)
        self._be_port_unit.blockSignals(True)
        if pk is not None:
            dix = self._be_port_dir.findText(pk.direction)
            if dix >= 0:
                self._be_port_dir.setCurrentIndex(dix)
            uix = self._be_port_unit.findText(pk.unit)
            if uix >= 0:
                self._be_port_unit.setCurrentIndex(uix)
            self._be_port_idx.setValue(int(pk.index))
        else:
            self._be_port_dir.setCurrentIndex(0)
            self._be_port_idx.setValue(0)
            self._be_port_unit.setCurrentIndex(0)
        self._be_port_dir.blockSignals(False)
        self._be_port_idx.blockSignals(False)
        self._be_port_unit.blockSignals(False)
        self._sync_be_port_layer_preview()
        self._be_port_x.setText(f"{x_mm:.3f}")
        self._be_port_y.setText(f"{y_mm:.3f}")
        self._stack.setCurrentIndex(self._BLOCK_PORT)

    def show_block_edit_geom(
        self,
        *,
        block_name: str,
        handle: str,
        dxftype: str,
        layer: str,
        detail: str,
        editable_linetype: str | None = None,
        linetype_subject: str = "",
        sketch_uid: str | None = None,
    ) -> None:
        self._uid = None
        self._wire_uid = None
        self._wire_branch_uid = None
        self._user_sk_uid = None
        self._user_sk_kind = ""
        self._clear_label_forms()
        self._clear_port_form(self._sym_ports_form)
        self._clear_port_form(self._gate_ports_form)
        self._clear_form(self._wb_legs_form)
        self._be_attdef_handle = ""
        self._be_port_edit_handle = ""
        self._be_geom_block.setText(block_name or "—")
        self._be_geom_type.setText(dxftype or "—")
        self._be_geom_handle.setText(handle or "—")
        self._be_geom_layer.setText(layer or "—")
        self._be_geom_detail.setText(detail or "—")
        self._be_geom_lt_subject = ""
        self._be_geom_lt_handle = ""
        self._be_geom_lt_sketch_uid = None
        self._be_geom_lt_wrap.hide()
        if editable_linetype is not None and linetype_subject in ("native_line", "user_sketch"):
            self._be_geom_lt_subject = linetype_subject
            self._be_geom_lt_handle = handle
            self._be_geom_lt_sketch_uid = sketch_uid
            idx = self._be_geom_lt.findText(editable_linetype)
            if idx >= 0:
                self._be_geom_lt.setCurrentIndex(idx)
            else:
                self._be_geom_lt.setCurrentIndex(0)
                self._be_geom_lt.setCurrentText(editable_linetype)
            self._be_geom_lt_wrap.show()
        self._stack.setCurrentIndex(self._BLOCK_GEOM)

    def show_block_edit_attdef(
        self,
        *,
        block_name: str,
        handle: str,
        tag: str,
        default_text: str,
        halign: int = 0,
        height_mm: float = 2.5,
    ) -> None:
        self._uid = None
        self._wire_uid = None
        self._wire_branch_uid = None
        self._user_sk_uid = None
        self._user_sk_kind = ""
        self._clear_label_forms()
        self._clear_port_form(self._sym_ports_form)
        self._clear_port_form(self._gate_ports_form)
        self._clear_form(self._wb_legs_form)
        self._be_geom_lt_wrap.hide()
        self._be_geom_lt_subject = ""
        self._be_geom_lt_handle = ""
        self._be_geom_lt_sketch_uid = None
        self._be_port_edit_handle = ""
        self._be_attdef_handle = str(handle or "")
        self._be_att_block.setText(block_name or "—")
        self._be_att_handle.setText(handle or "—")
        tag_choices = symbol_editor_attdef_tag_choices()
        self._be_att_tag.blockSignals(True)
        self._be_att_tag.clear()
        for t in tag_choices:
            self._be_att_tag.addItem(t)
        self._be_att_tag.blockSignals(False)
        cur = str(tag or "").strip()
        ix = self._be_att_tag.findText(cur)
        if ix >= 0:
            self._be_att_tag.setCurrentIndex(ix)
        else:
            self._be_att_tag.setCurrentIndex(0)
        self._be_att_default.setText(default_text)
        try:
            hh = float(height_mm)
        except (TypeError, ValueError):
            hh = 2.5
        self._be_att_h.setValue(max(0.25, hh))
        ha = int(halign)
        if ha not in (0, 1, 2):
            ha = 0
        hi = self._be_att_halign.findData(ha)
        self._be_att_halign.setCurrentIndex(hi if hi >= 0 else 0)
        self._stack.setCurrentIndex(self._BLOCK_ATTDEF)

    def show_symbol(
        self,
        uid: str,
        sym_text: str,
        *,
        block_name: str = "",
        entity_type: str = "SYMBOL",
        sym_visible: bool = True,
    ) -> None:
        self._wire_uid = None
        self._wire_branch_uid = None
        self._user_sk_uid = None
        self._user_sk_kind = ""
        self._uid = uid
        self._set_readonly_uid_field(self._sym_meta_uid, uid)
        self._sym_meta_block.setText(block_name or "—")
        self._sym_meta_type.setText(entity_type or "SYMBOL")
        self._sym_only.setText(sym_text)
        self._sym_show_only.setChecked(sym_visible)
        self._clear_port_form(self._gate_ports_form)
        self._populate_label_fields(self._sym_label_form, block_name)
        self._populate_port_rows(self._sym_ports_form, uid)
        self._stack.setCurrentIndex(self._SYM)

    def show_gate(
        self,
        uid: str,
        sym_text: str,
        n_inputs: int,
        sym_visible: bool = True,
        *,
        block_name: str = "",
        entity_type: str = "",
        show_input_stub_in_arrow: bool = False,
    ) -> None:
        self._wire_uid = None
        self._wire_branch_uid = None
        self._user_sk_uid = None
        self._user_sk_kind = ""
        self._uid = uid
        self._set_readonly_uid_field(self._gate_meta_uid, uid)
        self._gate_meta_block.setText(block_name or "—")
        self._gate_meta_type.setText(entity_type or "GATE")
        self._sym_gate.setText(sym_text)
        self._sym_show_gate.setChecked(sym_visible)
        self._gate_stub_in_arrow.setChecked(show_input_stub_in_arrow)
        self._gate_n_display.setText(str(n_inputs))
        self._clear_port_form(self._sym_ports_form)
        self._populate_label_fields(self._gate_label_form, block_name)
        self._populate_port_rows(self._gate_ports_form, uid)
        self._stack.setCurrentIndex(self._GATE)

    def show_page_ref(
        self,
        uid: str,
        target_layout: str,
        sym: str,
        show_page_name: bool = False,
        show_page_desc: bool = False,
        *,
        block_name: str = "",
        entity_type: str = "PAGE_REF",
    ) -> None:
        self._wire_uid = None
        self._wire_branch_uid = None
        self._user_sk_uid = None
        self._user_sk_kind = ""
        self._uid = uid
        self._clear_label_forms()
        self._clear_port_form(self._sym_ports_form)
        self._clear_port_form(self._gate_ports_form)
        self._set_readonly_uid_field(self._page_meta_uid, uid)
        self._page_meta_block.setText(block_name)
        self._page_meta_type.setText(entity_type)
        d = self._get_diagram()
        self._page_ref_target_layout = (target_layout or "").strip()
        self._refresh_page_ref_target_label()
        self._page_ref_rank_combo.blockSignals(True)
        self._page_ref_rank_combo.clear()
        if self._page_ref_target_layout and self._uid:
            allowed = page_ref_allowed_sym_ordinals_for_property_edit(
                d.doc, d.current_layout_name, self._uid, self._page_ref_target_layout
            )
            for rk in allowed:
                self._page_ref_rank_combo.addItem(page_index_to_letters(int(rk)), int(rk))
            stored = page_ref_stored_rank(d.doc, d.current_layout_name, self._uid)
            want = stored if stored is not None else page_ref_ordinal_for_uid(
                d.doc, d.current_layout_name, self._uid
            )
            if want is not None:
                idx = self._page_ref_rank_combo.findData(int(want))
                if idx >= 0:
                    self._page_ref_rank_combo.setCurrentIndex(idx)
                elif self._page_ref_rank_combo.count():
                    self._page_ref_rank_combo.setCurrentIndex(0)
            elif self._page_ref_rank_combo.count():
                self._page_ref_rank_combo.setCurrentIndex(0)
        self._page_ref_rank_combo.blockSignals(False)
        if self._page_ref_rank_combo.count():
            self._sync_page_ref_sym_preview_from_rank_combo()
        else:
            self._sym_page.setText(sym or "")
        self._page_show_page_name.setChecked(bool(show_page_name))
        self._page_show_page_desc.setChecked(bool(show_page_desc))
        self._stack.setCurrentIndex(self._PAGE)

    def show_inpage_ref(
        self,
        uid: str,
        peer_uid: str,
        sym: str,
        *,
        sym_height_mm: float = INPAGE_SYM_HEIGHT_MM,
        block_name: str = "",
        entity_type: str = ENTITY_TYPE_INPAGE_REF,
    ) -> None:
        """INPAGE_REF: peer, ※n display, and editable SYM height (mm)."""
        self._wire_uid = None
        self._wire_branch_uid = None
        self._user_sk_uid = None
        self._user_sk_kind = ""
        self._uid = uid
        self._clear_label_forms()
        self._clear_port_form(self._sym_ports_form)
        self._clear_port_form(self._gate_ports_form)
        self._set_readonly_uid_field(self._inpage_meta_uid, uid)
        self._inpage_meta_block.setText(block_name)
        self._inpage_meta_type.setText(entity_type)
        self._inpage_peer_uid.setText(peer_uid or "—")
        self._inpage_sym_display.setText(sym or "")
        self._inpage_sym_height_mm.setValue(float(sym_height_mm))
        self._stack.setCurrentIndex(self._INPAGE)

    def show_wire(self, wire_uid: str, linetype: str, *, entity_type: str = "WIRE") -> None:
        self._uid = None
        self._user_sk_uid = None
        self._user_sk_kind = ""
        self._wire_uid = wire_uid
        self._wire_branch_uid = None
        self._clear_label_forms()
        self._clear_port_form(self._sym_ports_form)
        self._clear_port_form(self._gate_ports_form)
        self._clear_form(self._wb_legs_form)
        self._set_readonly_uid_field(self._wire_meta_uid, wire_uid)
        self._wire_meta_type.setText(entity_type)
        d = self._get_diagram()
        meta: dict[str, str] = {}
        e = find_entity_by_uid(d.doc, wire_uid)
        if e is not None:
            meta = read_ld_app_dict(e)
        su, du = meta.get("src"), meta.get("dst")
        t0, tip0 = self._peer_display(d, su)
        t1, tip1 = self._peer_display(d, du)
        self._wire_src_detail.setText(t0)
        self._wire_src_detail.setToolTip(tip0)
        self._wire_dst_detail.setText(t1)
        self._wire_dst_detail.setToolTip(tip1)
        self._wire_manual.setChecked(wire_skips_auto_reroute(meta))
        self._wire_in_arrow.setChecked(str(meta.get(WIRE_XDATA_SHOW_IN_ARROW) or "") == "1")
        self._wire_allow_orthogonal.setChecked(wire_allows_orthogonal_cross(meta))
        log_ok, geo_ok = d.wire_connection_health(wire_uid)
        self._wire_health.setText(
            f"論理: {'OK' if log_ok else 'NG'}　端点幾何: {'OK' if geo_ok else 'NG'}"
        )
        i = self._wire_linetype_combo_index(self._wire_lt, linetype)
        if i >= 0:
            self._wire_lt.setCurrentIndex(i)
        self._stack.setCurrentIndex(self._WIRE)

    def _show_hub_incident_wires(self, hub_uid: str, *, caption_in: str, caption_out: str) -> None:
        """List wires touching hub ports; src/dst click order is ignored."""
        self._wb_port_in_label.setText(caption_in)
        self._wb_port_out_label.setText(caption_out)
        d = self._get_diagram()

        parent_by_wire: dict[str, dict] = {}
        child_by_wire: dict[str, dict] = {}
        for _ent, wu, meta in d.wires.iter_wire_meta(d.current_layout_name):
            su = str(meta.get("src") or "")
            du = str(meta.get("dst") or "")
            sp = str(meta.get("src_port") or "")
            dp = str(meta.get("dst_port") or "")
            wus = str(wu)
            for uid, port in ((su, sp), (du, dp)):
                if uid != hub_uid:
                    continue
                if self._ld_port_starts_with_in(port):
                    parent_by_wire[wus] = meta
                elif self._ld_port_starts_with_out(port):
                    child_by_wire[wus] = meta
                elif is_inout_port_key(port):
                    child_by_wire[wus] = meta
        parent_rows = sorted(parent_by_wire.items(), key=lambda item: item[0])
        child_rows = sorted(child_by_wire.items(), key=lambda item: item[0])

        n_parent = len(parent_rows)
        if n_parent == 1:
            self._set_readonly_uid_field(self._wb_parent_wire_uid, parent_rows[0][0])
        elif n_parent == 0:
            self._wb_parent_wire_uid.setText("—")
            self._wb_parent_wire_uid.setToolTip("")
        else:
            self._wb_parent_wire_uid.setText("—")
            self._wb_parent_wire_uid.setToolTip(
                "親候補（ハブの IN 側）が複数検出されました。データ不整合の可能性があります。"
            )

        if not child_rows:
            lab = QLabel("（なし）")
            lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self._wb_legs_form.addRow(lab)
        else:
            for wu, meta in child_rows:
                su, du = str(meta.get("src") or ""), str(meta.get("dst") or "")
                sp, dp = str(meta.get("src_port") or ""), str(meta.get("dst_port") or "")
                if su == hub_uid and self._ld_port_starts_with_out(sp):
                    peer_uid, peer_port, local_port = du, dp, sp
                elif du == hub_uid and self._ld_port_starts_with_out(dp):
                    peer_uid, peer_port, local_port = su, sp, dp
                else:
                    peer_uid, peer_port, local_port = du, dp, sp
                title = "出力"
                body, tip = self._peer_display(d, peer_uid)
                if peer_port:
                    body = f"{body}\n相手ポート: {peer_port}"
                if local_port:
                    body = f"{body}\nこのハブのポート: {local_port}"
                if is_inout_port_key(local_port):
                    title = "接続"
                detail = QLabel(body)
                detail.setWordWrap(True)
                detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                if tip:
                    detail.setToolTip(tip)
                left = QLabel(f"{title} · WIRE {format_uid_display(wu)}")
                left.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                left.setToolTip(wu)
                self._wb_legs_form.addRow(left, detail)

    def show_wire_branch(self, branch_uid: str, *, entity_type: str = "WIRE_BRANCH") -> None:
        self._uid = None
        self._wire_uid = None
        self._user_sk_uid = None
        self._user_sk_kind = ""
        self._wire_branch_uid = branch_uid
        self._clear_label_forms()
        self._clear_port_form(self._sym_ports_form)
        self._clear_port_form(self._gate_ports_form)
        self._clear_form(self._wb_legs_form)
        self._set_readonly_uid_field(self._wb_meta_uid, branch_uid)
        self._wb_meta_type.setText(entity_type)
        self._show_hub_incident_wires(
            branch_uid,
            caption_in="INOUT0_MULTI（複数可）",
            caption_out="INOUT0_MULTI（複数可）",
        )
        self._stack.setCurrentIndex(self._WIRE_BRANCH)

    def show_checkpoint(self, checkpoint_uid: str) -> None:
        self._uid = None
        self._wire_uid = None
        self._user_sk_uid = None
        self._user_sk_kind = ""
        self._wire_branch_uid = checkpoint_uid
        self._clear_label_forms()
        self._clear_port_form(self._sym_ports_form)
        self._clear_port_form(self._gate_ports_form)
        self._clear_form(self._wb_legs_form)
        self._set_readonly_uid_field(self._wb_meta_uid, checkpoint_uid)
        self._wb_meta_type.setText("CHECKPOINT")
        self._show_hub_incident_wires(
            checkpoint_uid,
            caption_in="IN0_MULTI（1本まで）",
            caption_out="OUT0_MULTI（1本まで）",
        )
        self._stack.setCurrentIndex(self._WIRE_BRANCH)

    def show_user_sketch(self, uid: str, *, entity_type: str) -> None:
        self._uid = None
        self._wire_uid = None
        self._wire_branch_uid = None
        self._user_sk_uid = uid
        self._clear_label_forms()
        self._clear_port_form(self._sym_ports_form)
        self._clear_port_form(self._gate_ports_form)
        self._clear_form(self._wb_legs_form)
        self._set_readonly_uid_field(self._usk_meta_uid, uid)
        self._usk_meta_type.setText(entity_type)
        d = self._get_diagram()
        e = find_entity_by_uid(d.doc, uid)
        if e is None:
            self._user_sk_kind = ""
            self._usk_row_lt.hide()
            self._usk_row_txt.hide()
            self._usk_row_pitch.hide()
            self._stack.setCurrentIndex(self._USER_SK)
            return
        t = str(entity_type).strip().upper()
        if t == ENTITY_TYPE_USER_LINE:
            self._user_sk_kind = "line"
            self._usk_row_lt.show()
            self._usk_row_txt.hide()
            self._usk_row_pitch.hide()
            lt = user_sketch_display_linetype_for_entity(e)
            i = self._wire_linetype_combo_index(self._usk_lt, lt)
            self._usk_lt.setCurrentIndex(i if i >= 0 else 0)
        elif t == ENTITY_TYPE_USER_CIRCLE:
            self._user_sk_kind = "circle"
            self._usk_row_lt.show()
            self._usk_row_txt.hide()
            self._usk_row_pitch.hide()
            lt = user_sketch_display_linetype_for_entity(e)
            i = self._wire_linetype_combo_index(self._usk_lt, lt)
            self._usk_lt.setCurrentIndex(i if i >= 0 else 0)
        elif t == ENTITY_TYPE_USER_CLOUD:
            self._user_sk_kind = "cloud"
            self._usk_row_lt.show()
            self._usk_row_txt.hide()
            self._usk_row_pitch.show()
            lt = user_sketch_display_linetype_for_entity(e)
            i = self._wire_linetype_combo_index(self._usk_lt, lt)
            self._usk_lt.setCurrentIndex(i if i >= 0 else 0)
            self._usk_pitch.setValue(d.get_user_cloud_pitch_display_mm(uid))
        elif t == ENTITY_TYPE_USER_TEXT:
            self._user_sk_kind = "text"
            self._usk_row_lt.hide()
            self._usk_row_txt.show()
            self._usk_row_pitch.hide()
            self._usk_txt.setText(str(getattr(e.dxf, "text", "") or ""))
            try:
                h = float(getattr(e.dxf, "height", 4.0) or 4.0)
            except (TypeError, ValueError):
                h = 4.0
            self._usk_h.setValue(max(0.25, h))
            ha = int(getattr(e.dxf, "halign", 0) or 0)
            if ha not in (0, 1, 2):
                ha = 0
            hi = self._usk_halign.findData(ha)
            self._usk_halign.setCurrentIndex(hi if hi >= 0 else 0)
        else:
            self._user_sk_kind = ""
            self._usk_row_lt.hide()
            self._usk_row_txt.hide()
            self._usk_row_pitch.hide()
        self._stack.setCurrentIndex(self._USER_SK)

    @staticmethod
    def _wire_linetype_combo_index(combo: QComboBox, linetype: str) -> int:
        want = (linetype or "").strip().upper()
        for j in range(combo.count()):
            data = combo.itemData(j)
            if data is not None and str(data).strip().upper() == want:
                return j
            if combo.itemText(j).strip().upper() == want:
                return j
        return -1

    @staticmethod
    def _page_ref_target_caption(doc, layout_name: str) -> str:
        name = (layout_name or "").strip()
        if not name:
            return "—"
        meta = read_page_meta(doc, name)
        desc = (meta.get("page_desc") or "").strip()
        return f"{name}:{desc}" if desc else name

    def _refresh_page_ref_target_label(self) -> None:
        d = self._get_diagram()
        if not (self._page_ref_target_layout or "").strip():
            self._page_target_label.setText("—")
            return
        self._page_target_label.setText(
            self._page_ref_target_caption(d.doc, self._page_ref_target_layout)
        )

    def _on_page_ref_rank_combo_changed(self, _index: int) -> None:
        self._sync_page_ref_sym_preview_from_rank_combo()

    def _sync_page_ref_sym_preview_from_rank_combo(self) -> None:
        tgt = (self._page_ref_target_layout or "").strip()
        if not tgt:
            return
        raw = self._page_ref_rank_combo.currentData()
        if raw is None:
            return
        self._sym_page.setText(page_ref_link_label(tgt, int(raw)))

    def _clear_label_forms(self) -> None:
        self._label_edits.clear()
        for form in (self._sym_label_form, self._gate_label_form):
            while form.rowCount() > 0:
                form.removeRow(0)

    def _populate_label_fields(self, form: QFormLayout, block_name: str) -> None:
        self._clear_label_forms()
        if not block_name or not self._uid:
            return
        d = self._get_diagram()
        tags = list_editable_text_attdef_tags(d.doc, block_name)
        if not tags:
            return
        ins = d.symbols.insert_by_uid(d.current_layout_name, self._uid)
        blk = d.doc.blocks.get(block_name)
        for tag in tags:
            val = ""
            want = str(tag).upper()
            if ins:
                for a in ins.attribs:
                    if str(a.dxf.tag).upper() == want:
                        val = str(a.dxf.text or "")
                        break
            if not val and blk is not None:
                for ent in blk:
                    if ent.dxftype() == "ATTDEF" and str(ent.dxf.tag).upper() == want:
                        val = str(ent.dxf.text or "")
                        break
            edit = QLineEdit()
            edit.setText(val)
            self._label_edits[tag] = edit
            form.addRow(tag, edit)

    def _apply_optional_symbol_fields(self, d, sym_text: str, sym_visible: bool) -> None:
        d.set_symbol_attr(self._uid, "SYM", sym_text)
        d.set_attrib_visible(self._uid, "SYM", sym_visible)
        for tag, ed in self._label_edits.items():
            d.set_symbol_attr(self._uid, tag, ed.text())

    def _apply_symbol_only(self) -> None:
        if not self._uid:
            return
        d = self._get_diagram()
        try:
            with d.begin("props"):
                self._apply_optional_symbol_fields(
                    d,
                    self._sym_only.text(),
                    self._sym_show_only.isChecked(),
                )
        except Exception as ex:
            QMessageBox.warning(self, "プロパティ", str(ex) or "適用に失敗しました。")
            return
        self._on_applied()

    def _apply_gate(self) -> None:
        if not self._uid:
            return
        d = self._get_diagram()
        try:
            with d.begin("props"):
                self._apply_optional_symbol_fields(
                    d,
                    self._sym_gate.text(),
                    self._sym_show_gate.isChecked(),
                )
                d.set_gate_show_input_stub_in_arrow(self._uid, self._gate_stub_in_arrow.isChecked())
        except Exception as ex:
            QMessageBox.warning(self, "プロパティ", str(ex) or "適用に失敗しました。")
            return
        self._on_applied()

    def _optimize_gate_inputs(self) -> None:
        if not self._uid:
            return
        d = self._get_diagram()
        try:
            with d.begin("optimize_inputs"):
                d.optimize_and_or_input_ports(self._uid)
        except Exception as ex:
            QMessageBox.warning(self, "入力最適化", str(ex) or "最適化に失敗しました。")
            return
        self._on_applied()

    def _apply_page_ref(self) -> None:
        if not self._uid:
            return
        d = self._get_diagram()
        if not (self._page_ref_target_layout or "").strip():
            QMessageBox.warning(self, "プロパティ", "リンク先ページがありません。")
            return
        rkw = self._page_ref_rank_combo.currentData()
        if rkw is None:
            QMessageBox.warning(self, "プロパティ", "付番を選択してください。")
            return
        try:
            with d.begin("props"):
                d.set_page_ref_rank(self._uid, int(rkw))
                d.set_page_ref_target_info_visibility(
                    self._uid,
                    show_page_name=self._page_show_page_name.isChecked(),
                    show_page_desc=self._page_show_page_desc.isChecked(),
                )
        except Exception as ex:
            QMessageBox.warning(self, "プロパティ", str(ex) or "適用に失敗しました。")
            return
        self._on_applied()

    def _apply_inpage_ref(self) -> None:
        if not self._uid:
            return
        d = self._get_diagram()
        try:
            with d.begin("props"):
                d.set_inpage_sym_height(self._uid, float(self._inpage_sym_height_mm.value()))
        except Exception as ex:
            QMessageBox.warning(self, "プロパティ", str(ex) or "適用に失敗しました。")
            return
        self._on_applied()

    def _apply_user_sketch(self) -> None:
        if not self._user_sk_uid:
            return
        d = self._get_diagram()
        try:
            with d.begin("props"):
                if self._user_sk_kind == "text":
                    ha_raw = self._usk_halign.currentData()
                    ha = int(ha_raw) if ha_raw is not None else 0
                    ok = d.set_user_sketch_text(
                        self._user_sk_uid,
                        self._usk_txt.text(),
                        self._usk_h.value(),
                        halign=ha,
                    )
                    if not ok:
                        raise ValueError("テキストの更新に失敗しました。")
                elif self._user_sk_kind in ("line", "circle", "cloud"):
                    ok = d.set_user_sketch_linetype(self._user_sk_uid, self._usk_lt.currentText())
                    if not ok:
                        raise ValueError("線種の更新に失敗しました。")
                    if self._user_sk_kind == "cloud":
                        ok_p = d.set_user_cloud_pitch_mm(self._user_sk_uid, float(self._usk_pitch.value()))
                        if not ok_p:
                            raise ValueError("雲マークのピッチ更新に失敗しました。")
                else:
                    return
        except Exception as ex:
            QMessageBox.warning(self, "プロパティ", str(ex) or "適用に失敗しました。")
            return
        self._on_applied()

    def _sync_be_port_layer_preview(self) -> None:
        try:
            lyr = make_port_layer_name(
                self._be_port_dir.currentText(),
                int(self._be_port_idx.value()),
                self._be_port_unit.currentText(),
            )
        except ValueError:
            lyr = "—"
        self._be_port_layer_preview.setText(lyr)

    def _apply_block_edit_port(self) -> None:
        if self._get_block_edit_session is None or self._on_block_scratch_applied is None:
            return
        sess = self._get_block_edit_session()
        if sess is None:
            return
        blk = sess.scratch_block()
        if blk is None or not self._be_port_edit_handle:
            return
        try:
            lyr = make_port_layer_name(
                self._be_port_dir.currentText(),
                int(self._be_port_idx.value()),
                self._be_port_unit.currentText(),
            )
        except ValueError as ex:
            QMessageBox.warning(self, "プロパティ", str(ex) or "無効なポート属性です。")
            return
        try:
            with sess.begin("block_edit_prop_port_layer"):
                update_scratch_port_layer(blk, self._be_port_edit_handle, lyr)
        except Exception as ex:
            QMessageBox.warning(self, "プロパティ", str(ex) or "適用に失敗しました。")
            return
        self._on_block_scratch_applied()

    def _apply_block_edit_linetype(self) -> None:
        if self._get_block_edit_session is None or self._on_block_scratch_applied is None:
            return
        sess = self._get_block_edit_session()
        if sess is None:
            return
        blk = sess.scratch_block()
        if blk is None:
            return
        doc = sess.scratch_doc
        lt = self._be_geom_lt.currentText()
        subj = self._be_geom_lt_subject
        try:
            if subj == "native_line":
                with sess.begin("block_edit_prop_linetype"):
                    ok = set_native_line_linetype_in_block(blk, self._be_geom_lt_handle, lt)
                if not ok:
                    raise ValueError("線種の更新に失敗しました。")
            elif subj == "user_sketch" and self._be_geom_lt_sketch_uid:
                with sess.begin("block_edit_prop_linetype"):
                    ok = set_scratch_user_sketch_linetype(doc, self._be_geom_lt_sketch_uid, lt)
                if not ok:
                    raise ValueError("線種の更新に失敗しました。")
            else:
                return
        except Exception as ex:
            QMessageBox.warning(self, "プロパティ", str(ex) or "適用に失敗しました。")
            return
        self._on_block_scratch_applied()

    def _apply_block_edit_attdef(self) -> None:
        if self._get_block_edit_session is None or self._on_block_scratch_applied is None:
            return
        sess = self._get_block_edit_session()
        if sess is None:
            return
        blk = sess.scratch_block()
        if blk is None or not self._be_attdef_handle:
            return
        tag = self._be_att_tag.currentText().strip()
        try:
            with sess.begin("block_edit_prop_attdef"):
                ha_raw = self._be_att_halign.currentData()
                ha = int(ha_raw) if ha_raw is not None else 0
                update_scratch_attdef_fields(
                    blk,
                    self._be_attdef_handle,
                    tag=tag,
                    default_text=self._be_att_default.text(),
                    halign=ha,
                    height_mm=float(self._be_att_h.value()),
                )
        except Exception as ex:
            QMessageBox.warning(self, "プロパティ", str(ex) or "適用に失敗しました。")
            return
        self._on_block_scratch_applied()

    def _apply_wire(self) -> None:
        if not self._wire_uid:
            return
        d = self._get_diagram()
        try:
            with d.begin("props"):
                d.set_wire_skip_auto_reroute(self._wire_uid, self._wire_manual.isChecked())
                d.set_wire_show_in_arrow(self._wire_uid, self._wire_in_arrow.isChecked())
                d.set_wire_allow_orthogonal_cross(
                    self._wire_uid, self._wire_allow_orthogonal.isChecked()
                )
                lt = self._wire_lt.currentData()
                if lt is None:
                    lt = self._wire_lt.currentText()
                d.set_wire_linetype(self._wire_uid, str(lt))
        except Exception as ex:
            QMessageBox.warning(self, "プロパティ", str(ex) or "適用に失敗しました。")
            return
        self._on_applied()
