"""Axis-aligned obstacles for wire routing (symbols + existing and reserved wires)."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Iterable

from ezdxf.math import Vec2, Vec3, bulge_to_arc

from logic_cad.core.model.constants import (
    ENTITY_TYPE_PAPER_FRAME,
    GRID_PITCH,
    LAYER_CONTENTS_AREA,
    ROUTING_PORT_ACCESS_WIDTH_MM,
    ROUTING_SYMBOL_MARGIN,
    ROUTING_WIRE_HALF_WIDTH,
)
from logic_cad.core.model.index_store import IndexStore
from logic_cad.core.model.wire_layers import is_wire_layer
from logic_cad.core.model.xdata import get_type, get_uid, read_ld_app_dict
from logic_cad.core.services.dynamic_gate_factory import GateViewGeometry, gate_view_geometry_from_block_name

if TYPE_CHECKING:
    from ezdxf.document import Drawing


def _inflate(x0: float, y0: float, x1: float, y1: float, m: float) -> tuple[float, float, float, float]:
    return (x0 - m, y0 - m, x1 + m, y1 + m)


def _world_bbox_from_local_rect(
    mat, lx0: float, ly0: float, lx1: float, ly1: float
) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for lx, ly in ((lx0, ly0), (lx1, ly0), (lx0, ly1), (lx1, ly1)):
        w = mat.transform(Vec3(lx, ly, 0.0))
        xs.append(float(w.x))
        ys.append(float(w.y))
    return (min(xs), min(ys), max(xs), max(ys))


def _gate_local_routing_aabb(g: GateViewGeometry) -> tuple[float, float, float, float]:
    """Block-space hull for AND/OR silk + label (below body)."""
    y_lo = min(g.yB, g.sym_y - 1.2)
    return (0.0, y_lo, g.x_out, g.yT)


def _clip_rect_to_box(
    rect: tuple[float, float, float, float],
    box: tuple[float, float, float, float],
) -> tuple[float, float, float, float] | None:
    x0 = max(rect[0], box[0])
    y0 = max(rect[1], box[1])
    x1 = min(rect[2], box[2])
    y1 = min(rect[3], box[3])
    if x1 - x0 <= 1e-9 or y1 - y0 <= 1e-9:
        return None
    return (x0, y0, x1, y1)


def _subtract_rect(
    box: tuple[float, float, float, float],
    hole: tuple[float, float, float, float],
) -> list[tuple[float, float, float, float]]:
    clipped = _clip_rect_to_box(hole, box)
    if clipped is None:
        return [box]
    bx0, by0, bx1, by1 = box
    hx0, hy0, hx1, hy1 = clipped
    out: list[tuple[float, float, float, float]] = []
    if hx0 - bx0 > 1e-9:
        out.append((bx0, by0, hx0, by1))
    if bx1 - hx1 > 1e-9:
        out.append((hx1, by0, bx1, by1))
    mx0 = max(bx0, hx0)
    mx1 = min(bx1, hx1)
    if hy0 - by0 > 1e-9 and mx1 - mx0 > 1e-9:
        out.append((mx0, by0, mx1, hy0))
    if by1 - hy1 > 1e-9 and mx1 - mx0 > 1e-9:
        out.append((mx0, hy1, mx1, by1))
    return out


def _port_access_cutout(
    bbox: tuple[float, float, float, float],
    port_world: tuple[float, float],
    margin: float,
    access_width: float = ROUTING_PORT_ACCESS_WIDTH_MM,
    preferred_side: str | None = None,
) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = bbox
    px, py = port_world
    half = max(access_width * 0.5, GRID_PITCH * 0.5)
    depth = max(access_width, GRID_PITCH)
    side = preferred_side or min(
        (
            (abs(px - x0), "left"),
            (abs(px - x1), "right"),
            (abs(py - y0), "bottom"),
            (abs(py - y1), "top"),
        ),
        key=lambda t: t[0],
    )[1]
    if side == "left":
        return (x0 - margin, py - half, min(x1 + margin, px + depth), py + half)
    if side == "right":
        return (max(x0 - margin, px - depth), py - half, x1 + margin, py + half)
    if side == "bottom":
        return (px - half, y0 - margin, px + half, min(y1 + margin, py + depth))
    return (px - half, max(y0 - margin, py - depth), px + half, y1 + margin)


def _preferred_port_cutout_side(index: IndexStore, uid: str, port_key: str) -> str | None:
    ins = index.inserts_by_uid.get(uid)
    if ins is None:
        return None
    geo = gate_view_geometry_from_block_name(str(ins.dxf.name))
    if geo is None:
        return None
    if port_key.startswith("IN"):
        return "left"
    if port_key.startswith("OUT"):
        return "right"
    return None


def estimate_port_facing(index: IndexStore, doc: Drawing, uid: str, port_key: str) -> tuple[int, int] | None:
    preferred_side = _preferred_port_cutout_side(index, uid, port_key)
    if preferred_side is None:
        boxes = _symbol_boxes(doc, index, uid)
        port_world = index.get_port_world(uid, port_key)
        if port_world is None or not boxes:
            return None
        x0 = min(b[0] for b in boxes)
        y0 = min(b[1] for b in boxes)
        x1 = max(b[2] for b in boxes)
        y1 = max(b[3] for b in boxes)
        px, py = port_world
        preferred_side = min(
            (
                (abs(px - x0), "left"),
                (abs(px - x1), "right"),
                (abs(py - y0), "bottom"),
                (abs(py - y1), "top"),
            ),
            key=lambda item: item[0],
        )[1]
    return {
        "left": (-1, 0),
        "right": (1, 0),
        "bottom": (0, -1),
        "top": (0, 1),
    }.get(preferred_side)


def _symbol_boxes(
    doc: Drawing,
    index: IndexStore,
    uid: str,
) -> list[tuple[float, float, float, float]]:
    from ezdxf import bbox as dxf_bbox

    boxes: list[tuple[float, float, float, float]] = []
    pts = [p for (pu, _pk), p in index.ports.items() if pu == uid]
    if pts:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        boxes.append((min(xs), min(ys), max(xs), max(ys)))
    ins = index.inserts_by_uid.get(uid)
    if ins is not None:
        geo = gate_view_geometry_from_block_name(str(ins.dxf.name))
        if geo is not None:
            vb = _virtual_block_world_bbox(ins)
            if vb is not None:
                boxes.append(vb)
            lx0, ly0, lx1, ly1 = _gate_local_routing_aabb(geo)
            boxes.append(_world_bbox_from_local_rect(ins.matrix44(), lx0, ly0, lx1, ly1))
        else:
            nb = _non_attdef_insert_world_bbox(doc, ins)
            if nb is not None:
                boxes.append(nb)
            else:
                try:
                    e = dxf_bbox.extents([ins])
                    if e is not None and getattr(e, "has_data", False):
                        emin, emax = e.extmin, e.extmax
                        boxes.append((float(emin.x), float(emin.y), float(emax.x), float(emax.y)))
                except Exception:
                    pass
    if not boxes and ins is not None:
        ix = float(ins.dxf.insert.x)
        iy = float(ins.dxf.insert.y)
        s = 5.0
        boxes.append((ix - s, iy - s, ix + s, iy + s))
    return boxes


def _non_attdef_insert_world_bbox(doc: Drawing, ins) -> tuple[float, float, float, float] | None:
    """WCS AABB from block geometry only (exclude ATTDEF), aligned with UI ``block_scaled_bounds`` geo pass."""
    from ezdxf import bbox as dxf_bbox

    bname = str(ins.dxf.name)
    if bname not in doc.blocks:
        return None
    blk = doc.blocks.get(bname)
    non_attdef = [
        e for e in blk if e.dxftype() != "ATTDEF" and str(e.dxf.layer) != LAYER_CONTENTS_AREA
    ]
    if not non_attdef:
        return None
    try:
        e = dxf_bbox.extents(non_attdef)
    except Exception:
        return None
    if e is None or not getattr(e, "has_data", False):
        return None
    sz = e.size
    if abs(float(sz.x)) < 1e-12 and abs(float(sz.y)) < 1e-12:
        return None
    emin, emax = e.extmin, e.extmax
    return _world_bbox_from_local_rect(
        ins.matrix44(),
        float(emin.x),
        float(emin.y),
        float(emax.x),
        float(emax.y),
    )


def _virtual_block_world_bbox(ins) -> tuple[float, float, float, float] | None:
    """INSERT exploded to WCS — catches geometry ezdxf.extents([INSERT]) can miss."""
    from ezdxf import bbox as dxf_bbox

    try:
        ve = list(ins.virtual_entities())
        if not ve:
            return None
        e = dxf_bbox.extents(ve)
        if e is None or not getattr(e, "has_data", False):
            return None
        emin, emax = e.extmin, e.extmax
        return (float(emin.x), float(emin.y), float(emax.x), float(emax.y))
    except Exception:
        return None


def symbol_obstacles(
    doc: Drawing,
    index: IndexStore,
    exclude_uids: set[str],
    margin: float = ROUTING_SYMBOL_MARGIN,
    access_ports: dict[str, set[str]] | None = None,
) -> list[tuple[float, float, float, float]]:
    """One AABB per symbol: port hull ∪ block world bbox (+ margin)."""
    out: list[tuple[float, float, float, float]] = []
    all_uids: set[str] = set(index.inserts_by_uid.keys()) | {uid for uid, _pk in index.ports.keys()}

    for uid in all_uids:
        if uid in exclude_uids:
            continue
        ins0 = index.inserts_by_uid.get(uid)
        if ins0 is not None and get_type(ins0) == ENTITY_TYPE_PAPER_FRAME:
            continue
        boxes = _symbol_boxes(doc, index, uid)
        if not boxes:
            continue
        x0 = min(b[0] for b in boxes)
        y0 = min(b[1] for b in boxes)
        x1 = max(b[2] for b in boxes)
        y1 = max(b[3] for b in boxes)
        rects = [_inflate(x0, y0, x1, y1, margin)]
        for port_key in sorted(access_ports.get(uid, set()) if access_ports else set()):
            pw = index.get_port_world(uid, port_key)
            if pw is None:
                continue
            cutout = _port_access_cutout(
                (x0, y0, x1, y1),
                pw,
                margin,
                preferred_side=_preferred_port_cutout_side(index, uid, port_key),
            )
            next_rects: list[tuple[float, float, float, float]] = []
            for rect in rects:
                next_rects.extend(_subtract_rect(rect, cutout))
            rects = next_rects
        out.extend(rects)
    return out


def _axis_aligned_segment_fat_rect(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    half_width: float,
) -> tuple[float, float, float, float]:
    xmin, xmax = (x0, x1) if x0 <= x1 else (x1, x0)
    ymin, ymax = (y0, y1) if y0 <= y1 else (y1, y0)
    if abs(x1 - x0) < 1e-9:
        return _inflate(xmin - half_width, ymin, xmax + half_width, ymax, 0)
    if abs(y1 - y0) < 1e-9:
        return _inflate(xmin, ymin - half_width, xmax, ymax + half_width, 0)
    return _inflate(xmin, ymin, xmax, ymax, half_width)


def _bulge_segment_fat_rect(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    bulge: float,
    half_width: float,
) -> tuple[float, float, float, float]:
    center, sa, ea, r = bulge_to_arc(Vec2(x0, y0), Vec2(x1, y1), bulge)
    cx, cy = float(center.x), float(center.y)
    xs = [x0, x1]
    ys = [y0, y1]
    for k in range(13):
        t = k / 12.0
        ang = sa + t * (ea - sa)
        xs.append(cx + r * math.cos(ang))
        ys.append(cy + r * math.sin(ang))
    return _inflate(min(xs), min(ys), max(xs), max(ys), half_width)


def _path_segment_obstacles(
    paths: Iterable[list[tuple[float, float]]],
    half_width: float = ROUTING_WIRE_HALF_WIDTH,
) -> list[tuple[float, float, float, float]]:
    """Fattened bounding strips per polyline segment."""
    out: list[tuple[float, float, float, float]] = []
    for pts in paths:
        for i in range(len(pts) - 1):
            x0, y0 = pts[i]
            x1, y1 = pts[i + 1]
            out.append(_axis_aligned_segment_fat_rect(x0, y0, x1, y1, half_width))
    return out


def _path_xyb_segment_obstacles(
    paths: Iterable[list[tuple[float, float, float]]],
    half_width: float = ROUTING_WIRE_HALF_WIDTH,
) -> list[tuple[float, float, float, float]]:
    """Fat obstacles for polylines with optional DXF bulge (arc segments)."""
    out: list[tuple[float, float, float, float]] = []
    for path in paths:
        for i in range(len(path) - 1):
            x0, y0, b0 = path[i]
            x1, y1, _b1 = path[i + 1]
            if abs(b0) < 1e-12:
                out.append(_axis_aligned_segment_fat_rect(x0, y0, x1, y1, half_width))
            else:
                out.append(_bulge_segment_fat_rect(x0, y0, x1, y1, b0, half_width))
    return out


def reserved_path_obstacles(
    paths: list[list[tuple[float, float]]],
    half_width: float = ROUTING_WIRE_HALF_WIDTH,
) -> list[tuple[float, float, float, float]]:
    return _path_segment_obstacles(paths, half_width)


def wire_obstacles(
    doc: Drawing,
    layout_name: str,
    exclude_wire_uids: set[str] | None = None,
    half_width: float = ROUTING_WIRE_HALF_WIDTH,
    *,
    index: IndexStore | None = None,
) -> list[tuple[float, float, float, float]]:
    """Fat obstacles from existing wire polylines.

    When ``index`` is set, skip wires that are not routable endpoints: missing ``src``
    or ``dst`` in xdata, or either INSERT uid absent from the index (orphans after
    symbol delete without deleting wires).
    """
    layout = doc.layouts.get(layout_name)
    blk = doc.blocks.get(layout.block_record_name)
    paths: list[list[tuple[float, float]]] = []
    excluded = exclude_wire_uids or set()
    for e in blk:
        if e.dxftype() != "LWPOLYLINE" or not is_wire_layer(str(e.dxf.layer)):
            continue
        if get_type(e) != "WIRE":
            continue
        wu = get_uid(e)
        if wu in excluded:
            continue
        if index is not None:
            d = read_ld_app_dict(e)
            su, du = d.get("src"), d.get("dst")
            if not su or not du:
                continue
            if su not in index.inserts_by_uid or du not in index.inserts_by_uid:
                continue
        row_list = list(e.get_points("xyb"))
        pts = [(float(r[0]), float(r[1]), float(r[2]) if len(r) > 2 else 0.0) for r in row_list]
        paths.append(pts)
    return _path_xyb_segment_obstacles(paths, half_width)


def build_symbol_only_routing_obstacles(
    doc: Drawing,
    index: IndexStore,
    layout_name: str,
    exclude_symbol_uids: set[str],
    access_ports: dict[str, set[str]] | None = None,
    symbol_margin: float = ROUTING_SYMBOL_MARGIN,
) -> list[tuple[float, float, float, float]]:
    """Hard obstacles from INSERT symbols only (no wire fat rects, no reserved paths).

    Used as ``obstacles_relaxed`` for routing layers 3–4 so paths may cross existing wires.
    ``layout_name`` is accepted for API symmetry with ``build_routing_obstacles``; it is unused.
    """
    _ = layout_name
    return symbol_obstacles(doc, index, exclude_symbol_uids, margin=symbol_margin, access_ports=access_ports)


def build_routing_obstacles(
    doc: Drawing,
    index: IndexStore,
    layout_name: str,
    exclude_symbol_uids: set[str],
    exclude_wire_uids: set[str] | None = None,
    reserved_paths: list[list[tuple[float, float]]] | None = None,
    access_ports: dict[str, set[str]] | None = None,
    symbol_margin: float = ROUTING_SYMBOL_MARGIN,
) -> list[tuple[float, float, float, float]]:
    o = build_symbol_only_routing_obstacles(
        doc, index, layout_name, exclude_symbol_uids, access_ports=access_ports, symbol_margin=symbol_margin
    )
    o = list(o)
    o.extend(wire_obstacles(doc, layout_name, exclude_wire_uids, index=index))
    if reserved_paths:
        o.extend(reserved_path_obstacles(reserved_paths))
    return o


def moved_symbols_world_bbox(
    doc: Drawing,
    index: IndexStore,
    symbol_uids: set[str],
) -> tuple[float, float, float, float] | None:
    """Union AABB of moved symbols (same geometry basis as routing obstacles)."""
    if not symbol_uids:
        return None
    boxes: list[tuple[float, float, float, float]] = []
    for uid in symbol_uids:
        boxes.extend(_symbol_boxes(doc, index, uid))
    if not boxes:
        return None
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes)
    y1 = max(b[3] for b in boxes)
    min_extent = 2.0 * float(GRID_PITCH)
    w, h = x1 - x0, y1 - y0
    if w < min_extent:
        c = 0.5 * (x0 + x1)
        half = 0.5 * min_extent
        x0, x1 = c - half, c + half
    if h < min_extent:
        c = 0.5 * (y0 + y1)
        half = 0.5 * min_extent
        y0, y1 = c - half, c + half
    return (x0, y0, x1, y1)


def branch_center_normalized_in_bbox(
    cx: float, cy: float, bbox: tuple[float, float, float, float]
) -> tuple[float, float] | None:
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0
    if w < 1e-12 or h < 1e-12:
        return None
    u = (cx - x0) / w
    v = (cy - y0) / h
    return (max(0.0, min(1.0, u)), max(0.0, min(1.0, v)))


def bbox_uv_to_world_mm(
    u: float, v: float, bbox: tuple[float, float, float, float]
) -> tuple[float, float]:
    x0, y0, x1, y1 = bbox
    return (x0 + u * (x1 - x0), y0 + v * (y1 - y0))
