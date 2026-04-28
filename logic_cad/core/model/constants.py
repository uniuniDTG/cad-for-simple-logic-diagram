"""Layer names and shared constants."""

from __future__ import annotations

APPID = "LD_APP"
# Document-level metadata (creator, doc format version, DXF profile); XDATA on a single model POINT.
APPID_DOC = "LD_DOC"

# Dynamic AND/OR blocks: minimum number of inputs (no AND_1/OR_1 for new placements or shrink).
MIN_AND_OR_INPUTS = 2
# IEC-style static labels shown inside gate symbols.
GATE_STATIC_LABEL_AND = "&"
GATE_STATIC_LABEL_OR = "≥1"
# STATIC_LABEL0 ATTDEF height (drawing units = mm); AND/OR gate symbols in dynamic_gate_factory.
GATE_STATIC_TEXT_HEIGHT_AND_MM = 2.5
GATE_STATIC_TEXT_HEIGHT_OR_MM = 2.5

# First page name
FIRST_PAGE_NAME = "01"

# Layers (spec 4-1)
LAYER_SYMBOL = "LD_SYMBOL"
LAYER_PORT = "LD_PORT"
# Per-port layers used by CHECKPOINT / WIRE_BRANCH blocks (must exist in ``new_document``).
LAYER_PORT_IN0_MULTI = "LD_PORT_IN0_MULTI"
LAYER_PORT_OUT0_MULTI = "LD_PORT_OUT0_MULTI"
LAYER_WIRE_LOGIC = "LD_WIRE_LOGIC"
LAYER_WIRE_VALUE = "LD_WIRE_VALUE"
LAYER_WIRE_COM = "LD_WIRE_COM"
LAYER_WIRE_COM_SEGMENT = "LD_WIRE_COM_SEGMENT"
LAYER_WIRE_COM_MARKER = "LD_WIRE_COM_MARKER"
LAYER_WIRE_BRIDGE = "LD_WIRE_BRIDGE"
LAYER_TEXT = "LD_TEXT"
LAYER_ANNOTATION = "LD_ANNOTATION"
# USER_LINE / USER_CIRCLE / USER_CLOUD (paper sketch): one layer per linetype (BYLAYER); not LD_WIRE LOGIC/VALUE.
LAYER_USER_LINE_CONTINUOUS = "LD_USER_LINE_CONTINUOUS"
LAYER_USER_LINE_CENTER = "LD_USER_LINE_CENTER"
LAYER_USER_LINE_DASHED = "LD_USER_LINE_DASHED"
LAYER_USER_CIRCLE_CONTINUOUS = "LD_USER_CIRCLE_CONTINUOUS"
LAYER_USER_CIRCLE_CENTER = "LD_USER_CIRCLE_CENTER"
LAYER_USER_CIRCLE_DASHED = "LD_USER_CIRCLE_DASHED"
LAYER_USER_CLOUD_CONTINUOUS = "LD_USER_CLOUD_CONTINUOUS"
LAYER_USER_CLOUD_CENTER = "LD_USER_CLOUD_CENTER"
LAYER_USER_CLOUD_DASHED = "LD_USER_CLOUD_DASHED"
LAYER_FRAME = "LD_FRAME"
LAYER_FRAME_TEXT = "LD_FRAME_TEXT"
LAYER_VPORT = "LD_VPORT"
LAYER_TOC = "LD_TOC"
# Single POINT anchor for LD_DOC XDATA (off-canvas; do not delete).
LAYER_DOC_META = "LD_DOC_META"
# Table of contents template geometry (area guide + block internals)
LAYER_CONTENTS_AREA = "LD_CONTENTS_AREA"
LAYER_CONTENTS_FRAME = "LD_CONTENTS_FRAME"
LAYER_CONTENTS_TEXT = "LD_CONTENTS_TEXT"

# AutoCAD/BricsCAD convention: paper-space model window VIEWPORT entities live here; layer stays off so the frame is not shown.
LAYER_VIEWPORTS = "VIEWPORTS"

# Primary TOC paper layout name (reserved slot ``0``)
TOC_LAYOUT_NAME = "0"

# PAGE_REF INSERT XDATA: link target is the paper layout name
TARGET_LAYOUT_XDATA = "target_layout"
# PAGE_REF INSERT XDATA: "1" shows PAGE_NAME ATTRIB on PAGE_TO/FROM; absent or "0" hides.
PAGE_REF_SHOW_PAGE_NAME_XDATA = "show_page_name"
# PAGE_REF INSERT XDATA: "1" shows PAGE_DESC ATTRIB on PAGE_TO/FROM; absent or "0" hides.
PAGE_REF_SHOW_PAGE_DESC_XDATA = "show_page_desc"
# Legacy PAGE_REF XDATA key: when "1", both PAGE_NAME/PAGE_DESC are treated as visible.
PAGE_REF_SHOW_TARGET_INFO_XDATA = "show_target_info"

# INPAGE_REF: paired INSERTs on one sheet; peer INSERT uid
PEER_UID_XDATA = "peer_uid"

# Footnote-style in-page link markers (※1, ※2, …)
ENTITY_TYPE_INPAGE_REF = "INPAGE_REF"
INPAGE_MARKER_PREFIX = "※"
INPAGE_SYM_HEIGHT_MM = 2.5
# LD_APP XDATA: optional per-INSERT SYM text height (mm); string for build_ld_app_tags
INPAGE_SYM_HEIGHT_XDATA = "sym_height_mm"
# Vertical offset (mm) for SYM ATTDEF insert: negative Y moves text downward on the sheet (DXF Y up).
INPAGE_SYM_INSERT_DY_MM = -1.0
# Minimal blocks: ports + SYM only; horizontal span for TO-side port + right-aligned text (mm)
INPAGE_BLOCK_EXTENT_MM = 24.0
INPAGE_TEXT_GAP_MM = 1.2
BLOCK_INPAGE_FROM = "INPAGE_FROM"
BLOCK_INPAGE_TO = "INPAGE_TO"

# Paper frame: single block (LD_FRAME + LD_FRAME_TEXT ATTDEFs) + INSERT with XDATA type:PAPER_FRAME
BLOCK_PAPER_FRAME = "LD_PAPER_FRAME"
ENTITY_TYPE_PAPER_FRAME = "PAPER_FRAME"

BLOCK_CONTENTS_HEADER = "CONTENTS_HEADER"
BLOCK_CONTENTS_ROW = "CONTENTS_ROW"
ENTITY_TYPE_TOC_HEADER = "TOC_HEADER"
ENTITY_TYPE_TOC_ROW = "TOC_ROW"

# User-drawn annotation entities (paper layout block; LINE/CIRCLE/CLOUD use LD_USER_* layers, TEXT uses LD_ANNOTATION)
ENTITY_TYPE_USER_LINE = "USER_LINE"
ENTITY_TYPE_USER_CIRCLE = "USER_CIRCLE"
ENTITY_TYPE_USER_CLOUD = "USER_CLOUD"
ENTITY_TYPE_USER_TEXT = "USER_TEXT"
# Wire branch: INSERT of ``LD_WIRE_BRANCH`` (ports + optional circle in block); XDATA type WIRE_BRANCH.
BLOCK_WIRE_BRANCH = "LD_WIRE_BRANCH"
ENTITY_TYPE_WIRE_BRANCH = "WIRE_BRANCH"
# Legacy hatch type (page duplicate only; no longer created)
ENTITY_TYPE_WIRE_BRANCH_HATCH = "WIRE_BRANCH_HATCH"

# Wire branch marker radius inside block (mm)
WIRE_BRANCH_RADIUS_MM = 0.5

# TOC row cell size (mm) — matches default blocks in generate/frame_template.py
CONTENTS_CELL_WIDTH_MM = 60.0
CONTENTS_CELL_HEIGHT_MM = 8.0
CONTENTS_CELL_COL_GAP_MM = 0.0
CONTENTS_CELL_ROW_GAP_MM = 0.0
# Default TOC table area (mm) when ``LD_CONTENTS_AREA`` is missing on a sheet
CONTENTS_AREA_DEFAULT_MINX_MM = 31.36
CONTENTS_AREA_DEFAULT_MINY_MM = 39.98
CONTENTS_AREA_DEFAULT_MAXX_MM = 273.87
CONTENTS_AREA_DEFAULT_MAXY_MM = 185.72

ALL_LAYERS = (
    LAYER_SYMBOL,
    LAYER_PORT,
    LAYER_PORT_IN0_MULTI,
    LAYER_PORT_OUT0_MULTI,
    LAYER_WIRE_LOGIC,
    LAYER_WIRE_VALUE,
    LAYER_WIRE_COM,
    LAYER_WIRE_COM_SEGMENT,
    LAYER_WIRE_COM_MARKER,
    LAYER_WIRE_BRIDGE,
    LAYER_TEXT,
    LAYER_ANNOTATION,
    LAYER_USER_LINE_CONTINUOUS,
    LAYER_USER_LINE_CENTER,
    LAYER_USER_LINE_DASHED,
    LAYER_USER_CIRCLE_CONTINUOUS,
    LAYER_USER_CIRCLE_CENTER,
    LAYER_USER_CIRCLE_DASHED,
    LAYER_USER_CLOUD_CONTINUOUS,
    LAYER_USER_CLOUD_CENTER,
    LAYER_USER_CLOUD_DASHED,
    LAYER_FRAME,
    LAYER_FRAME_TEXT,
    LAYER_VPORT,
    LAYER_TOC,
    LAYER_DOC_META,
    LAYER_CONTENTS_AREA,
    LAYER_CONTENTS_FRAME,
    LAYER_CONTENTS_TEXT,
)

# Default grid (mm)
GRID_PITCH = 1.0

# User-placed annotation TEXT height (default when sketch/text tools use this constant)
USER_TEXT_DEFAULT_HEIGHT_MM = 3.0
# USER_CLOUD defaults: arc bulge magnitude and calligraphy style.
USER_CLOUD_BULGE = 0.6
USER_CLOUD_CALLIGRAPHY = False
# Default revcloud segment_length (mm); matches sketch tool finalization in DiagramScene.
USER_CLOUD_DEFAULT_SEGMENT_MM = max(GRID_PITCH, 3.0)

# Routing clearance is expressed in grid cells so symbol, wire, and reserved path spacing stay aligned.
ROUTING_CLEARANCE_GRIDS = 2
ROUTING_CLEARANCE_MM = GRID_PITCH * ROUTING_CLEARANCE_GRIDS

# Paper layout (mm) — landscape sheet; matches frame_template / BricsCAD page
A4_LANDSCAPE_WIDTH_MM = 297.0
A4_LANDSCAPE_HEIGHT_MM = 210.0

# Some CADs leave a closed polyline on layer "0" for the printable area with 10% margins
# on each side (0.8 × sheet). Strip these decoys on load (configure_paper_layout).
A4_LANDSCAPE_PRINTABLE_80_W_MM = A4_LANDSCAPE_WIDTH_MM * 0.8
A4_LANDSCAPE_PRINTABLE_80_H_MM = A4_LANDSCAPE_HEIGHT_MM * 0.8

# If a block definition’s bbox max side exceeds this (mm), INSERT is scaled down uniformly.
# CAD exports often use thousands of drawing units; the editor viewport is A4-sized.
SYMBOL_BLOCK_MAX_DIM_MM = 400.0


def grid_snap_tolerance() -> float:
    """Near-port / snap halo (spec: grid_pitch * 0.5)."""
    return GRID_PITCH * 0.5

# Wire semicircle jump (vertical polyline bulge) at orthogonal crossings
BRIDGE_RADIUS = 0.7

# UI: LWPOLYLINE bulge arc tessellation (preview / hit test along arc)
WIRE_BULGE_ARC_SEGMENTS = 32
WIRE_DRAG_ARC_SAMPLES = 24

# First segment from port: along block local ±X (left-side ports use −X); fallback is world ±X.
# Keep this short so nearby connections do not jump out farther than necessary.
ROUTE_ESCAPE_MM = 1.0

# Obstacle padding (mm) around symbol geometry (ports ∪ block bbox).
ROUTING_SYMBOL_MARGIN = ROUTING_CLEARANCE_MM

# Extra inflation (mm) when testing segment vs obstacle so boundary-grazing paths count as blocked.
ROUTING_PATH_OBSTACLE_INFLATE_MM = 0.1

# Weighted grid search costs.
ROUTING_STEP_COST = 1.0
ROUTING_TURN_COST = 12.0
ROUTING_SOFT_OBSTACLE_PENALTY = 30.0
ROUTING_PORT_ACCESS_WIDTH_MM = GRID_PITCH
ROUTING_MAX_SEARCH_STATES = 3000
ROUTING_PRE_ENTRY_MM = 0.0

# Offset parallel vertical backbone segments (mm) by lane_index * this (snapped to grid).
ROUTING_VERTICAL_LANE_SPACING_MM = 2.0

# Fatten each wire segment by this half-width for obstacle tests. Two parallel runs should stay
# ≥ ROUTING_MIN_WIRE_SEPARATION_MM apart (centerline-to-centerline) → half_width = separation / 2.
ROUTING_MIN_WIRE_SEPARATION_MM = ROUTING_CLEARANCE_MM
ROUTING_WIRE_HALF_WIDTH = ROUTING_MIN_WIRE_SEPARATION_MM / 2.0

# Collinear centerline overlap longer than this (mm) is forbidden vs existing wires when routing.
ROUTING_COLLINEAR_OVERLAP_MIN_MM = max(1e-6, float(GRID_PITCH) * 0.01)

# Cross-page symbols (PAGE_TO / PAGE_FROM) — wide enough for auto label text
PAGE_LINK_WIDTH_MM = 9.0   # 6.0 × 1.5
PAGE_LINK_HEIGHT_MM = 3.0  # slightly taller than 2.4

BLOCK_PAGE_TO = "PAGE_TO"
BLOCK_PAGE_FROM = "PAGE_FROM"

# Relay node: two WIREs (into IN0_MULTI, out of OUT0_MULTI); block is POINT-only in DXF.
BLOCK_CHECKPOINT = "LD_CHECKPOINT"
ENTITY_TYPE_CHECKPOINT = "CHECKPOINT"
# Editor-only marker drawn over CHECKPOINT inserts (mm radius).
CHECKPOINT_MARK_RADIUS_MM = 0.8

# Wire-branch tee along trunk arc-length: inset from t=0/1 by at most this fraction of trunk length,
# and at least ~half GRID_PITCH along the wire (see routing.wire_polyline_geometry.clamp_branch_arc_fraction_t).
WIRE_BRANCH_ARC_END_CLAMP_FRAC = 0.02

# Linetype defaults by unit (DXF name). WIRE / LD_WIRE_* only — do not use for USER_* sketch;
# those must use LINETYPE_CONTINUOUS / LINETYPE_DASH / LINETYPE_CENTER so Logic-wire style can
# change (e.g. LOGIC → dashed) without affecting paper sketch defaults.
LINETYPE_LOGIC = "CONTINUOUS"
LINETYPE_VALUE = "DASHED"
LINETYPE_COM = "COM"

# COM wire bead pattern ("-○-○-"): line length and marker circle size in DXF mm.
WIRE_COM_DASH_MM = 5.0
WIRE_COM_MARKER_DIAMETER_MM = 1.0
WIRE_COM_MARKER_RADIUS_MM = WIRE_COM_MARKER_DIAMETER_MM / 2.0
ENTITY_TYPE_WIRE_COM_MARKER = "WIRE_COM_MARKER"

# Linetype defaults by user aux (DXF name; USER_LINE / USER_CIRCLE / USER_CLOUD / USER_TEXT on paper)
LINETYPE_CONTINUOUS = "CONTINUOUS"
LINETYPE_DASH = "DASHED"
LINETYPE_CENTER = "CENTER"

# WIRE end (IN side) arrow head: child LWPOLYLINE type WIRE_ARROW; wing offsets in DXF mm.
ENTITY_TYPE_WIRE_ARROW = "WIRE_ARROW"
WIRE_ARROW_BACK_MM = 2.0
WIRE_ARROW_SIDE_MM = 0.6
# WIRE XDATA extra: "1" shows IN-side arrow; absent = off.
WIRE_XDATA_SHOW_IN_ARROW = "show_in_arrow"
# WIRE XDATA extra: "1" routes with symbol-only hard obstacles (may cross wire hulls); absent = off.
WIRE_XDATA_ALLOW_ORTHOGONAL_CROSS = "allow_orthogonal_cross"
# AND/OR INSERT XDATA extra: "1" draws WIRE-style IN arrow at each input stub root (x = STUB_MM); absent = off.
GATE_XDATA_SHOW_INPUT_STUB_IN_ARROW = "show_input_stub_in_arrow"
