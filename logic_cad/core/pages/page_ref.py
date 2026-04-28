"""Cross-page PAGE_REF INSERT: remap target when a layout is renamed; SYM A/B/C per target on a sheet."""

from __future__ import annotations

from collections import defaultdict

from ezdxf.document import Drawing

from logic_cad.core.model.constants import (
    PAGE_REF_SHOW_PAGE_DESC_XDATA,
    PAGE_REF_SHOW_PAGE_NAME_XDATA,
    PAGE_REF_SHOW_TARGET_INFO_XDATA,
    TARGET_LAYOUT_XDATA,
)
from logic_cad.core.model.xdata import build_ld_app_tags, get_type, get_uid, read_ld_app_dict, set_entity_xdata
from logic_cad.core.pages.page_labels import page_index_to_letters, page_ref_link_label
from logic_cad.core.pages.page_layout_meta import read_page_meta


def count_page_refs_to_target(
    doc: Drawing,
    source_layout: str,
    target_layout: str,
    *,
    exclude_uid: str | None = None,
) -> int:
    """How many PAGE_REF on *source_layout* point to *target_layout* (optional *exclude_uid*)."""
    layout = doc.layouts.get(source_layout)
    if layout.is_modelspace:
        return 0
    blk = doc.blocks.get(layout.block_record_name)
    n = 0
    for e in blk:
        if e.dxftype() != "INSERT":
            continue
        if get_type(e) != "PAGE_REF":
            continue
        d = read_ld_app_dict(e)
        if (d.get(TARGET_LAYOUT_XDATA) or "").strip() != target_layout:
            continue
        uid = d.get("uid") or get_uid(e)
        if exclude_uid and uid == exclude_uid:
            continue
        n += 1
    return n


def page_link_picker_label(
    doc: Drawing,
    source_layout: str,
    target_page: str,
    *,
    exclude_uid: str | None = None,
) -> str:
    """Combo row: ``{page} ({letter}) - {description}`` (*letter* = next suffix if a link is added)."""
    k = count_page_refs_to_target(doc, source_layout, target_page, exclude_uid=exclude_uid)
    letter = page_index_to_letters(k)
    meta = read_page_meta(doc, target_page)
    desc = (meta.get("page_desc") or "").strip() or ""
    return f"{target_page} ({letter}) - {desc}"


def layout_name_for_insert(doc: Drawing, ins) -> str | None:
    """Paper layout name that owns this INSERT (entity must live in a paperspace block)."""
    h = ins.dxf.handle
    for layout in doc.layouts:
        if layout.is_modelspace:
            continue
        blk = doc.blocks.get(layout.block_record_name)
        for e in blk:
            if e.dxf.handle == h:
                return layout.name
    return None


def _block_attdef(doc: Drawing, block_name: str, tag: str):
    if block_name not in doc.blocks:
        return None
    want = str(tag).upper()
    for ent in doc.blocks.get(block_name):
        if ent.dxftype() != "ATTDEF":
            continue
        if str(ent.dxf.tag).upper() == want:
            return ent
    return None


def _upsert_insert_attrib_from_attdef(ins, doc: Drawing, tag: str, text: str, *, visible: bool) -> None:
    attdef = _block_attdef(doc, str(ins.dxf.name), tag)
    if attdef is None:
        return
    inv = 0 if visible else 1
    want = str(tag).upper()
    for a in ins.attribs:
        if str(a.dxf.tag).upper() == want:
            a.dxf.text = text
            a.dxf.invisible = inv
            return
    loc = attdef.dxf.insert
    dxfattribs: dict = {"height": float(getattr(attdef.dxf, "height", 0.25) or 0.25), "invisible": inv}
    if getattr(attdef.dxf, "rotation", None) is not None:
        dxfattribs["rotation"] = float(attdef.dxf.rotation)
    ins.add_attrib(str(attdef.dxf.tag), text, (float(loc.x), float(loc.y)), dxfattribs=dxfattribs)


def _is_on(value: str | None) -> bool:
    return str(value or "").strip() == "1"


def refresh_page_ref_syms_on_layout(doc: Drawing, layout_name: str) -> None:
    """Set ``sym`` + XDATA for every PAGE_REF on *layout_name*: per ``target_layout``, A then B then C …"""
    layout = doc.layouts.get(layout_name)
    if layout.is_modelspace:
        return
    blk = doc.blocks.get(layout.block_record_name)
    groups: dict[str, list] = defaultdict(list)
    for e in blk:
        if e.dxftype() != "INSERT":
            continue
        if get_type(e) != "PAGE_REF":
            continue
        d = read_ld_app_dict(e)
        tgt = (d.get(TARGET_LAYOUT_XDATA) or "").strip()
        if not tgt:
            continue
        groups[tgt].append(e)
    for tgt, ents in groups.items():
        meta = read_page_meta(doc, tgt)
        page_name = tgt
        page_desc = (meta.get("page_desc") or "").strip()
        ents.sort(
            key=lambda ent: (
                -float(ent.dxf.insert.y),
                float(ent.dxf.insert.x),
                str(ent.dxf.handle),
            )
        )
        for i, ent in enumerate(ents):
            sym = page_ref_link_label(tgt, i)
            prev = read_ld_app_dict(ent)
            uid_str = prev.get("uid") or get_uid(ent)
            if not uid_str:
                continue
            extra = {k: v for k, v in prev.items() if k not in ("ver", "uid", "type")}
            extra[TARGET_LAYOUT_XDATA] = tgt
            extra["sym"] = sym
            tags = build_ld_app_tags("1", uid_str, "PAGE_REF", extra)
            set_entity_xdata(ent, tags)
            _upsert_insert_attrib_from_attdef(ent, doc, "SYM", sym, visible=False)
            legacy_show = _is_on(str(extra.get(PAGE_REF_SHOW_TARGET_INFO_XDATA) or "0"))
            show_page_name = legacy_show or _is_on(str(extra.get(PAGE_REF_SHOW_PAGE_NAME_XDATA) or "0"))
            show_page_desc = legacy_show or _is_on(str(extra.get(PAGE_REF_SHOW_PAGE_DESC_XDATA) or "0"))
            _upsert_insert_attrib_from_attdef(ent, doc, "PAGE_NAME", page_name, visible=show_page_name)
            _upsert_insert_attrib_from_attdef(ent, doc, "PAGE_DESC", page_desc, visible=show_page_desc)


def refresh_all_page_ref_syms(doc: Drawing) -> None:
    for layout in doc.layouts:
        if not layout.is_modelspace:
            refresh_page_ref_syms_on_layout(doc, layout.name)


def remap_page_refs(doc: Drawing, old_target: str, new_target: str, pages: list[str]) -> None:
    """Update PAGE_REF inserts that pointed to *old_target* layout name to *new_target*; renumber SYM."""
    _ = pages
    if old_target == new_target:
        return
    for layout in doc.layouts:
        if layout.is_modelspace:
            continue
        blk = doc.blocks.get(layout.block_record_name)
        for e in blk:
            if e.dxftype() != "INSERT":
                continue
            if get_type(e) != "PAGE_REF":
                continue
            d = read_ld_app_dict(e)
            if d.get(TARGET_LAYOUT_XDATA) != old_target:
                continue
            uid = d.get("uid") or get_uid(e)
            if not uid:
                continue
            extra = {k: v for k, v in d.items() if k not in ("ver", "uid", "type")}
            extra[TARGET_LAYOUT_XDATA] = new_target
            extra["sym"] = d.get("sym", "")
            tags = build_ld_app_tags("1", uid, "PAGE_REF", extra)
            set_entity_xdata(e, tags)
    refresh_all_page_ref_syms(doc)
