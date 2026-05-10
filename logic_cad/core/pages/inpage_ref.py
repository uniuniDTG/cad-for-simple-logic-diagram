"""In-page INPAGE_REF pairs: ※n labels among auto pairs; optional manual ``sym`` (``inpage_link_name_auto``)."""

from __future__ import annotations

from ezdxf.document import Drawing

from logic_cad.core.model.constants import (
    ENTITY_TYPE_INPAGE_REF,
    INPAGE_LINK_NAME_AUTO_XDATA,
    INPAGE_MARKER_PREFIX,
    PEER_UID_XDATA,
)
from logic_cad.core.model.xdata import build_ld_app_tags, get_type, get_uid, read_ld_app_dict, set_entity_xdata
from logic_cad.core.paper_layout_access import paper_layout_block
from logic_cad.core.pages.insert_geom_sort import insert_geom_sort_tuple


def inpage_ref_label(ordinal_1based: int) -> str:
    """Display text for pair *ordinal_1based* (1, 2, …) on one layout.

    Args:
        ordinal_1based: 1-based index among valid pairs on the layout.

    Returns:
        String ``※`` + decimal index (e.g. ``※1``).
    """
    return f"{INPAGE_MARKER_PREFIX}{int(ordinal_1based)}"


def _insert_uid(e) -> str:
    return (read_ld_app_dict(e).get("uid") or get_uid(e) or "").strip()


def _pair_sort_key(e1, e2) -> tuple[float, float, str]:
    k1 = insert_geom_sort_tuple(e1)
    k2 = insert_geom_sort_tuple(e2)
    return k1 if k1 < k2 else k2


def _inpage_link_name_is_manual(xd: dict[str, str]) -> bool:
    """Return True when the pair end uses a user-defined link label (not auto ※n among auto pairs)."""
    return (xd.get(INPAGE_LINK_NAME_AUTO_XDATA) or "").strip() == "0"


def refresh_inpage_ref_syms_on_layout(doc: Drawing, layout_name: str) -> None:
    """Assign ``sym`` + XDATA for every INPAGE_REF on *layout_name*.

    Auto pairs (``inpage_link_name_auto`` not ``0``) receive ``※1``, ``※2``, … in pair sort order,
    counting **only** auto pairs. Manual pairs keep ``sym`` in sync on both ends and do not consume
    an auto ordinal.

    Args:
        doc: Drawing.
        layout_name: Paper layout name.

    Returns:
        None
    """
    layout = doc.layouts.get(layout_name)
    if layout.is_modelspace:
        return
    blk = paper_layout_block(doc, layout_name)

    inserts: list = []
    for e in blk:
        if e.dxftype() != "INSERT":
            continue
        if get_type(e) != ENTITY_TYPE_INPAGE_REF:
            continue
        inserts.append(e)

    uid_to_ent: dict[str, object] = {}
    for e in inserts:
        u = _insert_uid(e)
        if u:
            uid_to_ent[u] = e

    pair_edges: list[tuple[object, object]] = []
    seen_pair: set[tuple[str, str]] = set()
    for e in inserts:
        u = _insert_uid(e)
        if not u:
            continue
        d = read_ld_app_dict(e)
        peer = (d.get(PEER_UID_XDATA) or "").strip()
        if not peer or peer not in uid_to_ent:
            continue
        ep = uid_to_ent[peer]
        if get_type(ep) != ENTITY_TYPE_INPAGE_REF:
            continue
        a, b = (u, peer) if u < peer else (peer, u)
        key = (a, b)
        if key in seen_pair:
            continue
        seen_pair.add(key)
        pair_edges.append((uid_to_ent[a], uid_to_ent[b]))

    pair_edges.sort(key=lambda ab: _pair_sort_key(ab[0], ab[1]))

    in_pair: set[str] = set()
    for ea, eb in pair_edges:
        in_pair.add(_insert_uid(ea))
        in_pair.add(_insert_uid(eb))

    auto_ordinal = 0
    for ea, eb in pair_edges:
        da = read_ld_app_dict(ea)
        db = read_ld_app_dict(eb)
        if _inpage_link_name_is_manual(da) or _inpage_link_name_is_manual(db):
            text = (da.get("sym") or "").strip() or (db.get("sym") or "").strip()
            for ent in (ea, eb):
                prev = read_ld_app_dict(ent)
                uid_str = prev.get("uid") or get_uid(ent)
                if not uid_str:
                    continue
                extra = {k: v for k, v in prev.items() if k not in ("ver", "uid", "type")}
                extra["sym"] = text
                extra[INPAGE_LINK_NAME_AUTO_XDATA] = "0"
                tags = build_ld_app_tags("1", uid_str, ENTITY_TYPE_INPAGE_REF, extra)
                set_entity_xdata(ent, tags)
                for a in ent.attribs:
                    if str(a.dxf.tag).upper() == "SYM":
                        a.dxf.text = text
                        break
            continue
        auto_ordinal += 1
        sym = inpage_ref_label(auto_ordinal)
        for ent in (ea, eb):
            prev = read_ld_app_dict(ent)
            uid_str = prev.get("uid") or get_uid(ent)
            if not uid_str:
                continue
            extra = {k: v for k, v in prev.items() if k not in ("ver", "uid", "type")}
            extra["sym"] = sym
            extra[INPAGE_LINK_NAME_AUTO_XDATA] = "1"
            tags = build_ld_app_tags("1", uid_str, ENTITY_TYPE_INPAGE_REF, extra)
            set_entity_xdata(ent, tags)
            for a in ent.attribs:
                if str(a.dxf.tag).upper() == "SYM":
                    a.dxf.text = sym
                    break

    for e in inserts:
        u = _insert_uid(e)
        if not u or u in in_pair:
            continue
        prev = read_ld_app_dict(e)
        uid_str = prev.get("uid") or get_uid(e)
        if not uid_str:
            continue
        extra = {k: v for k, v in prev.items() if k not in ("ver", "uid", "type")}
        extra["sym"] = ""
        extra[INPAGE_LINK_NAME_AUTO_XDATA] = "1"
        tags = build_ld_app_tags("1", uid_str, ENTITY_TYPE_INPAGE_REF, extra)
        set_entity_xdata(e, tags)
        for a in e.attribs:
            if str(a.dxf.tag).upper() == "SYM":
                a.dxf.text = ""
                break


def refresh_all_inpage_ref_syms(doc: Drawing) -> None:
    """Renumber INPAGE_REF on every paper layout.

    Args:
        doc: Drawing.

    Returns:
        None
    """
    for layout in doc.layouts:
        if not layout.is_modelspace:
            refresh_inpage_ref_syms_on_layout(doc, layout.name)
