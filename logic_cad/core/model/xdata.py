"""XDATA helpers for LD_APP (ver, uid, type, ...)."""

from __future__ import annotations

import uuid
import ezdxf
from ezdxf.entities import DXFEntity
from ezdxf.lldxf.tags import Tags
from ezdxf.lldxf.types import DXFTag

from logic_cad.core.model.constants import APPID


def ensure_regapp(doc: ezdxf.document.Drawing) -> None:
    """Register APPID LD_APP if missing."""
    if APPID not in doc.appids:
        doc.appids.add(APPID)


def new_uid() -> str:
    return str(uuid.uuid4())


def _tags_from_pairs(pairs: list[tuple[int, str]]) -> Tags:
    """Data tags only (no 1001 APPID; set_xdata(appid, ...) adds it)."""
    return Tags(DXFTag(code, value) for code, value in pairs)


def build_ld_app_tags(
    ver: str,
    uid: str,
    entity_type: str,
    extra: dict[str, str] | None = None,
) -> Tags:
    """Build XDATA tags (1001 LD_APP + 1000 strings)."""
    pairs: list[tuple[int, str]] = [
        (1000, f"ver:{ver}"),
        (1000, f"uid:{uid}"),
        (1000, f"type:{entity_type}"),
    ]
    if extra:
        for k, v in extra.items():
            pairs.append((1000, f"{k}:{v}"))
    return _tags_from_pairs(pairs)


def set_entity_xdata(entity: DXFEntity, tags: Tags) -> None:
    """Replace entity XDATA for LD_APP."""
    entity.discard_xdata(APPID)
    entity.set_xdata(APPID, tags)


def parse_ld_string(s: str) -> tuple[str, str] | None:
    """Parse 'key:value' from XDATA 1000 string."""
    if ":" not in s:
        return None
    k, _, rest = s.partition(":")
    return k.strip(), rest


def read_ld_app_dict(entity: DXFEntity) -> dict[str, str]:
    """Read LD_APP XDATA as key->value (without prefixes ver:/uid:/type:)."""
    out: dict[str, str] = {}
    try:
        tags = entity.get_xdata(APPID)
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


def get_uid(entity: DXFEntity) -> str | None:
    d = read_ld_app_dict(entity)
    return d.get("uid")


def get_type(entity: DXFEntity) -> str | None:
    d = read_ld_app_dict(entity)
    return d.get("type")
