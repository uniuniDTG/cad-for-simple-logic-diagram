"""Unit tests for user sketch layer helpers."""

from __future__ import annotations

import ezdxf

from logic_cad.core.model.constants import (
    LAYER_ANNOTATION,
    LAYER_USER_CIRCLE_CENTER,
    LAYER_USER_CIRCLE_CONTINUOUS,
    LAYER_USER_CIRCLE_DASHED,
    LAYER_USER_CLOUD_CENTER,
    LAYER_USER_CLOUD_CONTINUOUS,
    LAYER_USER_CLOUD_DASHED,
    LAYER_USER_LINE_CENTER,
    LAYER_USER_LINE_CONTINUOUS,
    LAYER_USER_LINE_DASHED,
    LINETYPE_CONTINUOUS,
    LINETYPE_DASH,
    LINETYPE_VALUE,
)
from logic_cad.core.model.user_sketch_layers import (
    USER_SKETCH_WIRE_LAYERS,
    is_user_sketch_wire_layer,
    normalize_user_sketch_linetype,
    user_sketch_circle_layer_for_linetype,
    user_sketch_cloud_layer_for_linetype,
    user_sketch_display_linetype_for_entity,
    user_sketch_line_layer_for_linetype,
)


def test_user_sketch_wire_layers_set() -> None:
    """USER_SKETCH_WIRE_LAYERS lists all USER sketch linetype layers."""
    assert USER_SKETCH_WIRE_LAYERS == frozenset(
        {
            LAYER_USER_LINE_CONTINUOUS,
            LAYER_USER_LINE_CENTER,
            LAYER_USER_LINE_DASHED,
            LAYER_USER_CIRCLE_CONTINUOUS,
            LAYER_USER_CIRCLE_CENTER,
            LAYER_USER_CIRCLE_DASHED,
            LAYER_USER_CLOUD_CONTINUOUS,
            LAYER_USER_CLOUD_CENTER,
            LAYER_USER_CLOUD_DASHED,
        }
    )


def test_user_sketch_line_layer_for_linetype() -> None:
    """LINE layers map CONTINUOUS / CENTER / DASHED to LD_USER_LINE_*."""
    assert user_sketch_line_layer_for_linetype(LINETYPE_CONTINUOUS) == LAYER_USER_LINE_CONTINUOUS
    assert user_sketch_line_layer_for_linetype("CONTINUOUS") == LAYER_USER_LINE_CONTINUOUS
    assert user_sketch_line_layer_for_linetype("CENTER") == LAYER_USER_LINE_CENTER
    assert user_sketch_line_layer_for_linetype(LINETYPE_DASH) == LAYER_USER_LINE_DASHED
    assert user_sketch_line_layer_for_linetype("DASHED") == LAYER_USER_LINE_DASHED


def test_user_sketch_circle_layer_for_linetype() -> None:
    """CIRCLE layers map CONTINUOUS / CENTER / DASHED to LD_USER_CIRCLE_*."""
    assert user_sketch_circle_layer_for_linetype("CENTER") == LAYER_USER_CIRCLE_CENTER
    assert user_sketch_circle_layer_for_linetype("DASHED") == LAYER_USER_CIRCLE_DASHED


def test_user_sketch_cloud_layer_for_linetype() -> None:
    """CLOUD layers map CONTINUOUS / CENTER / DASHED to LD_USER_CLOUD_*."""
    assert user_sketch_cloud_layer_for_linetype("CONTINUOUS") == LAYER_USER_CLOUD_CONTINUOUS
    assert user_sketch_cloud_layer_for_linetype("CENTER") == LAYER_USER_CLOUD_CENTER
    assert user_sketch_cloud_layer_for_linetype("DASHED") == LAYER_USER_CLOUD_DASHED


def test_is_user_sketch_wire_layer() -> None:
    """Layer name classification."""
    assert is_user_sketch_wire_layer(LAYER_USER_LINE_CONTINUOUS) is True
    assert is_user_sketch_wire_layer(LAYER_ANNOTATION) is False


def test_user_sketch_display_linetype_by_layer() -> None:
    """BYLAYER resolves from LD_USER_LINE_* / LD_USER_CIRCLE_* layer name."""
    doc = ezdxf.new("R2010", setup=False)
    msp = doc.modelspace()
    e = msp.add_line((0, 0), (1, 0), dxfattribs={"layer": LAYER_USER_LINE_DASHED})
    e.dxf.linetype = "ByLayer"
    assert user_sketch_display_linetype_for_entity(e) == "DASHED"


def test_user_sketch_display_linetype_center_line_layer() -> None:
    """CENTER sketch line layer maps to CENTER in the property combo."""
    doc = ezdxf.new("R2010", setup=False)
    msp = doc.modelspace()
    e = msp.add_line((0, 0), (1, 0), dxfattribs={"layer": LAYER_USER_LINE_CENTER})
    e.dxf.linetype = "ByLayer"
    assert user_sketch_display_linetype_for_entity(e) == "CENTER"


def test_user_sketch_display_linetype_explicit_normalized() -> None:
    """Explicit entity linetype is normalized to combo values."""
    doc = ezdxf.new("R2010", setup=False)
    msp = doc.modelspace()
    e = msp.add_line((0, 0), (1, 0), dxfattribs={"layer": LAYER_USER_LINE_CONTINUOUS, "linetype": "DASHED"})
    assert user_sketch_display_linetype_for_entity(e) == "DASHED"


def test_normalize_user_sketch_linetype() -> None:
    """Aliases map to CONTINUOUS / DASHED / CENTER."""
    assert normalize_user_sketch_linetype("") == "CONTINUOUS"
    assert normalize_user_sketch_linetype(LINETYPE_CONTINUOUS) == "CONTINUOUS"
    assert normalize_user_sketch_linetype(LINETYPE_VALUE) == "DASHED"
    assert normalize_user_sketch_linetype("CENTER") == "CENTER"


def test_user_sketch_display_linetype_explicit_value_alias() -> None:
    """Explicit LINETYPE_VALUE alias is normalized to DASHED."""
    doc = ezdxf.new("R2010", setup=False)
    msp = doc.modelspace()
    e = msp.add_line(
        (0, 0),
        (1, 0),
        dxfattribs={"layer": LAYER_USER_LINE_CONTINUOUS, "linetype": LINETYPE_VALUE},
    )
    assert user_sketch_display_linetype_for_entity(e) == "DASHED"
