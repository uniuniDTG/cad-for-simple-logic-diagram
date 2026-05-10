"""Layouts (pages), frame / virtual viewport.

このパッケージは旧単一ファイル ``layout_service.py`` をドメイン分割したものです。
``from logic_cad.core.services.layout_service import …`` は ``__init__.py`` の再エクスポートにより
従来どおり動作します。

Submodules:
    layout_paths: アセット／リポジトリルートパス。
    layout_block_names: パレット・BEDIT 用ブロック名フィルタ。
    layout_builtin_blocks: システム用ブロック定義の保証。
    layout_symbol_library: シンボルライブラリのマージ／再読み込み。
    layout_frame_template: 図枠テンプレートの取り込みと一括適用。
    layout_uid_remap: 紙レイアウト複製・取り込み時の UID 書き換え。
    layout_page_service: :class:`LayoutService`（ページ CRUD 等）。

See Also:
    :mod:`logic_cad.core.paper_layout_strip`
    :mod:`logic_cad.core.paper_layout_configure`
"""

from __future__ import annotations

from logic_cad.core.paper_layout_configure import configure_paper_layout_a4_landscape

from .layout_block_names import (
    _iter_block_definition_names,
    list_block_editor_block_names,
    list_palette_block_names,
)
from .layout_builtin_blocks import (
    ensure_checkpoint_block,
    ensure_cross_page_reference_blocks,
    ensure_inpage_reference_blocks,
    ensure_wire_branch_block,
)
from .layout_frame_template import (
    apply_frame_template_from_path,
    ensure_frame_template_blocks,
    import_frame_template,
    import_frame_template_defined_blocks,
    validate_frame_template_path,
)
from .layout_page_service import LayoutService
from .layout_symbol_library import import_symbol_library, reload_symbol_library
from .layout_uid_remap import remap_layout_block_ld_uids

__all__ = (
    "LayoutService",
    "_iter_block_definition_names",
    "apply_frame_template_from_path",
    "configure_paper_layout_a4_landscape",
    "ensure_checkpoint_block",
    "ensure_cross_page_reference_blocks",
    "ensure_frame_template_blocks",
    "ensure_inpage_reference_blocks",
    "ensure_wire_branch_block",
    "import_frame_template",
    "import_frame_template_defined_blocks",
    "import_symbol_library",
    "list_block_editor_block_names",
    "list_palette_block_names",
    "reload_symbol_library",
    "remap_layout_block_ld_uids",
    "validate_frame_template_path",
)
