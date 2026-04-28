"""Export paper layouts from an in-memory DXF to a single multi-page PDF via ezdxf drawing + matplotlib."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import Optional, Sequence, Union

import matplotlib
import matplotlib.pyplot as plt
from ezdxf.document import Drawing
from ezdxf.entities import DXFGraphic
from ezdxf.layouts import Layout
from ezdxf.addons.drawing.config import (
    BackgroundPolicy,
    ColorPolicy,
    Configuration,
)
from ezdxf.addons.drawing import frontend as ez_draw_frontend
from ezdxf.addons.drawing.frontend import Frontend
from ezdxf.addons.drawing.matplotlib import (
    MatplotlibBackend,
    _get_aspect_ratio,
    _get_width_height,
)
from ezdxf.addons.drawing.properties import LayoutProperties, RenderContext
from ezdxf.addons.drawing.type_hints import Color, FilterFunc
from matplotlib.backends.backend_pdf import PdfPages

from logic_cad.core.model.constants import (
    A4_LANDSCAPE_HEIGHT_MM,
    A4_LANDSCAPE_WIDTH_MM,
)
from logic_cad.core.model.layout_entity_layer_policy import is_hidden_for_passive_layout_primitive
from logic_cad.core.text.layout_resolver import (
    apply_render_context_fonts_for_pdf_like_ui,
    decode_dxf_unicode_escapes,
)
from logic_cad.core.dxf.dxf_repository import ensure_standard_layers, ensure_standard_linetypes
from logic_cad.core.services.layout_service import LayoutService

class PdfExportCancelled(Exception):
    """Raised when export is aborted via *is_cancelled* (e.g. user pressed Cancel)."""


@dataclass
class PdfExportOptions:
    """User-chosen PDF export settings (extend with new fields as needed)."""

    monochrome: bool = False


def configuration_for_pdf_export(
    base: Optional[Configuration],
    options: PdfExportOptions,
) -> Configuration:
    """Merge *base* (or default) with *options* into a drawing :class:`Configuration`."""
    c = base if base is not None else Configuration()
    if options.monochrome:
        return c.with_changes(
            color_policy=ColorPolicy.BLACK,
            background_policy=BackgroundPolicy.WHITE,
        )
    return c


def pdf_export_entity_filter(entity: DXFGraphic) -> bool:
    """Return True if the entity should be drawn in PDF export.

    Excludes port/checkpoint routing layers and auxiliary guide/meta layers
    (contents area, document meta anchor, paper vport guide polyline).

    Args:
        entity: Graphic entity being considered for matplotlib rendering.

    Returns:
        False when the entity must not appear in exported PDF pages.
    """
    return not is_hidden_for_passive_layout_primitive(str(entity.dxf.layer))


class _PdfExportFrontend(Frontend):
    """ezdxf ``Frontend`` の ``INSERT`` 展開で ``draw_entities(..., filter_func=...)`` が省略されるため、
    レイアウトに渡した *filter_func* を内部の ``draw_entities`` / ビューポートコールバックにも適用する。
    """

    _layout_entity_filter: FilterFunc | None = None

    def draw_layout(
        self,
        layout,
        finalize: bool = True,
        *,
        filter_func: Optional[FilterFunc] = None,
        layout_properties: Optional[LayoutProperties] = None,
    ) -> None:
        prev = self._layout_entity_filter
        self._layout_entity_filter = filter_func
        try:
            super().draw_layout(
                layout,
                finalize=finalize,
                filter_func=filter_func,
                layout_properties=layout_properties,
            )
        finally:
            self._layout_entity_filter = prev

    def draw_entities(
        self,
        entities,
        *,
        filter_func: Optional[FilterFunc] = None,
    ) -> None:
        effective = filter_func if filter_func is not None else self._layout_entity_filter
        super().draw_entities(entities, filter_func=effective)

    def draw_entities_callback(self, ctx: RenderContext, entities) -> None:
        ez_draw_frontend._draw_entities(
            self,
            ctx,
            entities,
            filter_func=self._layout_entity_filter,
        )

    @staticmethod
    def _decoded_text_entity(entity: DXFGraphic) -> DXFGraphic:
        """Return a copied text entity with DXF unicode escapes decoded.

        The original entity in *doc* must stay unchanged because export should not
        mutate drawing data.
        """

        dt = str(entity.dxftype()).upper()
        if dt not in {"TEXT", "ATTRIB", "ATTDEF", "MTEXT"}:
            return entity
        try:
            cloned = entity.copy()
        except Exception:
            return entity
        try:
            if dt == "MTEXT":
                cloned.text = decode_dxf_unicode_escapes(str(getattr(cloned, "text", "") or ""))
                return cloned
            if dt == "ATTDEF":
                raw_tag = str(getattr(cloned.dxf, "tag", "") or "")
                if raw_tag:
                    cloned.dxf.tag = decode_dxf_unicode_escapes(raw_tag)
                if hasattr(cloned.dxf, "text"):
                    raw_text = str(getattr(cloned.dxf, "text", "") or "")
                    if raw_text:
                        cloned.dxf.text = decode_dxf_unicode_escapes(raw_text)
                return cloned
            raw = str(getattr(cloned.dxf, "text", "") or "")
            if raw:
                cloned.dxf.text = decode_dxf_unicode_escapes(raw)
            return cloned
        except Exception:
            return entity

    def draw_text_entity(self, entity: DXFGraphic, properties) -> None:
        super().draw_text_entity(self._decoded_text_entity(entity), properties)

    def draw_mtext_entity(self, entity: DXFGraphic, properties) -> None:
        super().draw_mtext_entity(self._decoded_text_entity(entity), properties)


def _paper_size_inches_from_layout(layout: Layout) -> tuple[float, float]:
    """Return figure width/height in inches matching the layout plot paper size (mm).

    ezdxf stores ``paper_width`` / ``paper_height`` on the layout block (Logic CAD uses mm).
    If either value is missing or non-positive, falls back to A4 landscape constants.

    Args:
        layout: Paper-space layout (not modelspace).

    Returns:
        ``(width_in, height_in)`` for :meth:`matplotlib.figure.Figure.set_size_inches`.
    """
    dxf = layout.dxf_layout.dxf
    try:
        pw = float(dxf.paper_width)
    except (TypeError, ValueError):
        pw = 0.0
    try:
        ph = float(dxf.paper_height)
    except (TypeError, ValueError):
        ph = 0.0
    if pw <= 0.0 or ph <= 0.0:
        pw = A4_LANDSCAPE_WIDTH_MM
        ph = A4_LANDSCAPE_HEIGHT_MM
    return (pw / 25.4, ph / 25.4)


def export_paper_layouts_to_pdf(
    doc: Drawing,
    pdf_path: Union[str, PathLike[str]],
    *,
    layout_names: Optional[Sequence[str]] = None,
    dpi: int = 300,
    backend: str = "agg",
    bg: Optional[Color] = None,
    fg: Optional[Color] = None,
    config: Optional[Configuration] = None,
    filter_func: Optional[FilterFunc] = None,
    size_inches: Optional[tuple[float, float]] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    is_cancelled: Optional[Callable[[], bool]] = None,
    export_options: Optional[PdfExportOptions] = None,
) -> None:
    """Write all paper layouts to one PDF using the same pipeline as ``ezdxf...matplotlib.qsave``.

    Pages follow *layout_names* if given, else :meth:`LayoutService.list_pages` order (TOC + natural sort).

    *progress_callback* is invoked as ``(done, total)`` after each page is appended (*done* is 1-based).
    If *is_cancelled* returns True before a page, raises :exc:`PdfExportCancelled`.

    *export_options* adjusts rendering (e.g. monochrome); merged into *config* via
    :func:`configuration_for_pdf_export`. When monochrome is on, *bg* / *fg* overrides are skipped.
    """
    path = Path(pdf_path)
    names = list(layout_names) if layout_names is not None else LayoutService(doc).list_pages()
    if not names:
        raise ValueError("エクスポートする用紙レイアウトがありません。")

    ensure_standard_layers(doc)
    ensure_standard_linetypes(doc)

    opts = export_options if export_options is not None else PdfExportOptions()
    draw_config = configuration_for_pdf_export(config, opts)

    base = filter_func

    def combined_filter(e: DXFGraphic) -> bool:
        if not pdf_export_entity_filter(e):
            return False
        if base is not None and not base(e):
            return False
        return True

    total = len(names)
    old_backend = matplotlib.get_backend()
    matplotlib.use(backend)
    try:
        try:
            with PdfPages(path) as pdf:
                for i, layout_name in enumerate(names):
                    if is_cancelled is not None and is_cancelled():
                        raise PdfExportCancelled()
                    layout = doc.layouts.get(layout_name)
                    if layout.is_modelspace:
                        continue
                    fig: plt.Figure = plt.figure(dpi=dpi)
                    ax: plt.Axes = fig.add_axes((0, 0, 1, 1))
                    ctx = RenderContext(layout.doc)
                    apply_render_context_fonts_for_pdf_like_ui(ctx, layout.doc)
                    layout_properties = LayoutProperties.from_layout(layout)
                    if bg is not None and not opts.monochrome:
                        layout_properties.set_colors(bg, fg)
                    out = MatplotlibBackend(ax)
                    _PdfExportFrontend(ctx, out, draw_config).draw_layout(
                        layout,
                        finalize=True,
                        filter_func=combined_filter,
                        layout_properties=layout_properties,
                    )
                    # MatplotlibBackend.finalize() sets fig size via plt.figaspect (not physical paper mm).
                    # Override so PDF MediaBox matches DXF paper_width/paper_height.
                    if size_inches is not None:
                        ratio = _get_aspect_ratio(ax)
                        w, h = _get_width_height(ratio, size_inches[0], size_inches[1])
                        fig.set_size_inches(w, h, True)
                    else:
                        w_p, h_p = _paper_size_inches_from_layout(layout)
                        fig.set_size_inches(w_p, h_p, True)
                    pdf.savefig(fig, dpi=dpi, facecolor=ax.get_facecolor(), transparent=True)
                    plt.close(fig)
                    if progress_callback is not None:
                        progress_callback(i + 1, total)
        except PdfExportCancelled:
            if path.is_file():
                try:
                    path.unlink()
                except OSError:
                    pass
            raise
    finally:
        matplotlib.use(old_backend)
