"""Baseline timing: move one AND gate in ``tests/test0.dxf`` and reroute attached wires.

Place ``logic_cad/tests/test0.dxf`` next to this file (not committed by default).
Run with ``pytest logic_cad/tests/test_routing_perf_test0.py -s`` to print milliseconds.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from logic_cad.core.debug.routing_perf import (
    routing_perf_format_lines,
    routing_perf_reset,
    routing_perf_snapshot,
)
from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.core.uid_display import format_uid_display

_TEST0_DXF = Path(__file__).resolve().parent / "test0.dxf"
_AND_DISPLAY_PREFIX = "5f9de047"
_MOVE_DX = 10.0
_MOVE_DY = -10.0


def _find_and_uid_on_any_layout(d: LogicDiagram, display_prefix: str) -> tuple[str, str]:
    """Return ``(layout_name, full_uid)`` for an INSERT whose block name starts with ``AND_``."""
    prefix_l = display_prefix.lower()
    for name in d.list_pages():
        d.set_current_page(name)
        for uid, ins in d.index.inserts_by_uid.items():
            if format_uid_display(uid).lower() != prefix_l:
                continue
            bname = str(ins.dxf.name)
            if bname.upper().startswith("AND_"):
                return name, uid
    pytest.fail(
        f"No AND_* INSERT with display uid {display_prefix!r} found in any layout of {_TEST0_DXF}"
    )


@pytest.mark.skipif(not _TEST0_DXF.is_file(), reason=f"missing fixture DXF: {_TEST0_DXF}")
def test_perf_move_and_gate_5f9de047_plus_10_minus_10mm_reroute(monkeypatch, capsys) -> None:
    """Time ``move_insert`` + ``reroute_wires_after_symbol_moves`` for the target AND symbol."""
    monkeypatch.setenv("LOGIC_CAD_PERF_ROUTING", "1")
    routing_perf_reset()

    d = LogicDiagram.open(_TEST0_DXF)
    layout, uid = _find_and_uid_on_any_layout(d, _AND_DISPLAY_PREFIX)
    d.set_current_page(layout)

    ins = d.symbols.insert_by_uid(layout, uid)
    assert ins is not None
    ox, oy, *_ = ins.dxf.insert
    nx, ny = float(ox) + _MOVE_DX, float(oy) + _MOVE_DY

    t0 = time.perf_counter()
    t_move_end = t0
    with d.begin("routing_perf"):
        t_move0 = time.perf_counter()
        d.symbols.move_insert(layout, uid, (nx, ny))
        t_move_end = time.perf_counter()
        ok = d.reroute_wires_after_symbol_moves(
            {uid},
            symbol_move_deltas={uid: (_MOVE_DX, _MOVE_DY)},
        )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    move_ms = (t_move_end - t_move0) * 1000.0
    perf_snapshot = routing_perf_snapshot()

    assert ok, "reroute_wires_after_symbol_moves failed"
    required = {
        "reroute.gate.optimize_bundle",
        "gate_input.bundle.order_pick",
        "gate_input.bundle.rm_route",
        "gate_input.bundle.rm_preflight_and_obstacles",
    }
    missing = sorted(required - set(perf_snapshot.keys()))
    assert not missing, f"missing routing_perf keys for wall case: {missing}"
    with capsys.disabled():
        print(
            f"\n[routing perf] {_TEST0_DXF.name} AND {format_uid_display(uid)} "
            f"move (+{_MOVE_DX:g},{_MOVE_DY:g}) mm + reroute (wall): {elapsed_ms:.2f} ms\n"
            f"  symbols.move_insert only: {move_ms:.2f} ms\n"
            f"  LOGIC_CAD_PERF_ROUTING breakdown:\n"
            + "\n".join(routing_perf_format_lines())
            + "\n"
        )
