"""Strip transient ``LD_CONTENTS_AREA`` guides from DXF paper layout blocks.

Keeps DXF persistence logic one-way dependent on helpers that do **not** import
``layout_service``, avoiding circular imports with ``dxf_repository``.
"""

from __future__ import annotations

from ezdxf.document import Drawing
from ezdxf.layouts.blocklayout import BlockLayout

from logic_cad.core.debug.debug_symlib import symlib_log
from logic_cad.core.model.constants import LAYER_CONTENTS_AREA


def strip_ld_contents_area_in_paper_block(doc: Drawing, blk: BlockLayout | None) -> None:
    """Remove top-level paper-space entities on ``LD_CONTENTS_AREA`` from one layout block.

    Guide geometry for the contents table is recreated as needed; it must not be written
    back as loose entities on that layer.

    Args:
        doc: Active drawing (used when ``BlockLayout.delete_entity`` fails as a fallback).
        blk: The paper layout's block table record, or ``None`` if missing.
    """
    if blk is None:
        return
    for e in list(blk):
        if str(e.dxf.layer) != LAYER_CONTENTS_AREA:
            continue
        try:
            blk.delete_entity(e)
        except Exception as ex:
            symlib_log(f"frame_template: strip contents area {e}: {ex}")
            try:
                doc.entitydb.delete_entity(e)
            except Exception as ex2:
                symlib_log(f"frame_template: entitydb.delete_entity {e}: {ex2}")


def strip_ld_contents_area_all_paper_layouts(doc: Drawing) -> None:
    """Remove top-level ``LD_CONTENTS_AREA`` guide geometry from every paper layout block.

    Args:
        doc: Drawing whose non-model layouts are iterated.
    """
    for layout in doc.layouts:
        if layout.is_modelspace:
            continue
        blk = doc.blocks.get(layout.block_record_name)
        strip_ld_contents_area_in_paper_block(doc, blk)
