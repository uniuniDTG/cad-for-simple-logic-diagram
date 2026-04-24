"""User-drawn sketch entities on paper layout blocks."""

from __future__ import annotations

import math
from typing import Any

from ezdxf import revcloud
from ezdxf.document import Drawing

from logic_cad.core.geometry.polyline_simplify import douglas_peucker, douglas_peucker_closed
from logic_cad.core.model.cloud_guide_xdata import (
    build_cloud_pitch_xdata_extra,
    parse_cloud_guide_vertices,
    parse_cloud_segment_mm,
    strip_cloud_pitch_keys,
)
from logic_cad.core.model.constants import (
    ENTITY_TYPE_USER_CIRCLE,
    ENTITY_TYPE_USER_CLOUD,
    ENTITY_TYPE_USER_LINE,
    ENTITY_TYPE_USER_TEXT,
    LAYER_ANNOTATION,
    USER_CLOUD_BULGE,
    USER_CLOUD_CALLIGRAPHY,
    USER_CLOUD_DEFAULT_SEGMENT_MM,
    LINETYPE_CONTINUOUS,
)
from logic_cad.core.model.user_sketch_layers import (
    user_sketch_entity_linetype_for_display,
    user_sketch_circle_layer_for_linetype,
    user_sketch_cloud_layer_for_linetype,
    user_sketch_display_linetype_for_entity,
    user_sketch_line_layer_for_linetype,
)
from logic_cad.core.pages.page_order import list_paper_layout_names_sorted
from logic_cad.core.routing import snap_to_grid
from logic_cad.core.undo.history import destroy_entity, find_entity_by_uid
from logic_cad.core.symbol_clipboard import UserSketchCopyRecord
from logic_cad.core.model.xdata import (
    build_ld_app_tags,
    get_type,
    new_uid,
    read_ld_app_dict,
    set_entity_xdata,
)


def _distance_sq(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Return squared distance between 2D points."""
    dx = float(a[0]) - float(b[0])
    dy = float(a[1]) - float(b[1])
    return dx * dx + dy * dy


def _open_cloud_points(
    vertices: list[tuple[float, float]],
    segment_length: float,
    bulge: float,
    *,
    calligraphy: bool,
) -> list[tuple[float, float, float, float, float]]:
    """Build open revision-cloud points by cutting the closing edge.

    Args:
        vertices: User path vertices. The last vertex is the intended open-path end.
        segment_length: Approximate cloud segment size in drawing units.
        calligraphy: When True, use calligraphy width taper.

    Returns:
        Open-path ``(x, y, start_width, end_width, bulge)`` points without
        the implicit closing segment.
    """
    src = [(float(x), float(y)) for x, y in vertices]
    if len(src) < 2:
        raise ValueError("開いた雲マークは2点以上の頂点が必要です。")
    if len(src) == 2:
        (x0, y0), (x1, y1) = src
        dx = x1 - x0
        dy = y1 - y0
        d = math.hypot(dx, dy)
        if d < 1e-9:
            raise ValueError("開いた雲マークの2点が同一点です。")
        # revcloud.points() needs >=3 vertices; add a short perpendicular helper edge
        # and cut at the actual end vertex so only the first edge remains visible.
        nx, ny = -dy / d, dx / d
        src = [src[0], src[1], (x1 + nx * segment_length, y1 + ny * segment_length)]
    end_width = 0.1 * segment_length if calligraphy else 0.0
    all_pts = [
        (
            float(row[0]),
            float(row[1]),
            float(row[2]) if len(row) > 2 else 0.0,
            float(row[3]) if len(row) > 3 else 0.0,
            float(row[4]) if len(row) > 4 else 0.0,
        )
        for row in revcloud.points(
            vertices=src,
            segment_length=segment_length,
            bulge=float(bulge),
            end_width=end_width,
        )
    ]
    end_vertex = (float(vertices[-1][0]), float(vertices[-1][1]))
    cut_idx = min(
        range(len(all_pts)),
        key=lambda i: _distance_sq((all_pts[i][0], all_pts[i][1]), end_vertex),
    )
    truncated = list(all_pts[: cut_idx + 1])
    if not truncated:
        raise ValueError("開いた雲マークの点列を生成できませんでした。")
    x_end, y_end, s_end, e_end, _ = truncated[-1]
    truncated[-1] = (x_end, y_end, s_end, e_end, 0.0)
    return truncated


def _signed_area2(vertices: list[tuple[float, float]]) -> float:
    """Return doubled signed area for the implied closed polygon."""
    if len(vertices) < 3:
        return 0.0
    area2 = 0.0
    count = len(vertices)
    for i in range(count):
        x0, y0 = vertices[i]
        x1, y1 = vertices[(i + 1) % count]
        area2 += x0 * y1 - x1 * y0
    return area2


def _open_cloud_bulge(vertices: list[tuple[float, float]]) -> float:
    """Choose bulge sign from polyline winding (open and closed clouds).

    Positive-area (CCW) paths use positive bulge and CW paths use negative
    bulge. This keeps revision-cloud arc orientation consistent regardless
    of whether the user traces the boundary clockwise or counter-clockwise.
    """
    area2 = _signed_area2(vertices)
    if area2 > 0.0:
        return abs(USER_CLOUD_BULGE)
    return -abs(USER_CLOUD_BULGE)


def _revcloud_rows_to_xyb(rows: list) -> list[tuple[float, float, float]]:
    """Convert revcloud / open-cloud rows to LWPOLYLINE ``xyb`` tuples.

    Args:
        rows: Rows from ``revcloud.points`` / ``_open_cloud_points`` (``xyseb``-style).

    Returns:
        ``(x, y, bulge)`` tuples for :meth:`ezdxf.entities.LWPolyline.set_points` with ``format='xyb'``.
    """
    out: list[tuple[float, float, float]] = []
    for row in rows:
        x = float(row[0])
        y = float(row[1])
        b = float(row[4]) if len(row) > 4 else 0.0
        out.append((x, y, b))
    return out


def _build_cloud_lwpolyline_xyb(
    vertices: list[tuple[float, float]],
    segment_length: float,
    *,
    is_closed: bool,
) -> list[tuple[float, float, float]]:
    """Build USER_CLOUD LWPOLYLINE vertices (``xyb``) from guide outline and pitch.

    Args:
        vertices: Guide polyline (same semantics as :meth:`UserGeometryService.add_cloud`).
        segment_length: ``revcloud.points`` segment length (mm / drawing units).
        is_closed: Closed revision cloud vs open path.

    Returns:
        Polyline vertices in ``xyb`` form.

    Raises:
        ValueError: Propagated from ``revcloud`` / open-cloud helpers when the outline is invalid.
    """
    seg_len = max(1e-3, float(segment_length))
    if is_closed:
        pts = revcloud.points(
            vertices=[(float(x), float(y)) for x, y in vertices],
            segment_length=seg_len,
            bulge=_open_cloud_bulge(vertices),
            end_width=0.1 * seg_len if USER_CLOUD_CALLIGRAPHY else 0.0,
        )
        return _revcloud_rows_to_xyb(pts)
    truncated = _open_cloud_points(
        vertices,
        seg_len,
        _open_cloud_bulge(vertices),
        calligraphy=USER_CLOUD_CALLIGRAPHY,
    )
    return _revcloud_rows_to_xyb(truncated)


def _lwpolyline_vertex_chain_xy(entity) -> list[tuple[float, float]]:
    """Return LW polyline vertices as plain ``(x, y)`` (legacy guide inference input).

    Args:
        entity: An ``LWPOLYLINE`` entity.

    Returns:
        Ordered vertex chain.
    """
    return [
        (float(r[0]), float(r[1]))
        for r in entity.get_points("xyb")
    ]


def _infer_guide_vertices_legacy(entity, pitch_mm: float) -> list[tuple[float, float]] | None:
    """Approximate a coarse guide outline from a tessellated revision cloud (no stored guides).

    Args:
        entity: Tessellated USER_CLOUD ``LWPOLYLINE``.
        pitch_mm: Target pitch used to choose simplification tolerance.

    Returns:
        Simplified guide vertices, or None if inference fails.
    """
    chain = _lwpolyline_vertex_chain_xy(entity)
    if len(chain) < 2:
        return None
    closed = bool(entity.closed)
    eps0 = max(2.0, float(pitch_mm) * 0.65)
    min_n = 3 if closed else 2
    for mult in (1.0, 0.55, 0.32, 0.18, 0.1):
        eps = eps0 * mult
        if closed:
            simp = douglas_peucker_closed(chain, eps)
        else:
            simp = douglas_peucker(chain, eps)
        if len(simp) >= min_n:
            return simp
    # Last resort: uniform decimation so revcloud still has a valid guide.
    step = max(1, len(chain) // max(min_n, 8))
    coarse = [chain[i] for i in range(0, len(chain), step)]
    if closed and len(coarse) < 3 and len(chain) >= 3:
        coarse = [chain[0], chain[len(chain) // 3], chain[2 * len(chain) // 3]]
    if len(coarse) >= min_n:
        return coarse
    return None


def _apply_cloud_xdata(
    entity,
    *,
    segment_length: float,
    guide_vertices: list[tuple[float, float]],
) -> None:
    """Write ``cloud_seg`` and chunked ``cloud_path_*`` while preserving other LD_APP keys.

    Args:
        entity: USER_CLOUD entity whose XDATA will be replaced for pitch fields only.
        segment_length: Stored pitch value.
        guide_vertices: Stored guide outline for future regeneration.
    """
    d = read_ld_app_dict(entity)
    ver = str(d.get("ver", "1"))
    uid = str(d.get("uid", ""))
    et = str(d.get("type", ENTITY_TYPE_USER_CLOUD))
    other = {k: v for k, v in d.items() if k not in ("ver", "uid", "type")}
    other = strip_cloud_pitch_keys(other)
    cloud_extra = build_cloud_pitch_xdata_extra(segment_length, guide_vertices)
    merged = {**other, **cloud_extra}
    set_entity_xdata(entity, build_ld_app_tags(ver, uid, et, merged))


class UserGeometryService:
    def __init__(self, doc: Drawing) -> None:
        self.doc = doc

    def delete_all_user_clouds_all_pages(self) -> int:
        """Delete all revision-cloud (USER_CLOUD) polylines on every paper layout.

        Collects matching entities first, then removes them so block iteration stays stable.

        Returns:
            The number of USER_CLOUD entities removed.
        """
        to_remove: list[Any] = []
        for layout_name in list_paper_layout_names_sorted(self.doc):
            layout = self.doc.layouts.get(layout_name)
            if layout is None or layout.is_modelspace:
                continue
            blk = self.doc.blocks.get(layout.block_record_name)
            for e in blk:
                if e.dxftype() == "LWPOLYLINE" and get_type(e) == ENTITY_TYPE_USER_CLOUD:
                    to_remove.append(e)
        for e in to_remove:
            destroy_entity(self.doc, e)
        return len(to_remove)

    def _layout_block(self, layout_name: str):
        layout = self.doc.layouts.get(layout_name)
        return self.doc.blocks.get(layout.block_record_name)

    def add_line(
        self,
        layout_name: str,
        start: tuple[float, float],
        end: tuple[float, float],
        linetype: str,
    ) -> str:
        blk = self._layout_block(layout_name)
        ulayer = user_sketch_line_layer_for_linetype(linetype)
        e = blk.add_line(
            start,
            end,
            dxfattribs={"layer": ulayer},
        )
        e.dxf.linetype = user_sketch_entity_linetype_for_display(linetype)
        uid = new_uid()
        set_entity_xdata(e, build_ld_app_tags("1", uid, ENTITY_TYPE_USER_LINE, None))
        return uid

    def add_circle(
        self,
        layout_name: str,
        center: tuple[float, float],
        radius: float,
        linetype: str,
    ) -> str:
        blk = self._layout_block(layout_name)
        ulayer = user_sketch_circle_layer_for_linetype(linetype)
        e = blk.add_circle(
            center=center,
            radius=float(radius),
            dxfattribs={"layer": ulayer},
        )
        e.dxf.linetype = user_sketch_entity_linetype_for_display(linetype)
        uid = new_uid()
        set_entity_xdata(e, build_ld_app_tags("1", uid, ENTITY_TYPE_USER_CIRCLE, None))
        return uid

    def add_text(
        self,
        layout_name: str,
        insert: tuple[float, float],
        text: str,
        height: float,
    ) -> str:
        blk = self._layout_block(layout_name)
        e = blk.add_text(
            text,
            height=float(height),
            rotation=0.0,
            dxfattribs={"layer": LAYER_ANNOTATION, "linetype": LINETYPE_CONTINUOUS},
        )
        e.dxf.insert = insert
        uid = new_uid()
        set_entity_xdata(e, build_ld_app_tags("1", uid, ENTITY_TYPE_USER_TEXT, None))
        return uid

    def add_cloud(
        self,
        layout_name: str,
        vertices: list[tuple[float, float]],
        segment_length: float,
        linetype: str,
        *,
        is_closed: bool,
    ) -> str:
        if len(vertices) < 2:
            raise ValueError("雲マークは2点以上の頂点が必要です。")
        if is_closed and len(vertices) < 3:
            raise ValueError("閉じた雲マークは3点以上の頂点が必要です。")
        blk = self._layout_block(layout_name)
        ulayer = user_sketch_cloud_layer_for_linetype(linetype)
        seg_len = max(1e-3, float(segment_length))
        if is_closed:
            pts = revcloud.points(
                vertices=[(float(x), float(y)) for x, y in vertices],
                segment_length=seg_len,
                bulge=_open_cloud_bulge(vertices),
                end_width=0.1 * seg_len if USER_CLOUD_CALLIGRAPHY else 0.0,
            )
            e = blk.add_lwpolyline(
                pts,
                format="xyseb",
                close=True,
                dxfattribs={"layer": ulayer},
            )
        else:
            pts = _open_cloud_points(
                vertices,
                seg_len,
                _open_cloud_bulge(vertices),
                calligraphy=USER_CLOUD_CALLIGRAPHY,
            )
            e = blk.add_lwpolyline(
                pts,
                format="xyseb",
                close=False,
                dxfattribs={"layer": ulayer},
            )
        e.dxf.linetype = user_sketch_entity_linetype_for_display(linetype)
        uid = new_uid()
        guide = [(float(x), float(y)) for x, y in vertices]
        cloud_extra = build_cloud_pitch_xdata_extra(seg_len, guide)
        set_entity_xdata(e, build_ld_app_tags("1", uid, ENTITY_TYPE_USER_CLOUD, cloud_extra))
        return uid

    def set_user_line_or_circle_linetype(self, layout_name: str, uid: str, linetype: str) -> bool:
        _ = layout_name
        e = find_entity_by_uid(self.doc, uid)
        if e is None:
            return False
        t = get_type(e)
        if t == ENTITY_TYPE_USER_LINE and e.dxftype() == "LINE":
            lt = str(linetype or LINETYPE_CONTINUOUS).strip() or LINETYPE_CONTINUOUS
            e.dxf.layer = user_sketch_line_layer_for_linetype(lt)
            e.dxf.linetype = user_sketch_entity_linetype_for_display(lt)
            return True
        if t == ENTITY_TYPE_USER_CIRCLE and e.dxftype() == "CIRCLE":
            lt = str(linetype or LINETYPE_CONTINUOUS).strip() or LINETYPE_CONTINUOUS
            e.dxf.layer = user_sketch_circle_layer_for_linetype(lt)
            e.dxf.linetype = user_sketch_entity_linetype_for_display(lt)
            return True
        if t == ENTITY_TYPE_USER_CLOUD and e.dxftype() == "LWPOLYLINE":
            lt = str(linetype or LINETYPE_CONTINUOUS).strip() or LINETYPE_CONTINUOUS
            e.dxf.layer = user_sketch_cloud_layer_for_linetype(lt)
            e.dxf.linetype = user_sketch_entity_linetype_for_display(lt)
            return True
        return False

    def set_user_text_props(self, layout_name: str, uid: str, text: str, height_mm: float) -> bool:
        _ = layout_name
        e = find_entity_by_uid(self.doc, uid)
        if e is None or e.dxftype() != "TEXT":
            return False
        if get_type(e) != ENTITY_TYPE_USER_TEXT:
            return False
        e.dxf.text = text
        e.dxf.height = max(0.25, float(height_mm))
        return True

    def set_user_line_geometry(
        self, uid: str, start: tuple[float, float], end: tuple[float, float]
    ) -> bool:
        e = find_entity_by_uid(self.doc, uid)
        if e is None or e.dxftype() != "LINE":
            return False
        if get_type(e) != ENTITY_TYPE_USER_LINE:
            return False
        e.dxf.start = (float(start[0]), float(start[1]), 0.0)
        e.dxf.end = (float(end[0]), float(end[1]), 0.0)
        return True

    def set_user_circle_geometry(
        self, uid: str, center: tuple[float, float], radius: float
    ) -> bool:
        e = find_entity_by_uid(self.doc, uid)
        if e is None or e.dxftype() != "CIRCLE":
            return False
        if get_type(e) != ENTITY_TYPE_USER_CIRCLE:
            return False
        e.dxf.center = (float(center[0]), float(center[1]), 0.0)
        e.dxf.radius = max(1e-9, float(radius))
        return True

    def set_user_text_insert(self, uid: str, insert: tuple[float, float]) -> bool:
        e = find_entity_by_uid(self.doc, uid)
        if e is None or e.dxftype() != "TEXT":
            return False
        if get_type(e) != ENTITY_TYPE_USER_TEXT:
            return False
        e.dxf.insert = (float(insert[0]), float(insert[1]), 0.0)
        return True

    def set_user_cloud_geometry(
        self,
        uid: str,
        points_xyb: list[tuple[float, float, float]],
        *,
        is_closed: bool,
    ) -> bool:
        e = find_entity_by_uid(self.doc, uid)
        if e is None or e.dxftype() != "LWPOLYLINE":
            return False
        if get_type(e) != ENTITY_TYPE_USER_CLOUD:
            return False
        if len(points_xyb) < 2:
            return False
        xd_before = read_ld_app_dict(e)
        guides = parse_cloud_guide_vertices(xd_before)
        seg_mm = parse_cloud_segment_mm(xd_before)
        old_rows = list(e.get_points("xyb"))
        ox = float(old_rows[0][0])
        oy = float(old_rows[0][1])
        e.set_points(
            [(float(x), float(y), float(b)) for x, y, b in points_xyb],
            format="xyb",
        )
        e.closed = bool(is_closed)
        if not guides:
            return True
        nx = float(points_xyb[0][0])
        ny = float(points_xyb[0][1])
        dx, dy = nx - ox, ny - oy
        tg = [(gx + dx, gy + dy) for gx, gy in guides]
        seg = seg_mm if seg_mm is not None else float(USER_CLOUD_DEFAULT_SEGMENT_MM)
        _apply_cloud_xdata(e, segment_length=seg, guide_vertices=tg)
        return True

    def set_user_cloud_pitch_mm(self, uid: str, pitch_mm: float) -> bool:
        """Regenerate USER_CLOUD with a new revcloud segment length (mm).

        When LD_APP guide vertices are missing (legacy), infers a coarse guide from the
        current tessellated outline before regenerating.

        Args:
            uid: USER_CLOUD entity UID.
            pitch_mm: Target ``segment_length`` (clamped to at least 1e-3).

        Returns:
            True if the LWPOLYLINE and pitch XDATA were updated.
        """
        e = find_entity_by_uid(self.doc, uid)
        if e is None or e.dxftype() != "LWPOLYLINE":
            return False
        if get_type(e) != ENTITY_TYPE_USER_CLOUD:
            return False
        pitch = max(1e-3, float(pitch_mm))
        xd = read_ld_app_dict(e)
        guides = parse_cloud_guide_vertices(xd)
        is_closed = bool(e.closed)
        if guides is None:
            guides = _infer_guide_vertices_legacy(e, pitch)
        if guides is None:
            return False
        if is_closed and len(guides) < 3:
            return False
        if not is_closed and len(guides) < 2:
            return False
        try:
            new_xyb = _build_cloud_lwpolyline_xyb(guides, pitch, is_closed=is_closed)
        except ValueError:
            return False
        e.set_points(new_xyb, format="xyb")
        e.closed = is_closed
        _apply_cloud_xdata(e, segment_length=pitch, guide_vertices=guides)
        return True

    def get_user_cloud_pitch_display_mm(self, uid: str) -> float:
        """Return stored pitch for the property panel, or the default when unknown.

        Args:
            uid: USER_CLOUD entity UID.

        Returns:
            Stored ``cloud_seg`` value, or ``USER_CLOUD_DEFAULT_SEGMENT_MM`` when absent.
        """
        e = find_entity_by_uid(self.doc, uid)
        if e is None:
            return float(USER_CLOUD_DEFAULT_SEGMENT_MM)
        seg = parse_cloud_segment_mm(read_ld_app_dict(e))
        if seg is not None:
            return float(seg)
        return float(USER_CLOUD_DEFAULT_SEGMENT_MM)

    def clipboard_record_for_uid(self, uid: str) -> UserSketchCopyRecord | None:
        e = find_entity_by_uid(self.doc, uid)
        if e is None:
            return None
        t = get_type(e)
        if t == ENTITY_TYPE_USER_LINE and e.dxftype() == "LINE":
            lt = user_sketch_display_linetype_for_entity(e)
            return UserSketchCopyRecord(
                entity_type=t,
                linetype=lt or LINETYPE_CONTINUOUS,
                line_start=(float(e.dxf.start.x), float(e.dxf.start.y)),
                line_end=(float(e.dxf.end.x), float(e.dxf.end.y)),
            )
        if t == ENTITY_TYPE_USER_CIRCLE and e.dxftype() == "CIRCLE":
            lt = user_sketch_display_linetype_for_entity(e)
            cx, cy = float(e.dxf.center.x), float(e.dxf.center.y)
            return UserSketchCopyRecord(
                entity_type=t,
                linetype=lt or LINETYPE_CONTINUOUS,
                circle_center=(cx, cy),
                circle_radius=float(e.dxf.radius),
            )
        if t == ENTITY_TYPE_USER_TEXT and e.dxftype() == "TEXT":
            ix, iy = float(e.dxf.insert.x), float(e.dxf.insert.y)
            h = float(getattr(e.dxf, "height", 4.0) or 4.0)
            return UserSketchCopyRecord(
                entity_type=t,
                text_insert=(ix, iy),
                text=str(e.dxf.text or ""),
                text_height_mm=max(0.25, h),
            )
        if t == ENTITY_TYPE_USER_CLOUD and e.dxftype() == "LWPOLYLINE":
            lt = user_sketch_display_linetype_for_entity(e)
            points_xyb = [
                (float(row[0]), float(row[1]), float(row[2]) if len(row) > 2 else 0.0)
                for row in e.get_points("xyb")
            ]
            xd = read_ld_app_dict(e)
            seg = parse_cloud_segment_mm(xd)
            gv = parse_cloud_guide_vertices(xd)
            return UserSketchCopyRecord(
                entity_type=t,
                linetype=lt or LINETYPE_CONTINUOUS,
                cloud_points_xyb=points_xyb,
                cloud_is_closed=bool(e.closed),
                cloud_pitch_mm=seg,
                cloud_guide_vertices=list(gv) if gv is not None else None,
            )
        return None

    def paste_sketch_record(
        self, layout_name: str, rec: UserSketchCopyRecord, dx: float, dy: float
    ) -> str:
        if rec.entity_type == ENTITY_TYPE_USER_LINE and rec.line_start and rec.line_end:
            x0, y0 = snap_to_grid(rec.line_start[0] + dx, rec.line_start[1] + dy)
            x1, y1 = snap_to_grid(rec.line_end[0] + dx, rec.line_end[1] + dy)
            return self.add_line(layout_name, (x0, y0), (x1, y1), rec.linetype)
        if rec.entity_type == ENTITY_TYPE_USER_CIRCLE and rec.circle_center is not None:
            cx, cy = snap_to_grid(rec.circle_center[0] + dx, rec.circle_center[1] + dy)
            r = max(1e-9, float(rec.circle_radius))
            return self.add_circle(layout_name, (cx, cy), r, rec.linetype)
        if rec.entity_type == ENTITY_TYPE_USER_TEXT:
            ix, iy = snap_to_grid(rec.text_insert[0] + dx, rec.text_insert[1] + dy)
            return self.add_text(layout_name, (ix, iy), rec.text, rec.text_height_mm)
        if rec.entity_type == ENTITY_TYPE_USER_CLOUD and rec.cloud_points_xyb:
            x0, y0, _b0 = rec.cloud_points_xyb[0]
            sx0, sy0 = snap_to_grid(x0 + dx, y0 + dy)
            shift_x = sx0 - x0
            shift_y = sy0 - y0
            shifted_xyb = [
                (float(x + shift_x), float(y + shift_y), float(b))
                for x, y, b in rec.cloud_points_xyb
            ]
            blk = self._layout_block(layout_name)
            ulayer = user_sketch_cloud_layer_for_linetype(rec.linetype)
            e = blk.add_lwpolyline(
                shifted_xyb,
                format="xyb",
                close=bool(rec.cloud_is_closed),
                dxfattribs={"layer": ulayer},
            )
            e.dxf.linetype = user_sketch_entity_linetype_for_display(rec.linetype)
            uid = new_uid()
            gv = rec.cloud_guide_vertices
            pitch = rec.cloud_pitch_mm
            if gv is not None and len(gv) >= 2 and pitch is not None:
                shifted_guides = [(float(x + shift_x), float(y + shift_y)) for x, y in gv]
                cloud_extra = build_cloud_pitch_xdata_extra(float(pitch), shifted_guides)
                set_entity_xdata(e, build_ld_app_tags("1", uid, ENTITY_TYPE_USER_CLOUD, cloud_extra))
            else:
                set_entity_xdata(e, build_ld_app_tags("1", uid, ENTITY_TYPE_USER_CLOUD, None))
            return uid
        raise ValueError(f"未対応のユーザー下絵クリップボード種別です: {rec.entity_type!r}")
