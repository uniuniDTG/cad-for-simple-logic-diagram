"""WIRE port keys, dynamic AND/OR input count, and xdata flags (no DXF)."""

from __future__ import annotations

from logic_cad.core.model.constants import WIRE_XDATA_ALLOW_ORTHOGONAL_CROSS
from logic_cad.core.model.index_store import IndexStore
from logic_cad.core.model.port_key import parse_port_key


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
    pk = parse_port_key(dst_port)
    if pk is None or pk.direction != "IN" or pk.unit != "LOGIC":
        return 0
    return pk.index - (n_inputs - 1) // 2


def _port_index(port_key: str) -> int | None:
    pk = parse_port_key(port_key)
    if pk is None or pk.direction != "IN" or pk.unit != "LOGIC":
        return None
    return pk.index


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
