from __future__ import annotations

from collections import defaultdict

from logic_cad.core.model.constants import BRIDGE_RADIUS, LAYER_WIRE_BRIDGE
from logic_cad.core.model.xdata import get_type, get_uid
from logic_cad.core.paper_layout_access import paper_layout_block
from logic_cad.core.routing import (
    apply_vertical_semijumps_to_xyb,
    horizontal_segment_goes_east,
    orthogonal_segments_crossing_relaxed,
    polyline_segments,
    strip_wire_xyb_semijumps,
)
from logic_cad.core.routing.wire_polyline_geometry import _vertical_segment_wire_uid


class WireServiceBridgeMixin:
    def clear_wire_bridges(self, layout_name: str) -> None:
        blk = paper_layout_block(self.doc, layout_name)
        to_del = []
        for e in blk:
            if e.dxftype() == "ARC" and e.dxf.layer == LAYER_WIRE_BRIDGE:
                to_del.append(e)
        for e in to_del:
            self.doc.entitydb.delete_entity(e)

    def recompute_all_bridges_ordered(self, layout_name: str) -> None:
        """Strip old LD_WIRE_BRIDGE ARCs; strip semijumps; re-apply vertical bulge semicircles at crossings."""
        self.clear_wire_bridges(layout_name)
        wires: list[tuple[object, str, list[tuple[float, float]]]] = []
        for e in self._iter_wire_polylines(layout_name):
            wu = get_uid(e)
            if not wu:
                continue
            xyb = strip_wire_xyb_semijumps(self._polyline_xyb(e))
            self._set_wire_xyb(layout_name, e, xyb, snap_branches=False)
            xy = [(float(x), float(y)) for x, y, _ in xyb]
            wires.append((e, wu, xy))
        crossings: dict[str, list[tuple[float, float, bool]]] = defaultdict(list)
        n_w = len(wires)
        for i in range(n_w):
            _ei, ui, pi = wires[i]
            segsi = polyline_segments(pi)
            for j in range(i + 1, n_w):
                _ej, uj, pj = wires[j]
                segsj = polyline_segments(pj)
                for a0, a1 in segsi:
                    for b0, b1 in segsj:
                        hit = orthogonal_segments_crossing_relaxed(a0, a1, b0, b1)
                        if hit is None:
                            continue
                        pt, hseg, vseg = hit
                        owner = _vertical_segment_wire_uid(pi, ui, pj, uj, vseg)
                        if owner is None:
                            continue
                        want_east = horizontal_segment_goes_east(hseg[0], hseg[1])
                        crossings[owner].append((pt[0], pt[1], want_east))
        for e, wu, xy in wires:
            raw = crossings.get(wu, [])
            if not raw:
                continue
            seen_xy: set[tuple[float, float]] = set()
            dedup: list[tuple[float, float, bool]] = []
            for xcc, ycc, we in raw:
                key_xy = (round(xcc, 6), round(ycc, 6))
                if key_xy in seen_xy:
                    continue
                seen_xy.add(key_xy)
                dedup.append((xcc, ycc, we))
            dedup.sort(key=lambda t: (t[1], t[0]))
            orient_fixed = dedup[0][2] if dedup else True
            dedup = [(x, y, orient_fixed) for x, y, _ in dedup]
            new_xyb = apply_vertical_semijumps_to_xyb(xy, dedup, BRIDGE_RADIUS)
            self._set_wire_xyb(layout_name, e, new_xyb, snap_branches=False)
