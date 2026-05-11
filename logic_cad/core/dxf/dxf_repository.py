"""Low-level ezdxf document access."""

from __future__ import annotations

from pathlib import Path

import ezdxf
from ezdxf import recover
from ezdxf.document import Drawing
from ezdxf.tools.standards import setup_linetypes

from logic_cad.core.debug.debug_log import logic_cad_log
from logic_cad.core.model.constants import (
    ALL_LAYERS,
    LAYER_CONTENTS_AREA,
    LAYER_CONTENTS_FRAME,
    LAYER_CONTENTS_TEXT,
    LAYER_DOC_META,
    LAYER_VPORT,
    LAYER_USER_ARC_CENTER,
    LAYER_USER_ARC_CONTINUOUS,
    LAYER_USER_ARC_DASHED,
    LAYER_USER_CIRCLE_CENTER,
    LAYER_USER_CIRCLE_CONTINUOUS,
    LAYER_USER_CIRCLE_DASHED,
    LAYER_USER_CLOUD_CENTER,
    LAYER_USER_CLOUD_CONTINUOUS,
    LAYER_USER_CLOUD_DASHED,
    LAYER_USER_LINE_CENTER,
    LAYER_USER_LINE_CONTINUOUS,
    LAYER_USER_LINE_DASHED,
    LAYER_WIRE_COM,
    LAYER_WIRE_COM_SEGMENT,
    LAYER_WIRE_COM_MARKER,
    LAYER_WIRE_LOGIC,
    LAYER_WIRE_VALUE,
    LINETYPE_CENTER,
    LINETYPE_CENTER_GAP1_MM,
    LINETYPE_CENTER_GAP2_MM,
    LINETYPE_CENTER_LONG_DASH_MM,
    LINETYPE_CENTER_SHORT_DASH_MM,
    LINETYPE_CONTINUOUS,
    LINETYPE_DASH,
    LINETYPE_DASHED_DASH_MM,
    LINETYPE_DASHED_GAP_MM,
    LINETYPE_LOGIC,
    LINETYPE_VALUE,
)
from logic_cad.core.model.document_meta import apply_document_meta_stamp, ensure_regapp_document_meta
from logic_cad.core.model.xdata import ensure_regapp
from logic_cad.core.dxf.attrib_geometry_sync import (
    AttribGeomSnapshot,
    persist_all_paper_layout_attrib_inserts_as_wcs_for_save,
    restore_paper_layout_insert_attrib_geometry,
    revert_all_paper_layout_attrib_inserts_from_wcs_after_load,
    snapshot_paper_layout_insert_attrib_geometry,
)
from logic_cad.core.pages.page_order import apply_paper_layout_taborder_by_name
from logic_cad.core.paper_layout_configure import configure_paper_layout_a4_landscape
from logic_cad.core.paper_layout_strip import strip_ld_contents_area_all_paper_layouts

# USER_LINE / USER_CIRCLE / USER_CLOUD / USER_ARC: layer default linetype matches sketch style (entities use ByLayer).
_USER_SKETCH_LAYER_DEFAULT_LINETYPE: tuple[tuple[str, str], ...] = (
    (LAYER_USER_LINE_CONTINUOUS, LINETYPE_CONTINUOUS),
    (LAYER_USER_LINE_CENTER, LINETYPE_CENTER),
    (LAYER_USER_LINE_DASHED, LINETYPE_DASH),
    (LAYER_USER_CIRCLE_CONTINUOUS, LINETYPE_CONTINUOUS),
    (LAYER_USER_CIRCLE_CENTER, LINETYPE_CENTER),
    (LAYER_USER_CIRCLE_DASHED, LINETYPE_DASH),
    (LAYER_USER_CLOUD_CONTINUOUS, LINETYPE_CONTINUOUS),
    (LAYER_USER_CLOUD_CENTER, LINETYPE_CENTER),
    (LAYER_USER_CLOUD_DASHED, LINETYPE_DASH),
    (LAYER_USER_ARC_CONTINUOUS, LINETYPE_CONTINUOUS),
    (LAYER_USER_ARC_CENTER, LINETYPE_CENTER),
    (LAYER_USER_ARC_DASHED, LINETYPE_DASH),
)


def _default_aci_for_new_standard_layer(layer_name: str) -> int:
    """Return default ACI when *layer_name* is first added to *doc.layers*.

    Previously ``ensure_standard_layers`` overwrote colors on every load; defaults
    now apply only at creation time so user layer colors persist in the DXF.

    Args:
        layer_name: Standard layer constant (``ALL_LAYERS``).

    Returns:
        ACI color index: ``7`` for most standard layers (logic, user sketch, frame
        text, TOC, annotation). ``8`` only for viewport guide, document-meta anchor,
        and contents-area guide layers (helper / off-plot style).
    """
    if layer_name in (
        LAYER_VPORT,
        LAYER_DOC_META,
        LAYER_CONTENTS_AREA,
    ):
        return 8
    return 7

# ezdxf / AutoCAD: 4 = millimeters (drawing unit matches Logic CAD geometry in mm).
_INSUNITS_MM = 4


def ensure_drawing_units_mm(doc: Drawing) -> None:
    """Declare drawing insertion units as millimeters (BricsCAD status bar, etc.)."""
    doc.units = _INSUNITS_MM


def load_dxf_with_recover(path: str | Path, *, errors: str = "ignore") -> Drawing:
    """Load DXF with fast path first, recover fallback second.

    Args:
        path: DXF file path.
        errors: Recover decode policy passed to ``recover.readfile``.

    Returns:
        Loaded drawing.

    Raises:
        ezdxf.DXFError: If both fast path and recover path fail.
        IOError: File I/O failure.
        UnicodeDecodeError: Recover decode error when ``errors='strict'``.
    """
    p = str(path)
    try:
        return ezdxf.readfile(p)
    except ezdxf.DXFError as fast_ex:
        logic_cad_log("dxf", f"readfile failed; trying recover: {p} ({fast_ex})")
        doc, auditor = recover.readfile(p, errors=errors)
        if auditor.has_errors:
            logic_cad_log("dxf", f"recover loaded with audit issues: {p}")
            try:
                for row in auditor.errors[:5]:
                    logic_cad_log("dxf", f"recover audit error: {row}")
            except Exception:
                pass
        return doc


def new_document() -> Drawing:
    # setup=True adds dim-style arrow blocks (_ARCHTICK, …) on layer "0"; we only need text styles.
    doc = ezdxf.new("R2010", setup=["styles"], units=_INSUNITS_MM)
    ensure_standard_layers(doc)
    ensure_regapp(doc)
    ensure_regapp_document_meta(doc)
    apply_document_meta_stamp(doc)
    return doc


def ensure_standard_linetypes(doc: Drawing) -> None:
    """Define ISO/ANSI linetypes (DASHED, HIDDEN, …) when missing.

    Entities may reference ``DASHED`` while the table only had ``Continuous`` (ezdxf
    ``new(setup=['styles'])``). Without definitions, PDF export and some CADs draw solid lines.

    After loading defaults, ``DASHED`` and ``CENTER`` simple patterns are always replaced
    with :mod:`logic_cad.core.model.constants` mm values so PDF export matches the canvas policy.
    """
    setup_linetypes(doc)
    _apply_app_standard_dash_linetype_patterns(doc)


def _apply_app_standard_dash_linetype_patterns(doc: Drawing) -> None:
    """Overwrite ``DASHED`` / ``CENTER`` table entries with app linetype geometry (mm).

    Args:
        doc: Drawing whose ``linetypes`` table already includes ISO names from
            :func:`setup_linetypes`.
    """
    if LINETYPE_DASH in doc.linetypes:
        d_mm = float(LINETYPE_DASHED_DASH_MM)
        g_mm = float(LINETYPE_DASHED_GAP_MM)
        doc.linetypes.get(LINETYPE_DASH).setup_pattern([d_mm + g_mm, d_mm, -g_mm])
    if LINETYPE_CENTER in doc.linetypes:
        long_mm = float(LINETYPE_CENTER_LONG_DASH_MM)
        g1 = float(LINETYPE_CENTER_GAP1_MM)
        short_mm = float(LINETYPE_CENTER_SHORT_DASH_MM)
        g2 = float(LINETYPE_CENTER_GAP2_MM)
        total = long_mm + g1 + short_mm + g2
        doc.linetypes.get(LINETYPE_CENTER).setup_pattern([total, long_mm, -g1, short_mm, -g2])


def ensure_standard_layers(doc: Drawing) -> None:
    """Create standard layers with default ACI colors on first insert only.

    Existing layer records keep their stored ``color`` / ``true_color`` so edits
    from the layer settings dialog survive load/save cycles.
    """
    ensure_standard_linetypes(doc)
    for name in ALL_LAYERS:
        if name not in doc.layers:
            doc.layers.add(name, color=_default_aci_for_new_standard_layer(name))
    for layer_name, lt in _USER_SKETCH_LAYER_DEFAULT_LINETYPE:
        if layer_name in doc.layers:
            doc.layers.get(layer_name).dxf.linetype = lt
    if LAYER_WIRE_LOGIC in doc.layers:
        doc.layers.get(LAYER_WIRE_LOGIC).dxf.linetype = LINETYPE_LOGIC
    if LAYER_WIRE_VALUE in doc.layers:
        doc.layers.get(LAYER_WIRE_VALUE).dxf.linetype = LINETYPE_VALUE
    if LAYER_WIRE_COM in doc.layers:
        doc.layers.get(LAYER_WIRE_COM).dxf.linetype = LINETYPE_CONTINUOUS
    if LAYER_WIRE_COM_SEGMENT in doc.layers:
        doc.layers.get(LAYER_WIRE_COM_SEGMENT).dxf.linetype = LINETYPE_CONTINUOUS
    if LAYER_WIRE_COM_MARKER in doc.layers:
        doc.layers.get(LAYER_WIRE_COM_MARKER).dxf.linetype = LINETYPE_CONTINUOUS


def readfile(path: str | Path) -> Drawing:
    """Load DXF with app post-load normalization (layouts, attrib geometry, strip).

    INSERT child attributes stored in layout/WCS convention (saved by Logic CAD's
    ``saveas`` or by host CAD) are converted back to block-local ATTDEF geometry when
    the heuristic matches (:func:`~logic_cad.core.dxf.attrib_geometry_sync.revert_all_paper_layout_attrib_inserts_from_wcs_after_load`).

    Args:
        path: Filesystem path to DXF.

    Returns:
        Drawing configured for Logic CAD editors.
    """
    doc = load_dxf_with_recover(path, errors="ignore")
    ensure_drawing_units_mm(doc)
    ensure_standard_layers(doc)
    ensure_standard_linetypes(doc)
    ensure_regapp(doc)
    ensure_regapp_document_meta(doc)
    for layout in doc.layouts:
        if not layout.is_modelspace:
            configure_paper_layout_a4_landscape(doc, layout.name)
    strip_ld_contents_area_all_paper_layouts(doc)
    revert_all_paper_layout_attrib_inserts_from_wcs_after_load(doc)
    return doc


def saveas(doc: Drawing, path: str | Path) -> None:
    """Persist drawing to *path* after standard pre-write hooks.

    INSERT child ``ATTRIB`` insert/align geometry is temporarily rewritten to paper-space
    WCS for interoperability with host CAD, then restored so the in-memory document keeps
    block-local coordinates matching ATTDEF definitions.

    Dynamic gates stay box/C-shape blocks; no IEC substitution. Before writing: set layout
    ``taborder`` to match paper layout name order (TOC first, then natural sort).
    """
    apply_paper_layout_taborder_by_name(doc)
    strip_ld_contents_area_all_paper_layouts(doc)
    ensure_standard_layers(doc)
    ensure_standard_linetypes(doc)
    if LAYER_CONTENTS_AREA in doc.layers:
        doc.layers.get(LAYER_CONTENTS_AREA).off()
    if LAYER_DOC_META in doc.layers:
        doc.layers.get(LAYER_DOC_META).off()
    if LAYER_VPORT in doc.layers:
        doc.layers.get(LAYER_VPORT).off()
    apply_document_meta_stamp(doc)

    layout_snaps: list[tuple[str, list[AttribGeomSnapshot]]] = []
    for layout in doc.layouts:
        if layout.is_modelspace:
            continue
        layout_snaps.append(
            (layout.name, snapshot_paper_layout_insert_attrib_geometry(doc, layout.name))
        )
    try:
        persist_all_paper_layout_attrib_inserts_as_wcs_for_save(doc)
        doc.saveas(str(path))
    finally:
        for _layout_name, snap in layout_snaps:
            restore_paper_layout_insert_attrib_geometry(doc, snap)


class DxfRepository:
    """Thin wrapper for tests / DI."""

    def __init__(self, doc: Drawing) -> None:
        self.doc = doc

    def save(self, path: str | Path) -> None:
        """Persist like :func:`saveas` (disk child ``ATTRIB`` uses layout WCS baked for CAD)."""
        saveas(self.doc, path)
