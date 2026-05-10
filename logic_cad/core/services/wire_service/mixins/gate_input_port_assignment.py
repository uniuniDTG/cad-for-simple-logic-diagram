"""Port assignment heuristics for AND/OR gate input bundles."""

from __future__ import annotations

from typing import Any

from logic_cad.core.debug.debug_log import logic_cad_log
from logic_cad.core.uid_display import format_uid_display
from logic_cad.core.model.index_store import IndexStore
from logic_cad.core.model.wire_port_helpers import _port_index
from logic_cad.core.model.xdata import build_ld_app_tags, read_ld_app_dict, set_entity_xdata


def assign_gate_input_ports_by_source_order(
    index: IndexStore,
    layout_name: str,
    gate_uid: str,
    rows: list[tuple[Any, str, str, str, str, int]],
    n_inputs: int,
    reserved_indices: set[int],
) -> list[tuple[Any, str, str, str, str, int]] | None:
    """Map auto wires to IN* ports using free slots only.

    Sources with OUT west of the gate input cluster (min IN world X) keep monotonic
    Y matching: lowest source Y to lowest free IN port Y, etc. Sources east of that
    reference use only extreme free ports (bottom/top in world Y), with interior wires
    consuming remaining free slots if more than two wrap-around connections exist.

    Args:
        index: Spatial index rebuilt for the active layout.
        layout_name: Active paper layout name (reserved for future logging context).
        gate_uid: Destination AND/OR gate UID.
        rows: Bundle rows ``(entity, wire_uid, src_uid, src_port, dst_port, old_idx)``.
        n_inputs: Dynamic gate input count ``n``.
        reserved_indices: IN indices held by manual (non-auto) wires.

    Returns:
        Updated rows with ``dst_port`` rewritten and sorted slot indices, or ``None``
        when no valid assignment exists.
    """
    _ = layout_name

    def _in_port_y(slot: int) -> float:
        ipw = index.get_port_world(gate_uid, f"IN{slot}_LOGIC")
        return float(ipw[1]) if ipw is not None else float(slot)

    free_slots = [i for i in range(n_inputs) if i not in reserved_indices]
    in_x_coords: list[float] = []
    for k in range(n_inputs):
        ipw = index.get_port_world(gate_uid, f"IN{k}_LOGIC")
        if ipw is not None:
            in_x_coords.append(ipw[0])
    if not in_x_coords:
        return None
    ref_x = min(in_x_coords)

    ranked: list[tuple[float, float, tuple[Any, str, str, str, str, int]]] = []
    for r in rows:
        pw = index.get_port_world(r[2], r[3])
        if pw is None:
            continue
        ranked.append((pw[1], pw[0], r))
    if len(ranked) > len(free_slots):
        logic_cad_log(
            "routing",
            (
                f"gate assign skip gate UUID={format_uid_display(gate_uid)}: need {len(ranked)} IN slots for auto wires "
                f"but only {len(free_slots)} free (n={n_inputs} reserved={sorted(reserved_indices)})"
            ),
        )
        return None

    free_by_y = sorted(free_slots, key=_in_port_y)
    left_side: list[tuple[float, float, tuple[Any, str, str, str, str, int]]] = []
    right_side: list[tuple[float, float, tuple[Any, str, str, str, str, int]]] = []
    for t in ranked:
        src_x = t[1]
        if src_x <= ref_x + 1e-9:
            left_side.append(t)
        else:
            right_side.append(t)
    left_side.sort(key=lambda t: (t[0], t[1]))
    right_side.sort(key=lambda t: (t[0], t[1]))

    slot_for_wire: dict[str, int] = {}
    used_slots: set[int] = set()

    bottom_slot = free_by_y[0]
    top_slot = free_by_y[-1]

    if right_side:
        if len(free_by_y) == 1:
            only = free_by_y[0]
            if len(right_side) > 1:
                logic_cad_log(
                    "routing",
                    (
                        f"gate assign skip gate UUID={format_uid_display(gate_uid)}: {len(right_side)} wrap wires "
                        f"but only one free IN slot"
                    ),
                )
                return None
            slot_for_wire[right_side[0][2][1]] = only
            used_slots.add(only)
        elif len(right_side) == 1:
            ry, _, rr = right_side[0]
            yb, yt = _in_port_y(bottom_slot), _in_port_y(top_slot)
            pick = (
                bottom_slot
                if abs(ry - yb) <= abs(ry - yt) + 1e-9
                else top_slot
            )
            slot_for_wire[rr[1]] = pick
            used_slots.add(pick)
        else:
            lo_t = right_side[0]
            hi_t = right_side[-1]
            slot_for_wire[lo_t[2][1]] = bottom_slot
            used_slots.add(bottom_slot)
            if hi_t[2][1] != lo_t[2][1]:
                slot_for_wire[hi_t[2][1]] = top_slot
                if top_slot != bottom_slot:
                    used_slots.add(top_slot)
            mid = right_side[1:-1]
            pool = sorted(
                [s for s in free_by_y if s not in used_slots],
                key=_in_port_y,
            )
            mid_sorted = sorted(mid, key=lambda t: (t[0], t[1]))
            if len(mid_sorted) > len(pool):
                logic_cad_log(
                    "routing",
                    (
                        f"gate assign skip gate UUID={format_uid_display(gate_uid)}: wrap bundle needs "
                        f"{len(mid_sorted)} extra IN slots but only {len(pool)} remain"
                    ),
                )
                return None
            for slot_t, sl in zip(mid_sorted, pool):
                slot_for_wire[slot_t[2][1]] = sl
                used_slots.add(sl)

    pool_left = sorted(
        [s for s in free_by_y if s not in used_slots],
        key=_in_port_y,
    )
    if len(left_side) > len(pool_left):
        logic_cad_log(
            "routing",
            (
                f"gate assign skip gate UUID={format_uid_display(gate_uid)}: left_slots={len(pool_left)} "
                f"left_wires={len(left_side)} (not enough after wrap assignment)"
            ),
        )
        return None
    chosen_left = pool_left[: len(left_side)]
    for t, sl in zip(left_side, chosen_left):
        slot_for_wire[t[2][1]] = sl

    out: list[tuple[Any, str, str, str, str, int]] = []
    for _y, _x, r in sorted(ranked, key=lambda t: (t[0], t[1])):
        slot = slot_for_wire[r[1]]
        new_port = f"IN{slot}_LOGIC"
        e, wu = r[0], r[1]
        if r[4] != new_port:
            d = dict(read_ld_app_dict(e))
            d["dst_port"] = new_port
            set_entity_xdata(e, build_ld_app_tags("1", wu, "WIRE", d))
        out.append((e, wu, r[2], r[3], new_port, slot))
    return out
