"""Coordinating ``PropertyPanel`` widget construction and shared port/label helpers."""

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
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from logic_cad.core.attrib_tags import list_editable_text_attdef_tags
from logic_cad.core.model.constants import INPAGE_LINK_DISPLAY_MAX_LEN, LINETYPE_COM, LINETYPE_LOGIC, LINETYPE_VALUE
from logic_cad.core.uid_display import format_uid_display

from logic_cad.ui.panels.property_panel.block_edit_section import PropertyPanelBlockEditSection
from logic_cad.ui.panels.property_panel.helpers import port_sort_key
from logic_cad.ui.panels.property_panel.symbol_section import PropertyPanelSymbolSection
from logic_cad.ui.panels.property_panel.wire_section import PropertyPanelWireSection

if TYPE_CHECKING:
    from logic_cad.core.logic_diagram import LogicDiagram
    from logic_cad.core.services.block_edit_session import BlockEditSession


class PropertyPanel(
    QWidget,
    PropertyPanelSymbolSection,
    PropertyPanelWireSection,
    PropertyPanelBlockEditSection,
):
    """Contextual properties: only fields relevant to the current selection.

    UI pages are built once in ``__init__``; behavioral blocks live in section
    mixins (symbols, wiring, block-edit scratch) to keep this coordinator file
    approachable while preserving a single public widget type.
    """

    _NONE, _MULTI, _SYM, _GATE, _PAGE, _INPAGE, _WIRE, _WIRE_BRANCH, _USER_SK, _BLOCK_PORT, _BLOCK_GEOM, _BLOCK_ATTDEF, _BLOCK_PLAIN_TEXT = range(
        13
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
        self._be_plain_text_handle: str = ""
        self._be_plain_text_is_mtext: bool = False
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
        fs_meta = QFormLayout()
        self._sym_meta_uid = QLineEdit()
        self._sym_meta_uid.setReadOnly(True)
        self._sym_meta_block = QLineEdit()
        self._sym_meta_block.setReadOnly(True)
        self._sym_meta_type = QLineEdit()
        self._sym_meta_type.setReadOnly(True)
        fs_meta.addRow("UUID", self._sym_meta_uid)
        fs_meta.addRow("ブロック名", self._sym_meta_block)
        fs_meta.addRow("タイプ", self._sym_meta_type)
        sym_outer.addLayout(fs_meta)
        self._sym_label_section = QWidget()
        self._sym_label_form = QFormLayout(self._sym_label_section)
        sym_outer.addWidget(QLabel("ラベル (ATTDEF: LABEL0 …)"))
        sym_outer.addWidget(self._sym_label_section)
        fs_sym = QFormLayout()
        self._sym_only = QLineEdit()
        self._sym_show_only = QCheckBox()
        self._sym_show_only.setChecked(False)
        btn_sym = QPushButton("適用")
        btn_sym.clicked.connect(self._apply_symbol_only)
        fs_sym.addRow("SYM", self._sym_only)
        fs_sym.addRow("SYM を表示", self._sym_show_only)
        fs_sym.addRow(btn_sym)
        sym_outer.addLayout(fs_sym)
        sym_outer.addWidget(QLabel("ポート接続"))
        self._sym_ports_wrap = QWidget()
        self._sym_ports_form = QFormLayout(self._sym_ports_wrap)
        sym_outer.addWidget(self._sym_ports_wrap)
        sym_outer.addStretch()

        self._page_gate = QWidget()
        gate_outer = QVBoxLayout(self._page_gate)
        gate_outer.setContentsMargins(0, 0, 0, 0)
        fg_meta = QFormLayout()
        self._gate_meta_uid = QLineEdit()
        self._gate_meta_uid.setReadOnly(True)
        self._gate_meta_block = QLineEdit()
        self._gate_meta_block.setReadOnly(True)
        self._gate_meta_type = QLineEdit()
        self._gate_meta_type.setReadOnly(True)
        fg_meta.addRow("UUID", self._gate_meta_uid)
        fg_meta.addRow("ブロック名", self._gate_meta_block)
        fg_meta.addRow("タイプ", self._gate_meta_type)
        gate_outer.addLayout(fg_meta)
        fg_gate_fields = QFormLayout()
        self._sym_gate = QLineEdit()
        self._sym_show_gate = QCheckBox()
        self._sym_show_gate.setChecked(False)
        self._gate_stub_in_arrow = QCheckBox()
        self._gate_n_display = QLabel()
        self._gate_n_display.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        fg_gate_fields.addRow("SYM", self._sym_gate)
        fg_gate_fields.addRow("SYM を表示", self._sym_show_gate)
        fg_gate_fields.addRow("矢印 を表示", self._gate_stub_in_arrow)
        fg_gate_fields.addRow("入力ポート数", self._gate_n_display)
        gate_outer.addLayout(fg_gate_fields)
        self._gate_label_section = QWidget()
        self._gate_label_form = QFormLayout(self._gate_label_section)
        gate_outer.addWidget(QLabel("ラベル (ATTDEF: LABEL0 …)"))
        gate_outer.addWidget(self._gate_label_section)
        fg_gate_actions = QFormLayout()
        btn_gate = QPushButton("適用")
        btn_gate.clicked.connect(self._apply_gate)
        fg_gate_actions.addRow(btn_gate)
        self._btn_optimize_inputs = QPushButton("入力ポートの配線を最適化")
        self._btn_optimize_inputs.setToolTip(
            "入力を割り当て直し配線を再計算します。"
        )
        self._btn_optimize_inputs.clicked.connect(self._optimize_gate_inputs)
        fg_gate_actions.addRow(self._btn_optimize_inputs)
        gate_outer.addLayout(fg_gate_actions)
        gate_outer.addWidget(QLabel("ポート接続"))
        self._gate_ports_wrap = QWidget()
        self._gate_ports_form = QFormLayout(self._gate_ports_wrap)
        gate_outer.addWidget(self._gate_ports_wrap)
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
        self._inpage_link_name_auto = QCheckBox("自動採番（*1, *2, …）")
        self._inpage_link_name_auto.setChecked(True)
        self._inpage_link_name_auto.toggled.connect(self._on_inpage_link_name_auto_toggled)
        self._inpage_sym_display = QLineEdit()
        self._inpage_sym_display.setReadOnly(True)
        self._inpage_sym_display.setMaxLength(INPAGE_LINK_DISPLAY_MAX_LEN)
        fin.addRow("UUID", self._inpage_meta_uid)
        fin.addRow("ブロック名", self._inpage_meta_block)
        fin.addRow("タイプ", self._inpage_meta_type)
        fin.addRow("相手 UUID", self._inpage_peer_uid)
        fin.addRow(self._inpage_link_name_auto)
        fin.addRow("表示（リンク名）", self._inpage_sym_display)
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

        self._page_block_plain_text = QWidget()
        fbpt = QFormLayout(self._page_block_plain_text)
        self._be_pt_block = QLineEdit()
        self._be_pt_block.setReadOnly(True)
        self._be_pt_handle = QLineEdit()
        self._be_pt_handle.setReadOnly(True)
        self._be_pt_kind = QLineEdit()
        self._be_pt_kind.setReadOnly(True)
        self._be_pt_line = QLineEdit()
        self._be_pt_plain = QPlainTextEdit()
        self._be_pt_plain.setMinimumHeight(72)
        self._be_pt_h = QDoubleSpinBox()
        self._be_pt_h.setRange(0.25, 80.0)
        self._be_pt_h.setSingleStep(0.25)
        self._be_pt_h.setSuffix(" mm")
        self._be_pt_rot = QDoubleSpinBox()
        self._be_pt_rot.setRange(-360.0, 360.0)
        self._be_pt_rot.setDecimals(2)
        self._be_pt_rot.setSuffix(" °")
        self._be_pt_halign = QComboBox()
        self._be_pt_halign.addItem("左", 0)
        self._be_pt_halign.addItem("中央", 1)
        self._be_pt_halign.addItem("右", 2)
        self._be_pt_width = QDoubleSpinBox()
        self._be_pt_width.setRange(0.0, 800.0)
        self._be_pt_width.setSingleStep(1.0)
        self._be_pt_width.setSuffix(" mm")
        self._be_pt_width.setSpecialValueText("0 = 幅指定なし")
        self._be_pt_attach = QComboBox()
        for ap, label in (
            (1, "1 左上"),
            (2, "2 上中央"),
            (3, "3 右上"),
            (4, "4 左中"),
            (5, "5 中央"),
            (6, "6 右中"),
            (7, "7 左下"),
            (8, "8 下中央"),
            (9, "9 右下"),
        ):
            self._be_pt_attach.addItem(label, ap)
        self._be_pt_apply = QPushButton("適用")
        self._be_pt_apply.clicked.connect(self._apply_block_edit_plain_text)
        fbpt.addRow("ブロック", self._be_pt_block)
        fbpt.addRow("ハンドル", self._be_pt_handle)
        fbpt.addRow("タイプ", self._be_pt_kind)
        fbpt.addRow("文字列（TEXT）", self._be_pt_line)
        fbpt.addRow("本文（MTEXT）", self._be_pt_plain)
        fbpt.addRow("字高", self._be_pt_h)
        fbpt.addRow("回転", self._be_pt_rot)
        self._be_pt_halign_wrap = QWidget()
        fph = QFormLayout(self._be_pt_halign_wrap)
        fph.setContentsMargins(0, 0, 0, 0)
        fph.addRow("水平揃え", self._be_pt_halign)
        fbpt.addRow(self._be_pt_halign_wrap)
        self._be_pt_mtext_wrap = QWidget()
        fpm = QFormLayout(self._be_pt_mtext_wrap)
        fpm.setContentsMargins(0, 0, 0, 0)
        fpm.addRow("折り返し幅", self._be_pt_width)
        fpm.addRow("取付点", self._be_pt_attach)
        fbpt.addRow(self._be_pt_mtext_wrap)
        fbpt.addRow(self._be_pt_apply)

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
            self._page_block_plain_text,
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
        """Remove dynamic rows while leaving the owning ``QWidget`` intact."""
        while form.rowCount() > 0:
            form.removeRow(0)

    @staticmethod
    def _clear_form(form: QFormLayout) -> None:
        """Remove all rows from a generic stacked form."""
        while form.rowCount() > 0:
            form.removeRow(0)

    @staticmethod
    def _set_readonly_uid_field(edit: QLineEdit, full_uid: str) -> None:
        """Populate a shortened UUID edit with tooltip for the authoritative id."""
        edit.setText(format_uid_display(full_uid))
        edit.setToolTip(full_uid)

    def _peer_display(self, d: LogicDiagram, uid: str | None) -> tuple[str, str]:
        """Return (short label text, tooltip = full UUID) for wiring summaries."""
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
        """Render read-only QLabel rows explaining each logical port attachment."""
        self._clear_port_form(form)
        d = self._get_diagram()
        idx = d.index
        ports = [pk for (u, pk) in idx.ports if u == uid]
        ports.sort(key=port_sort_key)
        for pk in ports:
            peer = d.wires.peer_for_symbol_port(d.current_layout_name, uid, pk)
            if peer:
                pu, pp = peer
                body, tip = self._peer_display(d, pu)
                # 表示が邪魔なので、一旦削除
                #if pp:
                #    body = f"{body}\n相手ポート: {pp}"
            else:
                body, tip = "未接続", ""
            lab = QLabel(body)
            lab.setWordWrap(True)
            lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            if tip:
                lab.setToolTip(tip)
            form.addRow(pk, lab)

    def _emit_align(self, mode: str) -> None:
        """Forward multi-select alignment intents to main window tooling."""
        if self._on_align_selected is not None:
            self._on_align_selected(mode)

    def clear_selection(self) -> None:
        """Reset cached editor state and reveal the idle placeholder stack page."""
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
        self._be_plain_text_handle = ""
        self._be_plain_text_is_mtext = False
        self._be_port_edit_handle = ""
        self._stack.setCurrentIndex(self._NONE)

    def show_multi(self, n: int) -> None:
        """Show count message plus alignment presets for multi-insert picks."""
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
        self._be_plain_text_handle = ""
        self._be_plain_text_is_mtext = False
        self._be_port_edit_handle = ""
        self._multi_label.setText(f"{n} 個のアイテムが選択されています。")
        self._stack.setCurrentIndex(self._MULTI)

    def _clear_label_forms(self) -> None:
        """Remove dynamic ATTDEF LABEL rows tracked in ``self._label_edits``."""
        self._label_edits.clear()
        for form in (self._sym_label_form, self._gate_label_form):
            while form.rowCount() > 0:
                form.removeRow(0)

    def _populate_label_fields(self, form: QFormLayout, block_name: str) -> None:
        """Create editable LABEL* rows reflecting current ``self._uid`` attribs."""
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
