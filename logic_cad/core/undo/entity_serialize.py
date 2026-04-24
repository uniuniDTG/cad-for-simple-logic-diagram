"""Serialize/deserialize DXF entities for DocumentDelta."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import ezdxf
from ezdxf.document import Drawing
from ezdxf.entities import DXFEntity
from ezdxf.entities import DXFGraphic


def _to_plain(value: Any) -> Any:
    """Make DXF attribute values JSON-friendly for snapshot compare."""
    if value is None:
        return None
    if isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_to_plain(v) for v in value]
    if hasattr(value, "x") and hasattr(value, "y"):
        z = getattr(value, "z", 0)
        return (float(value.x), float(value.y), float(z))
    return str(value)


def _serialize_dxfattribs(entity: DXFEntity) -> dict[str, Any]:
    keys = entity.dxf.all_existing_dxf_attribs()
    return {k: _to_plain(getattr(entity.dxf, k)) for k in keys}


def _restore_dxfattribs_layer_linetype_color(att: dict[str, Any], *, layer_default: str = "0") -> dict[str, Any]:
    da: dict[str, Any] = {"layer": att.get("layer", layer_default)}
    lt = att.get("linetype")
    if lt:
        da["linetype"] = str(lt)
    co = att.get("color")
    if co is not None:
        da["color"] = co
    return da


@dataclass(frozen=True)
class OwnerRef:
    kind: str  # "layout" | "block" | "model"
    name: str


def _owner_ref(doc: Drawing, entity: DXFEntity) -> OwnerRef | None:
    """Resolve where entity lives (layout block name, modelspace, or block definition)."""
    oid = entity.dxf.owner
    if not oid:
        return None
    owner = doc.entitydb.get(oid)
    if owner is None:
        return None
    ot = owner.dxftype()
    if ot == "BLOCK_RECORD":
        name = owner.dxf.name
        if name == "*Model_Space":
            return OwnerRef("model", "*Model_Space")
        # Paper space layout block or block definition share BLOCK_RECORD
        if name in doc.layouts:
            return OwnerRef("layout", name)
        return OwnerRef("block", name)
    return None


def entity_owner(doc: Drawing, entity: DXFEntity) -> OwnerRef | None:
    return _owner_ref(doc, entity)


def serialize_entity(doc: Drawing, entity: DXFEntity) -> dict[str, Any]:
    """Serialize entity to a JSON-like dict."""
    et = entity.dxftype()
    owner = entity_owner(doc, entity)
    base: dict[str, Any] = {
        "dxftype": et,
        "handle": entity.dxf.handle,
        "owner": {"kind": owner.kind, "name": owner.name} if owner else None,
        "dxfattribs": _serialize_dxfattribs(entity),
    }
    # XDATA as raw tags list (1001, value) pairs for LD_APP
    try:
        from logic_cad.core.model.constants import APPID

        xdata = entity.get_xdata(APPID)
        if xdata:
            base["xdata_ld_app"] = [(t.code, str(t.value)) for t in xdata]
    except ezdxf.DXFValueError:
        base["xdata_ld_app"] = None

    if et == "INSERT":
        attribs: list[dict[str, Any]] = []
        for a in entity.attribs:
            attribs.append(
                {
                    "tag": a.dxf.tag,
                    "text": a.dxf.text,
                    "insert": (a.dxf.insert.x, a.dxf.insert.y, a.dxf.insert.z),
                    "height": float(a.dxf.height),
                    "rotation": float(a.dxf.rotation),
                    "invisible": int(getattr(a.dxf, "invisible", 0) or 0),
                }
            )
        base["geometry"] = {
            "name": entity.dxf.name,
            "insert": (entity.dxf.insert.x, entity.dxf.insert.y, entity.dxf.insert.z),
            "rotation": float(entity.dxf.rotation),
            "xscale": float(entity.dxf.xscale),
            "yscale": float(entity.dxf.yscale),
            "zscale": float(entity.dxf.zscale),
            "attribs": attribs,
        }
    elif et == "LWPOLYLINE":
        pts_xyb = [
            (float(row[0]), float(row[1]), float(row[2]) if len(row) > 2 else 0.0)
            for row in entity.get_points("xyb")
        ]
        base["geometry"] = {
            "points_xyb": pts_xyb,
            "closed": bool(entity.closed),
        }
    elif et == "ARC":
        base["geometry"] = {
            "center": (entity.dxf.center.x, entity.dxf.center.y, entity.dxf.center.z),
            "radius": float(entity.dxf.radius),
            "start_angle": float(entity.dxf.start_angle),
            "end_angle": float(entity.dxf.end_angle),
        }
    elif et == "POINT":
        base["geometry"] = {
            "location": (entity.dxf.location.x, entity.dxf.location.y, entity.dxf.location.z),
        }
    elif et == "LINE":
        base["geometry"] = {
            "start": (entity.dxf.start.x, entity.dxf.start.y, entity.dxf.start.z),
            "end": (entity.dxf.end.x, entity.dxf.end.y, entity.dxf.end.z),
        }
    elif et == "CIRCLE":
        base["geometry"] = {
            "center": (entity.dxf.center.x, entity.dxf.center.y, entity.dxf.center.z),
            "radius": float(entity.dxf.radius),
        }
    elif et == "TEXT":
        base["geometry"] = {
            "insert": (entity.dxf.insert.x, entity.dxf.insert.y, entity.dxf.insert.z),
            "text": entity.dxf.text,
            "height": float(entity.dxf.height),
            "rotation": float(entity.dxf.rotation),
        }
    elif et == "ATTDEF":
        base["geometry"] = {
            "insert": (entity.dxf.insert.x, entity.dxf.insert.y, entity.dxf.insert.z),
            "tag": entity.dxf.tag,
            "text": entity.dxf.text,
            "height": float(entity.dxf.height),
            "rotation": float(entity.dxf.rotation),
        }
    elif et == "ATTRIB":
        base["geometry"] = {
            "insert": (entity.dxf.insert.x, entity.dxf.insert.y, entity.dxf.insert.z),
            "tag": entity.dxf.tag,
            "text": entity.dxf.text,
            "height": float(entity.dxf.height),
            "rotation": float(entity.dxf.rotation),
        }
    else:
        base["geometry"] = None
    return base


def snapshot_graphic_entities(doc: Drawing) -> dict[str, dict[str, Any]]:
    """Map handle -> serialized payload for all graphic entities."""
    out: dict[str, dict[str, Any]] = {}
    for handle in list(doc.entitydb.keys()):
        e = doc.entitydb.get(handle)
        if e is None or not isinstance(e, DXFGraphic):
            continue
        if e.dxftype() == "ATTRIB":
            # Child of INSERT: captured in INSERT geometry so undo does not duplicate / rename tags
            continue
        try:
            out[handle] = serialize_entity(doc, e)
        except Exception:
            continue
    return out


def _target_block(doc: Drawing, owner: OwnerRef | None):
    if owner is None:
        return doc.modelspace()
    if owner.kind == "model":
        return doc.modelspace()
    if owner.kind == "layout":
        return doc.blocks.get(owner.name)
    if owner.kind == "block":
        return doc.blocks.get(owner.name)
    return doc.modelspace()


def _apply_xdata(entity: DXFEntity, xdata_tags: list[tuple[int, str]] | None) -> None:
    if not xdata_tags:
        return
    from ezdxf.lldxf.tags import Tags
    from ezdxf.lldxf.types import DXFTag
    from logic_cad.core.model.constants import APPID

    tags = Tags()
    for code, val in xdata_tags:
        if code == 1001:
            continue
        tags.append(DXFTag(code, val))
    entity.discard_xdata(APPID)
    entity.set_xdata(APPID, tags)


def restore_entity_from_payload(doc: Drawing, payload: dict[str, Any]) -> DXFEntity | None:
    """Create entity from serialized payload in the correct block/layout space."""
    owner_data = payload.get("owner")
    owner: OwnerRef | None = None
    if owner_data:
        owner = OwnerRef(owner_data["kind"], owner_data["name"])
    blk = _target_block(doc, owner)
    et = payload["dxftype"]
    att = payload.get("dxfattribs", {})
    geom = payload.get("geometry") or {}

    if et == "ATTRIB":
        # Stored on INSERT snapshot; redo must not call BlockLayout.add_attrib (invalid).
        return None

    entity: DXFEntity | None = None
    if et == "INSERT":
        g = geom
        entity = blk.add_blockref(
            g["name"],
            g["insert"][:2],
            dxfattribs={
                "layer": att.get("layer", "0"),
                "color": att.get("color", 256),
                "linetype": att.get("linetype", "BYLAYER"),
            },
        )
        entity.dxf.rotation = g.get("rotation", 0)
        entity.dxf.xscale = g.get("xscale", 1)
        entity.dxf.yscale = g.get("yscale", 1)
        entity.dxf.zscale = g.get("zscale", 1)
        for a in list(entity.attribs):
            doc.entitydb.delete_entity(a)
        attrs = g.get("attribs") or []
        if attrs:
            texts = {str(spec["tag"]): str(spec.get("text", "")) for spec in attrs if spec.get("tag")}
            if texts:
                entity.add_auto_attribs(texts)
            by_tag = {str(s["tag"]).upper(): s for s in attrs if s.get("tag")}
            for a in entity.attribs:
                spec = by_tag.get(str(a.dxf.tag).upper())
                if spec is not None:
                    a.dxf.invisible = int(spec.get("invisible", 0) or 0)
    elif et == "LWPOLYLINE":
        pts_xyb = geom.get("points_xyb") or []
        pts = geom.get("points") or []
        if pts_xyb:
            pts = pts_xyb
        if len(pts) < 2:
            return None
        da: dict[str, Any] = {"layer": att.get("layer", "0")}
        lt = att.get("linetype")
        if lt:
            da["linetype"] = str(lt)
        co = att.get("color")
        if co is not None:
            da["color"] = co
        if pts_xyb:
            entity = blk.add_lwpolyline(pts, format="xyb", dxfattribs=da)
        else:
            entity = blk.add_lwpolyline(pts, dxfattribs=da)
        if geom.get("closed"):
            entity.close()
    elif et == "ARC":
        g = geom
        c = g["center"]
        entity = blk.add_arc(
            center=c[:2],
            radius=g["radius"],
            start_angle=g["start_angle"],
            end_angle=g["end_angle"],
            dxfattribs={"layer": att.get("layer", "0")},
        )
    elif et == "POINT":
        g = geom
        loc = g["location"]
        entity = blk.add_point(loc[:2], dxfattribs={"layer": att.get("layer", "0")})
    elif et == "LINE":
        g = geom
        entity = blk.add_line(
            g["start"][:2],
            g["end"][:2],
            dxfattribs=_restore_dxfattribs_layer_linetype_color(att),
        )
    elif et == "CIRCLE":
        g = geom
        c = g["center"]
        entity = blk.add_circle(
            center=c[:2],
            radius=g["radius"],
            dxfattribs=_restore_dxfattribs_layer_linetype_color(att),
        )
    elif et == "TEXT":
        g = geom
        entity = blk.add_text(
            g["text"],
            height=g["height"],
            rotation=g.get("rotation", 0),
            dxfattribs=_restore_dxfattribs_layer_linetype_color(att),
        )
        entity.dxf.insert = g["insert"][:2]
    elif et == "ATTDEF":
        g = geom
        entity = blk.add_attdef(
            tag=g["tag"],
            text=g["text"],
            insert=g["insert"][:2],
            height=g["height"],
            rotation=g.get("rotation", 0),
            dxfattribs={"layer": att.get("layer", "0")},
        )
    else:
        return None

    if entity and payload.get("xdata_ld_app"):
        _apply_xdata(entity, payload["xdata_ld_app"])
    return entity
