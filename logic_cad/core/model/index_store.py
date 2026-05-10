"""Rebuilt caches: uid/handle, ports, wires, connection graph."""

from __future__ import annotations

from dataclasses import dataclass, field

from ezdxf.document import Drawing
from ezdxf.math import Vec3

from logic_cad.core.geometry.manhattan_metrics import manhattan_distance
from logic_cad.core.model.connection_graph import ConnectionGraph
from logic_cad.core.model.constants import ENTITY_TYPE_CHECKPOINT, ENTITY_TYPE_WIRE_BRANCH
from logic_cad.core.model.port_key import is_input_port_key, parse_port_layer
from logic_cad.core.model.wire_layers import is_wire_layer
from logic_cad.core.model.xdata import get_type, get_uid, read_ld_app_dict
from logic_cad.core.paper_layout_access import paper_layout_block
from logic_cad.core.services.dynamic_gate_factory import gate_view_geometry_from_block_name


def _world_manhattan_escape(
    p0w: tuple[float, float],
    ux: float,
    uy: float,
    escape_mm: float,
    toward: tuple[float, float] | None,
    prefer_left: bool,
    *,
    toward_first: bool = False,
) -> tuple[float, float]:
    """First step from port in world space: one of ±X or ±Y by escape_mm (true Manhattan)."""
    px, py = p0w
    cands = [
        (px + escape_mm, py),
        (px - escape_mm, py),
        (px, py + escape_mm),
        (px, py - escape_mm),
    ]

    sign = -1.0 if prefer_left else 1.0
    tx, ty = px + sign * ux * escape_mm, py + sign * uy * escape_mm
    if toward is not None:
        if toward_first:
            return min(
                cands,
                key=lambda c: (manhattan_distance(c, toward), manhattan_distance(c, (tx, ty))),
            )
        # Keep the first leg outside the symbol, then bias toward the route target.
        return min(
            cands,
            key=lambda c: (manhattan_distance(c, (tx, ty)), manhattan_distance(c, toward)),
        )
    return min(cands, key=lambda c: manhattan_distance(c, (tx, ty)))


@dataclass
class IndexStore:
    doc: Drawing
    layout_name: str
    uid_to_handle: dict[str, str] = field(default_factory=dict)
    handle_to_uid: dict[str, str] = field(default_factory=dict)
    inserts_by_uid: dict[str, object] = field(default_factory=dict)
    ports: dict[tuple[str, str], tuple[float, float]] = field(default_factory=dict)
    port_block_local: dict[tuple[str, str], tuple[float, float]] = field(default_factory=dict)
    wire_by_uid: dict[str, str] = field(default_factory=dict)
    # (insert_uid, port_key) for every wire endpoint that has XDATA src/dst + src_port/dst_port.
    connected_endpoint_ports: set[tuple[str, str]] = field(default_factory=set)
    graph: ConnectionGraph = field(default_factory=ConnectionGraph)
    issues: list[str] = field(default_factory=list)

    def port_key(self, direction: str, idx: int, unit: str) -> str:
        return f"{direction}{idx}_{unit}"

    def rebuild(self, doc: Drawing, layout_name: str) -> None:
        self.doc = doc
        self.layout_name = layout_name
        self.uid_to_handle.clear()
        self.handle_to_uid.clear()
        self.inserts_by_uid.clear()
        self.ports.clear()
        self.port_block_local.clear()
        self.wire_by_uid.clear()
        self.connected_endpoint_ports.clear()
        self.graph = ConnectionGraph()
        self.issues.clear()

        layout = doc.layouts.get(layout_name)
        if layout is None or layout.is_modelspace:
            self.issues.append(f"Invalid layout {layout_name!r}")
            return
        blk = paper_layout_block(doc, layout_name)

        for e in blk:
            uid = get_uid(e)
            if uid:
                self.uid_to_handle[uid] = e.dxf.handle
                self.handle_to_uid[e.dxf.handle] = uid

            if e.dxftype() == "INSERT":
                ins = e
                if uid:
                    self.inserts_by_uid[uid] = ins
                    self._index_insert_ports(doc, ins, uid)

            if e.dxftype() == "LWPOLYLINE" and is_wire_layer(str(e.dxf.layer)) and get_type(e) == "WIRE" and uid:
                self.wire_by_uid[uid] = e.dxf.handle
                d = read_ld_app_dict(e)
                su, du = d.get("src"), d.get("dst")
                sp, dp = d.get("src_port") or "", d.get("dst_port") or ""
                if su and sp:
                    self.connected_endpoint_ports.add((su, sp))
                if du and dp:
                    self.connected_endpoint_ports.add((du, dp))
                if su and du:
                    self.graph.add_wire(su, du, uid)

    def _index_insert_ports(self, doc: Drawing, ins, ins_uid: str) -> None:
        bname = ins.dxf.name
        if bname not in doc.blocks:
            return
        b = doc.blocks.get(bname)
        mat = ins.matrix44()
        for ent in b:
            if ent.dxftype() != "POINT":
                continue
            layer = ent.dxf.layer
            parsed = parse_port_layer(str(layer))
            if parsed is None:
                continue
            loc = ent.dxf.location
            w = mat.transform(Vec3(float(loc.x), float(loc.y), float(loc.z)))
            key = self.port_key(parsed.direction, parsed.index, parsed.unit)
            self.ports[(ins_uid, key)] = (float(w.x), float(w.y))
            self.port_block_local[(ins_uid, key)] = (float(loc.x), float(loc.y))

    def get_port_world(self, ins_uid: str, port_key: str) -> tuple[float, float] | None:
        return self.ports.get((ins_uid, port_key))

    def port_first_escape_world(
        self,
        doc: Drawing,
        ins_uid: str,
        port_key: str,
        escape_mm: float,
        toward: tuple[float, float] | None = None,
    ) -> tuple[float, float] | None:
        """First routing step from port: axis-aligned in world space, biased toward local ±X when possible."""
        ins = self.inserts_by_uid.get(ins_uid)
        if ins is None:
            return None
        bname = ins.dxf.name
        if bname not in doc.blocks:
            return None
        b = doc.blocks.get(bname)
        layer = f"LD_PORT_{port_key}"
        mat = ins.matrix44()
        xs: list[float] = []
        for ent in b:
            if ent.dxftype() != "POINT":
                continue
            if not str(ent.dxf.layer).startswith("LD_PORT_"):
                continue
            xs.append(float(ent.dxf.location.x))
        if not xs:
            return None
        mid_x = (min(xs) + max(xs)) / 2.0
        toward_first = get_type(ins) in (ENTITY_TYPE_CHECKPOINT, ENTITY_TYPE_WIRE_BRANCH)
        for ent in b:
            if ent.dxftype() != "POINT":
                continue
            if ent.dxf.layer != layer:
                continue
            loc = ent.dxf.location
            lx = float(loc.x)
            ly = float(loc.y)
            lz = float(loc.z)
            p0w = mat.transform(Vec3(lx, ly, lz))
            ax = mat.transform(Vec3(lx + 1.0, ly, lz))
            vx, vy = float(ax.x - p0w.x), float(ax.y - p0w.y)
            vlen = (vx * vx + vy * vy) ** 0.5
            px, py = float(p0w.x), float(p0w.y)
            prefer_left = lx < mid_x - 1e-9
            if vlen < 1e-9:
                return _world_manhattan_escape(
                    (px, py), 1.0, 0.0, escape_mm, toward, prefer_left, toward_first=toward_first
                )
            ux, uy = vx / vlen, vy / vlen
            return _world_manhattan_escape(
                (px, py), ux, uy, escape_mm, toward, prefer_left, toward_first=toward_first
            )
        return None

    def gate_input_pre_entry_world(
        self,
        doc: Drawing,
        ins_uid: str,
        port_key: str,
    ) -> tuple[float, float] | None:
        ins = self.inserts_by_uid.get(ins_uid)
        if ins is None:
            return None
        bname = str(ins.dxf.name)
        geo = gate_view_geometry_from_block_name(bname)
        if geo is None or not is_input_port_key(port_key):
            return None
        local = self.port_block_local.get((ins_uid, port_key))
        if local is None:
            return None
        lx, ly = local
        mat = ins.matrix44()
        p0w = mat.transform(Vec3(lx, ly, 0.0))
        target = mat.transform(Vec3(geo.input_pre_entry_x, ly, 0.0))
        px, py = float(p0w.x), float(p0w.y)
        tx, ty = float(target.x), float(target.y)
        step = abs(geo.input_pre_entry_x - lx)
        cands = [
            (px + step, py),
            (px - step, py),
            (px, py + step),
            (px, py - step),
        ]
        return min(cands, key=lambda c: manhattan_distance(c, (tx, ty)))

    def port_unit_from_key(self, port_key: str) -> str | None:
        parts = port_key.split("_", 1)
        if len(parts) < 2:
            return None
        return parts[1]
