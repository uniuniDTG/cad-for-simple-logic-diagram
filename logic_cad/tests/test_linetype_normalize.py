"""Tests for ``DASHED`` / ``CENTER`` linetype normalization on load and save paths."""

from __future__ import annotations

import ezdxf

from logic_cad.core.dxf.dxf_repository import ensure_standard_linetypes
from logic_cad.core.model import constants as c


def test_ensure_standard_linetypes_normalizes_dashed_and_center() -> None:
    """After setup, ``DASHED`` and ``CENTER`` match constants (mm drawing units)."""
    doc = ezdxf.new("R2010", setup=["styles"])
    ensure_standard_linetypes(doc)
    dashed = doc.linetypes.get(c.LINETYPE_DASH)
    center = doc.linetypes.get(c.LINETYPE_CENTER)
    assert dashed.simplified_line_pattern() == (c.LINETYPE_DASHED_DASH_MM, c.LINETYPE_DASHED_GAP_MM)
    assert center.simplified_line_pattern() == (
        c.LINETYPE_CENTER_LONG_DASH_MM,
        c.LINETYPE_CENTER_GAP1_MM,
        c.LINETYPE_CENTER_SHORT_DASH_MM,
        c.LINETYPE_CENTER_GAP2_MM,
    )
