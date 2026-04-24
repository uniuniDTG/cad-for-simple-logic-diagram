"""Cumulative timings for symbol-move reroute (investigation).

Enable with ``LOGIC_CAD_PERF_ROUTING=1``. Used by ``reroute_wires_after_symbol_moves`` /
``reroute_wires_touching`` and optional tests. Single-threaded; not for parallel pytest workers
on the same process state without ``routing_perf_reset()`` between cases.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from time import perf_counter

_ACC: dict[str, float] = {}


def routing_perf_enabled() -> bool:
    v = os.environ.get("LOGIC_CAD_PERF_ROUTING", "")
    return v.strip().lower() in ("1", "true", "yes", "on")


def routing_perf_reset() -> None:
    _ACC.clear()


def routing_perf_add(label: str, seconds: float) -> None:
    if not routing_perf_enabled() or seconds <= 0.0:
        return
    _ACC[label] = _ACC.get(label, 0.0) + seconds


def routing_perf_snapshot() -> dict[str, float]:
    return dict(_ACC)


def routing_perf_format_lines(snapshot: dict[str, float] | None = None) -> list[str]:
    """Sorted lines ``label … ms`` for printing."""
    snap = snapshot if snapshot is not None else routing_perf_snapshot()
    if not snap:
        return ["(no routing_perf samples)"]
    total = sum(snap.values())
    lines = []
    for k in sorted(snap.keys()):
        ms = snap[k] * 1000.0
        pct = (snap[k] / total * 100.0) if total > 0 else 0.0
        lines.append(f"  {k}: {ms:8.2f} ms ({pct:5.1f}%)")
    lines.append(f"  --- total: {total * 1000.0:.2f} ms")
    return lines


@contextmanager
def routing_perf_span(label: str) -> Iterator[None]:
    if not routing_perf_enabled():
        yield
        return
    t0 = perf_counter()
    try:
        yield
    finally:
        routing_perf_add(label, perf_counter() - t0)
