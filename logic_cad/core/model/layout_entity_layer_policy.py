"""Shared rules for which DXF layers are omitted from passive canvas and PDF graphics."""

from __future__ import annotations

from logic_cad.core.model.constants import (
    LAYER_CONTENTS_AREA,
    LAYER_DOC_META,
    LAYER_PORT,
    LAYER_VPORT,
    LAYER_WIRE_COM,
)


def is_hidden_for_passive_layout_primitive(layer: str) -> bool:
    """Return True if primitives on *layer* must not appear as passive Qt items or in PDF.

    Matches the historical ``pdf_export_entity_filter`` layer policy: port and checkpoint
    routing layers, plus auxiliary guide/meta layers (contents clip, doc anchor, vport).

    Args:
        layer: DXF layer name from ``entity.dxf.layer``.

    Returns:
        True when the layer is internal/auxiliary and should be skipped.
    """
    name = str(layer)
    if name == LAYER_PORT or name.startswith("LD_PORT_"):
        return True
    if name.startswith("LD_CHECKPOINT"):
        return True
    # COM logical carrier polyline is internal; visible style is emitted as helper LINE/CIRCLE entities.
    if name == LAYER_WIRE_COM:
        return True
    if name in (LAYER_CONTENTS_AREA, LAYER_DOC_META, LAYER_VPORT):
        return True
    return False
