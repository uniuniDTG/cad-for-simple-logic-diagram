"""Symbol, gate, page-reference, and in-page link property pages.

This mixin expects the host ``PropertyPanel`` widget to expose label/port forms,
``_get_diagram``, ``_on_applied``, ``_clear_label_forms``, ``_populate_port_rows``,
and shared selection fields such as ``_uid``.
"""

from __future__ import annotations

from logic_cad.core.model.constants import ENTITY_TYPE_INPAGE_REF, INPAGE_SYM_HEIGHT_MM
from logic_cad.core.pages.page_labels import page_index_to_letters, page_ref_link_label
from logic_cad.core.pages.page_layout_meta import read_page_meta
from logic_cad.core.pages.page_ref import (
    page_ref_allowed_sym_ordinals_for_property_edit,
    page_ref_ordinal_for_uid,
    page_ref_stored_rank,
)

from logic_cad.ui.panels.property_panel.helpers import show_apply_warning, show_property_panel_warning


class PropertyPanelSymbolSection:
    """Mixin: INSERT-facing symbol metadata, ports, gates, and page links."""

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
        link_name_auto: bool = True,
        sym_height_mm: float = INPAGE_SYM_HEIGHT_MM,
        block_name: str = "",
        entity_type: str = ENTITY_TYPE_INPAGE_REF,
    ) -> None:
        """INPAGE_REF: peer, link label (auto or manual), and editable SYM height (mm).

        Args:
            uid: INSERT uid.
            peer_uid: Peer INSERT uid or empty when unlinked.
            sym: Current link label text (``sym`` / ATTRIB SYM).
            link_name_auto: When True, label is renumbered by refresh among auto pairs.
            sym_height_mm: SYM attrib height in mm.
            block_name: Block reference name.
            entity_type: XDATA type string.
        """
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
        self._inpage_link_name_auto.blockSignals(True)
        self._inpage_link_name_auto.setChecked(bool(link_name_auto))
        self._inpage_link_name_auto.blockSignals(False)
        self._inpage_sym_display.setText(sym or "")
        self._inpage_sym_display.setReadOnly(bool(link_name_auto))
        self._inpage_sym_height_mm.setValue(float(sym_height_mm))
        self._stack.setCurrentIndex(self._INPAGE)

    @staticmethod
    def _page_ref_target_caption(doc, layout_name: str) -> str:
        """Compose the page picker caption from layout meta (name + optional description)."""
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
            show_apply_warning(self, "プロパティ", ex)
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
            show_apply_warning(self, "プロパティ", ex)
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
            show_apply_warning(self, "入力最適化", ex, fallback="最適化に失敗しました。")
            return
        self._on_applied()

    def _apply_page_ref(self) -> None:
        if not self._uid:
            return
        d = self._get_diagram()
        if not (self._page_ref_target_layout or "").strip():
            show_property_panel_warning(self, "プロパティ", "リンク先ページがありません。")
            return
        rkw = self._page_ref_rank_combo.currentData()
        if rkw is None:
            show_property_panel_warning(self, "プロパティ", "付番を選択してください。")
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
            show_apply_warning(self, "プロパティ", ex)
            return
        self._on_applied()

    def _on_inpage_link_name_auto_toggled(self, checked: bool) -> None:
        """When auto-numbering is on, the link label field is read-only (preview only)."""
        self._inpage_sym_display.setReadOnly(bool(checked))

    def _apply_inpage_ref(self) -> None:
        if not self._uid:
            return
        d = self._get_diagram()
        try:
            with d.begin("props"):
                d.set_inpage_ref_link_display(
                    self._uid,
                    link_name_auto=self._inpage_link_name_auto.isChecked(),
                    display_text=self._inpage_sym_display.text(),
                )
                d.set_inpage_sym_height(self._uid, float(self._inpage_sym_height_mm.value()))
        except Exception as ex:
            show_apply_warning(self, "プロパティ", ex)
            return
        self._on_applied()
