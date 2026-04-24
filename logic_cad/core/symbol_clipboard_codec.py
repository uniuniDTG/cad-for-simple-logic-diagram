"""JSON codec for :class:`SymbolClipboardPayload` (system clipboard, cross-process).

Encodes clipboard payloads as UTF-8 JSON with a version field. All dict values
in xdata fields are normalized to strings for stable round-trips.
"""

from __future__ import annotations

import json
from typing import Any

from logic_cad.core.model.constants import LINETYPE_CONTINUOUS
from logic_cad.core.symbol_clipboard import (
    SymbolClipboardPayload,
    SymbolCopyRecord,
    UserSketchCopyRecord,
    WireCopyRecord,
)

# Custom MIME for QClipboard (logic_cad symbol / wire / user-sketch payload).
SYMBOL_CLIPBOARD_MIME = "application/x-logic-cad-symbol-clipboard"

# Bump when the JSON object shape changes (see decode docs).
SYMBOL_CLIPBOARD_JSON_VERSION = 1


def _xdata_for_json(d: dict[str, Any]) -> dict[str, str]:
    """Normalize xdata-like dicts to JSON-safe string values.

    Args:
        d: Arbitrary key/value mapping from LD_APP-style dicts.

    Returns:
        Copy with string keys and string values (``None`` becomes an empty string).
    """

    out: dict[str, str] = {}
    for k, v in d.items():
        out[str(k)] = "" if v is None else str(v)
    return out


def _user_sketch_to_obj(rec: UserSketchCopyRecord) -> dict[str, Any]:
    """Serialize one :class:`UserSketchCopyRecord` to a JSON object.

    Args:
        rec: User geometry row from the in-memory clipboard payload.

    Returns:
        Plain ``dict`` suitable for :func:`json.dumps`.
    """

    o: dict[str, Any] = {
        "entity_type": rec.entity_type,
        "linetype": rec.linetype,
        "line_start": list(rec.line_start) if rec.line_start is not None else None,
        "line_end": list(rec.line_end) if rec.line_end is not None else None,
        "circle_center": list(rec.circle_center) if rec.circle_center is not None else None,
        "circle_radius": float(rec.circle_radius),
        "text_insert": [float(rec.text_insert[0]), float(rec.text_insert[1])],
        "text": rec.text,
        "text_height_mm": float(rec.text_height_mm),
        "cloud_points_xyb": [
            [float(x), float(y), float(b)] for x, y, b in rec.cloud_points_xyb
        ],
        "cloud_is_closed": bool(rec.cloud_is_closed),
        "cloud_pitch_mm": rec.cloud_pitch_mm,
        "cloud_guide_vertices": (
            [[float(x), float(y)] for x, y in rec.cloud_guide_vertices]
            if rec.cloud_guide_vertices is not None
            else None
        ),
    }
    return o


def _user_sketch_from_obj(o: dict[str, Any]) -> UserSketchCopyRecord:
    """Deserialize one user sketch object.

    Args:
        o: JSON object from :func:`_user_sketch_to_obj` or compatible input.

    Returns:
        Reconstructed :class:`UserSketchCopyRecord`.

    Raises:
        ValueError: If required fields are missing or have wrong shapes.
    """

    try:
        et = str(o["entity_type"])
        lt = str(o.get("linetype") or "") or LINETYPE_CONTINUOUS
        ls = o.get("line_start")
        le = o.get("line_end")
        line_start = (float(ls[0]), float(ls[1])) if isinstance(ls, list) and len(ls) >= 2 else None
        line_end = (float(le[0]), float(le[1])) if isinstance(le, list) and len(le) >= 2 else None
        cc = o.get("circle_center")
        circle_center = (float(cc[0]), float(cc[1])) if isinstance(cc, list) and len(cc) >= 2 else None
        ti = o.get("text_insert") or [0.0, 0.0]
        if not isinstance(ti, list) or len(ti) < 2:
            raise ValueError("text_insert must be [x, y]")
        text_insert = (float(ti[0]), float(ti[1]))
        cpg = o.get("cloud_guide_vertices")
        gv: list[tuple[float, float]] | None = None
        if isinstance(cpg, list):
            gv = []
            for row in cpg:
                if isinstance(row, list) and len(row) >= 2:
                    gv.append((float(row[0]), float(row[1])))
        elif cpg is not None:
            raise ValueError("cloud_guide_vertices invalid")
        cpp = o.get("cloud_points_xyb")
        cloud_points_xyb: list[tuple[float, float, float]] = []
        if isinstance(cpp, list):
            for row in cpp:
                if isinstance(row, list) and len(row) >= 3:
                    cloud_points_xyb.append((float(row[0]), float(row[1]), float(row[2])))
                elif isinstance(row, list) and len(row) == 2:
                    cloud_points_xyb.append((float(row[0]), float(row[1]), 0.0))
        pitch_raw = o.get("cloud_pitch_mm")
        cloud_pitch_mm: float | None = float(pitch_raw) if pitch_raw is not None else None
        return UserSketchCopyRecord(
            entity_type=et,
            linetype=lt,
            line_start=line_start,
            line_end=line_end,
            circle_center=circle_center,
            circle_radius=float(o.get("circle_radius") or 0.0),
            text_insert=text_insert,
            text=str(o.get("text") or ""),
            text_height_mm=float(o.get("text_height_mm") or 4.0),
            cloud_points_xyb=cloud_points_xyb,
            cloud_is_closed=bool(o.get("cloud_is_closed", True)),
            cloud_pitch_mm=cloud_pitch_mm,
            cloud_guide_vertices=gv,
        )
    except (KeyError, TypeError, ValueError) as ex:
        raise ValueError(f"Invalid user_sketches row: {ex}") from ex


def encode_symbol_clipboard_payload_to_bytes(payload: SymbolClipboardPayload) -> bytes:
    """Serialize ``payload`` to UTF-8 JSON bytes for the system clipboard.

    Args:
        payload: Clipboard payload built by :meth:`LogicDiagram.build_symbol_clipboard_payload`.

    Returns:
        UTF-8 encoded JSON object ``{"v": int, "symbols": ..., "wires": ..., "user_sketches": ...}``.
    """

    symbols_out: list[dict[str, Any]] = []
    for s in payload.symbols:
        symbols_out.append(
            {
                "source_uid": s.source_uid,
                "block_name": s.block_name,
                "insert": [float(s.insert[0]), float(s.insert[1])],
                "rotation": float(s.rotation),
                "xscale": float(s.xscale),
                "yscale": float(s.yscale),
                "zscale": float(s.zscale),
                "entity_type": s.entity_type,
                "xdata_extra": _xdata_for_json(dict(s.xdata_extra)),
                "attribs": [[a[0], a[1], int(a[2])] for a in s.attribs],
            }
        )
    wires_out: list[dict[str, Any]] = []
    for w in payload.wires:
        wires_out.append(
            {
                "source_uid": w.source_uid,
                "points": [[float(x), float(y)] for x, y in w.points],
                "linetype": w.linetype,
                "xdata_extra": _xdata_for_json(dict(w.xdata_extra)),
            }
        )
    sketches_out = [_user_sketch_to_obj(u) for u in payload.user_sketches]
    root = {
        "v": SYMBOL_CLIPBOARD_JSON_VERSION,
        "symbols": symbols_out,
        "wires": wires_out,
        "user_sketches": sketches_out,
    }
    text = json.dumps(root, ensure_ascii=False, separators=(",", ":"))
    return text.encode("utf-8")


def decode_symbol_clipboard_payload_from_bytes(data: bytes) -> SymbolClipboardPayload:
    """Deserialize clipboard bytes from :func:`encode_symbol_clipboard_payload_to_bytes`.

    Args:
        data: UTF-8 JSON from the custom MIME payload.

    Returns:
        Reconstructed :class:`SymbolClipboardPayload`.

    Raises:
        ValueError: If ``data`` is not valid JSON, version is unsupported, or structure is invalid.
    """

    if not data:
        raise ValueError("Empty clipboard bytes")
    try:
        root = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as ex:
        raise ValueError(f"Invalid clipboard JSON: {ex}") from ex
    if not isinstance(root, dict):
        raise ValueError("Clipboard root must be a JSON object")
    ver = root.get("v")
    if ver != SYMBOL_CLIPBOARD_JSON_VERSION:
        raise ValueError(
            f"Unsupported symbol clipboard version: {ver!r} (expected {SYMBOL_CLIPBOARD_JSON_VERSION})"
        )
    symbols_raw = root.get("symbols")
    wires_raw = root.get("wires")
    sketches_raw = root.get("user_sketches")
    if not isinstance(symbols_raw, list) or not isinstance(wires_raw, list):
        raise ValueError("symbols and wires must be arrays")
    if sketches_raw is not None and not isinstance(sketches_raw, list):
        raise ValueError("user_sketches must be an array or absent")
    if sketches_raw is None:
        sketches_raw = []

    symbols: list[SymbolCopyRecord] = []
    for i, o in enumerate(symbols_raw):
        if not isinstance(o, dict):
            raise ValueError(f"symbols[{i}] must be an object")
        try:
            ins = o["insert"]
            if not isinstance(ins, list) or len(ins) < 2:
                raise ValueError("insert must be [x, y]")
            attribs_o = o.get("attribs") or []
            attribs: list[tuple[str, str, int]] = []
            if isinstance(attribs_o, list):
                for row in attribs_o:
                    if isinstance(row, list) and len(row) >= 3:
                        attribs.append((str(row[0]), str(row[1]), int(row[2])))
            xe = o.get("xdata_extra") or {}
            if not isinstance(xe, dict):
                raise ValueError("xdata_extra must be an object")
            symbols.append(
                SymbolCopyRecord(
                    source_uid=str(o["source_uid"]),
                    block_name=str(o["block_name"]),
                    insert=(float(ins[0]), float(ins[1])),
                    rotation=float(o["rotation"]),
                    xscale=float(o["xscale"]),
                    yscale=float(o["yscale"]),
                    zscale=float(o["zscale"]),
                    entity_type=str(o["entity_type"]),
                    xdata_extra=_xdata_for_json(xe),
                    attribs=attribs,
                )
            )
        except (KeyError, TypeError, ValueError) as ex:
            raise ValueError(f"Invalid symbols[{i}]: {ex}") from ex

    wires: list[WireCopyRecord] = []
    for i, o in enumerate(wires_raw):
        if not isinstance(o, dict):
            raise ValueError(f"wires[{i}] must be an object")
        try:
            pts = o.get("points") or []
            points: list[tuple[float, float]] = []
            if isinstance(pts, list):
                for row in pts:
                    if isinstance(row, list) and len(row) >= 2:
                        points.append((float(row[0]), float(row[1])))
            xe = o.get("xdata_extra") or {}
            if not isinstance(xe, dict):
                raise ValueError("xdata_extra must be an object")
            wires.append(
                WireCopyRecord(
                    source_uid=str(o["source_uid"]),
                    points=points,
                    linetype=str(o.get("linetype") or ""),
                    xdata_extra=_xdata_for_json(xe),
                )
            )
        except (KeyError, TypeError, ValueError) as ex:
            raise ValueError(f"Invalid wires[{i}]: {ex}") from ex

    user_sketches: list[UserSketchCopyRecord] = []
    for i, o in enumerate(sketches_raw):
        if not isinstance(o, dict):
            raise ValueError(f"user_sketches[{i}] must be an object")
        user_sketches.append(_user_sketch_from_obj(o))

    return SymbolClipboardPayload(symbols=symbols, wires=wires, user_sketches=user_sketches)
