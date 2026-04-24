"""Central QGraphicsScene Z values for editable diagram items (pick and paint order).

Qt uses larger ``zValue()`` for items that stack in front. This module is the single
source of truth for the main editing band.

Routing overlays in ``DiagramScene`` (values around 10000) are intentionally **not**
listed here; they are ephemeral preview geometry in a separate band.

Stack from back to front (increasing Z):

    - Frame/VPORT preview polylines (non-uid layout guides)
    - Paper-like symbols (frame / TOC chrome)
    - Passive DXF mirror (no LD_APP uid)
    - User sketch entities (cloud, circle, text, line)
    - WIRE polylines
    - Logic symbols and wire-arrow decorations
"""

from __future__ import annotations

# Deepest: layout-space frame and VPORT preview paths (see DiagramScene rebuild).
CANVAS_Z_FRAME_VPORT_PREVIEW: float = -21.0

# Paper chrome INSERTs (non-selectable / non-movable).
CANVAS_Z_PAPER_LIKE_SYMBOL: float = -20.0

# Non-interactive mirror of uid-less DXF entities (external CAD, stripped XDATA).
CANVAS_Z_PASSIVE_DXF_MIRROR: float = -10.0

# USER_CLOUD / USER_CIRCLE / USER_TEXT / USER_LINE (relative order: cloud back, line front).
CANVAS_Z_USER_CLOUD: float = -5.4
CANVAS_Z_USER_CIRCLE: float = -5.3
CANVAS_Z_USER_TEXT: float = -5.2
CANVAS_Z_USER_LINE: float = -5.1

# LD_WIRE_* centerlines (below symbols for overlapping picks).
CANVAS_Z_WIRE: float = -1.0

# INSERT symbols and WIRE_ARROW path (same band; arrow is non-selectable child of wire).
CANVAS_Z_SYMBOL_AND_WIRE_ARROW: float = 0.0
