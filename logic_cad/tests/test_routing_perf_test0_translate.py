"""Translate perf timing on ``tests/test0.dxf`` for selected display UIDs."""

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
_MOVE_DX = 0.0
_MOVE_DY = -10.0
_PARALLEL_UIDS = ["599139dd", "f987b1fc", "0d250df9", "73d39742", "5f9de047"]


def _find_layout_and_uid(d: LogicDiagram, display_prefix: str) -> tuple[str, str]:
    """Return ``(layout_name, full_uid)`` for a display UID found in any layout."""
    prefix_l = display_prefix.lower()
    for name in d.list_pages():
        d.set_current_page(name)
        for uid in d.index.inserts_by_uid:
            if format_uid_display(uid).lower() == prefix_l:
                return name, uid
    pytest.fail(f"display uid {display_prefix!r} not found in any layout of {_TEST0_DXF}")


def _run_translate_case(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    display_uids: list[str],
    case_name: str,
) -> None:
    """Move selected symbols and print reroute perf timing."""
    monkeypatch.setenv("LOGIC_CAD_PERF_ROUTING", "1")
    routing_perf_reset()
    d = LogicDiagram.open(_TEST0_DXF)
    resolved = [_find_layout_and_uid(d, duid) for duid in display_uids]
    layouts = {layout for layout, _ in resolved}
    if len(layouts) != 1:
        pytest.fail(
            f"all display uids must be on one layout, got {sorted(layouts)} for {display_uids!r}"
        )
    layout = resolved[0][0]
    d.set_current_page(layout)

    deltas: dict[str, tuple[float, float]] = {}
    moved_uids: set[str] = set()
    t0 = time.perf_counter()
    with d.begin(f"routing_perf:{case_name}"):
        for _layout, uid in resolved:
            ins = d.symbols.insert_by_uid(layout, uid)
            assert ins is not None
            ox, oy, *_ = ins.dxf.insert
            nx = float(ox) + _MOVE_DX
            ny = float(oy) + _MOVE_DY
            d.symbols.move_insert(layout, uid, (nx, ny))
            moved_uids.add(uid)
            deltas[uid] = (_MOVE_DX, _MOVE_DY)
        ok = d.reroute_wires_after_symbol_moves(moved_uids, symbol_move_deltas=deltas)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    perf_snapshot = routing_perf_snapshot()
    assert ok, f"reroute_wires_after_symbol_moves failed: {case_name}"
    _assert_perf_keys(case_name, perf_snapshot)
    with capsys.disabled():
        print(
            f"\n[routing perf translate] {_TEST0_DXF.name} {case_name}: "
            f"move ({_MOVE_DX:+g},{_MOVE_DY:+g}) mm + reroute: {elapsed_ms:.2f} ms\n"
            f"  moved display uids: {display_uids}\n"
            f"  LOGIC_CAD_PERF_ROUTING breakdown:\n"
            + "\n".join(routing_perf_format_lines())
            + "\n"
        )


def _assert_perf_keys(case_name: str, perf_snapshot: dict[str, float]) -> None:
    """Validate routing perf labels needed for before/after comparisons.

    Args:
        case_name: Human-readable perf case name.
        perf_snapshot: Snapshot from ``routing_perf_snapshot``.

    Raises:
        AssertionError: When required labels are missing.
    """
    required_common = {
        "reroute.gate.optimize_bundle",
        "gate_input.bundle.rm_route",
        "gate_input.bundle.rm_preflight_and_obstacles",
    }
    missing_common = sorted(required_common - set(perf_snapshot.keys()))
    assert not missing_common, (
        f"missing common routing_perf keys for {case_name}: {missing_common}"
    )
    if case_name == "parallel_5symbols":
        candidate_keys = [
            k
            for k in perf_snapshot.keys()
            if k.startswith("gate_input.bundle.order_pick.candidate.")
        ]
        assert candidate_keys, "expected candidate-level order_pick metrics in parallel case"


@pytest.mark.skipif(not _TEST0_DXF.is_file(), reason=f"missing fixture DXF: {_TEST0_DXF}")
def test_perf_translate_single_599139dd_minus_10y(monkeypatch, capsys) -> None:
    """Measure reroute after moving only ``599139dd`` by ``y-=10mm``."""
    _run_translate_case(
        monkeypatch=monkeypatch,
        capsys=capsys,
        display_uids=["599139dd"],
        case_name="single_599139dd",
    )


@pytest.mark.skipif(not _TEST0_DXF.is_file(), reason=f"missing fixture DXF: {_TEST0_DXF}")
def test_perf_translate_parallel_five_symbols_minus_10y(monkeypatch, capsys) -> None:
    """Measure reroute after moving the specified five symbols by ``y-=10mm``."""
    _run_translate_case(
        monkeypatch=monkeypatch,
        capsys=capsys,
        display_uids=list(_PARALLEL_UIDS),
        case_name="parallel_5symbols",
    )
