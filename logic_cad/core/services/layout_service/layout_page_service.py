"""Paper layout CRUD, foreign import, and duplication (orchestrates frame template + configure)."""

from __future__ import annotations

from ezdxf.addons import Importer
from ezdxf.document import Drawing

from logic_cad.core.debug.debug_log import logic_cad_log
from logic_cad.core.model.constants import LAYER_VPORT, TARGET_LAYOUT_XDATA
from logic_cad.core.model.xdata import (
    build_ld_app_tags,
    get_type,
    get_uid,
    new_uid,
    read_ld_app_dict,
    set_entity_xdata,
)
from logic_cad.core.pages.inpage_ref import refresh_inpage_ref_syms_on_layout
from logic_cad.core.pages.page_layout_meta import merge_layout_page_xdata, read_page_meta
from logic_cad.core.pages.page_order import (
    is_reserved_toc_page_id,
    is_toc_layout_name,
    list_paper_layout_names_sorted,
    validate_paper_layout_name,
)
from logic_cad.core.pages.page_ref import (
    reconnect_page_ref_peers_after_foreign_import,
    refresh_all_page_ref_syms,
    refresh_page_ref_syms_on_layout,
    remap_page_refs,
)
from logic_cad.core.paper_layout_access import paper_layout_block
from logic_cad.core.paper_layout_configure import configure_paper_layout_a4_landscape
from logic_cad.core.undo.history import destroy_entity

from .layout_builtin_blocks import ensure_cross_page_reference_blocks
from .layout_frame_template import import_frame_template
from .layout_uid_remap import remap_layout_block_ld_uids


class LayoutService:
    """High-level paper layout operations on a :class:`~ezdxf.document.Drawing`."""

    def __init__(self, doc: Drawing) -> None:
        self.doc = doc

    def list_pages(self) -> list[str]:
        return list_paper_layout_names_sorted(self.doc)

    def suggest_next_layout_name(self) -> str:
        """Next default paper layout name (numeric, not reserved for TOC slots)."""
        used = {L.name for L in self.doc.layouts if not L.is_modelspace}
        n = 10
        while str(n) in used or is_reserved_toc_page_id(str(n)):
            n += 1
        return str(n)

    def ensure_minimal_page(self, layout_name: str) -> None:
        """LAYOUT XDATA + optional ``import_frame_template`` when no ``LD_VPORT`` VPORT polyline.

        Does not synthesize ``LD_FRAME`` / ``LD_VPORT``; those come from the template or user CAD only.
        Page identity is ``layout_name`` only; XDATA keeps ``page_desc`` / ``page_rev`` if present.
        """
        layout = self.doc.layouts.get(layout_name)
        if layout.is_modelspace:
            return
        blk = paper_layout_block(self.doc, layout_name)
        le = layout.dxf_layout
        d = read_ld_app_dict(le)
        uid = d.get("uid") or new_uid()
        extra = {k: v for k, v in d.items() if k in ("page_desc", "page_rev")}
        tags = build_ld_app_tags("1", uid, "PAGE", extra)
        set_entity_xdata(le, tags)

        has_v = any(
            e.dxftype() == "LWPOLYLINE"
            and e.dxf.layer == LAYER_VPORT
            and get_type(e) == "VPORT"
            for e in blk
        )
        if not has_v:
            import_frame_template(self.doc, layout_name, path=None)

        configure_paper_layout_a4_landscape(self.doc, layout_name)

    def rename_page(self, old: str, new: str) -> None:
        """Rename a paper layout and update PAGE_REF targets."""
        if old == new:
            return
        validate_paper_layout_name(new)
        self.doc.layouts.rename(old, new)
        remap_page_refs(self.doc, old, new, self.list_pages())

    def add_page(self, name: str) -> None:
        validate_paper_layout_name(name)
        if name in self.doc.layouts:
            raise ValueError(f"レイアウト {name!r} は既に存在します。")
        self.doc.layouts.new(name)
        self.ensure_minimal_page(name)

    def _remove_page_refs_to_target(self, target_layout: str) -> None:
        """Delete PAGE_REF inserts on all paperspace layouts that link to *target_layout*."""
        for layout in self.doc.layouts:
            if layout.is_modelspace:
                continue
            # Iterates every layout tab (not doc.layouts.get(name)); paper_layout_block not applicable.
            blk = self.doc.blocks.get(layout.block_record_name)
            for e in list(blk):
                if e.dxftype() != "INSERT":
                    continue
                if get_type(e) != "PAGE_REF":
                    continue
                d = read_ld_app_dict(e)
                if (d.get(TARGET_LAYOUT_XDATA) or "").strip() != target_layout:
                    continue
                destroy_entity(self.doc, e)

    def delete_page(self, layout_name: str) -> None:
        """Remove a paperspace layout and any cross-page refs pointing to it."""
        if layout_name not in self.doc.layouts:
            raise ValueError(f"レイアウト {layout_name!r} がありません。")
        layout = self.doc.layouts.get(layout_name)
        if layout.is_modelspace:
            raise ValueError("モデル空間は削除できません")
        papers = list_paper_layout_names_sorted(self.doc)
        if len(papers) <= 1:
            raise ValueError("最後の1枚の用紙レイアウトは削除できません")
        if layout_name not in papers:
            raise ValueError(f"レイアウト {layout_name!r} は用紙レイアウトではありません。")
        self._remove_page_refs_to_target(layout_name)
        self.doc.layouts.delete(layout_name)
        refresh_all_page_ref_syms(self.doc)

    def suggest_import_dest_layout_name(self, desired: str) -> str:
        """Return *desired* if unused; else a unique paper layout name for import.

        Args:
            desired: Preferred layout name from the source document.

        Returns:
            A name valid for ``layouts.new`` in this document.
        """
        validate_paper_layout_name(desired)
        if desired not in self.doc.layouts:
            return desired
        base = f"{desired}_imp"
        name = base
        n = 1
        while name in self.doc.layouts:
            name = f"{base}{n}"
            n += 1
        validate_paper_layout_name(name)
        return name

    def import_paper_layouts_from_foreign_drawing(
        self,
        foreign_doc: Drawing,
        migrations: list[tuple[str, str]],
    ) -> list[str]:
        """Copy paper layouts from *foreign_doc* into this document with new UIDs.

        Dependent block definitions are merged with :class:`~ezdxf.addons.importer.Importer`
        (:meth:`~ezdxf.addons.importer.Importer.import_block`); layout contents are cloned with
        ``entity.copy()`` like :meth:`duplicate_paper_layout` so LD XDATA is preserved.
        PAGE_REF ``peer_uid`` is fixed on imported sheets by :func:`reconnect_page_ref_peers_after_foreign_import`
        when the partner INSERT exists on the destination drawing (``TARGET_LAYOUT`` / ranks are not rewritten).

        Args:
            foreign_doc: Source drawing (read-only use; not modified structurally here).
            migrations: Pairs ``(source_layout_name, dest_layout_name)`` to create.

        Returns:
            List of ``dest_layout_name`` values created, in *migrations* order.

        Raises:
            ValueError: Invalid names, missing source layout, or destination already exists.
        """
        if not migrations:
            return []
        dest_names = [d for _, d in migrations]
        if len(dest_names) != len(set(dest_names)):
            raise ValueError("取り込み先のレイアウト名が重複しています。")
        for src, dst in migrations:
            if is_toc_layout_name(src):
                raise ValueError(f"目次用レイアウト {src!r} は取り込めません。")
            validate_paper_layout_name(dst)
            if src not in foreign_doc.layouts:
                raise ValueError(f"ソースにレイアウト {src!r} がありません。")
            if dst in self.doc.layouts:
                raise ValueError(f"レイアウト {dst!r} は既に存在します。")
            sl = foreign_doc.layouts.get(src)
            if sl.is_modelspace:
                raise ValueError(f"レイアウト {src!r} はモデル空間です。")
            papers_f = list_paper_layout_names_sorted(foreign_doc)
            if src not in papers_f:
                raise ValueError(f"レイアウト {src!r} は用紙レイアウトではありません。")

        ensure_cross_page_reference_blocks(self.doc)
        insert_blocks_needed: set[str] = set()
        for src, _dst in migrations:
            src_blk0 = paper_layout_block(foreign_doc, src)
            for e in src_blk0:
                if e.dxftype() == "INSERT":
                    insert_blocks_needed.add(str(e.dxf.name))

        importer = Importer(foreign_doc, self.doc)
        for bname in sorted(insert_blocks_needed):
            if bname not in foreign_doc.blocks:
                logic_cad_log("layout", f"import_pages: unknown block reference {bname!r}")
                continue
            if bname in self.doc.blocks:
                continue
            try:
                importer.import_block(bname)
            except Exception as ex:
                logic_cad_log("layout", f"import_block {bname!r}: {ex}")
                raise ValueError(f"ブロック定義 {bname!r} を取り込めませんでした。") from ex
        importer.finalize()

        created: list[str] = []
        for src, dst in migrations:
            self.doc.layouts.new(dst)
            self.ensure_minimal_page(dst)
            dest_blk = paper_layout_block(self.doc, dst)
            for ent in list(dest_blk):
                destroy_entity(self.doc, ent)
            src_blk = paper_layout_block(foreign_doc, src)
            for e in list(src_blk):
                try:
                    ne = e.copy()
                    dest_blk.add_entity(ne)
                except Exception as ex:
                    logic_cad_log("layout", f"import_page copy skip {e.dxftype()}: {ex}")
            created.append(dst)

        old_to_new: dict[str, str] = {}
        for dst in created:
            blk = paper_layout_block(self.doc, dst)
            for ent in blk:
                u = get_uid(ent)
                if u and u not in old_to_new:
                    old_to_new[u] = new_uid()
        for dst in created:
            blk = paper_layout_block(self.doc, dst)
            remap_layout_block_ld_uids(blk, old_to_new)

        for src, dst in migrations:
            meta = read_page_meta(foreign_doc, src)
            desc_raw = str(meta.get("page_desc") or "").strip()
            rev_raw = str(meta.get("page_rev") or "").strip()
            merge_layout_page_xdata(
                self.doc,
                dst,
                page_desc=desc_raw if desc_raw else None,
                page_rev=rev_raw if rev_raw else None,
            )

        src_to_dest = {s: d for s, d in migrations}
        reconnect_page_ref_peers_after_foreign_import(self.doc, src_to_dest, created)
        for dst in created:
            refresh_page_ref_syms_on_layout(self.doc, dst)
            refresh_inpage_ref_syms_on_layout(self.doc, dst)
        return created

    def duplicate_paper_layout(self, source_name: str, dest_name: str) -> None:
        """Clone *source_name* paper block into a new layout *dest_name* (new UIDs; WIRE src/dst remapped)."""
        if is_toc_layout_name(source_name):
            raise ValueError("目次用レイアウト（0, 0A …）は複製できません。")
        validate_paper_layout_name(dest_name)
        if dest_name in self.doc.layouts:
            raise ValueError(f"レイアウト {dest_name!r} は既に存在します")
        if source_name not in self.doc.layouts:
            raise ValueError(f"レイアウト {source_name!r} がありません")
        src_layout = self.doc.layouts.get(source_name)
        if src_layout.is_modelspace:
            raise ValueError("モデル空間は複製できません")
        papers = list_paper_layout_names_sorted(self.doc)
        if source_name not in papers:
            raise ValueError(f"レイアウト {source_name!r} は用紙レイアウトではありません")

        self.doc.layouts.new(dest_name)
        self.ensure_minimal_page(dest_name)

        dest_blk = paper_layout_block(self.doc, dest_name)
        for e in list(dest_blk):
            destroy_entity(self.doc, e)

        src_blk = paper_layout_block(self.doc, source_name)
        for e in list(src_blk):
            try:
                ne = e.copy()
                dest_blk.add_entity(ne)
            except Exception as ex:
                logic_cad_log("layout", f"duplicate_page skip {e.dxftype()}: {ex}")

        old_to_new: dict[str, str] = {}
        for e in list(dest_blk):
            u = get_uid(e)
            if not u or u in old_to_new:
                continue
            old_to_new[u] = new_uid()

        remap_layout_block_ld_uids(dest_blk, old_to_new)

        refresh_page_ref_syms_on_layout(self.doc, dest_name)
        refresh_inpage_ref_syms_on_layout(self.doc, dest_name)
