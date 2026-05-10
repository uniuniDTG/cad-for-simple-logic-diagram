"""Wire, branch hub, checkpoint, and user-sketch property pages.

This mixin composes into ``PropertyPanel`` and relies on the host widget for
stack indices, ``_get_diagram``, ``_on_applied``, ``_clear_label_forms``, and
shared helpers such as ``_peer_display``.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QLabel

from logic_cad.core.model.constants import (
    ENTITY_TYPE_USER_ARC,
    ENTITY_TYPE_USER_CIRCLE,
    ENTITY_TYPE_USER_CLOUD,
    ENTITY_TYPE_USER_LINE,
    ENTITY_TYPE_USER_TEXT,
    WIRE_XDATA_SHOW_IN_ARROW,
)
from logic_cad.core.model.port_key import is_inout_port_key, is_input_port_key, is_output_port_key
from logic_cad.core.model.user_sketch_layers import user_sketch_display_linetype_for_entity
from logic_cad.core.model.wire_port_helpers import (
    wire_allows_orthogonal_cross,
    wire_skips_auto_reroute,
)
from logic_cad.core.model.xdata import read_ld_app_dict
from logic_cad.core.uid_display import format_uid_display
from logic_cad.core.undo.history import find_entity_by_uid

from logic_cad.ui.panels.property_panel.helpers import show_apply_warning


class PropertyPanelWireSection:
    """Mixin: diagram wiring and freehand sketch property UI + apply paths."""

    def _ld_port_starts_with_in(self, port: str) -> bool:
        return is_input_port_key(port)

    def _ld_port_starts_with_out(self, port: str) -> bool:
        return is_output_port_key(port)

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
        elif t == ENTITY_TYPE_USER_ARC:
            self._user_sk_kind = "arc"
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
        """Resolve a schematic linetype name to a combo index (data preferred)."""
        want = (linetype or "").strip().upper()
        for j in range(combo.count()):
            data = combo.itemData(j)
            if data is not None and str(data).strip().upper() == want:
                return j
            if combo.itemText(j).strip().upper() == want:
                return j
        return -1

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
                elif self._user_sk_kind in ("line", "circle", "arc", "cloud"):
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
            show_apply_warning(self, "プロパティ", ex)
            return
        self._on_applied()

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
            show_apply_warning(self, "プロパティ", ex)
            return
        self._on_applied()
