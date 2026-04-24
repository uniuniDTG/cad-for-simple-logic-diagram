"""Layer lineweight conversion helpers for DXF/UI labels.

Internal-only layers (ports, checkpoints, VIEWPORTS, document meta, TOC area guide,
paper vport guide) are omitted from the in-app layer table so lineweight/color stay
consistent with routing and export rules.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from ezdxf.lldxf.const import LINEWEIGHT_DEFAULT, VALID_DXF_LINEWEIGHTS

from logic_cad.core.model.constants import (
    LAYER_CONTENTS_AREA,
    LAYER_DOC_META,
    LAYER_PORT,
    LAYER_VIEWPORTS,
    LAYER_VPORT,
)


def layer_name_shown_in_layer_settings_dialog(name: str) -> bool:
    """Return whether *name* appears in the layer line settings dialog.

    Port layers, checkpoint helper layers, VIEWPORTS, document-meta / TOC-area /
    paper-vport guide layers, and a few document-internal layers are hidden so
    users do not accidentally change lineweight or color used for logic routing
    or PDF filtering. Layers remain in the DXF and can be edited in other CAD tools.

    Args:
        name: DXF layer name.

    Returns:
        True when the layer should be listed for editing.
    """
    n = str(name).strip()
    if n == LAYER_PORT or n.startswith("LD_PORT_"):
        return False
    if n.startswith("LD_CHECKPOINT"):
        return False
    if n == LAYER_VIEWPORTS:
        return False
    if n == LAYER_DOC_META:
        return False
    if n == LAYER_CONTENTS_AREA:
        return False
    if n == LAYER_VPORT:
        return False
    return True


def all_layer_lineweight_codes() -> tuple[int, ...]:
    """Return selectable layer lineweight codes.

    Returns:
        Tuple containing the default marker and all valid absolute codes.
    """
    return (LINEWEIGHT_DEFAULT, *tuple(int(v) for v in VALID_DXF_LINEWEIGHTS))


def normalize_layer_lineweight_code(code: int) -> int:
    """Normalize *code* to a selectable value.

    Args:
        code: DXF lineweight code.

    Returns:
        *code* if it is selectable, otherwise LINEWEIGHT_DEFAULT.
    """
    values = set(all_layer_lineweight_codes())
    return int(code) if int(code) in values else LINEWEIGHT_DEFAULT


def lineweight_code_to_label(code: int) -> str:
    """Convert DXF lineweight code to a display label.

    Args:
        code: DXF lineweight code.

    Returns:
        Human-readable label for QTable / QComboBox.
    """
    normalized = normalize_layer_lineweight_code(code)
    if normalized == LINEWEIGHT_DEFAULT:
        return "既定"
    return f"{normalized / 100.0:.2f} mm"


def layer_name_natural_sort_key(name: str) -> tuple[object, ...]:
    """Build natural-sort key for layer names.

    Args:
        name: Layer name.

    Returns:
        Tuple key where digit runs are compared as integers.
    """
    parts = re.split(r"(\d+)", str(name))
    key: list[object] = []
    for part in parts:
        if part.isdigit():
            key.append(int(part))
        else:
            key.append(part.lower())
    return tuple(key)


def sorted_layer_names(layer_names: Iterable[str]) -> list[str]:
    """Sort layer names by natural order.

    Args:
        layer_names: Unsorted layer names.

    Returns:
        Layer names sorted in natural order.
    """
    return sorted((str(name) for name in layer_names), key=layer_name_natural_sort_key)
