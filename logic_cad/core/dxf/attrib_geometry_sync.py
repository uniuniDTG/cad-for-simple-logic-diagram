"""Copy ATTDEF text geometry onto matching INSERT ATTRIB for CAD/PDF parity.

The Qt canvas resolves symbol labels via block ATTDEF + :func:`normalize_dxf_text_entity`,
while ezdxf's PDF pipeline renders each ATTRIB entity as stored. When ATTRIB lacks
``halign``/``align_point``/etc. that the ATTDEF defines, UI and PDF diverge.

``ezdxf.addons.drawing`` renders ``insert.attribs`` in a second pass **without** applying
the block reference transform, so child ATTRIB ``insert`` values must already be in
**paper / layout WCS** for matplotlib/PDF. App-created ATTRIBs often hold block-local
coordinates (matching ATTDEF); :func:`bake_paper_layout_attrib_inserts_to_wcs_for_pdf`
rewrites block-local inserts before matplotlib export inside
:func:`paper_layout_attrib_wcs_bake_for_pdf_session`, which restores the live document.

Saving through :func:`~logic_cad.core.dxf.dxf_repository.saveas` temporarily applies the same
**bake** so external CAD stacks attributes in layout coordinates, then restores the in-memory
block-local parity. :func:`~logic_cad.core.dxf.dxf_repository.readfile` runs
:func:`revert_all_paper_layout_attrib_inserts_from_wcs_after_load` so editors keep block-local.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from ezdxf.document import Drawing
from ezdxf.entities import DXFEntity, Insert
from ezdxf.layouts.blocklayout import BlockLayout
from ezdxf.math import Vec3

from logic_cad.core.paper_layout_access import paper_layout_block

PDF_ATTRIB_POSITION_EQ_TOL_MM = 0.05
"""Millimetres: ``insert`` equals within this tolerance → treat as same point."""

# DXF groups copied from ATTDEF onto ATTRIB by :func:`apply_attdef_text_geometry_to_attrib`
# (excluding ``insert`` / ``align_point``, which use ATTDEF point rules). Also used to build
# ``dxfattribs`` for :meth:`Insert.add_attrib` (with ``height`` handled separately).
_ATTRIB_TEXT_GEOMETRY_DXF_KEYS_EXCEPT_HEIGHT: tuple[str, ...] = (
    "rotation",
    "width",
    "oblique",
    "halign",
    "valign",
)


@dataclass(frozen=True)
class AttribGeomSnapshot:
    """Immutable ATTRIB ``insert`` / ``align_point`` for :func:`restore_paper_layout_insert_attrib_geometry`."""

    entity_handle: str
    insert: tuple[float, float, float]
    align_point: tuple[float, float, float] | None


def _vec3_from_dxf_point(v: Any) -> Vec3:
    return Vec3(float(v.x), float(v.y), float(v.z))


def _distance_mm(a: Vec3, b: Vec3) -> float:
    return float((a - b).magnitude)


def _paper_space_blocklayout_for_tab(
    doc: Drawing, layout_name: str
) -> BlockLayout | None:
    """Resolve a paper layout's ``BlockLayout`` using the same skips as layout-tab iteration.

    Combines ``doc.layouts.get`` + ``layout.is_modelspace`` with
    :func:`~logic_cad.core.paper_layout_access.paper_layout_block`, matching
    ``doc.blocks.get(layout.block_record_name)`` after an explicit
    ``layout.block_record_name in doc.blocks`` filter.

    Args:
        doc: Target drawing.
        layout_name: Layout tab name (``doc.layouts`` key).

    Returns:
        Block space for the tab, or ``None`` when the tab is modelspace or
        ``paper_layout_block`` finds no block record.
    """

    layout = doc.layouts.get(layout_name)
    if layout.is_modelspace:
        return None
    return paper_layout_block(doc, layout_name)


def _iter_paper_layout_blocklayouts(doc: Drawing) -> Iterator[BlockLayout]:
    """Yield each paper layout's block space in ``doc.layouts`` order when resolvable.

    Skips modelspace tabs and missing block records (same early-continue pattern as
    hand-written ``for layout in doc.layouts`` loops that used
    ``layout.block_record_name in doc.blocks`` then ``doc.blocks.get(rec)``).

    Args:
        doc: Target drawing.

    Yields:
        ``BlockLayout`` from :func:`~logic_cad.core.paper_layout_access.paper_layout_block`
        for each non-modelspace tab where that lookup succeeds.
    """

    for layout in doc.layouts:
        if layout.is_modelspace:
            continue
        blk = paper_layout_block(doc, layout.name)
        if blk is None:
            continue
        yield blk


def _iter_paper_layout_inserts(doc: Drawing, layout_name: str) -> Iterator[Insert]:
    """Yield each valid ``INSERT`` on a paper layout's block space.

    Skips modelspace, missing block records, and INSERTs with no / unknown block name
    (same guards as :func:`bake_paper_layout_attrib_inserts_to_wcs_for_pdf`).

    Args:
        doc: Target drawing.
        layout_name: Paper-space layout name.

    Yields:
        INSERT entities whose referenced block exists on *doc*.
    """

    blk = _paper_space_blocklayout_for_tab(doc, layout_name)
    if blk is None:
        return
    for ent in blk:
        if str(ent.dxftype()) != "INSERT":
            continue
        ins_ent: Insert = ent
        bname = str(ins_ent.dxf.name or "").strip()
        if not bname or bname not in doc.blocks:
            continue
        yield ins_ent


# --- Paper layout: PDF matplotlib (child ATTRIB must be layout WCS on the live doc) ---


def snapshot_paper_layout_insert_attrib_geometry(doc: Drawing, layout_name: str) -> list[AttribGeomSnapshot]:
    """Capture ``insert`` / ``align_point`` for every ATTRIB under INSERTs on a paper layout.

    Used with :func:`restore_paper_layout_insert_attrib_geometry` around PDF export so
    block-local coordinates baked for matplotlib are not persisted in the live document.

    Args:
        doc: Target drawing.
        layout_name: Paper-space layout name (not modelspace).

    Returns:
        Snapshot entries in arbitrary order (stable restore does not depend on order).
    """

    out: list[AttribGeomSnapshot] = []
    for ins_ent in _iter_paper_layout_inserts(doc, layout_name):
        for attrib in ins_ent.attribs:
            h = str(getattr(attrib.dxf, "handle", "") or "")
            if not h:
                continue
            ins = attrib.dxf.insert
            ins_t = (float(ins.x), float(ins.y), float(ins.z))
            ap_t: tuple[float, float, float] | None = None
            if attrib.dxf.hasattr("align_point") and attrib.dxf.align_point is not None:
                ap = attrib.dxf.align_point
                ap_t = (float(ap.x), float(ap.y), float(ap.z))
            out.append(AttribGeomSnapshot(entity_handle=h, insert=ins_t, align_point=ap_t))
    return out


def restore_paper_layout_insert_attrib_geometry(doc: Drawing, snapshots: list[AttribGeomSnapshot]) -> None:
    """Restore ATTRIB geometry from :func:`snapshot_paper_layout_insert_attrib_geometry`.

    Args:
        doc: Same drawing that was snapshotted.
        snapshots: List returned from the snapshot call.
    """

    for snap in snapshots:
        ent = doc.entitydb.get(snap.entity_handle)
        if ent is None or str(ent.dxftype()) != "ATTRIB":
            continue
        ent.dxf.insert = snap.insert
        if snap.align_point is None:
            if ent.dxf.hasattr("align_point"):
                try:
                    ent.dxf.discard("align_point")
                except (AttributeError, KeyError, ValueError):
                    pass
        else:
            ent.dxf.align_point = snap.align_point


def bake_paper_layout_attrib_inserts_to_wcs_for_pdf(doc: Drawing, layout_name: str) -> int:
    """Rewrite INSERT child ATTRIB points from block-local to layout WCS when needed for PDF.

    ezdxf's matplotlib frontend draws ``virtual_entities()`` with the INSERT transform,
    then draws ``insert.attribs`` using each ATTRIB's ``insert`` / ``align_point`` as **WCS**
    without re-applying the block reference matrix. When ``insert`` still matches the
    block ATTDEF (block coordinates), labels appear near the layout origin in PDF.

    For each ATTRIB with a matching ATTDEF:

    - If ``attrib.insert`` is already within :data:`PDF_ATTRIB_POSITION_EQ_TOL_MM` of the
      transformed ATTDEF insert → **skip** (already paper WCS or CAD-baked).
    - Else if ``attrib.insert`` matches ATTDEF insert within tolerance → **bake**:
      set ``insert`` / ``align_point`` to the INSERT ``matrix44()`` transform of the ATTDEF
      geometry.
    - Otherwise **skip** (ambiguous; avoids double-transform).

    Does not modify ATTDEF entities or non-ATTRIB geometry.

    Args:
        doc: Drawing to mutate (caller must snapshot/restore if the document must stay unchanged).
        layout_name: Paper layout tab name.

    Returns:
        Number of ATTRIB entities that were updated.
    """

    tol = float(PDF_ATTRIB_POSITION_EQ_TOL_MM)
    n = 0
    for ins_ent in _iter_paper_layout_inserts(doc, layout_name):
        bname = str(ins_ent.dxf.name or "").strip()
        m = ins_ent.matrix44()
        for attrib in ins_ent.attribs:
            attdef = _attdef_for_tag(doc, bname, str(attrib.dxf.tag))
            if attdef is None:
                continue
            local_ins = _vec3_from_dxf_point(attdef.dxf.insert)
            expected_ins = m.transform(local_ins)
            cur_ins = _vec3_from_dxf_point(attrib.dxf.insert)
            if _distance_mm(cur_ins, expected_ins) <= tol:
                continue
            if _distance_mm(cur_ins, local_ins) > tol:
                continue
            attrib.dxf.insert = (float(expected_ins.x), float(expected_ins.y), float(expected_ins.z))
            ad = attdef.dxf
            local_ap: Vec3 | None = None
            if ad.hasattr("align_point") and ad.align_point is not None:
                local_ap = _vec3_from_dxf_point(ad.align_point)
            if local_ap is not None:
                exp_ap = m.transform(local_ap)
                attrib.dxf.align_point = (float(exp_ap.x), float(exp_ap.y), float(exp_ap.z))
            elif attrib.dxf.hasattr("align_point") and attrib.dxf.align_point is not None:
                cur_ap = _vec3_from_dxf_point(attrib.dxf.align_point)
                exp_ap = m.transform(cur_ap)
                attrib.dxf.align_point = (float(exp_ap.x), float(exp_ap.y), float(exp_ap.z))
            n += 1
    return n


def persist_all_paper_layout_attrib_inserts_as_wcs_for_save(doc: Drawing) -> int:
    """Bake every paper layout INSERT's child attributes to layout WCS before writing DXF.

    External CAD stacks block references with child ``ATTRIB`` insertion points in layout
    (paper-space) coordinates, while this app normally keeps geometry block-local matching
    ATTDEF definitions. Persisting baked coordinates avoids labels appearing clustered near
    the layout origin after round-trips through AutoCAD, BricsCAD, nanoCAD, etc.

    Uses the same heuristics as :func:`bake_paper_layout_attrib_inserts_to_wcs_for_pdf` — no
    snapshot/restore unlike PDF export.

    Args:
        doc: Drawing about to be written with :meth:`~ezdxf.document.Drawing.saveas`.

    Returns:
        Total number of ``ATTRIB`` entities rewritten across all paper layouts.
    """

    total = 0
    for layout in doc.layouts:
        if layout.is_modelspace:
            continue
        total += bake_paper_layout_attrib_inserts_to_wcs_for_pdf(doc, layout.name)
    return total


def revert_paper_layout_attrib_inserts_from_wcs_to_block_local(
    doc: Drawing,
    layout_name: str,
) -> int:
    """Rewrite baked paper-space ``ATTRIB`` points back to block-local ATTDEF coordinates.

    When a DXF was saved by Logic CAD (:func:`persist_all_paper_layout_attrib_inserts_as_wcs_for_save`)
    or by CAD with layout-WCS semantics, loading should restore runtime invariants: child attributes
    match ATTDEF inserts in block space (:func:`apply_attdef_text_geometry_to_attrib`).

    Mirrors :func:`bake_paper_layout_attrib_inserts_to_wcs_for_pdf`:

    - If ``attrib.insert``≈ transformed ATTDEF insert (layout WCS) → copy geometry from ATTDEF.
    - If ``attrib.insert``≈ ATTDEF insert (already block-local legacy file) → **skip**.
    - Otherwise ambiguous → **skip**.

    ATTDEF definitions without ``align_point`` cause any leftover baked ``align_point`` on the
    child to be discarded so block-local parity matches ATTDEF semantics.

    Args:
        doc: Drawing just loaded into the editor runtime.
        layout_name: Paper-space layout name.

    Returns:
        Number of ``ATTRIB`` entities updated.
    """

    tol = float(PDF_ATTRIB_POSITION_EQ_TOL_MM)
    n = 0
    for ins_ent in _iter_paper_layout_inserts(doc, layout_name):
        bname = str(ins_ent.dxf.name or "").strip()
        m = ins_ent.matrix44()
        for attrib in ins_ent.attribs:
            attdef = _attdef_for_tag(doc, bname, str(attrib.dxf.tag))
            if attdef is None:
                continue
            local_ins = _vec3_from_dxf_point(attdef.dxf.insert)
            expected_ins = m.transform(local_ins)
            cur_ins = _vec3_from_dxf_point(attrib.dxf.insert)
            if _distance_mm(cur_ins, local_ins) <= tol:
                continue
            if _distance_mm(cur_ins, expected_ins) > tol:
                continue
            apply_attdef_text_geometry_to_attrib(attdef, attrib)
            ad = attdef.dxf
            if not ad.hasattr("align_point") or ad.align_point is None:
                if attrib.dxf.hasattr("align_point"):
                    try:
                        attrib.dxf.discard("align_point")
                    except (AttributeError, KeyError, ValueError):
                        pass
            n += 1
    return n


def revert_all_paper_layout_attrib_inserts_from_wcs_after_load(doc: Drawing) -> int:
    """Run :func:`revert_paper_layout_attrib_inserts_from_wcs_to_block_local` on every paper layout.

    Args:
        doc: Loaded drawing entering the app's runtime model.

    Returns:
        Aggregate count of attributes updated.
    """

    total = 0
    for layout in doc.layouts:
        if layout.is_modelspace:
            continue
        total += revert_paper_layout_attrib_inserts_from_wcs_to_block_local(doc, layout.name)
    return total


@contextmanager
def paper_layout_attrib_wcs_bake_for_pdf_session(doc: Drawing, layout_name: str) -> Iterator[None]:
    """Temporarily bake INSERT child ATTRIB points to layout WCS for matplotlib PDF export.

    On entry: snapshot geometry, then :func:`bake_paper_layout_attrib_inserts_to_wcs_for_pdf`.
    On exit (including errors): restore from the snapshot so the live document reverts.

    Args:
        doc: Drawing being exported.
        layout_name: Paper layout tab name.
    """

    snap = snapshot_paper_layout_insert_attrib_geometry(doc, layout_name)
    try:
        bake_paper_layout_attrib_inserts_to_wcs_for_pdf(doc, layout_name)
        yield
    finally:
        restore_paper_layout_insert_attrib_geometry(doc, snap)


# --- Block-local: copy ATTDEF text geometry onto INSERT ATTRIBs (Qt / repair parity) ---


def dxfattribs_for_attrib_from_attdef(attdef: DXFEntity) -> dict[str, Any]:
    """Build ``dxfattribs`` for :meth:`Insert.add_attrib` from an ATTDEF template.

    Omits ``text``, ``tag``, and ``invisible`` so callers can supply instance values.

    Args:
        attdef: Block definition ATTDEF.

    Returns:
        Keyword arguments for ezdxf attribute creation (height, alignment, etc.).

    Raises:
        ValueError: If *attdef* is not an ATTDEF.
    """

    if str(attdef.dxftype()) != "ATTDEF":
        raise ValueError(f"Expected ATTDEF, got {attdef.dxftype()!r}")
    d = attdef.dxf
    out: dict[str, Any] = {"height": float(getattr(d, "height", 0.25) or 0.25)}
    for key in _ATTRIB_TEXT_GEOMETRY_DXF_KEYS_EXCEPT_HEIGHT:
        if not d.hasattr(key):
            continue
        val = getattr(d, key)
        if val is None:
            continue
        if key in ("halign", "valign"):
            out[key] = int(val)
        else:
            out[key] = float(val)
    return out


def apply_attdef_text_geometry_to_attrib(attdef: DXFEntity, attrib: DXFEntity) -> None:
    """Overwrite ATTRIB insertion/alignment DXF fields to match the block ATTDEF.

    Does not change ``tag``, ``text``, or ``invisible``.

    Args:
        attdef: ATTDEF in the referenced block definition.
        attrib: ATTRIB attached to an INSERT of that block.

    Raises:
        ValueError: If entity types are not ATTDEF / ATTRIB.
    """

    if str(attdef.dxftype()) != "ATTDEF":
        raise ValueError(f"Expected ATTDEF, got {attdef.dxftype()!r}")
    if str(attrib.dxftype()) != "ATTRIB":
        raise ValueError(f"Expected ATTRIB, got {attrib.dxftype()!r}")

    src, dst = attdef.dxf, attrib.dxf
    ins = src.insert
    dst.insert = (float(ins.x), float(ins.y), float(ins.z))

    if src.hasattr("align_point"):
        ap = src.align_point
        dst.align_point = (float(ap.x), float(ap.y), float(ap.z))
    # If ATTDEF has no align_point DXF group, leave ATTRIB unchanged: forcing
    # align_point := insert breaks ezdxf/matplotlib placement for many blocks.

    for key in ("height", *_ATTRIB_TEXT_GEOMETRY_DXF_KEYS_EXCEPT_HEIGHT):
        if not src.hasattr(key):
            continue
        val = getattr(src, key)
        if val is None:
            continue
        setattr(dst, key, val)


def _attdef_for_tag(doc: Drawing, block_name: str, tag: str) -> DXFEntity | None:
    want = str(tag).upper()
    if block_name not in doc.blocks:
        return None
    for ent in doc.blocks.get(block_name):
        if str(ent.dxftype()) != "ATTDEF":
            continue
        if str(ent.dxf.tag).upper() == want:
            return ent
    return None


def sync_insert_attrib_geometry_from_attdefs(doc: Drawing, ins: Insert) -> None:
    """For each ATTRIB on *ins*, copy text geometry from the matching block ATTDEF."""

    bname = str(ins.dxf.name or "")
    for attrib in ins.attribs:
        attdef = _attdef_for_tag(doc, bname, str(attrib.dxf.tag))
        if attdef is None:
            continue
        apply_attdef_text_geometry_to_attrib(attdef, attrib)


def sync_paper_layout_insert_attrib_geometry_from_attdefs(doc: Drawing, layout_name: str) -> None:
    """Sync every INSERT's ATTRIB geometry on a paper layout from block ATTDEFs.

    Skips modelspace. Safe to call before ezdxf matplotlib export so PDF matches the UI.

    Args:
        doc: Drawing.
        layout_name: Paper-space layout tab name.
    """

    for ins_ent in _iter_paper_layout_inserts(doc, layout_name):
        sync_insert_attrib_geometry_from_attdefs(doc, ins_ent)


def sync_insert_attrib_geometry_for_block_name(doc: Drawing, block_name: str) -> int:
    """Copy ATTDEF text geometry onto ATTRIBs for every INSERT of *block_name* on paper layouts.

    Modelspace is skipped. Does not change ``text`` or ``invisible`` on ATTRIBs
    (:func:`apply_attdef_text_geometry_to_attrib`).

    Args:
        doc: Target drawing.
        block_name: Block definition name referenced by ``INSERT.dxf.name``.

    Returns:
        Number of ``INSERT`` entities that were processed (one count per INSERT, not
        per ATTRIB).
    """

    want = str(block_name or "").strip()
    if not want:
        return 0
    n = 0
    for blk in _iter_paper_layout_blocklayouts(doc):
        for ent in blk:
            if str(ent.dxftype()) != "INSERT":
                continue
            if str(ent.dxf.name or "") != want:
                continue
            sync_insert_attrib_geometry_from_attdefs(doc, ent)
            n += 1
    return n
