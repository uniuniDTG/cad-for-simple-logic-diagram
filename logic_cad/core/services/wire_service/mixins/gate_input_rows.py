"""Row queries and predicates for wires landing on gate logic inputs."""

from __future__ import annotations

from typing import Any

from logic_cad.core.model.wire_port_helpers import _port_index, wire_skips_auto_reroute
from logic_cad.core.model.xdata import read_ld_app_dict
from logic_cad.core.services.wire_service.mixins.gate_input_host import (
    GateInputWireServiceHost,
)


def collect_gate_input_rows_all(
    host: GateInputWireServiceHost,
    layout_name: str,
    gate_uid: str,
) -> list[tuple[Any, str, str, str, str, int]]:
    """Collect every WIRE terminating on *gate_uid* logic inputs.

    Args:
        host: Wire service host providing ``iter_wire_meta``.
        layout_name: Active paper layout name.
        gate_uid: Destination gate UID.

    Returns:
        Rows ``(entity, wire_uid, src_uid, src_port, dst_port, in_index)``.
    """
    rows: list[tuple[Any, str, str, str, str, int]] = []
    for e, wu, d in host.iter_wire_meta(layout_name):
        if d.get("dst") != gate_uid:
            continue
        dp = d.get("dst_port") or ""
        idx = _port_index(dp)
        if idx is None:
            continue
        su, sp = d.get("src"), d.get("src_port")
        if not su or not sp:
            continue
        rows.append((e, wu, su, sp, dp, idx))
    return rows


def gate_input_wire_paths(
    host: GateInputWireServiceHost,
    layout_name: str,
    gate_uid: str,
    exclude_wire_uids: set[str] | None = None,
) -> list[list[tuple[float, float]]]:
    """Return polylines for wires routed into *gate_uid* logic inputs.

    Args:
        host: Wire service host.
        layout_name: Active paper layout name.
        gate_uid: Destination gate UID.
        exclude_wire_uids: Optional wire UIDs to omit.

    Returns:
        List of vertex lists, layout order.
    """
    excluded = exclude_wire_uids or set()
    paths: list[list[tuple[float, float]]] = []
    for entity, wu, data in host.iter_wire_meta(layout_name):
        if wu in excluded:
            continue
        if data.get("dst") != gate_uid:
            continue
        if _port_index(data.get("dst_port") or "") is None:
            continue
        paths.append(host._polyline_points(entity))
    return paths


def gate_input_wire_rows_in_order(
    host: GateInputWireServiceHost,
    layout_name: str,
    gate_uid: str,
    n: int,
) -> list[tuple[Any, str, str, str, str, int]] | None:
    """Return bundle rows sorted by IN index when all ``IN0…IN(n-1)`` are used once.

    Args:
        host: Wire service host.
        layout_name: Active paper layout name.
        gate_uid: Destination gate UID.
        n: Expected dynamic input count.

    Returns:
        Sorted rows or ``None`` when the wiring does not match a full permutation.
    """
    rows = collect_gate_input_rows_all(host, layout_name, gate_uid)
    if len(rows) != n:
        return None
    if {r[5] for r in rows} != set(range(n)):
        return None
    return sorted(rows, key=lambda r: r[5])


def ordered_gate_inputs_allow_crossing_swaps(
    ordered: list[tuple[Any, str, str, str, str, int]] | None,
) -> bool:
    """Return whether crossing-swap optimization may rewrite dst ports.

    Args:
        ordered: Full-permutation gate input rows, if any.

    Returns:
        ``False`` when manual/skip-auto wires are present on the ordered inputs.
    """
    if ordered is None:
        return False
    for r in ordered:
        ent = r[0]
        d = read_ld_app_dict(ent)
        if wire_skips_auto_reroute(d):
            return False
    return True
