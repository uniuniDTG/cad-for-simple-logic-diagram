"""Resolve DXF layer/entity stroke colors for Qt display; write QColor to layer records."""

from __future__ import annotations

from PySide6.QtGui import QColor
from ezdxf.colors import aci2rgb, int2rgb, rgb2int
from ezdxf.document import Drawing

from logic_cad.core.model.constants import LINETYPE_CONTINUOUS

# Default wire/sketch stroke when layer is missing (matches former hardcoded pen).
_FALLBACK_STROKE_QCOLOR = QColor(200, 200, 210)


def dxf_layer_stroke_qcolor(layer) -> QColor:
    """Convert a DXF layer table entry to an opaque RGB stroke color.

    ``true_color`` (24-bit) takes precedence over ACI when present (``true_color``
    may be ``0`` for black; ``None`` means unset).

    Args:
        layer: ``doc.layers.get(name)`` table entry.

    Returns:
        Opaque ``QColor`` for canvas/PDF-consistent preview.
    """
    tc = getattr(layer.dxf, "true_color", None)
    if tc is not None:
        rgb = int2rgb(int(tc))
        return QColor(int(rgb.r), int(rgb.g), int(rgb.b))
    aci = int(layer.dxf.color)
    rgb = aci2rgb(aci)
    return QColor(int(rgb.r), int(rgb.g), int(rgb.b))


def layer_stroke_qcolor(doc: Drawing, layer_name: str) -> QColor:
    """Resolve stroke ``QColor`` for *layer_name* from *doc*.

    Args:
        doc: Active drawing.
        layer_name: DXF layer name.

    Returns:
        Resolved color, or a neutral fallback if the layer is missing.
    """
    name = str(layer_name).strip()
    if not name or name not in doc.layers:
        return QColor(_FALLBACK_STROKE_QCOLOR)
    return dxf_layer_stroke_qcolor(doc.layers.get(name))


def entity_stroke_qcolor(doc: Drawing, entity) -> QColor:
    """Resolve stroke color for a graphic entity (BYLAYER / true color / ACI).

    Args:
        doc: Active drawing (for BYLAYER resolution).
        entity: ``DXFGraphic`` with ``dxf.layer``, ``dxf.color``, optional ``dxf.true_color``.

    Returns:
        Opaque stroke ``QColor``.
    """
    dxf = entity.dxf
    tc = getattr(dxf, "true_color", None)
    if tc is not None:
        rgb = int2rgb(int(tc))
        return QColor(int(rgb.r), int(rgb.g), int(rgb.b))
    color = int(getattr(dxf, "color", 256) or 256)
    if color in (0, 256):
        return layer_stroke_qcolor(doc, str(dxf.layer))
    rgb = aci2rgb(color)
    return QColor(int(rgb.r), int(rgb.g), int(rgb.b))


def entity_effective_linetype(doc: Drawing, entity) -> str:
    """Resolve stroke linetype for Qt preview (BYLAYER from layer table, BYBLOCK → continuous).

    ``BYBLOCK`` is not resolved without an INSERT context; canvas block-definition paint treats
    it as continuous. Layer table chains that remain ``BYLAYER`` likewise fall back to
    continuous.
    """

    raw = getattr(entity.dxf, "linetype", None)
    lt_entity = str(raw).strip().upper() if raw is not None else ""
    if lt_entity == "BYBLOCK":
        return LINETYPE_CONTINUOUS
    need_layer = (not lt_entity) or lt_entity == "BYLAYER"
    if not need_layer:
        return lt_entity
    lyr = str(getattr(entity.dxf, "layer", "") or "").strip()
    if lyr and lyr in doc.layers:
        layer_raw = getattr(doc.layers.get(lyr).dxf, "linetype", None)
        lt_layer = str(layer_raw).strip().upper() if layer_raw is not None else ""
        if lt_layer and lt_layer not in ("BYLAYER", "BYBLOCK"):
            return lt_layer
    return LINETYPE_CONTINUOUS


def apply_qcolor_to_dxf_layer(layer, qc: QColor) -> None:
    """Store *qc* as DXF ``true_color`` on *layer* (preserves full picker RGB).

    Args:
        layer: Layer table entry to modify.
        qc: Opaque color from the UI (alpha ignored).
    """
    r, g, b = int(qc.red()), int(qc.green()), int(qc.blue())
    layer.dxf.true_color = int(rgb2int((r, g, b)))


def normalize_layer_aci(code: int) -> int:
    """Map a raw DXF layer ``color`` value to a valid ACI index for the UI (1–255).

    Values such as ``0`` (ByBlock) or ``256`` (ByLayer on entities) are not valid
    layer-table ACI indices for ezdxf's :func:`aci2rgb`; we fall back to ``7``
    (white), matching common DXF defaults.

    Args:
        code: Raw ``layer.dxf.color`` value.

    Returns:
        Integer in ``range(1, 256)``.
    """
    c = int(code)
    if 1 <= c <= 255:
        return c
    return 7


def qcolor_to_nearest_aci(qc: QColor) -> int:
    """Pick the ACI index (1–255) whose DXF palette RGB is closest to *qc*.

    Used when switching the layer color editor from true color to indexed color.

    Args:
        qc: Opaque sRGB color (alpha ignored).

    Returns:
        ACI index ``1`` … ``255`` minimizing Euclidean distance in RGB space.
    """
    r0, g0, b0 = int(qc.red()), int(qc.green()), int(qc.blue())
    best_i = 1
    best_d = 1 << 30
    for i in range(1, 256):
        rgb = aci2rgb(i)
        dr = int(rgb.r) - r0
        dg = int(rgb.g) - g0
        db = int(rgb.b) - b0
        d = dr * dr + dg * dg + db * db
        if d < best_d:
            best_d = d
            best_i = i
    return best_i


def apply_aci_to_dxf_layer(layer, aci: int) -> None:
    """Store indexed color *aci* on *layer* and clear ``true_color`` if set.

    Args:
        layer: Layer table entry to modify.
        aci: AutoCAD color index, ``1`` … ``255``.

    Raises:
        ValueError: If *aci* is outside ``1`` … ``255``.
    """
    a = int(aci)
    if not (1 <= a <= 255):
        raise ValueError(f"ACI must be 1..255, got {aci!r}")
    layer.dxf.color = a
    if getattr(layer.dxf, "true_color", None) is not None:
        del layer.dxf.true_color
