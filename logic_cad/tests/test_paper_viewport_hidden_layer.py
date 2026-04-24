"""Main paper VIEWPORT is kept on VIEWPORTS layer (layer off)."""

from __future__ import annotations

import ezdxf

from logic_cad.core.model.constants import LAYER_VIEWPORTS
from logic_cad.core.services.layout_service import configure_paper_layout_a4_landscape


def test_configure_keeps_one_main_viewport_on_viewports_layer_off() -> None:
    doc = ezdxf.new("R2010", setup=False)
    configure_paper_layout_a4_landscape(doc, "Layout1")
    layout = doc.layouts.get("Layout1")
    vps = layout.viewports()
    assert len(vps) == 1
    main = layout.main_viewport()
    assert main is not None
    assert str(main.dxf.layer) == LAYER_VIEWPORTS
    assert not doc.layers.get(LAYER_VIEWPORTS).is_on()
