"""Document transaction boundary and DocumentDelta construction."""

from __future__ import annotations

from typing import Any

from logic_cad.core.undo.entity_serialize import snapshot_graphic_entities
from logic_cad.core.undo.history import (
    DocumentDelta,
    EntitySnapshot,
    apply_delta,
    make_entity_snapshot,
)


def _payload_equal(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return a == b


def compute_delta(
    label: str,
    layout_name: str,
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]],
    doc,
) -> DocumentDelta:
    """Diff two graphic-entity snapshots (handle -> payload)."""
    h_before = set(before)
    h_after = set(after)
    added_h = h_after - h_before
    removed_h = h_before - h_after
    common = h_before & h_after

    added: list[EntitySnapshot] = []
    removed: list[EntitySnapshot] = []
    modified_before: list[EntitySnapshot] = []
    modified_after: list[EntitySnapshot] = []

    for h in sorted(added_h):
        p = after[h]
        e = doc.entitydb.get(h)
        if e is None:
            continue
        added.append(make_entity_snapshot(doc, e))

    for h in sorted(removed_h):
        p = before[h]
        removed.append(
            EntitySnapshot(
                handle=h,
                dxftype=p["dxftype"],
                owner=str(p.get("owner")),
                payload=p,
            )
        )

    for h in sorted(common):
        pb, pa = before[h], after[h]
        if _payload_equal(pb, pa):
            continue
        eb = doc.entitydb.get(h)
        if eb is None:
            continue
        modified_before.append(
            EntitySnapshot(
                handle=h,
                dxftype=pb["dxftype"],
                owner=str(pb.get("owner")),
                payload=pb,
            )
        )
        modified_after.append(make_entity_snapshot(doc, eb))

    return DocumentDelta(
        label=label,
        layout_name=layout_name,
        added=added,
        removed=removed,
        modified_before=modified_before,
        modified_after=modified_after,
        table_changes={},
    )


class DocumentTransaction:
    """UI operation boundary: commit pushes DocumentDelta; rollback restores before state."""

    def __init__(self, diagram: Any, label: str) -> None:
        self._diagram = diagram
        self._label = label
        self._before: dict[str, dict[str, Any]] | None = None
        self._committed = False
        self._rolled_back = False

    def __enter__(self) -> DocumentTransaction:
        self._diagram._on_transaction_begin(self._label)
        self._before = snapshot_graphic_entities(self._diagram.doc)
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
        self._diagram._on_transaction_pre_commit(self._label)
        after = snapshot_graphic_entities(self._diagram.doc)
        delta = compute_delta(
            self._label,
            self._diagram.current_layout_name,
            self._before,
            after,
            self._diagram.doc,
        )
        self._diagram.history.push(delta)
        self._diagram.rebuild_index()
        if delta.added or delta.removed or delta.modified_after:
            self._diagram.mark_modified()
        self._committed = True

    def rollback(self) -> None:
        if self._before is None or self._rolled_back:
            return

        after = snapshot_graphic_entities(self._diagram.doc)
        delta = compute_delta(
            self._label,
            self._diagram.current_layout_name,
            self._before,
            after,
            self._diagram.doc,
        )
        apply_delta(self._diagram.doc, delta, undo=True)
        self._diagram.rebuild_index()
        self._diagram._on_transaction_rollback(self._label)
        self._rolled_back = True
