"""Tests for layer lineweight / layer settings list helpers."""

from __future__ import annotations

from logic_cad.core.model.constants import (
    LAYER_CONTENTS_AREA,
    LAYER_DOC_META,
    LAYER_PORT,
    LAYER_VIEWPORTS,
    LAYER_VPORT,
    LAYER_WIRE_LOGIC,
)
from logic_cad.ui.layer_lineweight_utils import layer_name_shown_in_layer_settings_dialog


def test_layer_name_shown_in_layer_settings_dialog_hides_port_layers() -> None:
    """Port marker layers are not listed for user editing."""
    assert layer_name_shown_in_layer_settings_dialog(LAYER_PORT) is False
    assert layer_name_shown_in_layer_settings_dialog("LD_PORT_IN0_LOGIC") is False
    assert layer_name_shown_in_layer_settings_dialog("LD_PORT_OUT0_MULTI") is False


def test_layer_name_shown_in_layer_settings_dialog_hides_checkpoint_and_aux() -> None:
    """Checkpoint helper and document-internal layers are hidden."""
    assert layer_name_shown_in_layer_settings_dialog("LD_CHECKPOINT") is False
    assert layer_name_shown_in_layer_settings_dialog("LD_CHECKPOINT_OUTLINE") is False
    assert layer_name_shown_in_layer_settings_dialog(LAYER_VIEWPORTS) is False
    assert layer_name_shown_in_layer_settings_dialog(LAYER_DOC_META) is False
    assert layer_name_shown_in_layer_settings_dialog(LAYER_CONTENTS_AREA) is False
    assert layer_name_shown_in_layer_settings_dialog(LAYER_VPORT) is False


def test_layer_name_shown_in_layer_settings_dialog_shows_typical_drawing_layers() -> None:
    """Wire and symbol layers remain editable in the dialog."""
    assert layer_name_shown_in_layer_settings_dialog(LAYER_WIRE_LOGIC) is True
    assert layer_name_shown_in_layer_settings_dialog("LD_SYMBOL") is True
    assert layer_name_shown_in_layer_settings_dialog("LD_ANNOTATION") is True
