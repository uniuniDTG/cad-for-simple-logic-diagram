"""Tests for DXF stroke linetype resolution used by Qt preview (block strokes, editor)."""

from __future__ import annotations

import ezdxf

from logic_cad.core.model.constants import LAYER_SYMBOL, LINETYPE_CONTINUOUS
from logic_cad.ui.dxf_display_color import entity_effective_linetype


def test_entity_effective_linetype_bylayer_uses_symbol_layer_definition() -> None:
    doc = ezdxf.new("R2010", setup=False)
    doc.layers.add(LAYER_SYMBOL)
    doc.layers.get(LAYER_SYMBOL).dxf.linetype = "DASHED"
    blk = doc.blocks.new("TEST_BLK")
    ent = blk.add_line((0, 0), (10, 0), dxfattribs={"layer": LAYER_SYMBOL})
    ent.dxf.linetype = "ByLayer"
    assert entity_effective_linetype(doc, ent) == "DASHED"


def test_entity_effective_linetype_explicit_overrides_layer() -> None:
    doc = ezdxf.new("R2010", setup=False)
    doc.layers.add(LAYER_SYMBOL)
    doc.layers.get(LAYER_SYMBOL).dxf.linetype = LINETYPE_CONTINUOUS
    blk = doc.blocks.new("TEST_BLK")
    ent = blk.add_line((0, 0), (10, 0), dxfattribs={"layer": LAYER_SYMBOL})
    ent.dxf.linetype = "CENTER"
    assert entity_effective_linetype(doc, ent) == "CENTER"


def test_entity_effective_linetype_byblock_falls_back_to_continuous() -> None:
    doc = ezdxf.new("R2010", setup=False)
    doc.layers.add(LAYER_SYMBOL)
    doc.layers.get(LAYER_SYMBOL).dxf.linetype = "DASHED"
    blk = doc.blocks.new("TEST_BLK")
    ent = blk.add_line((0, 0), (10, 0), dxfattribs={"layer": LAYER_SYMBOL})
    ent.dxf.linetype = "ByBlock"
    assert entity_effective_linetype(doc, ent) == LINETYPE_CONTINUOUS


def test_entity_effective_linetype_unknown_layer_returns_continuous() -> None:
    doc = ezdxf.new("R2010", setup=False)
    blk = doc.blocks.new("TEST_BLK")
    ent = blk.add_line((0, 0), (10, 0), dxfattribs={"layer": "MISSING_LAYER_XYZ"})
    ent.dxf.linetype = "ByLayer"
    assert entity_effective_linetype(doc, ent) == LINETYPE_CONTINUOUS
