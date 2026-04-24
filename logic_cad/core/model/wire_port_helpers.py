"""WIRE port keys, dynamic AND/OR input count, and xdata flags (no DXF)."""

from __future__ import annotations

import re

from logic_cad.core.model.constants import WIRE_XDATA_ALLOW_ORTHOGONAL_CROSS
from logic_cad.core.model.index_store import IndexStore


def _and_or_input_count(index: IndexStore, uid: str) -> int | None:
    ins = index.inserts_by_uid.get(uid)
    if ins is None:
        return None
    bn = str(ins.dxf.name).upper()
    if not (bn.startswith("AND_") or bn.startswith("OR_")):
        return None
    try:
        return int(bn.split("_", 1)[1])
    except ValueError:
        return None


def _vertical_lane_from_in_port(dst_port: str, n_inputs: int) -> int:
    m = re.match(r"^IN(\d+)_LOGIC$", dst_port)
    if not m:
        return 0
    k = int(m.group(1))
    return k - (n_inputs - 1) // 2


def _port_index(port_key: str) -> int | None:
    m = re.match(r"^IN(\d+)_LOGIC$", port_key)
    if not m:
        return None
    return int(m.group(1))


def wire_skips_auto_reroute(xdata: dict) -> bool:
    """If set, AND/OR input bundle optimization skips this wire; symbol moves still reroute its geometry."""
    v = xdata.get("skip_auto_reroute")
    if v is None:
        return False
    return str(v).strip().lower() in ("1", "true", "yes")


def wire_allows_orthogonal_cross(xdata: dict) -> bool:
    """If set, routing uses symbol-only hard obstacles (may cross existing wire hulls orthogonally)."""
    v = xdata.get(WIRE_XDATA_ALLOW_ORTHOGONAL_CROSS)
    if v is None:
        return False
    return str(v).strip().lower() in ("1", "true", "yes")
