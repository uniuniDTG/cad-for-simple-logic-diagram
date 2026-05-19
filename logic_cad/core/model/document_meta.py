"""Document-level DXF metadata (LD_DOC XDATA on a single off-canvas POINT).

Other CAD may rewrite HEADER variables such as ``$ACADVER``; Logic CAD stores its own
creator, application version, document format version, and DXF profile string in XDATA
for forward-compatible migration checks.
"""

from __future__ import annotations

from dataclasses import dataclass

import ezdxf
from ezdxf.document import Drawing
from ezdxf.entities import DXFEntity
from ezdxf.lldxf.tags import Tags
from ezdxf.lldxf.types import DXFTag

from logic_cad import __version__ as LOGIC_CAD_APP_VERSION
from logic_cad.core.model.constants import APPID_DOC, LAYER_DOC_META
from logic_cad.core.model.xdata import parse_ld_string

# Bump when the on-disk document schema changes incompatibly (migration hook).
DOC_FORMAT_VERSION = "1"

CREATOR_NAME = "Logic CAD"

# LD_DOC XDATA key: project-wide UI/PDF font priority (empty / missing = use DXF style default order).
PREFERRED_FONT_FAMILY_KEY = "preferred_font_family"

# Far from typical A4 / grid content (mm); pair with ``LAYER_DOC_META`` for a stable anchor.
_DOC_META_ANCHOR_X = -1_000_000.0
_DOC_META_ANCHOR_Y = -1_000_000.0
_ANCHOR_EPS_MM = 1e-3


@dataclass(frozen=True)
class DocumentMeta:
    """Values read from ``LD_DOC`` XDATA on the document anchor POINT.

    Attributes:
        creator: Product name stamped at save time.
        app_version: ``logic_cad`` package version at save time.
        doc_format: Document schema / format id for migration (see ``DOC_FORMAT_VERSION``).
        dxf_profile: DXF version string used when saving (e.g. ``R2010``).
    """

    creator: str | None
    app_version: str | None
    doc_format: str | None
    dxf_profile: str | None


def ensure_regapp_document_meta(doc: Drawing) -> None:
    """Register APPID ``LD_DOC`` if missing."""
    if APPID_DOC not in doc.appids:
        doc.appids.add(APPID_DOC)


def find_document_meta_entity(doc: Drawing) -> DXFEntity | None:
    """Return the document metadata anchor POINT if present (layer + fixed coordinates)."""
    msp = doc.modelspace()
    for entity in msp.query("POINT"):
        if str(entity.dxf.layer) != LAYER_DOC_META:
            continue
        loc = entity.dxf.location
        if (
            abs(float(loc.x) - _DOC_META_ANCHOR_X) <= _ANCHOR_EPS_MM
            and abs(float(loc.y) - _DOC_META_ANCHOR_Y) <= _ANCHOR_EPS_MM
        ):
            return entity
    return None


def ensure_document_meta_entity(doc: Drawing) -> DXFEntity:
    """Ensure the anchor POINT exists in model space and return it."""
    ensure_regapp_document_meta(doc)
    if LAYER_DOC_META not in doc.layers:
        # Match ``ensure_standard_layers`` system-layer gray (ACI 8).
        doc.layers.add(LAYER_DOC_META, color=8)
    found = find_document_meta_entity(doc)
    if found is not None:
        return found
    msp = doc.modelspace()
    return msp.add_point(
        (_DOC_META_ANCHOR_X, _DOC_META_ANCHOR_Y),
        dxfattribs={"layer": LAYER_DOC_META},
    )


def read_document_meta_dict(entity: DXFEntity) -> dict[str, str]:
    """Parse ``LD_DOC`` XDATA on *entity* into key-value strings."""
    out: dict[str, str] = {}
    try:
        tags = entity.get_xdata(APPID_DOC)
    except ezdxf.DXFValueError:
        return out
    if not tags:
        return out
    for tag in tags:
        if tag.code != 1000:
            continue
        parsed = parse_ld_string(str(tag.value))
        if parsed:
            key, val = parsed
            out[key] = val
    return out


def read_document_meta(doc: Drawing) -> DocumentMeta | None:
    """Load document metadata from the anchor POINT, or None if missing or empty."""
    entity = find_document_meta_entity(doc)
    if entity is None:
        return None
    raw = read_document_meta_dict(entity)
    if not raw:
        return None
    return DocumentMeta(
        creator=raw.get("creator"),
        app_version=raw.get("app_version"),
        doc_format=raw.get("doc_format"),
        dxf_profile=raw.get("dxf_profile"),
    )


def _payload_for_stamp(*, dxf_profile: str) -> dict[str, str]:
    """Build the full key-value map written at save time."""
    return {
        "creator": CREATOR_NAME,
        "app_version": LOGIC_CAD_APP_VERSION,
        "doc_format": DOC_FORMAT_VERSION,
        "dxf_profile": dxf_profile,
    }


def _set_document_meta_xdata(entity: DXFEntity, payload: dict[str, str]) -> None:
    """Replace ``LD_DOC`` XDATA on *entity* with *payload* (1000 strings ``key:value``)."""
    pairs = [DXFTag(1000, f"{key}:{value}") for key, value in sorted(payload.items())]
    tags = Tags(pairs)
    entity.discard_xdata(APPID_DOC)
    entity.set_xdata(APPID_DOC, tags)


def read_project_preferred_font_family(doc: Drawing) -> str | None:
    """Return the project preferred font family from ``LD_DOC`` XDATA, or None for default.

    Args:
        doc: DXF drawing.

    Returns:
        Non-empty family name when set; otherwise ``None`` (same as UI \"既定\").
    """

    entity = find_document_meta_entity(doc)
    if entity is None:
        return None
    raw = read_document_meta_dict(entity).get(PREFERRED_FONT_FAMILY_KEY, "")
    s = str(raw or "").strip()
    return s if s else None


def set_project_preferred_font_family(doc: Drawing, family: str | None) -> None:
    """Store or clear project preferred font on the document anchor (merges with existing XDATA).

    Args:
        doc: DXF drawing.
        family: Font family name, or ``None`` / empty to clear (restore default chain).
    """

    ensure_regapp_document_meta(doc)
    entity = ensure_document_meta_entity(doc)
    prev = read_document_meta_dict(entity)
    profile = str(prev.get("dxf_profile", "") or "").strip() or "R2010"
    merged: dict[str, str] = {**prev, **_payload_for_stamp(dxf_profile=profile)}
    if family and str(family).strip():
        merged[PREFERRED_FONT_FAMILY_KEY] = str(family).strip()
    else:
        merged.pop(PREFERRED_FONT_FAMILY_KEY, None)
    _set_document_meta_xdata(entity, merged)
    # Keep TEXTSTYLE ``LOGIC_CAD_FONT`` font file in sync for BricsCAD (single-font TEXTSTYLE table).
    from logic_cad.core.dxf.text_style import ensure_logic_cad_font_style

    pf = str(family).strip() if family and str(family).strip() else None
    ensure_logic_cad_font_style(doc, preferred_family=pf)
    from logic_cad.core.text.pdf_like_font_faces import invalidate_pdf_like_font_face_cache

    invalidate_pdf_like_font_face_cache(doc=doc)


def apply_document_meta_stamp(doc: Drawing, *, dxf_profile: str = "R2010") -> None:
    """Write current product and format metadata onto the document anchor (create if needed).

    Preserves ``preferred_font_family`` when already set so save does not drop user choice.
    """
    ensure_regapp_document_meta(doc)
    entity = ensure_document_meta_entity(doc)
    prev = read_document_meta_dict(entity)
    payload = _payload_for_stamp(dxf_profile=dxf_profile)
    pff = str(prev.get(PREFERRED_FONT_FAMILY_KEY, "") or "").strip()
    if pff:
        payload[PREFERRED_FONT_FAMILY_KEY] = pff
    _set_document_meta_xdata(entity, payload)
