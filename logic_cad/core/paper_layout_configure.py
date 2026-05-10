"""Paper layout sizing and CAD viewport normalization (A4 landscape, margins, decoys).

Separated from ``layout_service`` so ``dxf_repository`` can call
:func:`configure_paper_layout_a4_landscape` at load without importing the service layer
(which itself depends on ``dxf_repository`` helpers).
"""

from __future__ import annotations

from ezdxf.document import Drawing
from ezdxf.entities import DXFEntity
from ezdxf.layouts import Layout

from logic_cad.core.debug.debug_symlib import symlib_log
from logic_cad.core.model.constants import (
    A4_LANDSCAPE_HEIGHT_MM,
    A4_LANDSCAPE_PRINTABLE_80_H_MM,
    A4_LANDSCAPE_PRINTABLE_80_W_MM,
    A4_LANDSCAPE_WIDTH_MM,
    LAYER_VIEWPORTS,
)
from logic_cad.core.paper_layout_access import paper_layout_block


def _lw_closed_rect_width_height_mm(entity: DXFEntity) -> tuple[float, float] | None:
    """Axis-aligned closed LWPOLYLINE with 4 corners → (width, height), else ``None``.

    Args:
        entity: Any DXF entity; non-``LWPOLYLINE`` types return ``None`` immediately.

    Returns:
        Width and height in drawing units when the entity is a closed rectangle, else
        ``None``.
    """
    if entity.dxftype() != "LWPOLYLINE":
        return None
    try:
        if not entity.closed:
            return None
    except Exception:
        return None
    try:
        pts = [p[:2] for p in entity.get_points("xyb")]
    except Exception:
        return None
    if len(pts) not in (4, 5):
        return None
    if len(pts) == 5 and (pts[0][0] != pts[4][0] or pts[0][1] != pts[4][1]):
        return None
    if len(pts) == 5:
        pts = pts[:4]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    w = max(xs) - min(xs)
    h = max(ys) - min(ys)
    return (w, h)


def _matches_printable_80_rect(w: float, h: float, tol: float = 0.75) -> bool:
    """Return whether *w*×*h* matches the default 80% A4 landscape printable rectangle.

    Args:
        w: Rectangle width (mm).
        h: Rectangle height (mm).
        tol: Absolute tolerance for comparison.

    Returns:
        ``True`` when dimensions match (including a 90° swap).
    """
    ew, eh = A4_LANDSCAPE_PRINTABLE_80_W_MM, A4_LANDSCAPE_PRINTABLE_80_H_MM
    return (abs(w - ew) < tol and abs(h - eh) < tol) or (abs(w - eh) < tol and abs(h - ew) < tol)


def _ensure_viewports_layer_off(doc: Drawing) -> None:
    """Ensure the CAD ``VIEWPORTS`` layer exists and is off (hide viewport frames)."""
    if LAYER_VIEWPORTS not in doc.layers:
        doc.layers.add(LAYER_VIEWPORTS)
    doc.layers.get(LAYER_VIEWPORTS).off()


def _ensure_single_main_viewport_hidden(doc: Drawing, layout: Layout) -> None:
    """Keep exactly one main paper VIEWPORT on ``VIEWPORTS`` (layer off)."""
    _ensure_viewports_layer_off(doc)
    main = layout.main_viewport()
    if main is None:
        for vp in list(layout.viewports()):
            try:
                layout.delete_entity(vp)
            except Exception as ex:
                symlib_log(f"paper_layout: drop orphan viewport {vp}: {ex}")
        try:
            layout.add_new_main_viewport()
        except Exception as ex:
            symlib_log(f"paper_layout: add_new_main_viewport failed: {ex}")
            return
    else:
        for vp in list(layout.viewports()):
            if vp.dxf.handle == main.dxf.handle:
                continue
            try:
                layout.delete_entity(vp)
            except Exception as ex:
                symlib_log(f"paper_layout: could not delete extra viewport {vp}: {ex}")
    main = layout.main_viewport()
    if main is None:
        return
    main.dxf.layer = LAYER_VIEWPORTS
    try:
        layout.set_current_viewport_handle(main.dxf.handle)
    except Exception as ex:
        symlib_log(f"paper_layout: set_current_viewport_handle failed: {ex}")


def _remove_layer0_printable_decoys(layout: Layout) -> None:
    """Drop layer-'0' closed rects matching default printable-area decoys (BricsCAD noise)."""
    blk = paper_layout_block(layout.doc, layout.name)
    if blk is None:
        return
    for e in list(blk):
        if str(e.dxf.layer) != "0":
            continue
        wh = _lw_closed_rect_width_height_mm(e)
        if wh is None:
            continue
        w, h = wh
        if _matches_printable_80_rect(w, h):
            try:
                layout.delete_entity(e)
            except Exception as ex:
                symlib_log(f"paper_layout: could not delete layer-0 decoy rect {e}: {ex}")


def configure_paper_layout_a4_landscape(doc: Drawing, layout_name: str) -> None:
    """Set plot paper to A4 landscape, normalize viewport, and clear layer-0 decoy rects.

    Keeps a single main paper-space VIEWPORT for CAD compatibility, moves it to
    ``VIEWPORTS``, and turns that layer off so the viewport frame is not visible. Logic
    CAD still uses ``LD_VPORT`` LWPOLYLINE for its own page/view semantics.

    Args:
        doc: Active drawing.
        layout_name: Paper layout tab name (ignored when it resolves to model space).
    """
    layout = doc.layouts.get(layout_name)
    if layout is None or layout.is_modelspace:
        return
    dxf = layout.dxf_layout.dxf
    dxf.paper_width = A4_LANDSCAPE_WIDTH_MM
    dxf.paper_height = A4_LANDSCAPE_HEIGHT_MM
    dxf.paper_size = "A4"
    dxf.left_margin = 0
    dxf.right_margin = 0
    dxf.top_margin = 0
    dxf.bottom_margin = 0
    dxf.plot_origin_x_offset = 0
    dxf.plot_origin_y_offset = 0
    dxf.plot_paper_units = 1

    _ensure_single_main_viewport_hidden(doc, layout)

    try:
        layout.plot_viewport_borders(False)
    except Exception as ex:
        symlib_log(f"paper_layout: plot_viewport_borders(False) failed: {ex}")
    _remove_layer0_printable_decoys(layout)

    layout.reset_paper_limits()
    layout.reset_extents()
