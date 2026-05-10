"""Block-edit scratch property rows (port geometry, ATTDEF, TEXT/MTEXT, linetype).

This mixin is composed into ``PropertyPanel`` and expects ``__init__`` on the host
widget to have created the ``_be_*`` controls and wired ``_get_block_edit_session`` /
``_on_block_scratch_applied`` callbacks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from logic_cad.core.attrib_tags import symbol_editor_attdef_tag_choices_for_block
from logic_cad.core.model.port_key import parse_port_layer
from logic_cad.core.services.block_edit_helpers import (
    make_port_layer_name,
    set_native_line_linetype_in_block,
    set_scratch_user_sketch_linetype,
    update_scratch_attdef_fields,
    update_scratch_mtext_fields,
    update_scratch_port_layer,
    update_scratch_text_fields,
)

from logic_cad.ui.panels.property_panel.helpers import show_apply_warning

if TYPE_CHECKING:
    from logic_cad.core.services.block_edit_session import BlockEditSession


class PropertyPanelBlockEditSection:
    """Mixin: scratch block-editor apply handlers and stacked property pages."""

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
        self._be_plain_text_handle = ""
        self._be_plain_text_is_mtext = False
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
        self._be_plain_text_handle = ""
        self._be_plain_text_is_mtext = False
        self._be_attdef_handle = str(handle or "")
        self._be_att_block.setText(block_name or "—")
        self._be_att_handle.setText(handle or "—")
        tag_choices = symbol_editor_attdef_tag_choices_for_block(block_name or "")
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

    def show_block_edit_scratch_text(
        self,
        *,
        block_name: str,
        handle: str,
        is_mtext: bool,
        text: str,
        height_mm: float,
        rotation_deg: float,
        halign: int = 0,
        width_mm: float = 0.0,
        attachment_point: int = 1,
    ) -> None:
        """Show block-editor properties for a scratch ``TEXT`` or ``MTEXT`` entity."""

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
        self._be_plain_text_handle = str(handle or "")
        self._be_plain_text_is_mtext = bool(is_mtext)
        self._be_pt_block.setText(block_name or "—")
        self._be_pt_handle.setText(handle or "—")
        self._be_pt_kind.setText("MTEXT" if is_mtext else "TEXT")
        self._be_pt_line.setText("" if is_mtext else str(text))
        self._be_pt_plain.setPlainText("" if not is_mtext else str(text))
        self._be_pt_line.setVisible(not is_mtext)
        self._be_pt_plain.setVisible(is_mtext)
        self._be_pt_halign_wrap.setVisible(not is_mtext)
        self._be_pt_mtext_wrap.setVisible(is_mtext)
        try:
            hh = float(height_mm)
        except (TypeError, ValueError):
            hh = 2.5
        self._be_pt_h.setValue(max(0.25, hh))
        try:
            rot = float(rotation_deg)
        except (TypeError, ValueError):
            rot = 0.0
        self._be_pt_rot.setValue(rot)
        ha = int(halign)
        if ha not in (0, 1, 2):
            ha = 0
        hi = self._be_pt_halign.findData(ha)
        self._be_pt_halign.setCurrentIndex(hi if hi >= 0 else 0)
        try:
            ww = float(width_mm)
        except (TypeError, ValueError):
            ww = 0.0
        self._be_pt_width.setValue(max(0.0, ww))
        ap = int(attachment_point)
        if ap < 1 or ap > 9:
            ap = 1
        aix = self._be_pt_attach.findData(ap)
        self._be_pt_attach.setCurrentIndex(aix if aix >= 0 else 0)
        self._stack.setCurrentIndex(self._BLOCK_PLAIN_TEXT)

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
        sess: BlockEditSession | None = self._get_block_edit_session()
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
            show_apply_warning(self, "プロパティ", ex, fallback="無効なポート属性です。")
            return
        try:
            with sess.begin("block_edit_prop_port_layer"):
                update_scratch_port_layer(blk, self._be_port_edit_handle, lyr)
        except Exception as ex:
            show_apply_warning(self, "プロパティ", ex)
            return
        self._on_block_scratch_applied()

    def _apply_block_edit_linetype(self) -> None:
        if self._get_block_edit_session is None or self._on_block_scratch_applied is None:
            return
        sess: BlockEditSession | None = self._get_block_edit_session()
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
            show_apply_warning(self, "プロパティ", ex)
            return
        self._on_block_scratch_applied()

    def _apply_block_edit_attdef(self) -> None:
        if self._get_block_edit_session is None or self._on_block_scratch_applied is None:
            return
        sess: BlockEditSession | None = self._get_block_edit_session()
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
            show_apply_warning(self, "プロパティ", ex)
            return
        self._on_block_scratch_applied()

    def _apply_block_edit_plain_text(self) -> None:
        if self._get_block_edit_session is None or self._on_block_scratch_applied is None:
            return
        sess: BlockEditSession | None = self._get_block_edit_session()
        if sess is None:
            return
        blk = sess.scratch_block()
        if blk is None or not self._be_plain_text_handle:
            return
        try:
            if self._be_plain_text_is_mtext:
                with sess.begin("block_edit_prop_mtext"):
                    update_scratch_mtext_fields(
                        blk,
                        self._be_plain_text_handle,
                        plain_text=self._be_pt_plain.toPlainText(),
                        char_height_mm=float(self._be_pt_h.value()),
                        rotation_deg=float(self._be_pt_rot.value()),
                        width_mm=float(self._be_pt_width.value()),
                        attachment_point=int(self._be_pt_attach.currentData() or 1),
                    )
            else:
                with sess.begin("block_edit_prop_text"):
                    ha_raw = self._be_pt_halign.currentData()
                    ha = int(ha_raw) if ha_raw is not None else 0
                    update_scratch_text_fields(
                        blk,
                        self._be_plain_text_handle,
                        text=self._be_pt_line.text(),
                        height_mm=float(self._be_pt_h.value()),
                        rotation_deg=float(self._be_pt_rot.value()),
                        halign=ha,
                    )
        except Exception as ex:
            show_apply_warning(self, "プロパティ", ex)
            return
        self._on_block_scratch_applied()
