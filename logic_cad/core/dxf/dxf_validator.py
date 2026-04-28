"""DXF consistency checks (load / save)."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import TYPE_CHECKING

from logic_cad.core.model.constants import ALL_LAYERS, APPID, ENTITY_TYPE_WIRE_ARROW, LAYER_VPORT
from logic_cad.core.model.wire_layers import is_wire_layer
from logic_cad.core.model.xdata import get_type, get_uid, read_ld_app_dict
from logic_cad.core.pages.page_order import validate_paper_layout_name

if TYPE_CHECKING:
    from ezdxf.document import Drawing

_PORT_LAYER_RE = re.compile(r"^LD_PORT_(IN|OUT)(\d+)_(LOGIC|VALUE|MULTI|COM)$")


def _validate_block_port_definitions(doc: Drawing) -> list[str]:
    issues: list[str] = []
    for block in doc.blocks:
        name = str(block.name)
        if name.startswith("*"):
            continue
        port_layers = [str(e.dxf.layer) for e in block if e.dxftype() == "POINT" and str(e.dxf.layer).startswith("LD_PORT_")]
        if not port_layers:
            continue
        counts = Counter(port_layers)
        for layer, count in sorted(counts.items()):
            if count > 1:
                issues.append(f"ブロック {name!r}: ポートレイヤー {layer!r} が重複しています（{count} 点）。")
        indexed: dict[tuple[str, str], set[int]] = defaultdict(set)
        for layer in port_layers:
            m = _PORT_LAYER_RE.fullmatch(layer)
            if m is None:
                issues.append(f"ブロック {name!r}: ポートレイヤー {layer!r} が不正です。")
                continue
            direction, idx_s, unit = m.groups()
            indexed[(direction, unit)].add(int(idx_s))
        for (direction, unit), indices in sorted(indexed.items()):
            if not indices:
                continue
            if direction == "IN":
                # Inputs may be optional or left unwired in diagrams; block defs may use
                # IN1+ only or non-contiguous indices (no IN0 requirement).
                continue
            if 0 not in indices:
                issues.append(
                    f"ブロック {name!r}: {direction}{unit} ポートの番号が 0 ではなく {min(indices)} から始まっています。"
                )
            expected = set(range(max(indices) + 1))
            if indices != expected:
                missing = sorted(expected - indices)
                if missing:
                    issues.append(f"ブロック {name!r}: {direction}{unit} ポートが不足しています {missing!r}。")
        out_units = {unit for direction, unit in indexed if direction == "OUT"}
        for unit in sorted(out_units):
            if 0 not in indexed[("OUT", unit)]:
                issues.append(f"ブロック {name!r}: OUT0_{unit} がありません。")
    return issues


def validate(doc: Drawing) -> list[str]:
    """Return human-readable issues (empty = OK for MVP checks)."""
    issues: list[str] = []

    if APPID not in doc.appids:
        issues.append(f"APPID {APPID!r} がありません。")

    for name in ALL_LAYERS:
        if name not in doc.layers:
            issues.append(f"レイヤー {name!r} がありません。")

    issues.extend(_validate_block_port_definitions(doc))

    for layout in doc.layouts:
        if layout.is_modelspace:
            continue
        try:
            validate_paper_layout_name(layout.name)
        except ValueError as e:
            issues.append(str(e))

    # One LD_VPORT wire per paperspace layout (LWPOLYLINE with type VPORT in XDATA)
    for layout in doc.layouts:
        if layout.is_modelspace:
            continue
        br = layout.block_record_name
        blk = doc.blocks.get(br)
        vport_count = 0
        for e in blk:
            if e.dxftype() != "LWPOLYLINE":
                continue
            if e.dxf.layer != LAYER_VPORT:
                continue
            if get_type(e) == "VPORT":
                vport_count += 1
        if vport_count > 1:
            issues.append(
                f"レイアウト {layout.name!r}: LD_VPORT の矩形は 1 つまでですが、{vport_count} 個見つかりました。"
            )

    # INSERT / WIRE should have uid
    for layout in doc.layouts:
        if layout.is_modelspace:
            continue
        blk = doc.blocks.get(layout.block_record_name)
        for e in blk:
            if e.dxftype() == "INSERT":
                t = get_type(e)
                if t and not get_uid(e):
                    issues.append(f"INSERT（ハンドル {e.dxf.handle}）に uid の XDATA がありません。")
            if e.dxftype() == "LWPOLYLINE" and is_wire_layer(str(e.dxf.layer)):
                wt = get_type(e)
                if wt == "WIRE" and not get_uid(e):
                    issues.append(f"WIRE（ハンドル {e.dxf.handle}）に uid の XDATA がありません。")
                if wt == ENTITY_TYPE_WIRE_ARROW:
                    if not get_uid(e):
                        issues.append(
                            f"WIRE_ARROW（ハンドル {e.dxf.handle}）に uid の XDATA がありません。"
                        )
                    else:
                        wd = read_ld_app_dict(e)
                        if not str(wd.get("wire") or "").strip():
                            issues.append(
                                f"WIRE_ARROW（ハンドル {e.dxf.handle}）に親 WIRE の wire: が XDATA にありません。"
                            )

    return issues
