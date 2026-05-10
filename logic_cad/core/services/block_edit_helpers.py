"""Block definition editing helpers (scratch doc ↔ main doc, ports)."""

from __future__ import annotations

import math

from ezdxf.document import Drawing

from logic_cad.core.model.constants import (
    ENTITY_TYPE_USER_ARC,
    ENTITY_TYPE_USER_CIRCLE,
    ENTITY_TYPE_USER_LINE,
    LAYER_SYMBOL,
    LAYER_TEXT,
)
from logic_cad.core.model.port_key import PortKey, format_port_layer, parse_port_layer
from logic_cad.core.model.user_sketch_layers import user_sketch_entity_linetype_for_display
from logic_cad.core.text.layout_resolver import normalize_dxf_text_entity
from logic_cad.core.model.xdata import get_uid, get_type
from logic_cad.core.services.user_sketch_entity_factory import finalize_new_user_sketch_entity
from logic_cad.core.undo.history import find_entity_by_uid
from logic_cad.core.undo.entity_serialize import restore_entity_from_payload, serialize_entity
from logic_cad.core.dxf.dxf_repository import ensure_standard_layers, new_document


def port_point_layers_in_block(block) -> set[str]:
    """Layers used by POINT entities under ``LD_PORT_*`` inside *block*."""
    out: set[str] = set()
    for ent in block:
        if ent.dxftype() != "POINT":
            continue
        layer = str(ent.dxf.layer or "")
        if parse_port_layer(layer) is not None:
            out.add(layer.upper())
    return out


def port_layer_is_taken(block, layer_name: str, *, ignore_handle: str | None = None) -> bool:
    """Return True if another POINT already uses this ``LD_PORT_*`` layer."""

    want = str(layer_name or "").strip().upper()
    if parse_port_layer(want) is None:
        return True
    for ent in block:
        if ent.dxftype() != "POINT":
            continue
        h = str(getattr(ent.dxf, "handle", "") or "")
        if ignore_handle and h == ignore_handle:
            continue
        if str(ent.dxf.layer or "").strip().upper() == want:
            return True
    return False


def add_user_line_to_block(
    block,
    start: tuple[float, float],
    end: tuple[float, float],
    linetype: str,
) -> str:
    """Add a ``USER_LINE`` (LD_APP + uid) on ``LAYER_SYMBOL``, same scheme as layout user lines."""

    e = block.add_line(
        (float(start[0]), float(start[1])),
        (float(end[0]), float(end[1])),
        dxfattribs={"layer": LAYER_SYMBOL},
    )
    return finalize_new_user_sketch_entity(
        e, ENTITY_TYPE_USER_LINE, sketch_linetype=linetype
    )


def add_user_circle_to_block(
    block,
    center: tuple[float, float],
    radius: float,
    linetype: str,
) -> str:
    """Add a ``USER_CIRCLE`` on ``LAYER_SYMBOL``, same tagging scheme as layout user circles."""

    cx, cy = float(center[0]), float(center[1])
    r = max(float(radius), 1e-9)
    e = block.add_circle(
        center=(cx, cy),
        radius=r,
        dxfattribs={"layer": LAYER_SYMBOL},
    )
    return finalize_new_user_sketch_entity(
        e, ENTITY_TYPE_USER_CIRCLE, sketch_linetype=linetype
    )


def add_user_arc_to_block(
    block,
    center: tuple[float, float],
    radius: float,
    start_angle_deg: float,
    end_angle_deg: float,
    linetype: str,
) -> str:
    """Add a ``USER_ARC`` (ARC + LD_APP) on ``LAYER_SYMBOL``."""

    e = block.add_arc(
        center=(float(center[0]), float(center[1])),
        radius=max(float(radius), 1e-9),
        start_angle=float(start_angle_deg),
        end_angle=float(end_angle_deg),
        dxfattribs={"layer": LAYER_SYMBOL},
    )
    return finalize_new_user_sketch_entity(e, ENTITY_TYPE_USER_ARC, sketch_linetype=linetype)


def add_attdef_to_block(
    block,
    tag: str,
    insert: tuple[float, float],
    default_text: str,
    *,
    height_mm: float = 2.5,
) -> str:
    """Add an ``ATTDEF`` on ``LAYER_TEXT`` (symbol label / attribute definition).

    New definitions get explicit left alignment and ``align_point`` equal to ``insert``
    so instance ATTRIBs created via ``dxfattribs_for_attrib_from_attdef`` are not
    missing alignment fields compared to typical CAD exports.

    Args:
        block: Target block layout (scratch or main).
        tag: ATTDEF tag string.
        insert: Insertion point in DXF mm (x, y).
        default_text: Default attribute string.
        height_mm: Text cap height in mm.

    Returns:
        Handle string of the new ``ATTDEF``.

    Raises:
        ValueError: If *tag* is already used by another ATTDEF in *block*.
    """

    tag_s = str(tag).strip()
    if scratch_block_attdef_tag_taken(block, tag_s):
        raise ValueError(f"タグ {tag_s!r} はこのブロック内ですでに使われています。")
    x, y = float(insert[0]), float(insert[1])
    e = block.add_attdef(
        tag=str(tag),
        text=str(default_text),
        insert=(x, y),
        height=max(0.25, float(height_mm)),
        dxfattribs={"layer": LAYER_TEXT},
    )
    ins = e.dxf.insert
    z = float(getattr(ins, "z", 0.0) or 0.0)
    e.dxf.halign = 0
    e.dxf.align_point = (float(ins.x), float(ins.y), z)
    return str(getattr(e.dxf, "handle", "") or "")


def scratch_block_attdef_tag_taken(block, tag: str, *, ignore_handle: str | None = None) -> bool:
    """Return True if another ATTDEF in *block* already uses *tag* (case-insensitive).

    Args:
        block: Block table iterable of entities.
        tag: Candidate ATTDEF tag.
        ignore_handle: When set, skip this entity handle (e.g. editing in place).

    Returns:
        True when a different ATTDEF already owns the same tag.
    """

    want = str(tag or "").strip().upper()
    if not want:
        return False
    ign = str(ignore_handle or "").strip()
    for e in block:
        if e.dxftype() != "ATTDEF":
            continue
        h = str(getattr(e.dxf, "handle", "") or "")
        if ign and h == ign:
            continue
        if str(e.dxf.tag).strip().upper() == want:
            return True
    return False


def set_scratch_user_sketch_linetype(doc: Drawing, uid: str, linetype: str) -> bool:
    """Set CONTINUOUS/DASHED/CENTER on a USER_LINE / USER_CIRCLE in *doc* (scratch)."""

    e = find_entity_by_uid(doc, uid)
    if e is None:
        return False
    t = get_type(e)
    lt = user_sketch_entity_linetype_for_display(linetype)
    if t == ENTITY_TYPE_USER_LINE and e.dxftype() == "LINE":
        e.dxf.linetype = lt
        return True
    if t == ENTITY_TYPE_USER_CIRCLE and e.dxftype() == "CIRCLE":
        e.dxf.linetype = lt
        return True
    if t == ENTITY_TYPE_USER_ARC and e.dxftype() == "ARC":
        e.dxf.linetype = lt
        return True
    return False


def set_native_line_linetype_in_block(block, handle: str, linetype: str) -> bool:
    """Set normalized linetype on a native LINE inside *block* (not USER_*)."""

    h = str(handle or "").strip()
    if not h:
        return False
    for ent in block:
        if str(getattr(ent.dxf, "handle", "") or "") != h:
            continue
        if ent.dxftype() != "LINE":
            return False
        if get_type(ent) == ENTITY_TYPE_USER_LINE:
            return False
        ent.dxf.linetype = user_sketch_entity_linetype_for_display(linetype)
        return True
    return False


def update_scratch_attdef_fields(
    block,
    handle: str,
    *,
    tag: str,
    default_text: str,
    halign: int,
    height_mm: float,
) -> None:
    """Update ATTDEF tag, default string, height, and horizontal alignment.

    Alignment uses DXF codes 0=left, 1=center, 2=right. The current UI anchor
    (insert vs align_point per :func:`normalize_dxf_text_entity`) is preserved
    when applying a new ``halign``.

    Args:
        block: Block containing the ATTDEF.
        handle: Entity handle.
        tag: New tag string.
        default_text: New default attribute value.
        halign: Horizontal alignment (0–2).
        height_mm: Character height in mm (DXF cap height).

    Raises:
        ValueError: If handle/tag invalid, entity missing, or duplicate tag.
    """

    h = str(handle or "").strip()
    tag_clean = str(tag).strip()
    if not h or not tag_clean:
        raise ValueError("タグまたはハンドルが空です。")
    ent = None
    for e in block:
        if str(getattr(e.dxf, "handle", "") or "") == h:
            ent = e
            break
    if ent is None or ent.dxftype() != "ATTDEF":
        raise ValueError("ATTDEF が見つかりません。")
    if scratch_block_attdef_tag_taken(block, tag_clean, ignore_handle=h):
        raise ValueError(f"タグ {tag_clean!r} はこのブロック内ですでに使われています。")
    ent.dxf.tag = tag_clean
    ent.dxf.text = str(default_text)
    ent.dxf.height = max(0.25, float(height_mm))
    ha = int(halign)
    if ha not in (0, 1, 2):
        ha = 0
    ent.dxf.halign = ha
    lay = normalize_dxf_text_entity(ent)
    ax, ay = float(lay.anchor_x), float(lay.anchor_y)
    ent.dxf.insert = (ax, ay, 0.0)
    ent.dxf.align_point = (ax, ay, 0.0)


def add_plain_text_to_block(
    block,
    insert: tuple[float, float],
    text: str,
    *,
    height_mm: float = 2.5,
) -> str:
    """Add a single-line ``TEXT`` on ``LAYER_TEXT`` (not an ``ATTDEF``).

    Args:
        block: Target block layout.
        insert: Insert point in DXF mm.
        text: Initial string.
        height_mm: Character cap height in mm.

    Returns:
        New entity handle string.

    Raises:
        ValueError: If the block rejects the entity (should not occur for normal text).
    """

    x, y = float(insert[0]), float(insert[1])
    e = block.add_text(
        str(text),
        height=max(0.25, float(height_mm)),
        dxfattribs={"layer": LAYER_TEXT},
    )
    e.dxf.insert = (x, y, 0.0)
    e.dxf.align_point = (x, y, 0.0)
    return str(getattr(e.dxf, "handle", "") or "")


def update_scratch_text_fields(
    block,
    handle: str,
    *,
    text: str,
    height_mm: float,
    rotation_deg: float,
    halign: int,
) -> None:
    """Update ``TEXT`` content, size, rotation, and horizontal alignment in a scratch block.

    Args:
        block: Block containing the ``TEXT``.
        handle: Entity handle.
        text: New string.
        height_mm: Cap height in mm.
        rotation_deg: Counter-clockwise rotation in degrees (DXF).
        halign: 0=left, 1=center, 2=right.

    Raises:
        ValueError: If the handle does not resolve to a ``TEXT`` entity.
    """

    h = str(handle or "").strip()
    if not h:
        raise ValueError("ハンドルが空です。")
    ent = None
    for e in block:
        if str(getattr(e.dxf, "handle", "") or "") == h:
            ent = e
            break
    if ent is None or ent.dxftype() != "TEXT":
        raise ValueError("TEXT が見つかりません。")
    ent.dxf.text = str(text)
    ent.dxf.height = max(0.25, float(height_mm))
    ent.dxf.rotation = float(rotation_deg)
    ha = int(halign)
    if ha not in (0, 1, 2):
        ha = 0
    ent.dxf.halign = ha
    lay = normalize_dxf_text_entity(ent)
    ax, ay = float(lay.anchor_x), float(lay.anchor_y)
    ent.dxf.insert = (ax, ay, 0.0)
    ent.dxf.align_point = (ax, ay, 0.0)


def update_scratch_mtext_fields(
    block,
    handle: str,
    *,
    plain_text: str,
    char_height_mm: float,
    rotation_deg: float,
    width_mm: float,
    attachment_point: int,
) -> None:
    """Update ``MTEXT`` fields on a scratch-block entity (paragraph breaks from newlines).

    Args:
        block: Block containing the ``MTEXT``.
        handle: Entity handle.
        plain_text: User text; ``\\n`` becomes MTEXT paragraph breaks.
        char_height_mm: Character height in mm.
        rotation_deg: DXF rotation in degrees.
        width_mm: Reference rectangle width (0 = unset / single column in ezdxf).
        attachment_point: DXF attachment point (1–9).

    Raises:
        ValueError: If the handle does not resolve to ``MTEXT``.
    """

    h = str(handle or "").strip()
    if not h:
        raise ValueError("ハンドルが空です。")
    ent = None
    for e in block:
        if str(getattr(e.dxf, "handle", "") or "") == h:
            ent = e
            break
    if ent is None or ent.dxftype() != "MTEXT":
        raise ValueError("MTEXT が見つかりません。")
    body = str(plain_text).replace("\r\n", "\n").replace("\r", "\n")
    ent.dxf.text = body.replace("\n", "\\P")
    ent.dxf.char_height = max(0.25, float(char_height_mm))
    ent.dxf.rotation = float(rotation_deg)
    ww = float(width_mm)
    ent.dxf.width = ww if ww > 1e-9 else 0.0
    ap = int(attachment_point)
    if ap < 1 or ap > 9:
        ap = 1
    ent.dxf.attachment_point = ap


def update_scratch_port_layer(block, handle: str, new_layer: str) -> None:
    """Set ``LD_PORT_*`` layer on a POINT by handle; raises ValueError if invalid or layer taken."""

    h = str(handle or "").strip()
    layer_u = str(new_layer or "").strip().upper()
    if not h:
        raise ValueError("ハンドルが空です。")
    if parse_port_layer(layer_u) is None:
        raise ValueError("レイヤは LD_PORT_IN0_LOGIC 形式である必要があります。")
    if port_layer_is_taken(block, layer_u, ignore_handle=h):
        raise ValueError(f"レイヤ {layer_u!r} は別のポートで使用されています。")
    for e in block:
        if e.dxftype() != "POINT":
            continue
        if str(getattr(e.dxf, "handle", "") or "") != h:
            continue
        e.dxf.layer = layer_u
        return
    raise ValueError("ポート（POINT）が見つかりません。")


def update_scratch_user_line_geometry(
    doc: Drawing,
    uid: str,
    p0: tuple[float, float],
    p1: tuple[float, float],
) -> bool:
    """Move a ``USER_LINE`` segment by uid in *doc* (e.g. scratch drawing)."""

    e = find_entity_by_uid(doc, uid)
    if e is None or e.dxftype() != "LINE":
        return False
    e.dxf.start = (float(p0[0]), float(p0[1]), 0.0)
    e.dxf.end = (float(p1[0]), float(p1[1]), 0.0)
    return True


def update_scratch_user_circle_geometry(
    doc: Drawing,
    uid: str,
    center: tuple[float, float],
    radius: float,
) -> bool:
    """Move a ``USER_CIRCLE`` by uid in *doc*."""

    e = find_entity_by_uid(doc, uid)
    if get_type(e) != ENTITY_TYPE_USER_CIRCLE:
        return False
    e.dxf.center = (float(center[0]), float(center[1]), 0.0)
    e.dxf.radius = max(1e-9, float(radius))
    return True


def update_scratch_user_arc_geometry(
    doc: Drawing,
    uid: str,
    center: tuple[float, float],
    radius: float,
    start_angle_deg: float,
    end_angle_deg: float,
) -> bool:
    """Move or reshape a ``USER_ARC`` by uid in *doc* (translation updates center only)."""

    e = find_entity_by_uid(doc, uid)
    if e is None or e.dxftype() != "ARC":
        return False
    if get_type(e) != ENTITY_TYPE_USER_ARC:
        return False
    e.dxf.center = (float(center[0]), float(center[1]), 0.0)
    e.dxf.radius = max(1e-9, float(radius))
    e.dxf.start_angle = float(start_angle_deg)
    e.dxf.end_angle = float(end_angle_deg)
    return True


def make_port_layer_name(direction: str, index: int, unit: str) -> str:
    """Build normalized ``LD_PORT_*`` layer from UI tokens."""

    d = str(direction or "").strip().upper()
    u = str(unit or "").strip().upper()
    if d not in ("IN", "OUT", "INOUT"):
        raise ValueError(f"invalid port direction: {direction!r}")
    if u not in ("LOGIC", "VALUE", "MULTI", "COM"):
        raise ValueError(f"invalid port unit: {unit!r}")
    if index < 0:
        raise ValueError("port index must be non-negative")
    return format_port_layer(PortKey(direction=d, index=int(index), unit=u))  # type: ignore[arg-type]


def count_block_insert_references(doc: Drawing, block_name: str) -> int:
    """Count INSERT entities in paper layouts that reference *block_name*."""

    total = 0
    name = str(block_name)
    for layout in doc.layouts:
        if layout.is_modelspace:
            continue
        blk = doc.blocks.get(layout.block_record_name)
        for entity in blk:
            if entity.dxftype() != "INSERT":
                continue
            if str(entity.dxf.name) == name:
                total += 1
    return total


def _collect_blocks_reachable_via_insert(doc: Drawing, root: str) -> frozenset[str]:
    """Collect block definition names reachable from *root* following INSERT refs.

    Only names present in ``doc.blocks`` are followed. Missing INSERT targets are
    ignored (same as DXF allowing unresolved refs).

    Args:
        doc: Source drawing.
        root: Starting block definition name.

    Returns:
        Set of block names including *root* when defined; empty if *root* missing.
    """
    root_s = str(root).strip()
    if not root_s or root_s not in doc.blocks:
        return frozenset()
    found: set[str] = set()
    stack = [root_s]
    while stack:
        bn = stack.pop()
        if bn in found:
            continue
        blk = doc.blocks.get(bn)
        if blk is None:
            continue
        found.add(bn)
        for ent in blk:
            if ent.dxftype() != "INSERT":
                continue
            child = str(ent.dxf.name)
            if child in doc.blocks and child not in found:
                stack.append(child)
    return frozenset(found)


def copy_block_definitions_tree_from_main_to_scratch(
    main_doc: Drawing,
    scratch: Drawing,
    entry_block_name: str,
) -> None:
    """Copy *entry_block_name* and nested INSERT targets into *scratch* with LD_APP XDATA.

    Uses the same ``serialize_entity`` / ``restore_entity_from_payload`` path as
    :func:`replace_main_block_from_scratch`, avoiding ``ezdxf.addons.Importer`` which
    strips XDATA (see ezdxf Importer docs).

    Empty block records are created for the full dependency closure before entities
    are restored so nested ``INSERT`` can resolve.

    Args:
        main_doc: Document that owns the block definitions.
        scratch: Minimal target drawing (e.g. from :func:`new_document`).
        entry_block_name: Block to open for editing (dependencies included).

    Raises:
        ValueError: If *entry_block_name* is not in *main_doc.blocks*, or if a
            needed block name already exists in *scratch* (unexpected for BEDIT scratch).
    """
    root = str(entry_block_name).strip()
    if root not in main_doc.blocks:
        raise ValueError(f"ブロック {root!r} は本体にありません。")
    needed = _collect_blocks_reachable_via_insert(main_doc, root)
    if root not in needed:
        raise ValueError(f"ブロック {root!r} は本体にありません。")
    for bn in sorted(needed):
        if bn in scratch.blocks:
            raise ValueError(
                f"スクラッチにブロック {bn!r} が既に存在します（複製を中止しました）。"
            )
        src_blk = main_doc.blocks.get(bn)
        nb = scratch.blocks.new(bn)
        try:
            nb.base_point = src_blk.base_point
        except Exception:
            nb.base_point = (0.0, 0.0, 0.0)
    for bn in sorted(needed):
        src_blk = main_doc.blocks.get(bn)
        for ent in list(src_blk):
            payload = serialize_entity(main_doc, ent)
            payload2 = dict(payload)
            payload2["owner"] = {"kind": "block", "name": bn}
            restore_entity_from_payload(scratch, payload2)


def create_scratch_with_block_from_main(main_doc: Drawing, block_name: str) -> Drawing:
    """New minimal drawing containing a copy of *block_name* from *main_doc*."""

    scratch = new_document()
    ensure_standard_layers(scratch)
    copy_block_definitions_tree_from_main_to_scratch(main_doc, scratch, block_name)
    return scratch


def create_scratch_for_new_block(block_name: str) -> Drawing:
    """Empty scratch doc with a new empty block *block_name*."""

    name = str(block_name or "").strip()
    if not name or name.startswith("*"):
        raise ValueError("ブロック名が無効です。")
    scratch = new_document()
    ensure_standard_layers(scratch)
    if name in scratch.blocks:
        raise ValueError(f"ブロック {name!r} は既に存在します。")
    blk = scratch.blocks.new(name)
    blk.base_point = (0.0, 0.0, 0.0)
    return scratch


def replace_main_block_from_scratch(
    main_doc: Drawing,
    scratch_doc: Drawing,
    block_name: str,
    *,
    scratch_block_name: str | None = None,
) -> None:
    """Replace *main_doc* block definition *block_name* contents with scratch copy."""

    src_nm = scratch_block_name or block_name
    if block_name not in main_doc.blocks:
        main_doc.blocks.new(block_name).base_point = (0.0, 0.0, 0.0)
    dest = main_doc.blocks.get(block_name)
    if src_nm not in scratch_doc.blocks:
        raise ValueError(f"スクラッチにブロック {src_nm!r} がありません。")
    src = scratch_doc.blocks.get(src_nm)
    for ent in list(dest):
        dest.delete_entity(ent)
    for ent in list(src):
        payload = serialize_entity(scratch_doc, ent)
        payload2 = dict(payload)
        payload2["owner"] = {"kind": "block", "name": block_name}
        restore_entity_from_payload(main_doc, payload2)
    try:
        dest.base_point = src.base_point
    except Exception:
        pass


def delete_block_definition_if_unused(doc: Drawing, block_name: str) -> None:
    """Delete *block_name* from *doc* when no INSERT references exist."""

    if block_name not in doc.blocks:
        raise ValueError(f"ブロック {block_name!r} はありません。")
    n = count_block_insert_references(doc, block_name)
    if n > 0:
        raise ValueError(f"ブロック {block_name!r} は使用中のため削除できません（参照 {n}）。")
    doc.blocks.delete_block(block_name)


def replace_insert_block_names_referencing(doc: Drawing, old_name: str, new_name: str) -> None:
    """Set ``INSERT.dxf.name`` from *old_name* to *new_name* for every INSERT in *doc*."""

    old_name = str(old_name)
    new_name = str(new_name)
    for handle in list(doc.entitydb.keys()):
        e = doc.entitydb.get(handle)
        if e is None:
            continue
        alive = getattr(e, "is_alive", True)
        if callable(alive):
            alive = alive()
        if not alive:
            continue
        if e.dxftype() != "INSERT":
            continue
        if str(e.dxf.name) == old_name:
            e.dxf.name = new_name


def rename_block_definition(doc: Drawing, old_name: str, new_name: str) -> None:
    """Rename block *old_name* to *new_name* and fix all INSERT references."""

    old_nm = str(old_name or "").strip()
    new_nm = str(new_name or "").strip()
    if not old_nm or old_nm.startswith("*"):
        raise ValueError("元のブロック名が無効です。")
    if not new_nm or new_nm.startswith("*"):
        raise ValueError("新しいブロック名が無効です。")
    if old_nm == new_nm:
        return
    if old_nm not in doc.blocks:
        raise ValueError(f"ブロック {old_nm!r} はありません。")
    if new_nm in doc.blocks:
        raise ValueError(f"ブロック {new_nm!r} は既に存在します。")
    replace_insert_block_names_referencing(doc, old_nm, new_nm)
    doc.blocks.rename_block(old_nm, new_nm)


def duplicate_block_definition(doc: Drawing, src_name: str, dst_name: str) -> None:
    """Create *dst_name* as a copy of *src_name* in *doc* (same as apply-from-scratch flow)."""

    src = str(src_name or "").strip()
    dst = str(dst_name or "").strip()
    if not src or src.startswith("*"):
        raise ValueError("コピー元ブロック名が無効です。")
    if not dst or dst.startswith("*"):
        raise ValueError("新しいブロック名が無効です。")
    if src not in doc.blocks:
        raise ValueError(f"ブロック {src!r} はありません。")
    if dst in doc.blocks:
        raise ValueError(f"ブロック {dst!r} は既に存在します。")
    scratch = create_scratch_with_block_from_main(doc, src)
    replace_main_block_from_scratch(doc, scratch, dst, scratch_block_name=src)


def _rot_xy(x: float, y: float, delta_deg: float) -> tuple[float, float]:
    rad = math.radians(float(delta_deg))
    c, s = math.cos(rad), math.sin(rad)
    return x * c - y * s, x * s + y * c


def _norm_deg(a: float) -> float:
    x = float(a) % 360.0
    if x < 0:
        x += 360.0
    return x


def _apply_rotate_to_entity(ent, delta_deg: float) -> None:
    dt = ent.dxftype()
    if dt == "LINE":
        x0, y0 = float(ent.dxf.start.x), float(ent.dxf.start.y)
        x1, y1 = float(ent.dxf.end.x), float(ent.dxf.end.y)
        rx0, ry0 = _rot_xy(x0, y0, delta_deg)
        rx1, ry1 = _rot_xy(x1, y1, delta_deg)
        ent.dxf.start = (rx0, ry0, 0.0)
        ent.dxf.end = (rx1, ry1, 0.0)
        return
    if dt == "CIRCLE":
        cx, cy = float(ent.dxf.center.x), float(ent.dxf.center.y)
        rx, ry = _rot_xy(cx, cy, delta_deg)
        ent.dxf.center = (rx, ry, 0.0)
        return
    if dt == "ARC":
        cx, cy = float(ent.dxf.center.x), float(ent.dxf.center.y)
        rx, ry = _rot_xy(cx, cy, delta_deg)
        ent.dxf.center = (rx, ry, 0.0)
        ent.dxf.start_angle = _norm_deg(float(ent.dxf.start_angle) + float(delta_deg))
        ent.dxf.end_angle = _norm_deg(float(ent.dxf.end_angle) + float(delta_deg))
        return
    if dt == "POINT":
        lx, ly = float(ent.dxf.location.x), float(ent.dxf.location.y)
        rx, ry = _rot_xy(lx, ly, delta_deg)
        ent.dxf.location = (rx, ry, 0.0)
        return
    if dt == "LWPOLYLINE":
        rows = list(ent.get_points("xyb"))
        if not rows:
            return
        out: list[tuple[float, float, float]] = []
        for row in rows:
            x, y = float(row[0]), float(row[1])
            b = float(row[2]) if len(row) > 2 else 0.0
            rx, ry = _rot_xy(x, y, delta_deg)
            out.append((rx, ry, b))
        ent.set_points(out, format="xyb")
        return
    if dt == "ATTDEF":
        dxfe = ent.dxf
        ins = dxfe.insert
        ix, iy = float(ins.x), float(ins.y)
        ri_x, ri_y = _rot_xy(ix, iy, delta_deg)
        dxfe.insert = (ri_x, ri_y, 0.0)
        ha = int(getattr(dxfe, "halign", 0) or 0)
        va = int(getattr(dxfe, "valign", 0) or 0)
        ap = getattr(dxfe, "align_point", None)
        if ap is not None and hasattr(ap, "x") and hasattr(ap, "y"):
            ax, ay = float(ap.x), float(ap.y)
            rax, ray = _rot_xy(ax, ay, delta_deg)
            dxfe.align_point = (rax, ray, 0.0)
        else:
            dxfe.align_point = (ri_x, ri_y, 0.0)
        # ALIGNED/FIT derive baseline angle from insert→align_point vector; updating both is enough.
        if ha not in (3, 5):
            dxfe.rotation = _norm_deg(float(getattr(dxfe, "rotation", 0.0) or 0.0) + float(delta_deg))
        return
    if dt == "TEXT":
        dxfe = ent.dxf
        ins = dxfe.insert
        ix, iy = float(ins.x), float(ins.y)
        ri_x, ri_y = _rot_xy(ix, iy, delta_deg)
        dxfe.insert = (ri_x, ri_y, 0.0)
        ha = int(getattr(dxfe, "halign", 0) or 0)
        ap = getattr(dxfe, "align_point", None)
        if ap is not None and hasattr(ap, "x") and hasattr(ap, "y"):
            ax, ay = float(ap.x), float(ap.y)
            rax, ray = _rot_xy(ax, ay, delta_deg)
            dxfe.align_point = (rax, ray, 0.0)
        else:
            dxfe.align_point = (ri_x, ri_y, 0.0)
        if ha not in (3, 5):
            dxfe.rotation = _norm_deg(float(getattr(dxfe, "rotation", 0.0) or 0.0) + float(delta_deg))
        return
    if dt == "MTEXT":
        dxfe = ent.dxf
        ins = dxfe.insert
        ix, iy = float(ins.x), float(ins.y)
        ri_x, ri_y = _rot_xy(ix, iy, delta_deg)
        dxfe.insert = (ri_x, ri_y, 0.0)
        dxfe.rotation = _norm_deg(float(getattr(dxfe, "rotation", 0.0) or 0.0) + float(delta_deg))
        return


def rotate_scratch_block_entities(
    blk,
    doc: Drawing,
    *,
    delta_deg: float,
    handles: frozenset[str],
    sketch_uids: frozenset[str],
) -> bool:
    """Rotate selected entities in scratch *blk* around DXF origin. Returns True if anything changed."""

    rotated_handles: set[str] = set()
    rotated_uids: set[str] = set()

    # USER_LINE / USER_CIRCLE by uid (also found in block iterable)
    for uid in sketch_uids:
        if not uid:
            continue
        ent = find_entity_by_uid(doc, uid)
        if ent is None:
            continue
        eh = str(getattr(ent.dxf, "handle", "") or "")
        ok = False
        for e in blk:
            if str(getattr(e.dxf, "handle", "") or "") == eh:
                ok = True
                break
        if not ok:
            continue
        t = get_type(ent)
        if ent.dxftype() == "LINE" and t == ENTITY_TYPE_USER_LINE:
            _apply_rotate_to_entity(ent, delta_deg)
            rotated_uids.add(uid)
        elif ent.dxftype() == "CIRCLE" and t == ENTITY_TYPE_USER_CIRCLE:
            _apply_rotate_to_entity(ent, delta_deg)
            rotated_uids.add(uid)
        elif ent.dxftype() == "ARC" and t == ENTITY_TYPE_USER_ARC:
            _apply_rotate_to_entity(ent, delta_deg)
            rotated_uids.add(uid)

    for h_in in handles:
        h = str(h_in or "").strip()
        if not h:
            continue
        ent = None
        for e in blk:
            if str(getattr(e.dxf, "handle", "") or "") == h:
                ent = e
                break
        if ent is None:
            continue
        if h in rotated_handles:
            continue
        uid = get_uid(ent)
        if uid and uid in rotated_uids:
            continue

        dt = ent.dxftype()
        if dt == "LINE" and get_type(ent) in (ENTITY_TYPE_USER_LINE,):
            continue
        if dt == "CIRCLE" and get_type(ent) in (ENTITY_TYPE_USER_CIRCLE,):
            continue
        if dt == "ARC" and get_type(ent) in (ENTITY_TYPE_USER_ARC,):
            continue

        _apply_rotate_to_entity(ent, delta_deg)
        rotated_handles.add(h)
    return bool(rotated_handles or rotated_uids)
