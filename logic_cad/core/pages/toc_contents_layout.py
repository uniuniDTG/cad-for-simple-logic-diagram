"""TOC contents grid: bbox from ``LD_CONTENTS_AREA`` and column/row counts."""

from __future__ import annotations

from logic_cad.core.model.constants import LAYER_CONTENTS_AREA


def contents_area_bbox_mm(blk) -> tuple[float, float, float, float] | None:
    """First closed ``LWPOLYLINE`` on ``LAYER_CONTENTS_AREA`` → ``(minx, miny, maxx, maxy)``."""
    for e in blk:
        if e.dxftype() != "LWPOLYLINE":
            continue
        if str(e.dxf.layer) != LAYER_CONTENTS_AREA:
            continue
        try:
            if not e.closed:
                continue
        except Exception:
            continue
        try:
            pts = [p[:2] for p in e.get_points("xyb")]
        except Exception:
            continue
        if len(pts) < 3:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))
    return None


def toc_grid_cols_and_data_rows(
    minx: float,
    miny: float,
    maxx: float,
    maxy: float,
    cell_w: float,
    cell_h: float,
    header_h: float,
    col_gap: float = 0.0,
    row_gap: float = 0.0,
) -> tuple[int, int]:
    """Header row + data grid: ``cols``, ``rows_data`` (cells below the header)."""
    area_w = maxx - minx
    area_h = maxy - miny
    if area_w <= 0 or area_h <= 0:
        return (1, 0)
    step_x = cell_w + col_gap
    step_y = cell_h + row_gap
    if step_x <= 0 or step_y <= 0:
        return (1, 0)
    cols = max(1, int(area_w // step_x))
    avail = area_h - header_h - row_gap
    if avail <= 0:
        return (cols, 0)
    rows_data = int(avail // step_y)
    return (cols, max(0, rows_data))
