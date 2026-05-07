"""Wire port direction: normalize click order, validate hub capacity, hub-chain flips.

normalize_wire_endpoints
------------------------
Converts any click-order combination to the canonical ``OUT* → IN*`` direction.
The decision is made **hub-first**: the presence of hubs is evaluated before port
names, because a hub's clicked port (``IN0_MULTI`` / ``OUT0_MULTI``) reflects only
which port was available at click time and must never be used as a directional signal.

Priority rules:

- **Both hubs**   : direction ambiguous — pass through as-is; BFS resolves later.
- **One hub**     : *only* the non-hub's port name is authoritative.
    - Non-hub = ``OUT*`` → non-hub drives hub  → ``(gate, OUT*, hub, IN0_MULTI)``
    - Non-hub = ``IN*``  → hub drives non-hub  → ``(hub, OUT0_MULTI, gate, IN*)``
    - Hub's clicked port is completely ignored.
- **No hub**      : port names determine direction.
    - ``OUT → IN``  : already canonical.
    - ``IN  → OUT`` : swap endpoints.
    - ``IN  → IN``  : ValueError.
    - ``OUT → OUT`` : ValueError.

assert_checkpoint_wire_capacity / assert_ld_port_direct_wiring_rules
----------------------------------------------------------------------
Capacity and 1-to-1 port rules for WB/CP and regular symbols.

find_hub_wire_flips
-------------------
Repairs hub-incident wires whose XDATA disagrees with signal flow direction:

1. **Explicit backwards** — ``src_port`` is ``IN*`` and ``dst_port`` is ``OUT*``.
   Always flip.

2. **Anchor BFS** — For hub–hub wires, infer flow direction from non-hub anchors:
   - Non-hub ``OUT*`` → hub ``IN*``: that hub is depth 0.
   - Hub ``OUT*`` → non-hub ``IN*``: that hub is depth 0.
   Walk hub–hub edges; the shallower hub must be ``src`` (``OUT0_MULTI``).
   Emit a ``WireFlip`` when the stored direction disagrees.

find_flip_to_free_branch_in_for_pending_connection
--------------------------------------------------
Before adding a new driver wire into a hub's ``IN0_MULTI``, check whether the
currently-blocking hub→hub chain can be reversed to free the slot.  Traverses
upstream hub-only segments; stops (returns ``None``) when a non-hub is encountered.
Returns a list of ``WireFlip`` objects — one per segment to reverse.

Public API
----------
normalize_wire_endpoints(src_uid, src_port, dst_uid, dst_port, *, is_wire_hub_fn)
normalize_wire_endpoints_with_deps(deps, src_uid, src_port, dst_uid, dst_port)
assert_checkpoint_wire_capacity(..., *, deps)
assert_ld_port_direct_wiring_rules(..., *, deps)
find_hub_wire_flips(layout_name, *, deps) -> list[WireFlip]
find_flip_to_free_branch_in_for_pending_connection(layout_name, dst_uid, dst_port, *, deps)
    -> list[WireFlip] | None

``deps`` is :class:`~logic_cad.core.graph.wire_graph_deps.WireGraphDeps` (see that module).
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from logic_cad.core.graph.wire_graph_deps import WireGraphDeps
from logic_cad.core.model.constants import (
    ENTITY_TYPE_CHECKPOINT,
    ENTITY_TYPE_WIRE_BRANCH,
)
from logic_cad.core.model.port_key import (
    is_inout_port_key,
    is_input_port_key,
    is_output_port_key,
)

_HUB_TYPES: frozenset[str] = frozenset({ENTITY_TYPE_WIRE_BRANCH, ENTITY_TYPE_CHECKPOINT})

# Canonical checkpoint hub port names.
_HUB_OUT = "OUT0_MULTI"
_HUB_IN = "IN0_MULTI"
_HUB_INOUT = "INOUT0_MULTI"


def normalize_wire_endpoints(
    src_uid: str,
    src_port: str,
    dst_uid: str,
    dst_port: str,
    *,
    is_wire_hub_fn: Callable[[str], bool],
) -> tuple[str, str, str, str]:
    """Return (src_uid, src_port, dst_uid, dst_port) in canonical OUT* → IN* order.

    Hub presence is evaluated before port names.  When exactly one endpoint is a
    hub, only the non-hub's port name is used to decide direction; the hub's
    clicked port is intentionally ignored (it reflects availability, not intent).
    """
    src_is_hub = is_wire_hub_fn(src_uid)
    dst_is_hub = is_wire_hub_fn(dst_uid)

    # ── Both hubs: direction is ambiguous — pass through for BFS ─────────────
    if src_is_hub and dst_is_hub:
        return src_uid, src_port, dst_uid, dst_port

    # ── Exactly one hub: non-hub IN/OUT wins, otherwise keep click order ───────
    if src_is_hub or dst_is_hub:
        if src_is_hub:
            hub_uid, hub_port = src_uid, src_port
            gate_uid, gate_port = dst_uid, dst_port
            gate_is_src = False
        else:
            hub_uid, hub_port = dst_uid, dst_port
            gate_uid, gate_port = src_uid, src_port
            gate_is_src = True

        if is_output_port_key(gate_port):
            return gate_uid, gate_port, hub_uid, hub_port
        if is_input_port_key(gate_port):
            return hub_uid, hub_port, gate_uid, gate_port
        if is_inout_port_key(gate_port):
            if gate_is_src:
                return gate_uid, gate_port, hub_uid, hub_port
            return hub_uid, hub_port, gate_uid, gate_port
        # Unrecognised port format — return as-is; downstream validators will catch it
        return src_uid, src_port, dst_uid, dst_port

    # ── No hubs: port names are authoritative ────────────────────────────────
    src_is_in = is_input_port_key(src_port)
    src_is_out = is_output_port_key(src_port)
    src_is_inout = is_inout_port_key(src_port)
    dst_is_in = is_input_port_key(dst_port)
    dst_is_out = is_output_port_key(dst_port)
    dst_is_inout = is_inout_port_key(dst_port)

    if src_is_in and dst_is_out:
        # Swap to canonical OUT → IN
        return dst_uid, dst_port, src_uid, src_port
    if src_is_out and dst_is_in:
        # Already canonical
        return src_uid, src_port, dst_uid, dst_port
    if src_is_in and dst_is_in:
        raise ValueError(
            "配線の向きが不正です: 両端がINポートです。"
            "OUTポート（または配線分岐・チェックポイント）を始点にしてください。"
        )
    if src_is_out and dst_is_out:
        raise ValueError(
            "配線の向きが不正です: 両端がOUTポートです。"
            "INポート（または配線分岐・チェックポイント）を終点にしてください。"
        )
    if src_is_out and dst_is_inout:
        return src_uid, src_port, dst_uid, dst_port
    if src_is_inout and dst_is_in:
        return src_uid, src_port, dst_uid, dst_port
    if src_is_in and dst_is_inout:
        return dst_uid, dst_port, src_uid, src_port
    if src_is_inout and dst_is_out:
        return dst_uid, dst_port, src_uid, src_port
    if src_is_inout and dst_is_inout:
        return src_uid, src_port, dst_uid, dst_port
    # Unrecognised combination (e.g. empty port names) — return as-is
    return src_uid, src_port, dst_uid, dst_port


def normalize_wire_endpoints_with_deps(
    deps: WireGraphDeps,
    src_uid: str,
    src_port: str,
    dst_uid: str,
    dst_port: str,
) -> tuple[str, str, str, str]:
    """Same as :func:`normalize_wire_endpoints` using ``deps.is_wire_hub`` for hub detection."""
    return normalize_wire_endpoints(
        src_uid, src_port, dst_uid, dst_port, is_wire_hub_fn=deps.is_wire_hub
    )


def _iter_wire_meta_dicts(
    layout_name: str,
    iter_wire_meta: Callable[[str], Iterator[tuple[object, str, dict]]],
) -> Iterator[dict]:
    for _e, _wu, d in iter_wire_meta(layout_name):
        yield d


def assert_checkpoint_wire_capacity(
    layout_name: str,
    src_uid: str,
    src_port: str,
    dst_uid: str,
    dst_port: str,
    *,
    deps: WireGraphDeps,
) -> None:
    """CHECKPOINT keeps IN/OUT caps; WIRE_BRANCH uses one INOUT port with no cap."""
    iter_wire_meta = deps.iter_wire_meta
    symbol_entity_type_fn = deps.symbol_entity_type_fn
    t_dst = symbol_entity_type_fn(dst_uid)
    if t_dst == ENTITY_TYPE_WIRE_BRANCH:
        if dst_port != _HUB_INOUT:
            raise ValueError("配線分岐へ接続するには INOUT0_MULTI を使ってください")
    if t_dst == ENTITY_TYPE_CHECKPOINT:
        if dst_port != "IN0_MULTI":
            raise ValueError("チェックポイントへ接続するには入力 IN0_MULTI を使ってください")
        n_in = sum(
            1
            for d in _iter_wire_meta_dicts(layout_name, iter_wire_meta)
            if d.get("dst") == dst_uid and str(d.get("dst_port") or "") == "IN0_MULTI"
        )
        if n_in >= 1:
            raise ValueError("チェックポイントの入力は1本までです")
    t_src = symbol_entity_type_fn(src_uid)
    if t_src == ENTITY_TYPE_WIRE_BRANCH:
        if src_port != _HUB_INOUT:
            raise ValueError("配線分岐から配線を出すには INOUT0_MULTI を使ってください")
        return
    if t_src == ENTITY_TYPE_CHECKPOINT:
        if src_port != "OUT0_MULTI":
            raise ValueError("チェックポイントから配線を出すには出力 OUT0_MULTI を使ってください")
        n_out = sum(
            1
            for d in _iter_wire_meta_dicts(layout_name, iter_wire_meta)
            if d.get("src") == src_uid and str(d.get("src_port") or "") == "OUT0_MULTI"
        )
        if n_out >= 1:
            raise ValueError("チェックポイントの出力は1本までです")


def _wire_uses_dst_port(
    layout_name: str,
    dst_uid: str,
    dst_port: str,
    *,
    deps: WireGraphDeps,
) -> bool:
    for d in _iter_wire_meta_dicts(layout_name, deps.iter_wire_meta):
        if d.get("dst") == dst_uid and str(d.get("dst_port") or "") == dst_port:
            return True
    return False


def _direct_wire_uses_src_port(
    layout_name: str,
    src_uid: str,
    src_port: str,
    *,
    deps: WireGraphDeps,
) -> bool:
    for d in _iter_wire_meta_dicts(layout_name, deps.iter_wire_meta):
        if d.get("src") == src_uid and str(d.get("src_port") or "") == src_port:
            return True
    return False


def _wire_uses_port_any_role(
    layout_name: str,
    symbol_uid: str,
    port_key: str,
    *,
    deps: WireGraphDeps,
) -> bool:
    """Return True when *port_key* is already used as src or dst on *symbol_uid*."""

    for d in _iter_wire_meta_dicts(layout_name, deps.iter_wire_meta):
        if d.get("src") == symbol_uid and str(d.get("src_port") or "") == port_key:
            return True
        if d.get("dst") == symbol_uid and str(d.get("dst_port") or "") == port_key:
            return True
    return False


def assert_ld_port_direct_wiring_rules(
    layout_name: str,
    src_uid: str,
    src_port: str,
    dst_uid: str,
    dst_port: str,
    *,
    deps: WireGraphDeps,
) -> None:
    """At most one wire per dst port; one direct wire per src port except WIRE_BRANCH OUT0_MULTI (fan-out)."""
    dst_is_branch_inout = (
        deps.symbol_entity_type_fn(dst_uid) == ENTITY_TYPE_WIRE_BRANCH
        and str(dst_port or "").upper() == _HUB_INOUT
    )
    if dst_is_branch_inout:
        pass
    elif is_inout_port_key(dst_port):
        if _wire_uses_port_any_role(layout_name, dst_uid, dst_port, deps=deps):
            raise ValueError("このポートにはすでに配線が1本接続されています")
    elif _wire_uses_dst_port(layout_name, dst_uid, dst_port, deps=deps):
        raise ValueError("このポートにはすでに配線が1本接続されています")

    src_is_branch_inout = (
        deps.symbol_entity_type_fn(src_uid) == ENTITY_TYPE_WIRE_BRANCH
        and str(src_port or "").upper() == _HUB_INOUT
    )
    if (
        not src_is_branch_inout
        and (
            _wire_uses_port_any_role(layout_name, src_uid, src_port, deps=deps)
            if is_inout_port_key(src_port)
            else _direct_wire_uses_src_port(layout_name, src_uid, src_port, deps=deps)
        )
    ):
        raise ValueError("このポートからの直接配線はすでに1本あります（分岐ポイントから分岐してください）")


def is_hub_type(entity_type: str | None) -> bool:
    """Return True when *entity_type* is WIRE_BRANCH or CHECKPOINT."""
    return entity_type in _HUB_TYPES


@dataclass
class WireFlip:
    """Describes one wire that needs its XDATA src/dst swapped."""

    wire_uid: str
    new_src: str
    new_src_port: str
    new_dst: str
    new_dst_port: str


def _collect_wires(
    layout_name: str,
    iter_wire_meta: Callable[[str], Iterator[tuple[object, str, dict]]],
) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for _e, wu, meta in iter_wire_meta(layout_name):
        if wu:
            out.append((wu, meta))
    return out


def _explicit_in_out_flips(
    wires: list[tuple[str, dict]],
    symbol_entity_type_fn: Callable[[str], str | None],
) -> dict[str, WireFlip]:
    """IN*→OUT* wires incident to a hub."""
    by_uid: dict[str, WireFlip] = {}
    for wu, meta in wires:
        src = str(meta.get("src") or "")
        dst = str(meta.get("dst") or "")
        sp_raw = str(meta.get("src_port") or "")
        dp_raw = str(meta.get("dst_port") or "")
        sp = sp_raw.upper()
        dp = dp_raw.upper()
        if not (src and dst and sp and dp):
            continue
        st = symbol_entity_type_fn(src)
        dt = symbol_entity_type_fn(dst)
        if not (is_hub_type(st) or is_hub_type(dt)):
            continue
        if is_input_port_key(sp_raw) and is_output_port_key(dp_raw):
            by_uid[wu] = WireFlip(
                wire_uid=wu,
                new_src=dst,
                new_src_port=dp_raw,
                new_dst=src,
                new_dst_port=sp_raw,
            )
    return by_uid


def _undirected_hub_neighbors(
    wires: list[tuple[str, dict]],
    symbol_entity_type_fn: Callable[[str], str | None],
) -> dict[str, set[str]]:
    """Hub-only adjacency: two hubs share an undirected edge if a wire connects them."""
    nbr: dict[str, set[str]] = defaultdict(set)
    for _wu, meta in wires:
        src = str(meta.get("src") or "")
        dst = str(meta.get("dst") or "")
        if not (src and dst):
            continue
        if is_hub_type(symbol_entity_type_fn(src)) and is_hub_type(symbol_entity_type_fn(dst)):
            nbr[src].add(dst)
            nbr[dst].add(src)
    return nbr


def _anchor_bfs_depths(
    wires: list[tuple[str, dict]],
    symbol_entity_type_fn: Callable[[str], str | None],
) -> dict[str, int]:
    """BFS hop count from anchor hubs over the *undirected* hub–hub graph."""
    hub_nbr = _undirected_hub_neighbors(wires, symbol_entity_type_fn)

    hub_depth: dict[str, int] = {}
    queue: deque[str] = deque()

    for _wu, meta in wires:
        src = str(meta.get("src") or "")
        dst = str(meta.get("dst") or "")
        sp_raw = str(meta.get("src_port") or "")
        dp_raw = str(meta.get("dst_port") or "")
        st = symbol_entity_type_fn(src)
        dt = symbol_entity_type_fn(dst)
        # Non-hub OUT → hub IN
        if (
            not is_hub_type(st)
            and is_hub_type(dt)
            and is_output_port_key(sp_raw)
            and is_input_port_key(dp_raw)
        ):
            if dst not in hub_depth:
                hub_depth[dst] = 0
                queue.append(dst)
        # Hub OUT → non-hub IN
        if (
            is_hub_type(st)
            and not is_hub_type(dt)
            and is_output_port_key(sp_raw)
            and is_input_port_key(dp_raw)
        ):
            if src not in hub_depth:
                hub_depth[src] = 0
                queue.append(src)

    while queue:
        cur = queue.popleft()
        d = hub_depth[cur]
        for other in hub_nbr.get(cur, ()):
            if other not in hub_depth:
                hub_depth[other] = d + 1
                queue.append(other)

    return hub_depth


def _bfs_oriented_hub_hub_flips(
    wires: list[tuple[str, dict]],
    hub_depth: dict[str, int],
    symbol_entity_type_fn: Callable[[str], str | None],
    skip_wire_uids: set[str],
) -> dict[str, WireFlip]:
    """Hub–hub wires whose XDATA upstream/downstream disagrees with BFS depths."""
    by_uid: dict[str, WireFlip] = {}
    for wu, meta in wires:
        if wu in skip_wire_uids:
            continue
        src = str(meta.get("src") or "")
        dst = str(meta.get("dst") or "")
        if not (src and dst):
            continue
        if not (is_hub_type(symbol_entity_type_fn(src)) and is_hub_type(symbol_entity_type_fn(dst))):
            continue
        if src not in hub_depth or dst not in hub_depth:
            continue
        ds, dd = hub_depth[src], hub_depth[dst]
        if ds == dd:
            continue
        if ds < dd:
            upstream, downstream = src, dst
        else:
            upstream, downstream = dst, src
        # Canonical: upstream OUT0_MULTI → downstream IN0_MULTI
        if meta.get("src") == upstream and meta.get("dst") == downstream:
            continue
        if meta.get("src") == downstream and meta.get("dst") == upstream:
            by_uid[wu] = WireFlip(
                wire_uid=wu,
                new_src=upstream,
                new_src_port=_HUB_OUT,
                new_dst=downstream,
                new_dst_port=_HUB_IN,
            )
    return by_uid


def find_hub_wire_flips(
    layout_name: str,
    *,
    deps: WireGraphDeps,
) -> list[WireFlip]:
    """Return wires that need flipping for hub-chain consistency."""
    iter_wire_meta = deps.iter_wire_meta
    symbol_entity_type_fn = deps.symbol_entity_type_fn
    wires = _collect_wires(layout_name, iter_wire_meta)
    explicit = _explicit_in_out_flips(wires, symbol_entity_type_fn)
    hub_depth = _anchor_bfs_depths(wires, symbol_entity_type_fn)
    bfs_flips = _bfs_oriented_hub_hub_flips(
        wires,
        hub_depth,
        symbol_entity_type_fn,
        skip_wire_uids=set(explicit.keys()),
    )
    merged: dict[str, WireFlip] = {**bfs_flips, **explicit}
    return list(merged.values())


def find_flip_to_free_branch_in_for_pending_connection(
    layout_name: str,
    dst_uid: str,
    dst_port: str,
    *,
    deps: WireGraphDeps,
) -> list[WireFlip] | None:
    """Hub-chain reversal is no longer used (kept for API compatibility)."""
    _ = layout_name, dst_uid, dst_port, deps
    return None
