"""Symbol and user-sketch clipboard build/paste helpers for :class:`LogicDiagram`.

Kept separate from :mod:`logic_cad.core.logic_diagram` to keep the facade smaller
without changing the public :class:`LogicDiagram` API.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from logic_cad.core.model.constants import ENTITY_TYPE_INPAGE_REF, PEER_UID_XDATA
from logic_cad.core.model.xdata import (
    build_ld_app_tags,
    get_type,
    get_uid,
    read_ld_app_dict,
    set_entity_xdata,
)
from logic_cad.core.pages.inpage_ref import refresh_inpage_ref_syms_on_layout
from logic_cad.core.routing import snap_to_grid
from logic_cad.core.symbol_clipboard import SymbolClipboardPayload

if TYPE_CHECKING:
    from logic_cad.core.logic_diagram import LogicDiagram


def build_symbol_clipboard_payload(
    diagram: LogicDiagram,
    symbol_uids: list[str],
    user_sketch_uids: list[str] | None = None,
) -> SymbolClipboardPayload:
    """Collect symbol, internal wire, and user-sketch records for clipboard export.

    Args:
        diagram: Active diagram facade (current layout and services).
        symbol_uids: INSERT uids to serialize from the current layout.
        user_sketch_uids: Optional USER_* sketch uids to include.

    Returns:
        Payload suitable for :func:`paste_symbol_clipboard_payload`.
    """
    layout = diagram.current_layout_name
    user_sketch_uids = user_sketch_uids or []
    symbols = []
    for u in symbol_uids:
        if not u:
            continue
        rec = diagram.symbols.clipboard_record_for_insert(layout, u)
        if rec is not None:
            symbols.append(rec)
    uid_set = {rec.source_uid for rec in symbols}
    wires = diagram.wires.clipboard_records_internal_wires(layout, uid_set)
    sketches = []
    for u in user_sketch_uids:
        if not u:
            continue
        sr = diagram.user_geom.clipboard_record_for_uid(u)
        if sr is not None:
            sketches.append(sr)
    return SymbolClipboardPayload(symbols=symbols, wires=wires, user_sketches=sketches)


def paste_symbol_clipboard_payload(
    diagram: LogicDiagram,
    payload: SymbolClipboardPayload,
    anchor_dxf: tuple[float, float],
) -> tuple[list[str], list[str]]:
    """Paste symbols/wires and/or user sketches; return (new INSERT uids, new sketch uids).

    Args:
        diagram: Active diagram facade.
        payload: Serialized clipboard content.
        anchor_dxf: Paste origin in DXF coordinates (mm).

    Returns:
        Tuple of new symbol INSERT uids and new user-sketch uids. Both lists are
        empty when *payload* has no symbols and no sketches.
    """
    layout = diagram.current_layout_name
    if not payload.symbols and not payload.user_sketches:
        return [], []
    minx, miny = payload.bbox_min()
    minx, miny = snap_to_grid(minx, miny)
    ax, ay = snap_to_grid(float(anchor_dxf[0]), float(anchor_dxf[1]))
    dx, dy = ax - minx, ay - miny
    pasted_syms: list[str] = []
    old_to_new: dict[str, str] = {}
    if payload.symbols:
        for rec in payload.symbols:
            pos = snap_to_grid(rec.insert[0] + dx, rec.insert[1] + dy)
            nu = diagram.symbols.paste_insert_from_clipboard(layout, rec, pos)
            old_to_new[rec.source_uid] = nu
            pasted_syms.append(nu)
        diagram.rebuild_index()
        for wrec in payload.wires:
            diagram.wires.paste_wire_from_clipboard(layout, wrec, old_to_new, (dx, dy))
        diagram.rebuild_index()
        diagram.wires.recompute_all_bridges_ordered(layout)
        for nu in pasted_syms:
            ins = diagram.symbols.insert_by_uid(layout, nu)
            if ins is None:
                continue
            if get_type(ins) != ENTITY_TYPE_INPAGE_REF:
                continue
            d = read_ld_app_dict(ins)
            p = (d.get(PEER_UID_XDATA) or "").strip()
            if p in old_to_new:
                p2 = old_to_new[p]
                uid_str = str(d.get("uid") or get_uid(ins) or "")
                extra = {k: v for k, v in d.items() if k not in ("ver", "uid", "type")}
                extra[PEER_UID_XDATA] = p2
                set_entity_xdata(ins, build_ld_app_tags("1", uid_str, ENTITY_TYPE_INPAGE_REF, extra))
        refresh_inpage_ref_syms_on_layout(diagram.doc, layout)
    pasted_sk: list[str] = []
    if payload.user_sketches:
        for ur in payload.user_sketches:
            nu = diagram.user_geom.paste_sketch_record(layout, ur, dx, dy)
            pasted_sk.append(nu)
        diagram.rebuild_index()
    return pasted_syms, pasted_sk
