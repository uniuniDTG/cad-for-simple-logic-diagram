"""Focus canvas on a :class:`TextSearchHit` (page switch, select, center view)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer

from logic_cad.core.services.text_find_replace import TextSearchHit
from logic_cad.ui.items.symbol_item import SymbolItem
from logic_cad.ui.items.user_geometry_items import UserTextItem

if TYPE_CHECKING:
    from logic_cad.ui.main_window.window import MainWindow


def apply_text_search_hit(main_window: MainWindow, hit: TextSearchHit) -> None:
    """Switch page if needed, then select the target item and center the view on it.

    Args:
        main_window: Main application window.
        hit: Result from :func:`logic_cad.core.services.text_find_replace.list_text_search_hits`.
    """
    d = main_window._diagram
    if hit.layout_name != d.current_layout_name:
        d.set_current_page(hit.layout_name)
        main_window._scene.set_diagram(d)
        main_window._page_bar.sync_from_diagram()
    main_window._props.clear_selection()

    def _go() -> None:
        scene = main_window._scene
        view = main_window._view
        if hit.kind == "symbol":
            it: SymbolItem | None = scene._symbol_items.get(hit.uid)  # noqa: SLF001
            if it is None:
                for x in scene.items():
                    if isinstance(x, SymbolItem) and x.symbol_uid == hit.uid:
                        it = x
                        break
            if it is None:
                return
            scene.clearSelection()
            it.setSelected(True)
            br = it.sceneBoundingRect()
            if br.isEmpty() or not br.isValid():
                return
            view.centerOn(br.adjusted(-10.0, -10.0, 10.0, 10.0).center())
        else:
            for x in scene.items():
                if isinstance(x, UserTextItem) and x.sketch_uid == hit.uid:
                    scene.clearSelection()
                    x.setSelected(True)
                    br = x.sceneBoundingRect()
                    if br.isEmpty() or not br.isValid():
                        return
                    view.centerOn(br.adjusted(-10.0, -10.0, 10.0, 10.0).center())
                    return

    QTimer.singleShot(0, _go)
