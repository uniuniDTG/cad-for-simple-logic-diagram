"""Undo transactions against a standalone :class:`Drawing` (e.g. block-edit scratch doc)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ezdxf.document import Drawing

from logic_cad.core.undo.entity_serialize import snapshot_graphic_entities
from logic_cad.core.undo.history import HistoryService, apply_delta
from logic_cad.core.undo.transaction import compute_delta


@dataclass
class ScratchUndoDiagram:
    """Minimal adapter so :class:`HistoryService` can run without a :class:`LogicDiagram`."""

    doc: Drawing

    def rebuild_index(self) -> None:
        """No index for scratch documents."""


class ScratchDocumentTransaction:
    """Like :class:`DocumentTransaction` but targets *doc* / *history* only (no main diagram)."""

    def __init__(self, doc: Drawing, history: HistoryService, layout_name: str, label: str) -> None:
        self._doc = doc
        self._history = history
        self._layout_name = layout_name
        self._label = label
        self._before: dict[str, dict[str, Any]] | None = None
        self._committed = False
        self._rolled_back = False

    def __enter__(self) -> ScratchDocumentTransaction:
        self._before = snapshot_graphic_entities(self._doc)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._committed or self._rolled_back:
            return
        if exc_type is not None:
            self.rollback()
        else:
            self.commit()

    def commit(self) -> None:
        if self._committed:
            return
        if self._before is None:
            raise RuntimeError("トランザクションが開始されていません。")
        after = snapshot_graphic_entities(self._doc)
        delta = compute_delta(self._label, self._layout_name, self._before, after, self._doc)
        self._history.push(delta)
        self._committed = True

    def rollback(self) -> None:
        if self._before is None or self._rolled_back:
            return

        after = snapshot_graphic_entities(self._doc)
        delta = compute_delta(self._label, self._layout_name, self._before, after, self._doc)
        apply_delta(self._doc, delta, undo=True)
        self._rolled_back = True


def scratch_undo(diagram: ScratchUndoDiagram, history: HistoryService) -> bool:
    if not history.undo_stack:
        return False
    return history.undo(diagram)


def scratch_redo(diagram: ScratchUndoDiagram, history: HistoryService) -> bool:
    if not history.redo_stack:
        return False
    return history.redo(diagram)
