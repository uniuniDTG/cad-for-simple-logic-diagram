"""Block definition editor: copy/paste entities within the scratch document (JSON MIME).

Serialized payloads use :func:`serialize_entity` / :func:`restore_entity_from_payload`.
Supported types for v1: LD_PORT POINT, LINE (incl. USER_LINE), CIRCLE (incl. USER_CIRCLE),
LWPOLYLINE, ARC, ATTDEF, TEXT, MTEXT. INSERT and other types are skipped on copy.
"""

from __future__ import annotations

import copy
import json
from typing import Any

from logic_cad.core.model.constants import ENTITY_TYPE_USER_ARC, ENTITY_TYPE_USER_CIRCLE, ENTITY_TYPE_USER_LINE
from logic_cad.core.model.port_key import PortKey, format_port_layer, parse_port_layer
from logic_cad.core.model.xdata import ensure_regapp, new_uid
from logic_cad.core.services.block_edit_helpers import port_layer_is_taken
from logic_cad.core.services.block_edit_session import BlockEditSession
from logic_cad.core.undo.entity_serialize import restore_entity_from_payload, serialize_entity
from logic_cad.core.undo.history import find_entity_by_uid

BLOCK_EDIT_ENTITIES_MIME = "application/x-logic-cad-block-edit-entities"
_BLOCK_CLIPBOARD_JSON_VERSION = 1

_ALLOWED_COPY_TYPES = frozenset({"POINT", "LINE", "CIRCLE", "LWPOLYLINE", "ARC", "ATTDEF", "TEXT", "MTEXT"})


def _tuple2(v: Any) -> tuple[float, float] | None:
    if v is None or len(v) < 2:
        return None
    return float(v[0]), float(v[1])


def _geom_sample_points(payload: dict[str, Any]) -> list[tuple[float, float]]:
    et = str(payload.get("dxftype") or "")
    g = payload.get("geometry") or {}
    out: list[tuple[float, float]] = []
    if et == "LINE":
        for key in ("start", "end"):
            t = _tuple2(g.get(key))
            if t:
                out.append(t)
    elif et == "CIRCLE":
        t = _tuple2(g.get("center"))
        if t:
            out.append(t)
    elif et == "POINT":
        t = _tuple2(g.get("location"))
        if t:
            out.append(t)
    elif et == "LWPOLYLINE":
        rows = g.get("points_xyb") or []
        for row in rows:
            if row is not None and len(row) >= 2:
                out.append((float(row[0]), float(row[1])))
    elif et == "ARC":
        t = _tuple2(g.get("center"))
        if t:
            out.append(t)
    elif et == "ATTDEF":
        t = _tuple2(g.get("insert"))
        if t:
            out.append(t)
    elif et in ("TEXT", "MTEXT"):
        t = _tuple2(g.get("insert"))
        if t:
            out.append(t)
    return out


def _anchor_dxf(payloads: list[dict[str, Any]]) -> tuple[float, float]:
    pts: list[tuple[float, float]] = []
    for p in payloads:
        pts.extend(_geom_sample_points(p))
    if not pts:
        return (0.0, 0.0)
    ax = sum(x for x, _ in pts) / len(pts)
    ay = sum(y for _, y in pts) / len(pts)
    return (ax, ay)


def _offset_payload_geom(payload: dict[str, Any], dx: float, dy: float) -> None:
    g = payload.get("geometry")
    if not isinstance(g, dict):
        return
    et = str(payload.get("dxftype") or "")

    def off_pt(key: str) -> None:
        t = g.get(key)
        if t is None or len(t) < 2:
            return
        z = float(t[2]) if len(t) > 2 else 0.0
        g[key] = (float(t[0]) + dx, float(t[1]) + dy, z)

    if et == "LINE":
        off_pt("start")
        off_pt("end")
    elif et == "CIRCLE":
        off_pt("center")
    elif et == "POINT":
        off_pt("location")
    elif et == "ARC":
        off_pt("center")
    elif et == "ATTDEF":
        off_pt("insert")
    elif et in ("TEXT", "MTEXT"):
        off_pt("insert")
    elif et == "LWPOLYLINE":
        rows = g.get("points_xyb")
        if isinstance(rows, list):
            g["points_xyb"] = [
                (float(row[0]) + dx, float(row[1]) + dy, float(row[2]) if len(row) > 2 else 0.0)
                for row in rows
            ]


def _rewrite_uid_for_user_sketch_payload(payload: dict[str, Any]) -> None:
    xd = payload.get("xdata_ld_app")
    if not isinstance(xd, list) or not xd:
        return
    typ: str | None = None
    for code, val in xd:
        if int(code) == 1000 and str(val).startswith("type:"):
            typ = str(val).split(":", 1)[1].strip()
            break
    if typ not in (ENTITY_TYPE_USER_LINE, ENTITY_TYPE_USER_CIRCLE, ENTITY_TYPE_USER_ARC):
        return
    nu = new_uid()
    new_xd: list[tuple[int, str]] = []
    for code, val in xd:
        c = int(code)
        if c == 1000 and str(val).startswith("uid:"):
            new_xd.append((c, f"uid:{nu}"))
        else:
            new_xd.append((c, str(val)))
    payload["xdata_ld_app"] = new_xd


def _existing_attdef_tags_upper(block) -> set[str]:
    out: set[str] = set()
    for e in block:
        if e.dxftype() == "ATTDEF":
            out.add(str(e.dxf.tag).strip().upper())
    return out


def _ensure_unique_attdef_payload(payload: dict[str, Any], reserved_upper: set[str]) -> None:
    if str(payload.get("dxftype") or "") != "ATTDEF":
        return
    g = payload.get("geometry")
    if not isinstance(g, dict):
        return
    tag0 = str(g.get("tag") or "").strip()
    if not tag0:
        return
    cand = tag0
    n = 0
    while cand.upper() in reserved_upper:
        n += 1
        cand = f"{tag0}_{n}"
    g["tag"] = cand
    reserved_upper.add(cand.upper())


def _remap_port_layer_if_taken(payload: dict[str, Any], block) -> None:
    if str(payload.get("dxftype") or "") != "POINT":
        return
    da = payload.get("dxfattribs")
    if not isinstance(da, dict):
        return
    layer = str(da.get("layer") or "").strip()
    pk = parse_port_layer(layer)
    if pk is None:
        return
    if not port_layer_is_taken(block, layer):
        return
    idx = int(pk.index)
    for _ in range(100):
        nl = format_port_layer(PortKey(direction=pk.direction, index=idx, unit=pk.unit))
        if not port_layer_is_taken(block, nl):
            da["layer"] = nl
            return
        idx += 1


def encode_entity_payloads(payloads: list[dict[str, Any]]) -> bytes | None:
    """Serialize entity dicts to UTF-8 JSON for the block-edit clipboard MIME.

    Args:
        payloads: List of :func:`serialize_entity` results for one block.

    Returns:
        Encoded bytes, or ``None`` when *payloads* is empty.
    """
    if not payloads:
        return None
    ax, ay = _anchor_dxf(payloads)
    root = {
        "version": _BLOCK_CLIPBOARD_JSON_VERSION,
        "anchor_dxf": [ax, ay],
        "entities": payloads,
    }
    return json.dumps(root, separators=(",", ":")).encode("utf-8")


def decode_entity_clipboard(data: bytes) -> dict[str, Any] | None:
    """Parse clipboard bytes into a root dict (version, anchor_dxf, entities).

    Args:
        data: Raw UTF-8 JSON from :func:`encode_entity_payloads`.

    Returns:
        Root mapping, or ``None`` when invalid or version mismatch.
    """
    if not data:
        return None
    try:
        root = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(root, dict):
        return None
    if int(root.get("version", 0)) != _BLOCK_CLIPBOARD_JSON_VERSION:
        return None
    ent = root.get("entities")
    if not isinstance(ent, list) or not ent:
        return None
    return root


def entity_payload_allowed_for_block_copy(payload: dict[str, Any]) -> bool:
    """Return True if *payload* is a supported block entity type for copy/paste.

    Args:
        payload: One serialized entity dict.

    Returns:
        False for unknown types or POINT without ``LD_PORT_*`` layer.
    """
    et = str(payload.get("dxftype") or "")
    if et not in _ALLOWED_COPY_TYPES:
        return False
    if et == "POINT":
        da = payload.get("dxfattribs") or {}
        layer = str(da.get("layer") or "")
        return parse_port_layer(layer) is not None
    return True


def paste_entity_clipboard_root(
    session: BlockEditSession,
    root: dict[str, Any],
    paste_anchor_dxf: tuple[float, float],
) -> list[str]:
    """Clone entities from decoded *root* into the scratch block under one undo transaction.

    Args:
        session: Active block edit session.
        root: Result of :func:`decode_entity_clipboard`.
        paste_anchor_dxf: Target paste position in DXF mm (e.g. cursor).

    Returns:
        Handles of newly created entities in the scratch block.
    """
    doc = session.scratch_doc
    blk = session.scratch_block()
    if blk is None:
        return []
    anchor = root.get("anchor_dxf")
    if not isinstance(anchor, list) or len(anchor) < 2:
        return []
    ax, ay = float(anchor[0]), float(anchor[1])
    px, py = float(paste_anchor_dxf[0]), float(paste_anchor_dxf[1])
    dx, dy = px - ax, py - ay
    block_name = session.scratch_block_name or session.block_name
    owner_blob = {"kind": "block", "name": block_name}

    raw_list = root.get("entities")
    if not isinstance(raw_list, list):
        return []

    ensure_regapp(doc)

    reserved_attdef = _existing_attdef_tags_upper(blk)
    new_handles: list[str] = []
    with session.begin("block_edit_paste_entities"):
        for raw in raw_list:
            if not isinstance(raw, dict):
                continue
            if not entity_payload_allowed_for_block_copy(raw):
                continue
            pl = copy.deepcopy(raw)
            pl.pop("handle", None)
            pl["owner"] = owner_blob
            _offset_payload_geom(pl, dx, dy)
            _rewrite_uid_for_user_sketch_payload(pl)
            _ensure_unique_attdef_payload(pl, reserved_attdef)
            _remap_port_layer_if_taken(pl, blk)
            ent = restore_entity_from_payload(doc, pl)
            if ent is not None:
                h = str(getattr(ent.dxf, "handle", "") or "")
                if h:
                    new_handles.append(h)
    return new_handles


def collect_serialized_entities_from_block(
    doc,
    blk,
    handle_keys: list[tuple[str, str]],
) -> list[dict[str, Any]]:
    """Build serialized payloads for entities selected by handle or USER sketch uid.

    Args:
        doc: Scratch drawing (for uid lookup).
        blk: Scratch block layout.
        handle_keys: Pairs ``("handle", h)`` or ``("uid", sketch_uid)``.

    Returns:
        Serializable dicts filtered by :func:`entity_payload_allowed_for_block_copy`.
    """
    payloads: list[dict[str, Any]] = []
    for kind, key in handle_keys:
        ent = None
        if kind == "handle":
            for e in blk:
                if str(getattr(e.dxf, "handle", "") or "") == key:
                    ent = e
                    break
        else:
            ent = find_entity_by_uid(doc, key)
        if ent is None:
            continue
        pl = serialize_entity(doc, ent)
        if entity_payload_allowed_for_block_copy(pl):
            payloads.append(pl)
    return payloads
