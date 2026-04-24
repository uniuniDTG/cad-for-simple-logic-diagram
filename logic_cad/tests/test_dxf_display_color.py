"""Tests for DXF layer/entity stroke color resolution and layer true_color round-trip."""

from __future__ import annotations

from pathlib import Path

import ezdxf
from ezdxf.colors import aci2rgb, int2rgb, rgb2int
from PySide6.QtGui import QColor

from logic_cad.core.dxf.dxf_repository import ensure_standard_layers, readfile, saveas
from logic_cad.core.model.constants import LAYER_WIRE_LOGIC
from logic_cad.ui.dxf_display_color import (
    apply_aci_to_dxf_layer,
    apply_qcolor_to_dxf_layer,
    dxf_layer_stroke_qcolor,
    entity_stroke_qcolor,
    normalize_layer_aci,
    qcolor_to_nearest_aci,
)


def test_dxf_layer_stroke_qcolor_uses_true_color_when_set() -> None:
    """Layer table true_color overrides ACI for display."""
    doc = ezdxf.new("R2010")
    ly = doc.layers.get("0")
    ly.dxf.true_color = int(rgb2int((10, 20, 30)))
    c = dxf_layer_stroke_qcolor(ly)
    assert c.red() == 10 and c.green() == 20 and c.blue() == 30


def test_apply_qcolor_to_dxf_layer_round_trip() -> None:
    """apply_qcolor_to_dxf_layer stores RGB readable via int2rgb."""
    doc = ezdxf.new("R2010")
    ly = doc.layers.get("0")
    apply_qcolor_to_dxf_layer(ly, QColor(200, 100, 50))
    tc = int(ly.dxf.true_color)
    rgb = int2rgb(tc)
    assert rgb.r == 200 and rgb.g == 100 and rgb.b == 50


def test_entity_stroke_qcolor_bylayer_uses_layer() -> None:
    """Entity color 256 resolves from layer stroke."""
    doc = ezdxf.new("R2010")
    ensure_standard_layers(doc)
    msp = doc.modelspace()
    apply_qcolor_to_dxf_layer(doc.layers.get(LAYER_WIRE_LOGIC), QColor(99, 88, 77))
    lw = msp.add_lwpolyline([(0, 0), (5, 0)], dxfattribs={"layer": LAYER_WIRE_LOGIC, "color": 256})
    c = entity_stroke_qcolor(doc, lw)
    assert c.red() == 99 and c.green() == 88 and c.blue() == 77


def test_normalize_layer_aci_maps_invalid_to_seven() -> None:
    """Out-of-range layer color codes map to ACI 7 for UI spinboxes."""
    assert normalize_layer_aci(0) == 7
    assert normalize_layer_aci(256) == 7
    assert normalize_layer_aci(42) == 42


def test_qcolor_to_nearest_aci_pure_red() -> None:
    """Pure red RGB maps to the standard red ACI (1)."""
    assert qcolor_to_nearest_aci(QColor(255, 0, 0)) == 1


def test_apply_aci_to_dxf_layer_clears_true_color() -> None:
    """Indexed mode clears true_color so display follows ACI."""
    doc = ezdxf.new("R2010")
    ly = doc.layers.get("0")
    apply_qcolor_to_dxf_layer(ly, QColor(10, 20, 30))
    apply_aci_to_dxf_layer(ly, 5)
    assert getattr(ly.dxf, "true_color", None) is None
    assert int(ly.dxf.color) == 5
    c = dxf_layer_stroke_qcolor(ly)
    rgb = aci2rgb(5)
    assert c.red() == int(rgb.r) and c.green() == int(rgb.g) and c.blue() == int(rgb.b)


def test_readfile_preserves_layer_true_color(tmp_path: Path) -> None:
    """ensure_standard_layers no longer clobbers user layer true_color on load."""
    doc = ezdxf.new("R2010")
    ensure_standard_layers(doc)
    apply_qcolor_to_dxf_layer(doc.layers.get(LAYER_WIRE_LOGIC), QColor(41, 42, 43))
    path = tmp_path / "layer_tc.dxf"
    saveas(doc, path)
    doc2 = readfile(path)
    ly = doc2.layers.get(LAYER_WIRE_LOGIC)
    tc = int(ly.dxf.true_color)
    rgb = int2rgb(tc)
    assert rgb.r == 41 and rgb.g == 42 and rgb.b == 43
