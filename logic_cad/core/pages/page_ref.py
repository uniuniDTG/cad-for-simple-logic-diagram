"""Cross-page PAGE_REF INSERT: remap target when a layout is renamed; SYM A/B/C per target on a sheet."""

from __future__ import annotations

from collections import defaultdict

from ezdxf.document import Drawing

from logic_cad.core.dxf.attrib_geometry_sync import dxfattribs_for_attrib_from_attdef
from logic_cad.core.model.constants import (
    PAGE_REF_RANK_XDATA,
    PAGE_REF_SHOW_PAGE_DESC_XDATA,
    PAGE_REF_SHOW_PAGE_NAME_XDATA,
    PAGE_REF_SHOW_TARGET_INFO_XDATA,
    PEER_UID_XDATA,
    TARGET_LAYOUT_XDATA,
)
from logic_cad.core.model.xdata import build_ld_app_tags, get_type, get_uid, read_ld_app_dict, set_entity_xdata
from logic_cad.core.paper_layout_access import paper_layout_block
from logic_cad.core.pages.insert_geom_sort import insert_geom_sort_tuple
from logic_cad.core.pages.page_layout_meta import read_page_meta
from logic_cad.core.pages.page_labels import page_index_to_letters, page_ref_link_label
from logic_cad.core.pages.page_order import is_toc_layout_name, list_paper_layout_names_sorted


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
    blk = paper_layout_block(doc, source_layout)
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


def _parse_page_ref_rank(d: dict[str, str]) -> int | None:
    raw = str(d.get(PAGE_REF_RANK_XDATA) or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _geom_tuple(ent) -> tuple[float, float, str]:
    """Tiebreaker within PAGE_REF ordering (matches historical behavior)."""
    return insert_geom_sort_tuple(ent)


def page_ref_sort_key(ent, xd: dict[str, str]) -> tuple:
    """Sort key shared by ordinal computation and refresh renumber."""
    rk = _parse_page_ref_rank(xd)
    geo = _geom_tuple(ent)
    if rk is not None:
        return (0, rk) + geo
    return (1,) + geo


def sym_ordinal_numbers_for_sorted_group(ents: list) -> list[int]:
    """Ordinal arguments for ``page_ref_link_label``: rank values when all ranked, else 0..n-1."""
    rks = [_parse_page_ref_rank(read_ld_app_dict(ent)) for ent in ents]
    if rks and all(v is not None for v in rks):
        return [int(v) for v in rks]
    return list(range(len(ents)))


def sorted_page_refs_by_target(layout_block, target_layout: str) -> list:
    """Return PAGE_REF INSERTs targeting *target_layout* in refresh order."""
    ents: list = []
    for e in layout_block:
        if e.dxftype() != "INSERT":
            continue
        if get_type(e) != "PAGE_REF":
            continue
        d = read_ld_app_dict(e)
        tgt = (d.get(TARGET_LAYOUT_XDATA) or "").strip()
        if tgt != target_layout:
            continue
        ents.append(e)
    ents.sort(key=lambda ent: page_ref_sort_key(ent, read_ld_app_dict(ent)))
    return ents


def page_ref_target_layouts_on_sheet(doc: Drawing, layout_name: str) -> list[str]:
    """Distinct ``target_layout`` values for PAGE_REF on *layout_name*, sorted."""
    layout = doc.layouts.get(layout_name)
    if layout.is_modelspace:
        return []
    blk = paper_layout_block(doc, layout_name)
    seen: set[str] = set()
    for e in blk:
        if e.dxftype() != "INSERT" or get_type(e) != "PAGE_REF":
            continue
        d = read_ld_app_dict(e)
        t = (d.get(TARGET_LAYOUT_XDATA) or "").strip()
        if t:
            seen.add(t)
    return sorted(seen)


def page_ref_ordinal_for_uid(doc: Drawing, layout_name: str, uid: str) -> int | None:
    """SYM ordinal integer for *uid*: rank value when the whole ``target`` group is ranked, else 0..n-1."""
    layout = doc.layouts.get(layout_name)
    if layout.is_modelspace:
        return None
    blk = paper_layout_block(doc, layout_name)
    target = ""
    ref_ins = None
    for e in blk:
        if e.dxftype() != "INSERT" or get_type(e) != "PAGE_REF":
            continue
        d = read_ld_app_dict(e)
        u = str(d.get("uid") or get_uid(e) or "")
        if u == uid:
            target = (d.get(TARGET_LAYOUT_XDATA) or "").strip()
            ref_ins = e
            break
    if ref_ins is None or not target:
        return None
    ordered = sorted_page_refs_by_target(blk, target)
    nums = sym_ordinal_numbers_for_sorted_group(ordered)
    try:
        for i, ent in enumerate(ordered):
            d = read_ld_app_dict(ent)
            if str(d.get("uid") or get_uid(ent) or "") == uid:
                return nums[i]
    except (TypeError, ValueError, IndexError):
        return None
    return None


def page_link_picker_label(
    doc: Drawing,
    source_layout: str,
    target_page: str,
    *,
    exclude_uid: str | None = None,
) -> str:
    """Combo row text: letters match actual SYM ordinal when editing *exclude_uid* for that target."""
    if exclude_uid:
        cur_u = exclude_uid.strip()
        if cur_u:
            cur_tgt = ""
            blk0 = paper_layout_block(doc, source_layout)
            for e in blk0:
                if e.dxftype() != "INSERT" or get_type(e) != "PAGE_REF":
                    continue
                d0 = read_ld_app_dict(e)
                if str(d0.get("uid") or get_uid(e) or "") != cur_u:
                    continue
                cur_tgt = (d0.get(TARGET_LAYOUT_XDATA) or "").strip()
                break
            if cur_tgt == target_page:
                ord_i = page_ref_ordinal_for_uid(doc, source_layout, cur_u)
                if ord_i is not None:
                    k = ord_i
                else:
                    k = count_page_refs_to_target(doc, source_layout, target_page, exclude_uid=exclude_uid)
            else:
                k = count_page_refs_to_target(doc, source_layout, target_page, exclude_uid=exclude_uid)
        else:
            k = count_page_refs_to_target(doc, source_layout, target_page)
    else:
        k = count_page_refs_to_target(doc, source_layout, target_page)
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


def corridor_slots_used_for_placement(doc: Drawing, layout_a: str, layout_b: str) -> set[int]:
    """Slots unavailable when choosing a ``PAGE_REF_RANK_XDATA`` on ``layout_a ↔ layout_b`` corridor."""

    used_explicit: set[int] = set()
    has_missing_rank = False
    pessimistic_union: set[int] = set()
    for ln, tgt in ((layout_a, layout_b), (layout_b, layout_a)):
        layout = doc.layouts.get(ln)
        if layout.is_modelspace:
            continue
        blk = paper_layout_block(doc, ln)
        ents = sorted_page_refs_by_target(blk, tgt)
        pessimistic_union |= set(range(len(ents)))
        for ent in ents:
            d = read_ld_app_dict(ent)
            rk = _parse_page_ref_rank(d)
            if rk is not None:
                used_explicit.add(rk)
            else:
                has_missing_rank = True
    if not has_missing_rank:
        return used_explicit
    return pessimistic_union | used_explicit


def vacant_page_ref_sym_ordinals(
    doc: Drawing, layout_src: str, layout_dst: str, *, max_slot: int = 64
) -> list[int]:
    """Ordinal indices that are still free for a new PAGE_REF pair on ``layout_src ↔ layout_dst``."""
    used = corridor_slots_used_for_placement(doc, layout_src, layout_dst)
    return [i for i in range(max_slot) if i not in used]


def page_ref_stored_rank(doc: Drawing, layout_name: str, uid: str) -> int | None:
    """Persisted ``PAGE_REF_RANK_XDATA`` for *uid* on *layout_name*, if any."""
    layout = doc.layouts.get(layout_name)
    if layout is None or layout.is_modelspace:
        return None
    blk = paper_layout_block(doc, layout_name)
    if blk is None:
        return None
    uid_s = str(uid or "").strip()
    for e in blk:
        if e.dxftype() != "INSERT" or get_type(e) != "PAGE_REF":
            continue
        d = read_ld_app_dict(e)
        u = str(d.get("uid") or get_uid(e) or "")
        if u == uid_s:
            return _parse_page_ref_rank(d)
    return None


def page_ref_allowed_sym_ordinals_for_property_edit(
    doc: Drawing,
    source_layout: str,
    uid: str,
    target_layout: str,
    *,
    max_slot: int = 64,
) -> list[int]:
    """Sym ordinals allowed in properties: corridor vacancies plus this link's current slot."""
    tgt = (target_layout or "").strip()
    if not tgt:
        return [0]
    vacant = vacant_page_ref_sym_ordinals(doc, source_layout, tgt, max_slot=max_slot)
    merged: set[int] = set(vacant)
    stored = page_ref_stored_rank(doc, source_layout, uid)
    ord_geom = page_ref_ordinal_for_uid(doc, source_layout, uid)
    cur = stored if stored is not None else ord_geom
    if cur is not None and 0 <= int(cur) < max_slot:
        merged.add(int(cur))
    out = sorted(merged)
    return out if out else [0]


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
    dxfattribs = dxfattribs_for_attrib_from_attdef(attdef)
    dxfattribs["invisible"] = inv
    ins.add_attrib(str(attdef.dxf.tag), text, (float(loc.x), float(loc.y)), dxfattribs=dxfattribs)


def _is_on(value: str | None) -> bool:
    return str(value or "").strip() == "1"


def refresh_page_ref_syms_on_layout(doc: Drawing, layout_name: str) -> None:
    """Set ``sym`` + XDATA for every PAGE_REF on *layout_name*: per ``target_layout``, ordered then labeled."""
    layout = doc.layouts.get(layout_name)
    if layout.is_modelspace:
        return
    blk = paper_layout_block(doc, layout_name)
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
        usable_tgt = page_layout_target_is_usable(doc, tgt)
        ents.sort(key=lambda ent: page_ref_sort_key(ent, read_ld_app_dict(ent)))
        ord_nums = sym_ordinal_numbers_for_sorted_group(ents)
        for i, ent in enumerate(ents):
            sym = page_ref_link_label(tgt, ord_nums[i])
            prev = read_ld_app_dict(ent)
            uid_str = prev.get("uid") or get_uid(ent)
            if not uid_str:
                continue
            lo = layout_name_for_insert(doc, ent) or layout_name
            broken = page_ref_insert_broken_for_editor(doc, lo, prev)
            meta = read_page_meta(doc, tgt) if usable_tgt and not broken else {}
            page_name = tgt
            page_desc = (meta.get("page_desc") or "").strip()
            extra = {k: v for k, v in prev.items() if k not in ("ver", "uid", "type")}
            extra[TARGET_LAYOUT_XDATA] = tgt
            extra["sym"] = sym
            tags = build_ld_app_tags("1", uid_str, "PAGE_REF", extra)
            set_entity_xdata(ent, tags)
            _upsert_insert_attrib_from_attdef(ent, doc, "SYM", sym, visible=True)
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


def find_page_ref_insert(doc: Drawing, uid: str) -> tuple[str, object] | None:
    """Return ``(layout_name, INSERT)`` for a PAGE_REF uid, or ``None``."""
    u = str(uid or "").strip()
    if not u:
        return None
    for layout in doc.layouts:
        if layout.is_modelspace:
            continue
        blk = doc.blocks.get(layout.block_record_name)
        for e in blk:
            if e.dxftype() != "INSERT" or get_type(e) != "PAGE_REF":
                continue
            d = read_ld_app_dict(e)
            if str(d.get("uid") or get_uid(e) or "") != u:
                continue
            return layout.name, e
    return None


def apply_ordered_page_ref_ranks_with_peers(
    doc: Drawing,
    layout_src: str,
    target_dst: str,
    ordered_uids_on_src_side: list[str],
) -> None:
    """Dense ranks ``0 .. n-1`` on INSERTs pointing *layout_src* → *target_dst* and peers on opposite layout."""

    def _merge_rank(ent, rank_val: int) -> None:
        prev = read_ld_app_dict(ent)
        uid_str = prev.get("uid") or get_uid(ent)
        if not uid_str:
            return
        extra = {k: v for k, v in prev.items() if k not in ("ver", "uid", "type")}
        extra[PAGE_REF_RANK_XDATA] = str(int(rank_val))
        tags = build_ld_app_tags("1", uid_str, "PAGE_REF", extra)
        set_entity_xdata(ent, tags)

    layout_s = doc.layouts.get(layout_src)
    if layout_s.is_modelspace:
        return
    blk_src = paper_layout_block(doc, layout_src)
    ents = sorted_page_refs_by_target(blk_src, target_dst)
    present = []
    for e in ents:
        d = read_ld_app_dict(e)
        uid_s = str(d.get("uid") or get_uid(e) or "")
        if uid_s and (d.get(TARGET_LAYOUT_XDATA) or "").strip() == target_dst:
            present.append(uid_s)
    want = [str(u).strip() for u in ordered_uids_on_src_side if str(u).strip()]
    if set(want) != set(present) or len(want) != len(present):
        raise ValueError("ページリンク並べ替え: リストが現在のリンク集合と一致しません。")

    touched: set[str] = set()
    for idx, uid_s in enumerate(want):
        lo, ent_s = find_page_ref_insert(doc, uid_s)
        if lo is None or ent_s is None or lo != layout_src:
            continue
        ds = read_ld_app_dict(ent_s)
        if (ds.get(TARGET_LAYOUT_XDATA) or "").strip() != target_dst:
            continue
        _merge_rank(ent_s, idx)
        touched.add(lo)
        peer = (ds.get(PEER_UID_XDATA) or "").strip()
        if peer:
            lo2, ent_p = find_page_ref_insert(doc, peer)
            if lo2 is not None and ent_p is not None:
                dp = read_ld_app_dict(ent_p)
                if (dp.get(TARGET_LAYOUT_XDATA) or "").strip() == layout_src and str(
                    dp.get(PEER_UID_XDATA) or ""
                ).strip() == uid_s:
                    _merge_rank(ent_p, idx)
                    touched.add(lo2)
    for name in touched:
        refresh_page_ref_syms_on_layout(doc, name)


def page_layout_target_is_usable(doc: Drawing, target_layout_name: str) -> bool:
    """Return True if *target_layout_name* identifies an existing paper layout (not Model).

    Args:
        doc: Drawing to validate against.
        target_layout_name: ``TARGET_LAYOUT_XDATA`` value.

    Returns:
        False for empty names, unknown layouts, model space, or non-paper layouts.
    """
    s = str(target_layout_name or "").strip()
    if not s:
        return False
    if s not in doc.layouts:
        return False
    layout = doc.layouts.get(s)
    if layout.is_modelspace:
        return False
    papers = list_paper_layout_names_sorted(doc)
    return s in papers


def page_ref_peers_mutual_ok(doc: Drawing, ld_app: dict[str, str]) -> bool | None:
    """Return ``True`` if PEER_UID points to an INSERT whose peer_uid round-trips.

    Args:
        doc: Drawing.
        ld_app: LD_APP-like dict including ``uid`` and optionally ``peer_uid``.

    Returns:
        ``None`` when *peer_uid* is absent or empty (stub / not yet paired).
        ``False`` when peer missing in doc or mismatch.
        ``True`` when mutual pairing matches.
    """
    peer_raw = str(ld_app.get(PEER_UID_XDATA) or "").strip()
    if not peer_raw:
        return None
    uid_self = str(ld_app.get("uid") or "").strip()
    if not uid_self:
        return False
    hit = find_page_ref_insert(doc, peer_raw)
    if hit is None:
        return False
    _lo, ins_p = hit
    dp = read_ld_app_dict(ins_p)
    peer_back = str(dp.get(PEER_UID_XDATA) or "").strip()
    return peer_back == uid_self


def page_ref_insert_broken_for_editor(doc: Drawing, layout_here: str, ld_app: dict[str, str]) -> bool:
    """True when PAGE_REF should render as broken (red) on *layout_here*."""
    tgt = str(ld_app.get(TARGET_LAYOUT_XDATA) or "").strip()
    mutual = page_ref_peers_mutual_ok(doc, ld_app)
    if mutual is False:
        return True
    if mutual is None:
        return not page_layout_target_is_usable(doc, tgt)
    return False


def page_ref_insert_target_unresolved_for_editor(
    doc: Drawing, target_layout_name: str, *, layout_here: str | None = None, ld_app: dict[str, str] | None = None
) -> bool:
    """True when a PAGE_REF should be drawn as broken in the editor.

    Two-parameter form keeps legacy behavior (target layout not usable on *doc*).

    When *layout_here* and *ld_app* are given, also treats dangling or mismatched
    ``peer_uid`` as broken (mutual pairing required when peer is set).
    """
    if layout_here is not None and ld_app is not None:
        return page_ref_insert_broken_for_editor(doc, layout_here, ld_app)
    return not page_layout_target_is_usable(doc, target_layout_name)


def _page_ref_rank_pair_compatible(d_a: dict[str, str], d_b: dict[str, str]) -> bool:
    ra = _parse_page_ref_rank(d_a)
    rb = _parse_page_ref_rank(d_b)
    if ra is None and rb is None:
        return True
    if ra is None or rb is None:
        return False
    return int(ra) == int(rb)


def _target_literal_points_to_layout_here(
    cand_target: str, layout_here: str, imported_src_to_dest: dict[str, str]
) -> bool:
    s = str(cand_target or "").strip()
    if not s:
        return False
    if s == layout_here:
        return True
    return str(imported_src_to_dest.get(s) or "").strip() == layout_here


def apply_mutual_page_ref_peer_uids(
    doc: Drawing, layout_a: str, uid_a: str, layout_b: str, uid_b: str
) -> None:
    """Set ``peer_uid`` on both PAGE_REF INSERTs (layout_a/uid_a and layout_b/uid_b)."""
    for lo, ua, peer in ((layout_a, uid_a, uid_b), (layout_b, uid_b, uid_a)):
        hit = find_page_ref_insert(doc, ua)
        if hit is None:
            raise ValueError(f"ページ参照 UID {ua!r} が見つかりません。")
        ln, ins = hit
        if ln != lo:
            raise ValueError(f"ページ参照 UID {ua!r} のレイアウトが一致しません。")
        prev = read_ld_app_dict(ins)
        if get_type(ins) != "PAGE_REF":
            raise ValueError("ページ参照（PAGE_REF）ではありません。")
        uid_str = str(prev.get("uid") or get_uid(ins) or "")
        if not uid_str:
            raise ValueError("INSERT に uid がありません。")
        extra = {k: v for k, v in prev.items() if k not in ("ver", "uid", "type")}
        extra[PEER_UID_XDATA] = peer
        tags = build_ld_app_tags("1", uid_str, "PAGE_REF", extra)
        set_entity_xdata(ins, tags)


def reconnect_page_ref_peers_after_foreign_import(
    doc: Drawing,
    imported_src_to_dest: dict[str, str],
    imported_dest_layouts: list[str],
) -> None:
    """Wire ``peer_uid`` on PAGE_REF INSERTs imported in this batch; never change TARGET_LAYOUT or ranks.

    For each PAGE_REF on *imported_dest_layouts*, if ``peer_uid`` does not resolve in *doc*,
    scan the layout ``imported_src_to_dest.get(raw_target, raw_target)`` for a unique partner
    whose TARGET points back to *layout_here* (via literal or map) and ranks are compatible.

    Refreshes sym/attribs only on layouts that were mutated.
    """
    if not imported_dest_layouts:
        return

    refreshed: set[str] = set()

    for layout_here in imported_dest_layouts:
        layout = doc.layouts.get(layout_here)
        if layout.is_modelspace:
            continue
        blk = paper_layout_block(doc, layout_here)
        for ent in list(blk):
            if ent.dxftype() != "INSERT" or get_type(ent) != "PAGE_REF":
                continue
            d = read_ld_app_dict(ent)
            uid_self = str(d.get("uid") or get_uid(ent) or "").strip()
            if not uid_self:
                continue

            if page_ref_peers_mutual_ok(doc, d) is True:
                continue

            raw_tgt = str(d.get(TARGET_LAYOUT_XDATA) or "").strip()
            if not raw_tgt:
                continue
            l_tgt = str(imported_src_to_dest.get(raw_tgt) or raw_tgt).strip()
            if not l_tgt or not page_layout_target_is_usable(doc, l_tgt):
                continue

            blk_tgt = paper_layout_block(doc, l_tgt)

            candidates: list[tuple[str, dict[str, str], object]] = []
            for cand in blk_tgt:
                if cand.dxftype() != "INSERT" or get_type(cand) != "PAGE_REF":
                    continue
                if cand.dxf.handle == ent.dxf.handle:
                    continue
                cd = read_ld_app_dict(cand)
                uid_c = str(cd.get("uid") or get_uid(cand) or "").strip()
                if not uid_c or uid_c == uid_self:
                    continue
                cand_back = str(cd.get(TARGET_LAYOUT_XDATA) or "").strip()
                if not _target_literal_points_to_layout_here(cand_back, layout_here, imported_src_to_dest):
                    continue
                if not _page_ref_rank_pair_compatible(d, cd):
                    continue
                candidates.append((uid_c, cd, cand))

            if len(candidates) != 1:
                continue
            uid_cand, _, _ins_cand = candidates[0]
            apply_mutual_page_ref_peer_uids(doc, layout_here, uid_self, l_tgt, uid_cand)
            refreshed.add(layout_here)
            refreshed.add(l_tgt)

    for ln in refreshed:
        refresh_page_ref_syms_on_layout(doc, ln)
