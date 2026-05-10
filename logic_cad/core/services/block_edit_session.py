"""In-app block definition editing session (scratch :class:`Drawing`)."""

from __future__ import annotations

from dataclasses import dataclass, field

from ezdxf.document import Drawing

from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.core.services.block_edit_helpers import (
    create_scratch_for_new_block,
    create_scratch_with_block_from_main,
    replace_main_block_from_scratch,
)
from logic_cad.core.undo.history import HistoryService
from logic_cad.core.undo.scratch_transaction import ScratchDocumentTransaction


@dataclass
class BlockEditSession:
    """Holds scratch document, undo stack, and metadata until apply or discard."""

    scratch_doc: Drawing
    block_name: str
    is_new_block: bool
    block_history: HistoryService = field(default_factory=HistoryService)
    scratch_block_name: str | None = None

    def __post_init__(self) -> None:
        if self.scratch_block_name is None:
            self.scratch_block_name = self.block_name

    def scratch_block(self):
        return self.scratch_doc.blocks.get(self.scratch_block_name or self.block_name)

    def scratch_definition_name(self) -> str:
        """Name of the block definition inside ``scratch_doc`` (``scratch_block().name``).

        Prefer this for editor UI (ATTDEF tag lists, labels) so choices match the definition
        actually open in the scratch drawing even if metadata differs.
        """
        blk = self.scratch_block()
        if blk is not None:
            try:
                nm = str(blk.name).strip()
                if nm:
                    return nm
            except (AttributeError, TypeError):
                pass
        return str(self.block_name or "").strip()

    def begin(self, label: str) -> ScratchDocumentTransaction:
        return ScratchDocumentTransaction(
            self.scratch_doc,
            self.block_history,
            self.block_name,
            label,
        )

    def clear_history(self) -> None:
        self.block_history.undo_stack.clear()
        self.block_history.redo_stack.clear()

    def is_dirty(self) -> bool:
        """True if scratch edits exist (undo stack non-empty after user transactions)."""
        return bool(self.block_history.undo_stack)

    def apply_to(self, diagram: LogicDiagram) -> None:
        """Merge scratch block into main document (does not push main undo)."""

        replace_main_block_from_scratch(
            diagram.doc,
            self.scratch_doc,
            self.block_name,
            scratch_block_name=self.scratch_block_name,
        )
        diagram.mark_modified()

    @staticmethod
    def open_existing(main_doc: Drawing, block_name: str) -> BlockEditSession:
        scratch = create_scratch_with_block_from_main(main_doc, block_name)
        return BlockEditSession(scratch_doc=scratch, block_name=block_name, is_new_block=False)

    @staticmethod
    def open_new(block_name: str) -> BlockEditSession:
        scratch = create_scratch_for_new_block(block_name)
        return BlockEditSession(scratch_doc=scratch, block_name=block_name, is_new_block=True)
