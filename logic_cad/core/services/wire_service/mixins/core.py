from __future__ import annotations

from ezdxf.document import Drawing

from logic_cad.core.graph.wire_graph_deps import WireGraphDeps
from logic_cad.core.model.constants import (
    ENTITY_TYPE_CHECKPOINT,
    ENTITY_TYPE_WIRE_BRANCH,
    GRID_PITCH,
    LINETYPE_LOGIC,
    LINETYPE_VALUE,
    ROUTE_ESCAPE_MM,
    MIN_AND_OR_INPUTS,
)
from logic_cad.core.model.wire_layers import is_wire_layer
from logic_cad.core.model.connection_graph import ports_compatible, resolve_wire_unit
from logic_cad.core.model.index_store import IndexStore
from logic_cad.core.model.wire_port_helpers import _and_or_input_count, _port_index
from logic_cad.core.model.xdata import build_ld_app_tags, get_type, get_uid, new_uid, read_ld_app_dict, set_entity_xdata
from logic_cad.core.obstacles import (
    build_routing_obstacles,
    build_symbol_only_routing_obstacles,
    estimate_port_facing,
    reserved_path_obstacles,
    symbol_obstacles,
    wire_obstacles,
)
from logic_cad.core.routing import (
    DEFAULT_ROUTING_PROFILE,
    RoutingProfile,
    dedupe_colinear,
    path_hits_obstacles,
    route_manhattan_with_escape,
    snap_to_grid,
)
from logic_cad.core.routing.wire_polyline_geometry import (
    MANHATTAN_EPS as _MANHATTAN_EPS,
    offset_polyline_segment_parallel_xyb,
)

class WireServiceCoreMixin:
    def __init__(self, doc: Drawing) -> None:
        self.doc = doc

    def _layout_block(self, layout_name: str):
        layout = self.doc.layouts.get(layout_name)
        return self.doc.blocks.get(layout.block_record_name)

    def route_manhattan(
        self,
        src_pt: tuple[float, float],
        dst_pt: tuple[float, float],
        obstacles: list[tuple[float, float, float, float]] | None = None,
    ) -> list[tuple[float, float]]:
        return route_manhattan_with_escape(
            src_pt, dst_pt, obstacles, existing_wire_segments=None
        )

    def _port_facing(
        self,
        index: IndexStore,
        uid: str,
        port_key: str,
    ) -> tuple[int, int] | None:
        return estimate_port_facing(index, self.doc, uid, port_key)

    def _symbol_uids_exclude_from_routing_obstacles(self, *endpoint_uids: str | None) -> set[str]:
        """Omit CHECKPOINT inserts from symbol hard obstacles for this route.

        IN0/OUT0 share one world point; a single axis-aligned port cutout often leaves the opposite
        side closed so paths from e.g. east cannot reach IN (cutout opened on west by tie-break).
        """
        from logic_cad.core.undo.history import find_entity_by_uid

        out: set[str] = set()
        for u in endpoint_uids:
            if not u:
                continue
            e = find_entity_by_uid(self.doc, u)
            if e is not None and get_type(e) in (ENTITY_TYPE_CHECKPOINT, ENTITY_TYPE_WIRE_BRANCH):
                out.add(u)
        return out

    def _existing_wire_path_segments(
        self,
        layout_name: str,
        exclude_wire_uids: set[str] | None = None,
    ) -> list[tuple[tuple[float, float], tuple[float, float]]]:
        """Flatten other WIRE polylines to segments for collinear-overlap checks (one build per route call)."""
        from logic_cad.core.routing.overlap import wire_paths_to_flat_segments

        ex = exclude_wire_uids or set()
        paths: list[list[tuple[float, float]]] = []
        for entity, wu, d in self.iter_wire_meta(layout_name):
            if not wu or wu in ex:
                continue
            paths.append(self._polyline_points(entity))
        return wire_paths_to_flat_segments(paths)

    def _banned_src_cardinals_for_route(
        self,
        layout_name: str,
        src_uid: str,
        src_port: str,
        exclude_wire_uids: set[str] | None = None,
    ):
        """Cardinal directions already used at a hub (WIRE_BRANCH/CHECKPOINT OUT0_MULTI)."""
        from logic_cad.core.model.constants import ENTITY_TYPE_CHECKPOINT
        from logic_cad.core.routing.occupancy import banned_out_cardinals_for_hub

        if src_port != "OUT0_MULTI":
            return None
        t = self._symbol_entity_type(src_uid)
        if t not in (ENTITY_TYPE_CHECKPOINT, ENTITY_TYPE_WIRE_BRANCH):
            return None
        banned = banned_out_cardinals_for_hub(
            layout_name,
            src_uid,
            iter_wire_meta=self.iter_wire_meta,
            polyline_points_fn=self._polyline_points,
            exclude_wire_uids=exclude_wire_uids,
        )
        return banned if banned else None

    def iter_wire_meta(self, layout_name: str):
        """Yield (entity, wire_uid, xdata dict)."""
        blk = self._layout_block(layout_name)

        for e in blk:
            if e.dxftype() != "LWPOLYLINE" or not is_wire_layer(str(e.dxf.layer)):
                continue
            if get_type(e) != "WIRE":
                continue
            wu = get_uid(e)
            if not wu:
                continue
            yield e, wu, read_ld_app_dict(e)

    def _symbol_entity_type(self, uid: str) -> str | None:
        from logic_cad.core.undo.history import find_entity_by_uid
        from logic_cad.core.model.xdata import get_type

        e = find_entity_by_uid(self.doc, uid)
        if e is None:
            return None
        return get_type(e)

    def wire_graph_deps(self) -> WireGraphDeps:
        # Single bundle for port_src_dst_solver so LogicDiagram and connection code do not
        # duplicate iter_wire_meta / _symbol_entity_type pairs at every call site.
        # TODO: If profiling shows hot paths, allow reusing one instance per transaction
        #       (today: cheap frozen bundle; document state must stay in sync with callers).
        return WireGraphDeps(
            iter_wire_meta=self.iter_wire_meta,
            symbol_entity_type_fn=self._symbol_entity_type,
        )

    def current_and_or_input_count(self, index: IndexStore, gate_uid: str) -> int | None:
        """AND_n/OR_n *n* if *gate_uid* is a dynamic gate INSERT; else None."""
        return _and_or_input_count(index, gate_uid)

    def required_and_or_input_count(
        self, index: IndexStore, layout_name: str, gate_uid: str
    ) -> int | None:
        """Smallest *n* so all wires with dst=this gate use only IN0…IN(n-1); at least MIN_AND_OR_INPUTS."""
        from logic_cad.core.model.constants import MIN_AND_OR_INPUTS

        if _and_or_input_count(index, gate_uid) is None:
            return None
        max_idx = -1
        for _e, _wu, d in self.iter_wire_meta(layout_name):
            if d.get("dst") != gate_uid:
                continue
            dp = d.get("dst_port") or ""
            idx = _port_index(dp)
            if idx is None:
                continue
            max_idx = max(max_idx, idx)
        min_n = MIN_AND_OR_INPUTS
        if max_idx < 0:
            return min_n
        return max(min_n, max_idx + 1)

    def _gate_input_pre_entry(
        self,
        index: IndexStore,
        gate_uid: str,
        dst_port: str,
        toward: tuple[float, float],
        extra_offset_mm: float = 0.0,
    ) -> tuple[float, float] | None:
        _ = toward
        base = index.gate_input_pre_entry_world(self.doc, gate_uid, dst_port)
        if base is None or extra_offset_mm <= 1e-9:
            return base
        port = index.get_port_world(gate_uid, dst_port)
        if port is None:
            return base
        dx = base[0] - port[0]
        dy = base[1] - port[1]
        if abs(dx) >= abs(dy):
            sign = 1.0 if dx >= 0 else -1.0
            return snap_to_grid(base[0] + sign * extra_offset_mm, base[1])
        sign = 1.0 if dy >= 0 else -1.0
        return snap_to_grid(base[0], base[1] + sign * extra_offset_mm)

    def _append_port_segment(
        self,
        pts: list[tuple[float, float]],
        port_pt: tuple[float, float],
    ) -> list[tuple[float, float]]:
        if not pts:
            return [port_pt]
        if abs(pts[-1][0] - port_pt[0]) < 1e-9 and abs(pts[-1][1] - port_pt[1]) < 1e-9:
            return pts
        return pts + [port_pt]

    def _normalize_auto_route_points(
        self,
        pts: list[tuple[float, float]],
        src_port_pt: tuple[float, float],
        dst_port_pt: tuple[float, float],
        *,
        pitch: float = GRID_PITCH,
    ) -> list[tuple[float, float]]:
        """Normalize auto-routed polyline endpoints and trim tiny terminal backtracks.

        Args:
            pts: Routed polyline points before final sanitization.
            src_port_pt: Exact world coordinate for the source port.
            dst_port_pt: Exact world coordinate for the destination port.
            pitch: Routing grid pitch used to derive tiny-tail tolerance.

        Returns:
            Sanitized Manhattan points with exact port endpoints and no tiny
            terminal reverse segment.
        """
        out = [(float(x), float(y)) for x, y in pts]
        if not out:
            return [(float(src_port_pt[0]), float(src_port_pt[1])), (float(dst_port_pt[0]), float(dst_port_pt[1]))]
        out[0] = (float(src_port_pt[0]), float(src_port_pt[1]))
        out[-1] = (float(dst_port_pt[0]), float(dst_port_pt[1]))
        out = self._dedupe_consecutive_points(out)
        tiny_tol_mm = max(float(pitch) * 0.5, 1e-6)
        out = self._trim_terminal_backtrack(out, tiny_tol_mm)
        out = dedupe_colinear(out)
        out = self._dedupe_consecutive_points(out)
        out = self._trim_terminal_backtrack(out, tiny_tol_mm)
        if len(out) >= 2:
            out[0] = (float(src_port_pt[0]), float(src_port_pt[1]))
            out[-1] = (float(dst_port_pt[0]), float(dst_port_pt[1]))
            return out
        return [(float(src_port_pt[0]), float(src_port_pt[1])), (float(dst_port_pt[0]), float(dst_port_pt[1]))]

    def _dedupe_consecutive_points(
        self,
        pts: list[tuple[float, float]],
    ) -> list[tuple[float, float]]:
        """Remove consecutive duplicate points.

        Args:
            pts: Polyline points.

        Returns:
            Input order without immediate duplicates.
        """
        if not pts:
            return []
        out = [pts[0]]
        for x, y in pts[1:]:
            px, py = out[-1]
            if abs(x - px) < 1e-9 and abs(y - py) < 1e-9:
                continue
            out.append((x, y))
        return out

    def _trim_terminal_backtrack(
        self,
        pts: list[tuple[float, float]],
        tiny_tol_mm: float,
    ) -> list[tuple[float, float]]:
        """Drop tiny reverse segment at either endpoint.

        Args:
            pts: Polyline points.
            tiny_tol_mm: Maximum terminal reverse length to collapse.

        Returns:
            Polyline with tiny terminal reversal removed from head/tail.
        """
        out = list(pts)
        while len(out) >= 3 and self._is_tiny_reverse_triplet(out[0], out[1], out[2], tiny_tol_mm, at_head=True):
            del out[1]
        while len(out) >= 3 and self._is_tiny_reverse_triplet(
            out[-3], out[-2], out[-1], tiny_tol_mm, at_head=False
        ):
            del out[-2]
        return out

    def _is_tiny_reverse_triplet(
        self,
        a: tuple[float, float],
        b: tuple[float, float],
        c: tuple[float, float],
        tiny_tol_mm: float,
        *,
        at_head: bool,
    ) -> bool:
        """Return True when A->B->C forms same-axis reverse with tiny terminal leg.

        Args:
            a: First point.
            b: Middle point.
            c: Last point.
            tiny_tol_mm: Maximum endpoint leg length considered accidental.
            at_head: True when checking start side, False for end side.

        Returns:
            True if the triplet is colinear on one axis, reverses direction, and
            the endpoint-side leg length is below tolerance.
        """
        eps = 1e-9
        v1x = b[0] - a[0]
        v1y = b[1] - a[1]
        v2x = c[0] - b[0]
        v2y = c[1] - b[1]
        horizontal = abs(v1y) < eps and abs(v2y) < eps
        vertical = abs(v1x) < eps and abs(v2x) < eps
        if not (horizontal or vertical):
            return False
        if v1x * v2x + v1y * v2y >= 0.0:
            return False
        endpoint_leg = abs(v1x) + abs(v1y) if at_head else abs(v2x) + abs(v2y)
        return endpoint_leg <= tiny_tol_mm + eps

    def _pair_symbol_soft_obstacles(
        self,
        index: IndexStore,
        src_uid: str,
        dst_uid: str,
        access_ports: dict[str, set[str]],
    ) -> list[tuple[float, float, float, float]]:
        keep = {src_uid, dst_uid}
        exclude = set(index.inserts_by_uid.keys()) - keep
        return symbol_obstacles(self.doc, index, exclude, access_ports=access_ports)

    def _spread_escape_point(
        self,
        src_pt: tuple[float, float],
        escape_pt: tuple[float, float] | None,
        extra_offset_mm: float,
    ) -> tuple[float, float] | None:
        if escape_pt is None or extra_offset_mm <= 1e-9:
            return escape_pt
        dx = escape_pt[0] - src_pt[0]
        dy = escape_pt[1] - src_pt[1]
        if abs(dx) >= abs(dy):
            sign = 1.0 if dx >= 0 else -1.0
            return snap_to_grid(escape_pt[0] + sign * extra_offset_mm, escape_pt[1])
        sign = 1.0 if dy >= 0 else -1.0
        return snap_to_grid(escape_pt[0], escape_pt[1] + sign * extra_offset_mm)

    def _polyline_xyb(self, e) -> list[tuple[float, float, float]]:
        out: list[tuple[float, float, float]] = []
        for row in e.get_points("xyb"):
            x = float(row[0])
            y = float(row[1])
            b = float(row[2]) if len(row) > 2 else 0.0
            out.append((x, y, b))
        return out

    def _polyline_points(self, e) -> list[tuple[float, float]]:
        return [(x, y) for x, y, _ in self._polyline_xyb(e)]

    def set_wire_points(
        self,
        layout_name: str,
        entity,
        pts: list[tuple[float, float]],
        *,
        snap_branches: bool = True,
    ) -> None:
        _ = layout_name
        _ = snap_branches
        if len(pts) < 2:
            return
        entity.set_points([(float(x), float(y)) for x, y in pts], format="xy")
        self._after_wire_geometry_changed(layout_name, entity)

    def _set_wire_xyb(
        self,
        layout_name: str,
        entity,
        xyb: list[tuple[float, float, float]],
        *,
        snap_branches: bool = True,
    ) -> None:
        _ = layout_name
        _ = snap_branches
        if len(xyb) < 2:
            return
        entity.set_points([(float(x), float(y), float(b)) for x, y, b in xyb], format="xyb")
        self._after_wire_geometry_changed(layout_name, entity)

    def offset_wire_segment_parallel(
        self, layout_name: str, wire_uid: str, seg_index: int, delta: float
    ) -> bool:
        """Parallel-offset one interior segment by delta (grid-snapped dx or dy); refresh bridges."""
        from logic_cad.core.undo.history import find_entity_by_uid
        from logic_cad.core.model.xdata import get_type

        if abs(delta) < _MANHATTAN_EPS:
            return True
        e = find_entity_by_uid(self.doc, wire_uid)
        if e is None or e.dxftype() != "LWPOLYLINE" or get_type(e) != "WIRE":
            return False
        xyb = self._polyline_xyb(e)
        new_xyb = offset_polyline_segment_parallel_xyb(xyb, seg_index, delta)
        if new_xyb is None:
            return False
        self._set_wire_xyb(layout_name, e, new_xyb)
        self.recompute_all_bridges_ordered(layout_name)
        return True

    def _iter_wire_polylines(self, layout_name: str):
        blk = self._layout_block(layout_name)
        from logic_cad.core.model.xdata import get_type

        for e in blk:
            if e.dxftype() != "LWPOLYLINE" or not is_wire_layer(str(e.dxf.layer)):
                continue
            if get_type(e) == "WIRE":
                yield e
