"""Low-level access helpers for paper layout records in the DXF document.

These helpers live outside ``core/services`` so routing, pages, and services can
share layout→block resolution without a “services know geometry” dependency
direction smell.
"""

from __future__ import annotations

from ezdxf.document import Drawing
from ezdxf.layouts.blocklayout import BlockLayout


def paper_layout_block(doc: Drawing, layout_name: str) -> BlockLayout | None:
    """Return the paper-space ``BlockLayout`` that stores entities for *layout_name*.

    This mirrors ``layout = doc.layouts.get(layout_name); doc.blocks.get(layout.block_record_name)``
    without adding model-space or layout-existence guards.

    Args:
        doc: Active DXF drawing.
        layout_name: Name as registered in ``doc.layouts``.

    Returns:
        The layout's block table record, or ``None`` if ``doc.blocks.get`` finds
        no entry for ``layout.block_record_name``.

    Note:
        If *layout_name* is missing, ``doc.layouts.get`` returns ``None`` and
        accessing ``layout.block_record_name`` raises ``AttributeError`` (not
        ``KeyError``). Missing block records do not raise ``KeyError`` because
        ``doc.blocks.get`` is used.
    """

    layout = doc.layouts.get(layout_name)
    return doc.blocks.get(layout.block_record_name)
