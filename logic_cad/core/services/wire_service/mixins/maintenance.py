from __future__ import annotations

from logic_cad.core.model.constants import (
    LAYER_WIRE_COM,
    LAYER_WIRE_COM_SEGMENT,
    LAYER_WIRE_COM_MARKER,
    LAYER_WIRE_LOGIC,
    LAYER_WIRE_VALUE,
    LINETYPE_COM,
    LINETYPE_CONTINUOUS,
    ENTITY_TYPE_WIRE_ARROW,
    LINETYPE_LOGIC,
    LINETYPE_VALUE,
    ROUTE_ESCAPE_MM,
    WIRE_COM_DASH_MM,
    WIRE_COM_MARKER_RADIUS_MM,
    WIRE_XDATA_ALLOW_ORTHOGONAL_CROSS,
    WIRE_XDATA_SHOW_IN_ARROW,
    grid_snap_tolerance,
)
from logic_cad.core.model.wire_layers import is_wire_layer, layer_for_wire_unit
from logic_cad.core.model.connection_graph import ports_compatible
from logic_cad.core.model.index_store import IndexStore
from logic_cad.core.model.xdata import (
    build_ld_app_tags,
    get_type,
    get_uid,
    new_uid,
    read_ld_app_dict,
    set_entity_xdata,
)
from logic_cad.core.routing.wire_arrow_geometry import wire_in_arrow_wing_points_xyb
from logic_cad.core.routing.wire_polyline_geometry import _dist_mm, _lwpolyline_vertices


class WireServiceMaintenanceMixin:
    def _wire_effective_linetype(self, wire_entity) -> str:
        """Return resolved linetype for a WIRE entity when BYLAYER/empty is used."""
        lt_raw = getattr(wire_entity.dxf, "linetype", None)
        lt = str(lt_raw).strip() if lt_raw else ""
        if lt:
            return lt
        if str(getattr(wire_entity.dxf, "layer", "")).upper() == LAYER_WIRE_VALUE.upper():
            return LINETYPE_VALUE
        return LINETYPE_LOGIC

    def _wire_is_com_style(self, wire_entity) -> bool:
        """Return True when *wire_entity* should render COM beads."""
        d = read_ld_app_dict(wire_entity)
        unit = str(d.get("unit") or "").strip().upper()
        if unit == "COM":
            return True
        lt = str(getattr(wire_entity.dxf, "linetype", "") or "").strip().upper()
        if lt == LINETYPE_COM.upper():
            return True
        return str(getattr(wire_entity.dxf, "layer", "")).strip().upper() == LAYER_WIRE_COM.upper()

    def _com_marker_centers_for_polyline(
        self, points_xy: list[tuple[float, float]]
    ) -> list[tuple[float, float]]:
        """Return COM marker centers for each segment with per-segment restart."""
        _line_segs, centers = self._com_visual_segments_and_markers(points_xy)
        return centers

    def _com_visual_segments_and_markers(
        self,
        points_xy: list[tuple[float, float]],
    ) -> tuple[list[tuple[tuple[float, float], tuple[float, float]]], list[tuple[float, float]]]:
        """Build COM helper LINE segments and marker centers from a wire polyline.

        Pattern is reset per segment and always starts with a 5 mm line from each
        corner/vertex.
        """
        if len(points_xy) < 2:
            return ([], [])
        line_mm = float(WIRE_COM_DASH_MM)
        radius_mm = float(WIRE_COM_MARKER_RADIUS_MM)
        marker_diameter_mm = radius_mm * 2.0
        out_lines: list[tuple[tuple[float, float], tuple[float, float]]] = []
        out: list[tuple[float, float]] = []
        for i in range(len(points_xy) - 1):
            ax, ay = points_xy[i]
            bx, by = points_xy[i + 1]
            dx = float(bx) - float(ax)
            dy = float(by) - float(ay)
            seg_len = (dx * dx + dy * dy) ** 0.5
            if seg_len <= 1e-9:
                continue
            ux = dx / seg_len
            uy = dy / seg_len
            pos_mm = 0.0
            while pos_mm < seg_len - 1e-9:
                line_end_mm = min(pos_mm + line_mm, seg_len)
                if line_end_mm > pos_mm + 1e-9:
                    sx = float(ax) + ux * pos_mm
                    sy = float(ay) + uy * pos_mm
                    ex = float(ax) + ux * line_end_mm
                    ey = float(ay) + uy * line_end_mm
                    out_lines.append(((sx, sy), (ex, ey)))
                if line_end_mm >= seg_len - 1e-9:
                    break
                # If the marker slot does not fit, merge the remaining tail into straight line.
                remaining_after_line_mm = seg_len - line_end_mm
                if remaining_after_line_mm <= marker_diameter_mm + 1e-9:
                    tail_start_x = float(ax) + ux * line_end_mm
                    tail_start_y = float(ay) + uy * line_end_mm
                    out_lines.append(((tail_start_x, tail_start_y), (float(bx), float(by))))
                    break
                center_mm = line_end_mm + radius_mm
                cx = float(ax) + ux * center_mm
                cy = float(ay) + uy * center_mm
                out.append((cx, cy))
                pos_mm = line_end_mm + marker_diameter_mm
        return out_lines, out

    def refresh_com_wire_markers(self, layout_name: str) -> None:
        """Rebuild COM helper LINE/CIRCLE entities in *layout_name* from wire geometry."""
        blk = self._layout_block(layout_name)
        stale_markers = [
            e
            for e in blk
            if (
                e.dxftype() == "CIRCLE"
                and str(getattr(e.dxf, "layer", "")).strip().upper() == LAYER_WIRE_COM_MARKER.upper()
            )
            or (
                e.dxftype() == "LINE"
                and str(getattr(e.dxf, "layer", "")).strip().upper() == LAYER_WIRE_COM_SEGMENT.upper()
            )
        ]
        for marker in stale_markers:
            self.doc.entitydb.delete_entity(marker)
        for e in blk:
            if e.dxftype() != "LWPOLYLINE" or not is_wire_layer(str(e.dxf.layer)):
                continue
            if get_type(e) != "WIRE":
                continue
            if not self._wire_is_com_style(e):
                continue
            line_segs, centers = self._com_visual_segments_and_markers(_lwpolyline_vertices(e))
            for (sx, sy), (ex, ey) in line_segs:
                blk.add_line(
                    (float(sx), float(sy)),
                    (float(ex), float(ey)),
                    dxfattribs={"layer": LAYER_WIRE_COM_SEGMENT, "linetype": LINETYPE_CONTINUOUS},
                )
            for cx, cy in centers:
                blk.add_circle(
                    (float(cx), float(cy)),
                    float(WIRE_COM_MARKER_RADIUS_MM),
                    dxfattribs={"layer": LAYER_WIRE_COM_MARKER, "linetype": LINETYPE_CONTINUOUS},
                )

    def _after_wire_geometry_changed(self, layout_name: str, entity) -> None:
        """Refresh WIRE_ARROW child LWPOLYLINE when a WIRE polyline's vertices change."""
        from logic_cad.core.model.xdata import get_uid as xget_uid

        if entity.dxftype() != "LWPOLYLINE":
            return
        if get_type(entity) != "WIRE":
            return
        wu = xget_uid(entity)
        if not wu:
            return
        wd = read_ld_app_dict(entity)
        if str(wd.get(WIRE_XDATA_SHOW_IN_ARROW) or "") != "1":
            self.refresh_com_wire_markers(layout_name)
            return
        self.sync_wire_arrow_dxf(layout_name, wu)
        self.refresh_com_wire_markers(layout_name)

    def remove_wire_arrow_children(self, layout_name: str, parent_wire_uid: str) -> None:
        """Delete all WIRE_ARROW decorations attached to *parent_wire_uid*."""
        for ent in self._iter_wire_arrow_entities(layout_name, parent_wire_uid):
            self.doc.entitydb.delete_entity(ent)

    def _iter_wire_arrow_entities(self, layout_name: str, parent_wire_uid: str):
        blk = self._layout_block(layout_name)
        for e in blk:
            if e.dxftype() != "LWPOLYLINE" or not is_wire_layer(str(e.dxf.layer)):
                continue
            if get_type(e) != ENTITY_TYPE_WIRE_ARROW:
                continue
            d = read_ld_app_dict(e)
            if d.get("wire") == parent_wire_uid:
                yield e

    def sync_wire_arrow_dxf(self, layout_name: str, wire_uid: str) -> None:
        """Create, update, or delete WIRE_ARROW LWPOLYLINE from WIRE *wire_uid* and ``show_in_arrow``."""
        from logic_cad.core.undo.history import find_entity_by_uid

        w_ent = find_entity_by_uid(self.doc, wire_uid)
        if w_ent is None or w_ent.dxftype() != "LWPOLYLINE" or get_type(w_ent) != "WIRE":
            self.remove_wire_arrow_children(layout_name, wire_uid)
            return
        wd = read_ld_app_dict(w_ent)
        if str(wd.get(WIRE_XDATA_SHOW_IN_ARROW) or "") != "1":
            self.remove_wire_arrow_children(layout_name, wire_uid)
            return
        xyb = self._polyline_xyb(w_ent)
        tri = wire_in_arrow_wing_points_xyb(xyb)
        if tri is None:
            self.remove_wire_arrow_children(layout_name, wire_uid)
            return
        a_pt, _p_pt, b_pt = tri
        pts_xy = [a_pt, _p_pt, b_pt]
        wire_layer = str(w_ent.dxf.layer)
        lt = self._wire_effective_linetype(w_ent)
        arrow_ents = list(self._iter_wire_arrow_entities(layout_name, wire_uid))
        for extra in arrow_ents[1:]:
            self.doc.entitydb.delete_entity(extra)
        if arrow_ents:
            e0 = arrow_ents[0]
            e0.set_points([(float(x), float(y)) for x, y in pts_xy], format="xy")
            e0.dxf.layer = wire_layer
            e0.dxf.linetype = lt
            return
        blk = self._layout_block(layout_name)
        lw = blk.add_lwpolyline(
            [(float(x), float(y)) for x, y in pts_xy],
            dxfattribs={"layer": wire_layer, "linetype": lt},
        )
        au = new_uid()
        set_entity_xdata(
            lw,
            build_ld_app_tags("1", au, ENTITY_TYPE_WIRE_ARROW, {"wire": wire_uid}),
        )

    def set_wire_show_in_arrow(self, layout_name: str, wire_uid: str, show: bool) -> None:
        """Persist ``show_in_arrow`` on WIRE XDATA and sync or remove WIRE_ARROW geometry."""
        from logic_cad.core.undo.history import find_entity_by_uid

        e = find_entity_by_uid(self.doc, wire_uid)
        if e is None or e.dxftype() != "LWPOLYLINE":
            raise ValueError("配線が見つかりません。")
        if get_type(e) != "WIRE":
            raise ValueError("WIRE 以外のエンティティです。")
        d = read_ld_app_dict(e)
        ver = str(d.get("ver", "1"))
        wu = str(d.get("uid") or get_uid(e) or wire_uid)
        extra = {k: v for k, v in d.items() if k not in ("ver", "uid", "type")}
        if show:
            extra[WIRE_XDATA_SHOW_IN_ARROW] = "1"
        else:
            extra.pop(WIRE_XDATA_SHOW_IN_ARROW, None)
        set_entity_xdata(e, build_ld_app_tags(ver, wu, "WIRE", extra))
        if show:
            self.sync_wire_arrow_dxf(layout_name, wire_uid)
        else:
            self.remove_wire_arrow_children(layout_name, wire_uid)

    def disconnect(self, layout_name: str, wire_uid: str) -> None:
        from logic_cad.core.undo.history import find_entity_by_uid

        self.remove_wire_arrow_children(layout_name, wire_uid)
        e = find_entity_by_uid(self.doc, wire_uid)
        if e is None or e.dxftype() != "LWPOLYLINE":
            raise ValueError("配線が見つかりません。")
        self.doc.entitydb.delete_entity(e)
        self.refresh_com_wire_markers(layout_name)

    def set_wire_linetype(self, layout_name: str, wire_uid: str, linetype: str) -> None:
        from logic_cad.core.undo.history import find_entity_by_uid

        e = find_entity_by_uid(self.doc, wire_uid)
        if e is None:
            raise ValueError("配線が見つかりません。")
        d = read_ld_app_dict(e)
        ver = str(d.get("ver", "1"))
        wu = str(d.get("uid") or get_uid(e) or wire_uid)
        extra = {k: v for k, v in d.items() if k not in ("ver", "uid", "type")}
        lt = str(linetype or "").strip().upper()
        if lt == LINETYPE_COM.upper():
            extra["unit"] = "COM"
            e.dxf.layer = LAYER_WIRE_COM
            e.dxf.linetype = LINETYPE_CONTINUOUS
        elif lt == LINETYPE_VALUE.upper():
            extra["unit"] = "VALUE"
            e.dxf.layer = LAYER_WIRE_VALUE
            e.dxf.linetype = LINETYPE_VALUE
        else:
            extra["unit"] = "LOGIC"
            e.dxf.layer = LAYER_WIRE_LOGIC
            e.dxf.linetype = LINETYPE_LOGIC
        set_entity_xdata(e, build_ld_app_tags(ver, wu, "WIRE", extra))
        d = read_ld_app_dict(e)
        if str(d.get(WIRE_XDATA_SHOW_IN_ARROW) or "") == "1":
            self.sync_wire_arrow_dxf(layout_name, wire_uid)
        self.refresh_com_wire_markers(layout_name)

    def set_wire_skip_auto_reroute(self, layout_name: str, wire_uid: str, skip: bool) -> None:
        from logic_cad.core.undo.history import find_entity_by_uid

        e = find_entity_by_uid(self.doc, wire_uid)
        if e is None or e.dxftype() != "LWPOLYLINE":
            raise ValueError("配線が見つかりません。")
        d = read_ld_app_dict(e)
        ver = str(d.get("ver", "1"))
        wu = str(d.get("uid") or get_uid(e) or wire_uid)
        extra = {k: v for k, v in d.items() if k not in ("ver", "uid", "type")}
        if skip:
            extra["skip_auto_reroute"] = "1"
        else:
            extra.pop("skip_auto_reroute", None)
        set_entity_xdata(e, build_ld_app_tags(ver, wu, "WIRE", extra))

    def set_wire_allow_orthogonal_cross(self, layout_name: str, wire_uid: str, allow: bool) -> None:
        """Persist ``allow_orthogonal_cross`` on WIRE XDATA for symbol-only hard-obstacle routing."""
        from logic_cad.core.undo.history import find_entity_by_uid

        _ = layout_name
        e = find_entity_by_uid(self.doc, wire_uid)
        if e is None or e.dxftype() != "LWPOLYLINE":
            raise ValueError("配線が見つかりません。")
        if get_type(e) != "WIRE":
            raise ValueError("WIRE 以外のエンティティです。")
        d = read_ld_app_dict(e)
        ver = str(d.get("ver", "1"))
        wu = str(d.get("uid") or get_uid(e) or wire_uid)
        extra = {k: v for k, v in d.items() if k not in ("ver", "uid", "type")}
        if allow:
            extra[WIRE_XDATA_ALLOW_ORTHOGONAL_CROSS] = "1"
        else:
            extra.pop(WIRE_XDATA_ALLOW_ORTHOGONAL_CROSS, None)
        set_entity_xdata(e, build_ld_app_tags(ver, wu, "WIRE", extra))

    def wire_connection_health(
        self,
        index: IndexStore,
        _layout_name: str,
        wire_uid: str,
        endpoint_tol_mm: float | None = None,
    ) -> tuple[bool, bool]:
        """Returns (logical_ok, geometry_ok). Either False marks the wire as visually broken."""
        from logic_cad.core.undo.history import find_entity_by_uid
        from logic_cad.core.model.xdata import get_type

        tol = endpoint_tol_mm
        if tol is None:
            tol = max(grid_snap_tolerance() * 2.0, ROUTE_ESCAPE_MM)

        e = find_entity_by_uid(self.doc, wire_uid)
        if e is None or e.dxftype() != "LWPOLYLINE" or get_type(e) != "WIRE":
            return (False, False)

        d = read_ld_app_dict(e)
        su, du = str(d.get("src") or ""), str(d.get("dst") or "")
        sp, dp = str(d.get("src_port") or ""), str(d.get("dst_port") or "")

        logical = True
        if not (su and du and sp and dp):
            logical = False
        elif su not in index.inserts_by_uid or du not in index.inserts_by_uid:
            logical = False
        else:
            p0w = index.get_port_world(su, sp)
            p1w = index.get_port_world(du, dp)
            if p0w is None or p1w is None:
                logical = False
            else:
                unit_a = index.port_unit_from_key(sp)
                unit_b = index.port_unit_from_key(dp)
                if unit_a is None or unit_b is None or not ports_compatible(unit_a, unit_b):
                    logical = False
                elif not any(s == su and d == du and w == wire_uid for s, d, w in index.graph.edges):
                    logical = False

        pts = _lwpolyline_vertices(e)
        geometry = True
        if len(pts) < 2:
            geometry = False
        else:
            pw0 = index.get_port_world(su, sp) if su and sp else None
            pw1 = index.get_port_world(du, dp) if du and dp else None
            if pw0 is None or pw1 is None:
                geometry = False
            elif _dist_mm(pts[0], pw0) > tol or _dist_mm(pts[-1], pw1) > tol:
                geometry = False

        return (logical, geometry)

    def peer_for_symbol_port(
        self, layout_name: str, symbol_uid: str, port_key: str
    ) -> tuple[str, str] | None:
        """If a WIRE attaches to this port, return (peer_insert_uid, peer_port_key)."""
        for _ent, _wu, meta in self.iter_wire_meta(layout_name):
            if meta.get("src") == symbol_uid and meta.get("src_port") == port_key:
                du = meta.get("dst")
                dp = str(meta.get("dst_port") or "")
                if du:
                    return (str(du), dp)
            if meta.get("dst") == symbol_uid and meta.get("dst_port") == port_key:
                su = meta.get("src")
                sp = str(meta.get("src_port") or "")
                if su:
                    return (str(su), sp)
        return None
    def clipboard_records_internal_wires(self, layout_name: str, uids: set[str]):
        from logic_cad.core.symbol_clipboard import WireCopyRecord
        from logic_cad.core.model.xdata import get_type

        out: list = []
        blk = self._layout_block(layout_name)
        for e in blk:
            if e.dxftype() != "LWPOLYLINE" or not is_wire_layer(str(e.dxf.layer)):
                continue
            if get_type(e) != "WIRE":
                continue
            d = read_ld_app_dict(e)
            su, du = d.get("src"), d.get("dst")
            if not su or not du or su not in uids or du not in uids:
                continue
            wu = d.get("uid") or get_uid(e)
            if not wu:
                continue
            pts = [(float(x), float(y)) for x, y in e.get_points("xy")]
            lt = self._wire_effective_linetype(e)
            extra = {k: v for k, v in d.items() if k not in ("ver", "uid", "type")}
            out.append(WireCopyRecord(source_uid=str(wu), points=pts, linetype=lt, xdata_extra=extra))
        return out

    def paste_wire_from_clipboard(
        self,
        layout_name: str,
        rec,
        uid_map: dict[str, str],
        delta_xy: tuple[float, float],
    ) -> str:
        dx, dy = float(delta_xy[0]), float(delta_xy[1])
        pts = [(float(x) + dx, float(y) + dy) for x, y in rec.points]
        if len(pts) < 2:
            raise ValueError("配線の頂点数が足りません。")
        extra = dict(rec.xdata_extra)
        osrc, odst = extra.get("src"), extra.get("dst")
        if not osrc or not odst or osrc not in uid_map or odst not in uid_map:
            raise ValueError("貼り付け後のシンボル対応表に、クリップボードの配線の端点がありません。")
        extra["src"] = uid_map[osrc]
        extra["dst"] = uid_map[odst]
        blk = self._layout_block(layout_name)
        wunit_str = str(extra.get("unit") or "LOGIC")
        wl = layer_for_wire_unit(wunit_str)
        wu_norm = wunit_str.upper()
        if wu_norm == "COM":
            default_lt = LINETYPE_CONTINUOUS
        elif wu_norm == "LOGIC":
            default_lt = LINETYPE_LOGIC
        else:
            default_lt = LINETYPE_VALUE
        rlt = str(rec.linetype or "").strip()
        dxfattribs: dict[str, str] = {"layer": wl}
        if rlt and rlt.upper() != default_lt.upper():
            dxfattribs["linetype"] = rlt
        lw = blk.add_lwpolyline(pts, dxfattribs=dxfattribs)
        wu = new_uid()
        set_entity_xdata(lw, build_ld_app_tags("1", wu, "WIRE", extra))
        self.recompute_all_bridges_ordered(layout_name)
        self.refresh_com_wire_markers(layout_name)
        if str(extra.get(WIRE_XDATA_SHOW_IN_ARROW) or "") == "1":
            self.sync_wire_arrow_dxf(layout_name, wu)
        return wu
