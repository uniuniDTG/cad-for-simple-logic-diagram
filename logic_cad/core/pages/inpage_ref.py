"""In-page INPAGE_REF pairs: ※n labels on one sheet (footnote-style)."""

from __future__ import annotations

from ezdxf.document import Drawing

from logic_cad.core.model.constants import (
    ENTITY_TYPE_INPAGE_REF,
    INPAGE_MARKER_PREFIX,
    PEER_UID_XDATA,
)
from logic_cad.core.model.xdata import build_ld_app_tags, get_type, get_uid, read_ld_app_dict, set_entity_xdata


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
    k1 = (-float(e1.dxf.insert.y), float(e1.dxf.insert.x), str(e1.dxf.handle))
    k2 = (-float(e2.dxf.insert.y), float(e2.dxf.insert.x), str(e2.dxf.handle))
    return k1 if k1 < k2 else k2


def refresh_inpage_ref_syms_on_layout(doc: Drawing, layout_name: str) -> None:
    """Assign ``sym`` + XDATA for every INPAGE_REF on *layout_name*; renumber ※1, ※2, … by pair position.

    Args:
        doc: Drawing.
        layout_name: Paper layout name.

    Returns:
        None
    """
    layout = doc.layouts.get(layout_name)
    if layout.is_modelspace:
        return
    blk = doc.blocks.get(layout.block_record_name)

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

    for i, (ea, eb) in enumerate(pair_edges, start=1):
        sym = inpage_ref_label(i)
        for ent in (ea, eb):
            prev = read_ld_app_dict(ent)
            uid_str = prev.get("uid") or get_uid(ent)
            if not uid_str:
                continue
            extra = {k: v for k, v in prev.items() if k not in ("ver", "uid", "type")}
            extra["sym"] = sym
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
