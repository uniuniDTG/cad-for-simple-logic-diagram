"""Stacked property editors for diagram entities (public path unchanged).

Callers import ``PropertyPanel`` from ``logic_cad.ui.panels.property_panel`` as
before; implementation lives in submodules under this package (see
``docs/developer.md``).

Modules:
    widget: Main ``PropertyPanel`` QWidget coordination and page construction.
    helpers: Shared Qt warning helpers and ``port_sort_key``.
    symbol_section / wire_section / block_edit_section: Behavioral mixins.

Returns:
    Only ``PropertyPanel`` is re-exported at package root for outside imports.
"""

from logic_cad.ui.panels.property_panel.widget import PropertyPanel

__all__ = ["PropertyPanel"]
