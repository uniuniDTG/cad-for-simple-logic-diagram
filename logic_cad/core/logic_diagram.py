"""Public facade for logic diagram editing."""

from __future__ import annotations

import logging
import re
import time

from ezdxf.document import Drawing

from logic_cad.core.debug.debug_log import logic_cad_debug_enabled, logic_cad_log
from logic_cad.core.debug.routing_perf import routing_perf_span
from logic_cad.core.routing import FAST_MOVE_REROUTE_PROFILE, RoutingProfile, snap_to_grid
from logic_cad.core.model.constants import (
    BLOCK_CHECKPOINT,
    FIRST_PAGE_NAME,
    ENTITY_TYPE_INPAGE_REF,
    ENTITY_TYPE_TOC_HEADER,
    ENTITY_TYPE_TOC_ROW,
    ENTITY_TYPE_WIRE_BRANCH,
    PEER_UID_XDATA,
    TOC_LAYOUT_NAME,
)
from logic_cad.core.model.document_meta import (
    read_project_preferred_font_family,
    set_project_preferred_font_family as write_project_preferred_font_family_to_doc,
)
from logic_cad.core.graph.port_src_dst_solver import (
    WireFlip,
    normalize_wire_endpoints_with_deps,
)
from logic_cad.core.dxf.dxf_repository import new_document, readfile, saveas
from logic_cad.core.dxf.dxf_validator import validate as validate_document
from logic_cad.core.undo.history import HistoryService, destroy_entity, find_entity_by_uid
from logic_cad.core.pages.page_order import is_toc_layout_name
from logic_cad.core.pages.inpage_ref import refresh_inpage_ref_syms_on_layout
from logic_cad.core.pages.page_ref import (
    apply_ordered_page_ref_ranks_with_peers,
    layout_name_for_insert,
    refresh_all_page_ref_syms,
    refresh_page_ref_syms_on_layout,
)
from logic_cad.core.model.index_store import IndexStore
from logic_cad.core.services.dynamic_gate_factory import DynamicGateFactory
from logic_cad.core.services.layout_service import LayoutService, import_symbol_library
from logic_cad.core.services.symbol_service import SymbolService
from logic_cad.core.services.validation_service import ValidationService
from logic_cad.core.services.user_geometry_service import UserGeometryService
from logic_cad.core.services.wire_service import WireService
from logic_cad.core.services.wire_service.gate_profile import _GATE_CONNECT_OPTIMIZE_PROFILE
from logic_cad.core.undo.transaction import DocumentTransaction
from logic_cad.core.model.xdata import (
    build_ld_app_tags,
    get_type,
    read_ld_app_dict,
    set_entity_xdata,
)
from logic_cad.core.pages.page_layout_meta import read_page_meta, merge_layout_page_xdata
from logic_cad.core.services.toc_frame_service import refresh_frame_for_layout
from logic_cad.core.services.toc_frame_service import regenerate_toc as _reg
from logic_cad.core.services.toc_frame_service import refresh_all_frame_captions
from logic_cad.core.logic_diagram_clipboard import (
    build_symbol_clipboard_payload as _build_symbol_clipboard_payload,
    paste_symbol_clipboard_payload as _paste_symbol_clipboard_payload,
)
from logic_cad.core.symbol_clipboard import SymbolClipboardPayload

class RerouteAfterGeometryChangeError(Exception):
    """Raised to roll back a move/rotate transaction when attached wires could not all be rerouted."""


class LogicDiagram:
    def __init__(self, doc: Drawing, current_layout_name: str, path: str | None = None) -> None:
        self.doc = doc
        self.current_layout_name = current_layout_name
        self.path = path
        self.index = IndexStore(doc, current_layout_name)
        self.layouts = LayoutService(doc)
        self.gates = DynamicGateFactory()
        self.symbols = SymbolService(doc, self.gates)
        self.wires = WireService(doc)
        self.user_geom = UserGeometryService(doc)
        self.validator = ValidationService(doc, self.index)
        self.history = HistoryService()
        self._dirty = False
        self._wire_shrink_batch_stack: list[set[str]] = []
        self.rebuild_index()

    def is_dirty(self) -> bool:
        return self._dirty

    def mark_saved(self) -> None:
        self._dirty = False

    def mark_modified(self) -> None:
        self._dirty = True
        from logic_cad.core.text.pdf_like_font_faces import invalidate_pdf_like_font_face_cache

        invalidate_pdf_like_font_face_cache(doc=self.doc)

    @classmethod
    def new(cls) -> LogicDiagram:
        doc = new_document()
        ls = LayoutService(doc)
        paper_names = [L.name for L in doc.layouts if not L.is_modelspace]
        # ezdxf の新規ドキュメントは既定で紙レイアウト1枚（多くは Layout1）を持つだけなので、
        # FIRST_PAGE_NAME へ揃えてタブ名とコード上の「先頭ページ」を一致させる。
        if len(paper_names) == 1 and paper_names[0] != FIRST_PAGE_NAME:
            ls.rename_page(paper_names[0], FIRST_PAGE_NAME)
        if len(paper_names) == 1:
            first = FIRST_PAGE_NAME
        elif paper_names:
            first = paper_names[0]
        else:
            first = FIRST_PAGE_NAME
        ls.ensure_minimal_page(first)
        import_symbol_library(doc)
        return cls(doc, first, None)

    @classmethod
    def open(cls, path: str) -> LogicDiagram:
        doc = readfile(path)
        names = [L.name for L in doc.layouts if not L.is_modelspace]
        first = names[0] if names else FIRST_PAGE_NAME
        return cls(doc, first, str(path))

    def save(self, path: str | None = None) -> list[str]:
        p = path or self.path
        if not p:
            raise ValueError("保存先のパスがありません。")
        issues = validate_document(self.doc)
        if issues:
            logger = logging.getLogger("logic_cad.validation.save")
            for issue in issues:
                logger.warning(issue)
        saveas(self.doc, p)
        self.path = str(p)
        self.mark_saved()
        return issues

    def begin(self, label: str) -> DocumentTransaction:
        return DocumentTransaction(self, label)

    def list_pages(self) -> list[str]:
        return self.layouts.list_pages()

    def add_page(self, name: str) -> None:
        self.layouts.add_page(name)

        refresh_frame_for_layout(self.doc, name)
        if TOC_LAYOUT_NAME in self.doc.layouts:
            self.regenerate_toc()

    def duplicate_page(
        self,
        source_name: str,
        dest_name: str,
        *,
        description: str | None = None,
        revision: str | None = None,
    ) -> None:
        """Clone *source_name* to new paper layout *dest_name*; optional page_desc / page_rev."""


        self.layouts.duplicate_paper_layout(source_name, dest_name)
        meta = read_page_meta(self.doc, source_name)
        src_desc = (meta.get("page_desc") or "").strip()
        if description is not None:
            desc = description
        elif src_desc:
            desc = f"{src_desc} (コピー)"
        else:
            desc = "（コピー）"
        rev = revision if revision is not None else (meta.get("page_rev") or "").strip()
        self.set_page_metadata(dest_name, description=desc, revision=rev or None)
        refresh_frame_for_layout(self.doc, dest_name)
        if TOC_LAYOUT_NAME in self.doc.layouts:
            self.regenerate_toc()
        self.rebuild_index()

    def import_pages_from_foreign_drawing(
        self,
        foreign_doc: Drawing,
        migrations: list[tuple[str, str]],
    ) -> list[str]:
        """Copy paper layouts from another drawing into this one and refresh frames/TOC labels.

        Layout block content, dependent block definitions, PAGE_REF target remapping,
        and Logic CAD UIDs are handled by :meth:`LayoutService.import_paper_layouts_from_foreign_drawing`.

        Args:
            foreign_doc: Source DXF drawing.
            migrations: Source layout names and destination layout names to create here.

        Returns:
            Destination layout names that were created.

        Raises:
            ValueError: Passed through when validation or ezdxf import fails.
        """
        created = self.layouts.import_paper_layouts_from_foreign_drawing(foreign_doc, migrations)
        if not created:
            return created
        for dn in created:
            refresh_frame_for_layout(self.doc, dn)
        refresh_all_frame_captions(self.doc)
        refresh_all_page_ref_syms(self.doc)
        if TOC_LAYOUT_NAME in self.doc.layouts:
            self.regenerate_toc()
        self.mark_modified()
        self.rebuild_index()
        return created

    def rename_page(self, old: str, new: str) -> None:
        self.layouts.rename_page(old, new)
        if self.current_layout_name == old:
            self.current_layout_name = new
        self.rebuild_index()

        refresh_frame_for_layout(self.doc, new)
        if TOC_LAYOUT_NAME in self.doc.layouts:
            self.regenerate_toc()

    def delete_page(self, name: str) -> None:
        if name not in self.doc.layouts:
            raise ValueError(f"ページ {name!r} がありません")
        papers = self.list_pages()
        if name not in papers:
            raise ValueError(f"ページ {name!r} は用紙レイアウトではありません")
        if self.current_layout_name == name:
            others = [p for p in papers if p != name]
            if not others:
                raise ValueError("最後の1枚の用紙レイアウトは削除できません")
            self.current_layout_name = others[0]
        self.layouts.delete_page(name)
        self.rebuild_index()


        refresh_all_frame_captions(self.doc)
        if TOC_LAYOUT_NAME in self.doc.layouts:
            self.regenerate_toc()

    def set_page_metadata(
        self,
        layout_name: str,
        *,
        description: str | None = None,
        revision: str | None = None,
    ) -> None:


        merge_layout_page_xdata(self.doc, layout_name, page_desc=description, page_rev=revision)
        refresh_frame_for_layout(self.doc, layout_name)
        refresh_all_page_ref_syms(self.doc)
        if TOC_LAYOUT_NAME in self.doc.layouts:
            self.regenerate_toc()

    def regenerate_toc(self) -> None:

        _reg(self.doc)

    def get_project_preferred_font_family(self) -> str | None:
        """Return project preferred font from ``LD_DOC`` XDATA, or ``None`` for default chain."""

        return read_project_preferred_font_family(self.doc)

    def set_project_preferred_font_family(self, family: str | None) -> None:
        """Persist project preferred font on the document anchor and mark the diagram dirty."""

        write_project_preferred_font_family_to_doc(self.doc, family)
        self.mark_modified()

    def set_drawing_number(self, drawing_number: str) -> None:
        """Store drawing-wide number in ``$PROJECTNAME`` and refresh frame placeholders."""


        self.doc.header["$PROJECTNAME"] = drawing_number.strip()
        refresh_all_frame_captions(self.doc)
        if TOC_LAYOUT_NAME in self.doc.layouts:
            self.regenerate_toc()

    def set_drawing_page_numbering(self, *, start_page: int, total_pages: int | None) -> None:
        """Store ``{{PAGE_NUM}}`` / ``{{PAGE_TOTAL}}`` settings (``$USERI1`` / ``$USERI2``) and refresh frames."""


        self.doc.header["$USERI1"] = max(1, int(start_page))
        if total_pages is not None and int(total_pages) >= 1:
            self.doc.header["$USERI2"] = int(total_pages)
        else:
            self.doc.header["$USERI2"] = 0
        refresh_all_frame_captions(self.doc)
        if TOC_LAYOUT_NAME in self.doc.layouts:
            self.regenerate_toc()

    def set_current_page(self, name: str) -> None:
        if name not in self.doc.layouts:
            raise ValueError(f"ページ {name!r} が見つかりません。")
        self.current_layout_name = name
        self.rebuild_index()

    def place_checkpoint(self, pos: tuple[float, float], ref: str | None = None) -> str:
        pos = snap_to_grid(*pos)
        uid = self.symbols.place_checkpoint(self.current_layout_name, pos, ref)
        logic_cad_log("diagram", f"place_checkpoint uid={uid} layout={self.current_layout_name!r}")
        self.rebuild_index()
        return uid

    def place_symbol(self, block_name: str, pos: tuple[float, float], ref: str | None = None) -> str:
        if block_name == BLOCK_CHECKPOINT:
            return self.place_checkpoint(pos, ref)
        pos = snap_to_grid(*pos)
        if ref is None:
            ref = self.symbols.next_sym_label(self.current_layout_name, block_name)
        uid = self.symbols.place_symbol(self.current_layout_name, block_name, pos, ref, "SYMBOL")
        logic_cad_log("diagram", f"place_symbol uid={uid} block={block_name!r} layout={self.current_layout_name!r}")
        self.rebuild_index()
        return uid

    def place_and_gate(self, n_inputs: int, pos: tuple[float, float], ref: str | None = None) -> str:
        pos = snap_to_grid(*pos)
        uid = self.symbols.place_and_gate(self.current_layout_name, n_inputs, pos, ref)
        self.rebuild_index()
        return uid

    def place_or_gate(self, n_inputs: int, pos: tuple[float, float], ref: str | None = None) -> str:
        pos = snap_to_grid(*pos)
        uid = self.symbols.place_or_gate(self.current_layout_name, n_inputs, pos, ref)
        self.rebuild_index()
        return uid

    def build_symbol_clipboard_payload(
        self, symbol_uids: list[str], user_sketch_uids: list[str] | None = None
    ) -> SymbolClipboardPayload:
        return _build_symbol_clipboard_payload(self, symbol_uids, user_sketch_uids)

    def paste_symbol_clipboard_payload(
        self, payload: SymbolClipboardPayload, anchor_dxf: tuple[float, float]
    ) -> tuple[list[str], list[str]]:
        """Paste symbols/wires and/or user sketches; return (new INSERT uids, new sketch uids)."""
        return _paste_symbol_clipboard_payload(self, payload, anchor_dxf)

    def _on_transaction_begin(self, label: str) -> None:
        if label != "delete":
            return
        self._wire_shrink_batch_stack.append(set())

    def _on_transaction_pre_commit(self, label: str) -> None:
        """Apply deferred wire-topology gate shrink before the post-transaction snapshot (undo delta)."""
        if label != "delete":
            return
        if not self._wire_shrink_batch_stack:
            return
        pending = self._wire_shrink_batch_stack.pop()
        if self._wire_shrink_batch_stack:
            self._wire_shrink_batch_stack[-1] |= pending
        elif pending:
            self._shrink_and_or_gates_for_touch_uids(pending)

    def _on_transaction_rollback(self, label: str) -> None:
        if label != "delete":
            return
        if self._wire_shrink_batch_stack:
            self._wire_shrink_batch_stack.pop()

    def _enqueue_gate_shrink_after_wire_topology_change(self, touched: set[str | None]) -> None:
        """After WIRE removal, compact AND/OR dst ports on affected gates; shrink if fewer inputs suffice.

        ``required_and_or_input_count`` uses the maximum IN* index; deleting middle inputs leaves
        holes until bundle optimization reassigns IN0…

        Only INSERTs that are AND/OR dynamic gates (``current_and_or_input_count`` not None) among
        *touched* endpoints are processed. During ``begin(\"delete\")``, work is deferred until
        commit so multiple wire deletes run one localized pass.
        """
        normalized = {u for u in touched if u}
        if not normalized:
            return
        if self._wire_shrink_batch_stack:
            self._wire_shrink_batch_stack[-1] |= normalized
        else:
            self._shrink_and_or_gates_for_touch_uids(normalized)

    def _shrink_and_or_gates_for_touch_uids(self, candidate_uids: set[str]) -> None:
        """Optimize and optionally shrink only AND/OR gates whose UID is in *candidate_uids*."""
        t0 = time.perf_counter()
        layout = self.current_layout_name
        profile = _GATE_CONNECT_OPTIMIZE_PROFILE
        self.rebuild_index()
        gate_uids: list[str] = []
        for uid in candidate_uids:
            if uid not in self.index.inserts_by_uid:
                continue
            if self.wires.current_and_or_input_count(self.index, uid) is None:
                continue
            gate_uids.append(uid)
        gate_uids.sort()
        for uid in gate_uids:
            self.optimize_and_or_input_ports(uid, routing_profile=profile)
        self.rebuild_index()
        for uid in gate_uids:
            cur = self.wires.current_and_or_input_count(self.index, uid)
            if cur is None:
                continue
            req = self.wires.required_and_or_input_count(self.index, layout, uid)
            if req is None:
                continue
            if req < cur:
                if logic_cad_debug_enabled():
                    logic_cad_log("diagram", f"shrink gate={uid} req={req} cur={cur}")
                self.change_gate_inputs(uid, req)
        if logic_cad_debug_enabled():
            dt_ms = (time.perf_counter() - t0) * 1000.0
            logic_cad_log(
                "diagram",
                f"localized_gate_shrink_ms={dt_ms:.1f} candidates={len(candidate_uids)} and_or_gates={len(gate_uids)}",
            )

    def _shrink_all_and_or_gates_to_required(self) -> None:
        """Compact every AND/OR gate's inputs, then shrink any block larger than required."""
        layout = self.current_layout_name
        profile = _GATE_CONNECT_OPTIMIZE_PROFILE
        for uid in list(self.index.inserts_by_uid.keys()):
            if self.wires.current_and_or_input_count(self.index, uid) is None:
                continue
            self.optimize_and_or_input_ports(uid, routing_profile=profile)
        self.rebuild_index()
        for uid in list(self.index.inserts_by_uid.keys()):
            cur = self.wires.current_and_or_input_count(self.index, uid)
            if cur is None:
                continue
            req = self.wires.required_and_or_input_count(self.index, layout, uid)
            if req is None:
                continue
            if req < cur:
                if logic_cad_debug_enabled():
                    logic_cad_log("diagram", f"shrink gate={uid} req={req} cur={cur}")
                self.change_gate_inputs(uid, req)

    def change_gate_inputs(self, uid: str, new_n: int) -> None:
        """Swap AND/OR block; keep OUT0_LOGIC world position via INSERT translation."""
        old_out = self.index.get_port_world(uid, "OUT0_LOGIC")
        self.symbols.change_gate_inputs(self.current_layout_name, uid, new_n)
        self.rebuild_index()
        if old_out is not None:
            new_out = self.index.get_port_world(uid, "OUT0_LOGIC")
            if new_out is not None:
                dx, dy = old_out[0] - new_out[0], old_out[1] - new_out[1]
                if abs(dx) > 1e-9 or abs(dy) > 1e-9:
                    ins = self.symbols.insert_by_uid(self.current_layout_name, uid)
                    if ins is not None:
                        self.symbols.move_insert(
                            self.current_layout_name,
                            uid,
                            (float(ins.dxf.insert.x) + dx, float(ins.dxf.insert.y) + dy),
                        )
                    self.rebuild_index()

    def set_symbol_attr(self, uid: str, tag: str, value: str) -> None:
        self.symbols.set_symbol_attr(self.current_layout_name, uid, tag, value)
        self.rebuild_index()

    def set_symbol_text_visible(self, uid: str, visible: bool) -> None:
        self.symbols.set_symbol_text_visible(self.current_layout_name, uid, visible)
        self.rebuild_index()

    def set_attrib_visible(self, uid: str, tag: str, visible: bool) -> None:
        self.symbols.set_attrib_visible(self.current_layout_name, uid, tag, visible)
        self.rebuild_index()

    def set_gate_show_input_stub_in_arrow(self, uid: str, show: bool) -> None:
        """Show or hide WIRE-style IN arrows at each AND/OR input stub root (DXF-visible).

        Args:
            uid: INSERT entity uid for an AND or OR gate.
            show: If True, persist XDATA and layout ``GATE_INPUT_STUB_ARROW`` LW polylines.

        Returns:
            None
        """
        self.symbols.set_gate_show_input_stub_in_arrow(self.current_layout_name, uid, show)
        self.rebuild_index()

    def set_symbol_linetype(self, uid: str, linetype: str) -> None:
        self.symbols.set_symbol_linetype(self.current_layout_name, uid, linetype)
        self.rebuild_index()

    def rotate_symbol(self, uid: str, delta_degrees: float) -> bool:
        """Rotate INSERT by delta in degrees (e.g. ±90). Wires touching this symbol are rerouted.

        Returns False if any affected wire or gate bundle could not be rerouted (caller may roll back).
        """
        e = find_entity_by_uid(self.doc, uid)
        if (
            e is not None
            and e.dxftype() == "INSERT"
            and get_type(e) in (ENTITY_TYPE_TOC_HEADER, ENTITY_TYPE_TOC_ROW)
            and is_toc_layout_name(self.current_layout_name)
        ):
            return True
        self.symbols.rotate_insert_relative_deg(self.current_layout_name, uid, delta_degrees)
        return self.reroute_wires_after_symbol_moves({uid})

    def connect_ports(self, src_uid: str, src_port: str, dst_uid: str, dst_port: str) -> str:
        self.rebuild_index()
        gd = self.wires.wire_graph_deps()
        src_uid, src_port, dst_uid, dst_port = normalize_wire_endpoints_with_deps(
            gd, src_uid, src_port, dst_uid, dst_port
        )
        dst_port = self._resolve_gate_dst_port(src_uid, src_port, dst_uid, dst_port)
        # TODO: batch UI could pass gd through to avoid a second wire_graph_deps() inside connect_*.
        wid = self.wires.connect_ports(
            self.index, self.current_layout_name, src_uid, src_port, dst_uid, dst_port
        )
        self.rebuild_index()
        return wid

    def connect_ports_manual(
        self,
        src_uid: str,
        src_port: str,
        dst_uid: str,
        dst_port: str,
        bend_points_dxf: list[tuple[float, float]],
    ) -> str:
        """Manhattan path via interior bend points (DXF mm); excluded from gate-input bundle optimization only."""
        self.rebuild_index()
        gd = self.wires.wire_graph_deps()
        src_uid, src_port, dst_uid, dst_port = normalize_wire_endpoints_with_deps(
            gd, src_uid, src_port, dst_uid, dst_port
        )
        dst_port = self._resolve_gate_dst_port(src_uid, src_port, dst_uid, dst_port)
        # TODO: batch UI could pass gd through to avoid a second wire_graph_deps() inside connect_*.
        wid = self.wires.connect_ports_manual(
            self.index,
            self.current_layout_name,
            src_uid,
            src_port,
            dst_uid,
            dst_port,
            bend_points_dxf,
        )
        self.rebuild_index()
        return wid

    def _resolve_gate_dst_port(self, src_uid: str, src_port: str, dst_uid: str, dst_port: str) -> str:


        ins = self.symbols.insert_by_uid(self.current_layout_name, dst_uid)
        if ins is None:
            return dst_port
        bn = ins.dxf.name.upper()
        if not (bn.startswith("AND_") or bn.startswith("OR_")):
            return dst_port
        try:
            n = int(bn.split("_", 1)[1])
        except ValueError:
            return dst_port
        if self.wires.all_and_inputs_wired(self.current_layout_name, dst_uid, n):
            self.change_gate_inputs(dst_uid, n + 1)
            self.rebuild_index()
            return f"IN{n}_LOGIC"
        # AND/OR inputs are symmetric: only ensure we reserve some free slot.
        if re.match(r"^IN\d+_LOGIC$", dst_port):
            if not self.wires.wire_uses_input_port(self.current_layout_name, dst_uid, dst_port):
                return dst_port
            free = self.wires.first_free_and_input(self.current_layout_name, dst_uid, n)
            if free:
                return free
        if self.wires.wire_uses_input_port(self.current_layout_name, dst_uid, dst_port):
            free = self.wires.first_free_and_input(self.current_layout_name, dst_uid, n)
            if free:
                return free
            self.change_gate_inputs(dst_uid, n + 1)
            self.rebuild_index()
            return f"IN{n}_LOGIC"
        return dst_port

    def _apply_hub_wire_flip(self, flip: WireFlip) -> None:
        e = find_entity_by_uid(self.doc, flip.wire_uid)
        if e is None:
            return
        old_meta = read_ld_app_dict(e)
        new_extra = {
            "unit": old_meta.get("unit", "LOGIC"),
            "src": flip.new_src,
            "src_port": flip.new_src_port,
            "dst": flip.new_dst,
            "dst_port": flip.new_dst_port,
        }
        set_entity_xdata(e, build_ld_app_tags("1", flip.wire_uid, "WIRE", new_extra))
        if e.dxftype() == "LWPOLYLINE":
            pts = list(e.get_points("xyb"))
            e.set_points([(x, y, b) for x, y, b in reversed(pts)])

    def repair_hub_wire_directions(self, layout_name: str | None = None) -> int:
        """Kept for compatibility; hub-chain direction repair is not used."""
        _ = layout_name
        return 0

    def optimize_and_or_input_ports(
        self, gate_uid: str, *, routing_profile: RoutingProfile | None = None
    ) -> bool:
        """Reassign IN0…IN(n-1) among wires into an AND/OR gate to reduce crossings and obstacle hits."""
        self.rebuild_index()
        ok = self.wires.optimize_and_or_input_ports(
            self.index, self.current_layout_name, gate_uid, routing_profile=routing_profile
        )
        self.rebuild_index()
        return ok

    def reroute_wires_after_symbol_moves(
        self,
        symbol_uids: set[str],
        symbol_move_deltas: dict[str, tuple[float, float]] | None = None,
    ) -> bool:
        """Rebuild wire geometry for wires incident to moved symbols. Returns False if any reroute failed."""
        if not symbol_uids:
            return True
        with routing_perf_span("reroute_after_move.index_rebuild_pre"):
            self.rebuild_index()
        ok = self.wires.reroute_wires_touching(
            self.index,
            self.current_layout_name,
            symbol_uids,
            routing_profile=FAST_MOVE_REROUTE_PROFILE,
            symbol_move_deltas=symbol_move_deltas,
        )
        with routing_perf_span("reroute_after_move.index_rebuild_post"):
            self.rebuild_index()
        return ok

    def place_page_link(self, pos: tuple[float, float], target_layout: str) -> str:
        pos = snap_to_grid(*pos)
        uid = self.symbols.place_page_link(self.current_layout_name, pos, target_layout, self.list_pages())
        self.rebuild_index()
        return uid

    def place_page_link_pair_ranked(
        self, pos: tuple[float, float], target_layout: str, sym_ordinal: int
    ) -> tuple[str, str]:
        """Place PAGE_FROM/PAGE_TO pair with mutual ``peer_uid`` and shared rank; refresh both layouts."""
        pos = snap_to_grid(*pos)
        src = self.current_layout_name
        x0, y0 = float(pos[0]), float(pos[1])
        rk = int(sym_ordinal)
        uid_from = self.symbols.place_page_link(
            src,
            (x0, y0),
            target_layout,
            self.list_pages(),
            defer_refresh=True,
            page_ref_rank=rk,
        )
        uid_to = self.symbols.place_page_link(
            target_layout,
            (x0 + 28.0, y0 + 22.0),
            src,
            self.list_pages(),
            outgoing=False,
            defer_refresh=True,
            page_ref_rank=rk,
        )
        self.symbols.link_page_ref_peers_cross_layout(src, uid_from, target_layout, uid_to)
        refresh_page_ref_syms_on_layout(self.doc, src)
        refresh_page_ref_syms_on_layout(self.doc, target_layout)
        self.rebuild_index()
        return uid_from, uid_to

    def reorder_page_refs_on_corridor(self, target_layout: str, ordered_src_side_uids: list[str]) -> None:
        apply_ordered_page_ref_ranks_with_peers(
            self.doc,
            self.current_layout_name,
            target_layout,
            ordered_src_side_uids,
        )
        self.rebuild_index()

    def place_page_link_at(self, layout_name: str, pos: tuple[float, float], target_layout: str) -> str:
        """Place PAGE_TO on the **destination** layout (stub pointing back to *target_layout*)."""
        pos = snap_to_grid(*pos)
        uid = self.symbols.place_page_link(layout_name, pos, target_layout, self.list_pages(), outgoing=False)
        if layout_name == self.current_layout_name:
            self.rebuild_index()
        return uid

    def place_inpage_link(self, pos: tuple[float, float]) -> str:
        """Place INPAGE_FROM (``●※n``) on the current page; pair with :meth:`place_inpage_link_peer`."""
        pos = snap_to_grid(*pos)
        uid = self.symbols.place_inpage_ref(self.current_layout_name, pos, outgoing=True, peer_uid="")
        self.rebuild_index()
        return uid

    def place_inpage_link_peer(self, from_uid: str, pos: tuple[float, float]) -> str:
        """Place INPAGE_TO (``※n●``) and link it with *from_uid* on the current page."""
        pos = snap_to_grid(*pos)
        to_uid = self.symbols.place_inpage_ref(
            self.current_layout_name, pos, outgoing=False, peer_uid=from_uid
        )
        self.symbols.link_inpage_ref_pair(self.current_layout_name, from_uid, to_uid)
        self.rebuild_index()
        return to_uid

    def set_inpage_sym_height(self, uid: str, height_mm: float) -> None:
        """Set INPAGE_REF SYM height (mm) on the current page."""
        self.symbols.set_inpage_sym_height(self.current_layout_name, uid, height_mm)
        self.rebuild_index()

    def set_inpage_ref_link_display(
        self,
        uid: str,
        *,
        link_name_auto: bool,
        display_text: str = "",
    ) -> None:
        """Set INPAGE_REF link label mode for the current page (both ends when paired).

        Args:
            uid: One INSERT uid of the pair.
            link_name_auto: Use automatic ※ labels among auto pairs, or fixed manual text.
            display_text: Manual label when *link_name_auto* is False.

        Raises:
            ValueError: Passed through from :class:`SymbolService`.
        """
        self.symbols.set_inpage_ref_link_display(
            self.current_layout_name,
            uid,
            link_name_auto=link_name_auto,
            display_text=display_text,
        )
        self.rebuild_index()

    def set_page_ref(self, uid: str, target_layout: str) -> None:
        self.symbols.set_page_ref(self.current_layout_name, uid, target_layout, self.list_pages())
        self.rebuild_index()

    def set_page_ref_rank(self, uid: str, rank: int) -> None:
        self.symbols.set_page_ref_rank(self.current_layout_name, uid, rank)
        self.rebuild_index()

    def set_page_ref_target_info_visibility(
        self, uid: str, *, show_page_name: bool, show_page_desc: bool
    ) -> None:
        self.symbols.set_page_ref_target_info_visibility(
            self.current_layout_name,
            uid,
            show_page_name=show_page_name,
            show_page_desc=show_page_desc,
        )
        self.rebuild_index()

    def place_wire_branch(self, pos: tuple[float, float], ref: str | None = None) -> str:
        pos = snap_to_grid(*pos)
        uid = self.symbols.place_wire_branch(self.current_layout_name, pos, ref)
        self.rebuild_index()
        return uid

    def move_wire_branch(self, branch_uid: str, dxf_xy: tuple[float, float]) -> bool:
        """Move WIRE_BRANCH INSERT; reroute incident wires. Returns False if reroute failed."""
        self.rebuild_index()
        x, y = snap_to_grid(float(dxf_xy[0]), float(dxf_xy[1]))
        self.symbols.move_insert(self.current_layout_name, branch_uid, (x, y))
        self.rebuild_index()
        return self.reroute_wires_after_symbol_moves({branch_uid})

    def add_user_line(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        linetype: str,
    ) -> str:
        uid = self.user_geom.add_line(self.current_layout_name, start, end, linetype)
        self.rebuild_index()
        return uid

    def add_user_circle(
        self,
        center: tuple[float, float],
        radius: float,
        linetype: str,
    ) -> str:
        uid = self.user_geom.add_circle(self.current_layout_name, center, radius, linetype)
        self.rebuild_index()
        return uid

    def add_user_arc(
        self,
        center: tuple[float, float],
        radius: float,
        start_angle_deg: float,
        end_angle_deg: float,
        linetype: str,
    ) -> str:
        uid = self.user_geom.add_arc(
            self.current_layout_name,
            center,
            radius,
            start_angle_deg,
            end_angle_deg,
            linetype,
        )
        self.rebuild_index()
        return uid

    def add_user_text(self, insert: tuple[float, float], text: str, height: float) -> str:
        uid = self.user_geom.add_text(self.current_layout_name, insert, text, height)
        self.rebuild_index()
        return uid

    def add_user_cloud(
        self,
        vertices: list[tuple[float, float]],
        segment_length: float,
        linetype: str,
        *,
        is_closed: bool,
    ) -> str:
        uid = self.user_geom.add_cloud(
            self.current_layout_name,
            vertices,
            segment_length,
            linetype,
            is_closed=is_closed,
        )
        self.rebuild_index()
        return uid

    def set_user_sketch_linetype(self, uid: str, linetype: str) -> bool:
        ok = self.user_geom.set_user_line_or_circle_linetype(self.current_layout_name, uid, linetype)
        if ok:
            self.rebuild_index()
        return ok

    def set_user_sketch_text(
        self,
        uid: str,
        text: str,
        height_mm: float,
        *,
        halign: int | None = None,
    ) -> bool:
        """Update USER_TEXT string, height, and optionally horizontal alignment.

        Args:
            uid: Sketch entity UID.
            text: New displayed text.
            height_mm: Cap height (mm).
            halign: When not ``None``, DXF horizontal alignment (0=left, 1=center, 2=right).

        Returns:
            True if the entity was updated.
        """

        ok = self.user_geom.set_user_text_props(
            self.current_layout_name, uid, text, height_mm, halign=halign
        )
        if ok:
            self.rebuild_index()
        return ok

    def set_user_cloud_pitch_mm(self, uid: str, pitch_mm: float) -> bool:
        """Regenerate USER_CLOUD with a new revcloud segment length (mm)."""
        ok = self.user_geom.set_user_cloud_pitch_mm(uid, pitch_mm)
        if ok:
            self.rebuild_index()
        return ok

    def get_user_cloud_pitch_display_mm(self, uid: str) -> float:
        """Pitch value for the property panel (stored or default)."""
        return self.user_geom.get_user_cloud_pitch_display_mm(uid)

    def delete_all_user_clouds_all_pages(self) -> int:
        """Remove every USER_CLOUD entity from all paper layouts."""
        return self.user_geom.delete_all_user_clouds_all_pages()

    def set_wire_linetype(self, wire_uid: str, linetype: str) -> None:
        self.wires.set_wire_linetype(self.current_layout_name, wire_uid, linetype)
        self.rebuild_index()

    def set_wire_skip_auto_reroute(self, wire_uid: str, skip: bool) -> None:
        self.wires.set_wire_skip_auto_reroute(self.current_layout_name, wire_uid, skip)
        self.rebuild_index()

    def set_wire_show_in_arrow(self, wire_uid: str, show: bool) -> None:
        self.wires.set_wire_show_in_arrow(self.current_layout_name, wire_uid, show)
        self.rebuild_index()

    def set_wire_allow_orthogonal_cross(self, wire_uid: str, allow: bool) -> None:
        self.wires.set_wire_allow_orthogonal_cross(self.current_layout_name, wire_uid, allow)
        self.rebuild_index()

    def offset_wire_segment_parallel(self, wire_uid: str, seg_index: int, delta: float) -> bool:
        """P4: slide an interior wire segment perpendicular (delta in mm, grid-snapped by caller)."""
        self.rebuild_index()
        ok = self.wires.offset_wire_segment_parallel(self.current_layout_name, wire_uid, seg_index, delta)
        self.rebuild_index()
        return ok

    def wire_connection_health(self, wire_uid: str) -> tuple[bool, bool]:
        return self.wires.wire_connection_health(self.index, self.current_layout_name, wire_uid)

    def disconnect(self, wire_uid: str) -> None:
        e = find_entity_by_uid(self.doc, wire_uid)
        touched: set[str | None] = set()
        if e is not None and get_type(e) == "WIRE":
            wd = read_ld_app_dict(e)
            touched.add(wd.get("src"))
            touched.add(wd.get("dst"))
        self.wires.disconnect(self.current_layout_name, wire_uid)
        self.rebuild_index()
        self._enqueue_gate_shrink_after_wire_topology_change(touched)

    def delete_by_uid(self, uid: str) -> None:
        e = find_entity_by_uid(self.doc, uid)
        if e is None:
            return
        if (
            e.dxftype() == "INSERT"
            and get_type(e) in (ENTITY_TYPE_TOC_HEADER, ENTITY_TYPE_TOC_ROW)
            and is_toc_layout_name(self.current_layout_name)
        ):
            return
        if e.dxftype() == "INSERT" and get_type(e) == ENTITY_TYPE_WIRE_BRANCH:
            touched = self.wires.remove_wire_branch(self.current_layout_name, uid)
            self.rebuild_index()
            self._enqueue_gate_shrink_after_wire_topology_change(touched)
            return
        if e.dxftype() == "LWPOLYLINE" and get_type(e) == "WIRE":
            wd = read_ld_app_dict(e)
            touched: set[str | None] = {wd.get("src"), wd.get("dst")}
            self.wires.remove_wire_arrow_children(self.current_layout_name, uid)
            destroy_entity(self.doc, e)
            self.wires.refresh_com_wire_markers(self.current_layout_name)
            self.rebuild_index()
            self._enqueue_gate_shrink_after_wire_topology_change(touched)
            return
        if e.dxftype() == "INSERT" and get_type(e) == ENTITY_TYPE_INPAGE_REF:
            layout_nm = layout_name_for_insert(self.doc, e)
            d = read_ld_app_dict(e)
            peer = (d.get(PEER_UID_XDATA) or "").strip()
            if peer:
                pe = find_entity_by_uid(self.doc, peer)
                if pe is not None and pe.dxftype() == "INSERT":
                    destroy_entity(self.doc, pe)
            destroy_entity(self.doc, e)
            if layout_nm:
                refresh_inpage_ref_syms_on_layout(self.doc, layout_nm)
            self.rebuild_index()
            return
        page_ref_layout: str | None = None
        if e.dxftype() == "INSERT" and get_type(e) == "PAGE_REF":
            page_ref_layout = layout_name_for_insert(self.doc, e)
        if e.dxftype() == "INSERT" and get_type(e) in ("AND", "OR"):
            self.symbols.remove_gate_stub_arrow_children(self.current_layout_name, uid)
        destroy_entity(self.doc, e)
        if page_ref_layout is not None:
            refresh_page_ref_syms_on_layout(self.doc, page_ref_layout)
        self.rebuild_index()

    def undo(self) -> bool:
        ok = self.history.undo(self)
        if ok:
            self.mark_modified()
        return ok

    def redo(self) -> bool:
        ok = self.history.redo(self)
        if ok:
            self.mark_modified()
        return ok

    def validate(self) -> list[str]:
        self.rebuild_index()
        return self.validator.validate()

    def rebuild_index(self) -> None:
        self.index.rebuild(self.doc, self.current_layout_name)
        self.validator = ValidationService(self.doc, self.index)
