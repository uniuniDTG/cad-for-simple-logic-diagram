"""Remap LD_APP UIDs inside a paper layout block (import/duplicate)."""

from __future__ import annotations

from logic_cad.core.model.constants import (
    ENTITY_TYPE_INPAGE_REF,
    ENTITY_TYPE_WIRE_BRANCH_HATCH,
    PEER_UID_XDATA,
)
from logic_cad.core.model.xdata import build_ld_app_tags, get_type, get_uid, read_ld_app_dict, set_entity_xdata


def remap_layout_block_ld_uids(dest_blk: object, old_to_new: dict[str, str]) -> None:
    """Apply *old_to_new* uid map to LD-tagged entities in a paper layout block.

    Phase 1 assigns new ``uid`` in XDATA on every mapped entity; phase 2 remaps ``WIRE``,
    ``WIRE_ALIAS``, wire-branch hatch dependencies, ``INPAGE_REF``, and ``PAGE_REF`` peer
    UIDs embedded in dictionaries.

    Args:
        dest_blk: Block layout (paperspace layout block record).
        old_to_new: Mapping from previously collected UIDs to new UIDs.
    """
    for ent in list(dest_blk):
        u = get_uid(ent)
        if not u:
            continue
        nu = old_to_new.get(u)
        if not nu:
            continue
        d = read_ld_app_dict(ent)
        t = get_type(ent) or "SYM"
        extra = {k: v for k, v in d.items() if k not in ("ver", "uid", "type")}
        set_entity_xdata(ent, build_ld_app_tags("1", nu, t, extra))

    for ent in list(dest_blk):
        t = get_type(ent)
        if not t:
            continue
        d = read_ld_app_dict(ent)
        nu = d.get("uid")
        if not nu:
            continue
        extra = {k: v for k, v in d.items() if k not in ("ver", "uid", "type")}
        if t == "WIRE":
            su, du = extra.get("src"), extra.get("dst")
            if su in old_to_new:
                extra["src"] = old_to_new[su]
            if du in old_to_new:
                extra["dst"] = old_to_new[du]
            set_entity_xdata(ent, build_ld_app_tags("1", nu, "WIRE", extra))
        elif t == ENTITY_TYPE_WIRE_BRANCH_HATCH:
            b = extra.get("branch")
            if b in old_to_new:
                extra["branch"] = old_to_new[b]
            set_entity_xdata(ent, build_ld_app_tags("1", nu, ENTITY_TYPE_WIRE_BRANCH_HATCH, extra))
        elif t == "WIRE_ALIAS":
            w = extra.get("wire")
            if w in old_to_new:
                extra["wire"] = old_to_new[w]
            set_entity_xdata(ent, build_ld_app_tags("1", nu, "WIRE_ALIAS", extra))
        elif t == ENTITY_TYPE_INPAGE_REF:
            p = (extra.get(PEER_UID_XDATA) or "").strip()
            if p in old_to_new:
                extra[PEER_UID_XDATA] = old_to_new[p]
            set_entity_xdata(ent, build_ld_app_tags("1", nu, ENTITY_TYPE_INPAGE_REF, extra))
        elif t == "PAGE_REF":
            peer = (extra.get(PEER_UID_XDATA) or "").strip()
            if peer in old_to_new:
                extra[PEER_UID_XDATA] = old_to_new[peer]
                set_entity_xdata(ent, build_ld_app_tags("1", nu, "PAGE_REF", extra))
