"""Shared helpers for USER_* sketch entities (LD_APP tagging after DXF create).

Callers own block/layout placement, layers, geometry, and transaction/undo
wrapping (:meth:`LogicDiagram.begin`, etc.). This module only mirrors the
long-standing convention: ``ver`` is ``\"1\"``, a fresh UUID is assigned, and
optional display linetype is applied via :func:`user_sketch_entity_linetype_for_display`.
"""

from __future__ import annotations

from ezdxf.entities import DXFEntity

from logic_cad.core.model.user_sketch_layers import user_sketch_entity_linetype_for_display
from logic_cad.core.model.xdata import build_ld_app_tags, new_uid, set_entity_xdata


def finalize_new_user_sketch_entity(
    entity: DXFEntity,
    entity_type: str,
    *,
    sketch_linetype: str | None = None,
    ld_extra: dict[str, str] | None = None,
) -> str:
    """Apply sketch display linetype (optional) and assign new LD_APP XDATA.

    Used by paper-layout user geometry and block-edit scratch flows so tagging
    stays identical (``build_ld_app_tags(\"1\", <uid>, type, extra)``).

    Args:
        entity: Entity just added to a block (layout table or definition).
        entity_type: LD_APP ``type`` value (e.g. ``ENTITY_TYPE_USER_LINE``).
        sketch_linetype: When set, updates ``entity.dxf.linetype`` using the
            same normalization as other user sketch primitives. Omit for entities
            that set linetype only via ``dxfattribs`` (e.g. ``USER_TEXT``).
        ld_extra: Optional string map merged into LD_APP after ``ver``/``uid``/``type``.

    Returns:
        Newly generated UID string stored on the entity.
    """

    if sketch_linetype is not None:
        entity.dxf.linetype = user_sketch_entity_linetype_for_display(sketch_linetype)
    uid = new_uid()
    set_entity_xdata(entity, build_ld_app_tags("1", uid, entity_type, ld_extra))
    return uid
