"""DocumentDelta stack for Undo/Redo."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ezdxf.document import Drawing

from logic_cad.core.model.xdata import get_uid
from logic_cad.core.undo.entity_serialize import restore_entity_from_payload, serialize_entity


@dataclass
class EntitySnapshot:
    handle: str
    dxftype: str
    owner: str | None
    payload: dict[str, Any]


@dataclass
class DocumentDelta:
    label: str
    layout_name: str
    added: list[EntitySnapshot]
    removed: list[EntitySnapshot]
    modified_before: list[EntitySnapshot]
    modified_after: list[EntitySnapshot]
    table_changes: dict[str, Any] = field(default_factory=dict)


def make_entity_snapshot(doc: Drawing, entity) -> EntitySnapshot:
    payload = serialize_entity(doc, entity)
    owner = payload.get("owner")
    owner_s = None
    if owner:
        owner_s = f"{owner['kind']}:{owner['name']}"
    return EntitySnapshot(
        handle=entity.dxf.handle,
        dxftype=entity.dxftype(),
        owner=owner_s,
        payload=payload,
    )


def _uid_from_snapshot(s: EntitySnapshot) -> str | None:
    p = s.payload
    x = p.get("xdata_ld_app")
    if not x:
        return None
    for code, val in x:
        if code == 1000 and str(val).startswith("uid:"):
            return str(val).split(":", 1)[1]
    return None


def find_entity_by_uid(doc: Drawing, uid: str):
    """Scan entitydb for entity with LD_APP uid."""
    for handle in doc.entitydb.keys():
        e = doc.entitydb.get(handle)
        if e is None or not getattr(e, "is_alive", True):
            continue
        u = get_uid(e)
        if u == uid:
            return e
    return None


def destroy_entity(doc: Drawing, entity) -> None:
    """Remove entity from drawing (INSERT: remove child ATTRIB first)."""
    if entity.dxftype() == "INSERT":
        for a in list(entity.attribs):
            doc.entitydb.delete_entity(a)
    doc.entitydb.delete_entity(entity)


def apply_delta(doc: Drawing, delta: DocumentDelta, *, undo: bool) -> None:
    """Apply delta forward (redo) or backward (undo)."""
    if undo:
        # Undo: reverse the transaction
        # 1) Remove what was added
        for snap in reversed(delta.added):
            uid = _uid_from_snapshot(snap)
            if uid:
                e = find_entity_by_uid(doc, uid)
                if e:
                    destroy_entity(doc, e)
            else:
                e = doc.entitydb.get(snap.handle)
                if e and getattr(e, "is_alive", True):
                    destroy_entity(doc, e)
        # 2) Restore removed
        for snap in delta.removed:
            restore_entity_from_payload(doc, snap.payload)
        # 3) Modified: restore before
        for snap in delta.modified_before:
            uid = _uid_from_snapshot(snap)
            if uid:
                e = find_entity_by_uid(doc, uid)
                if e:
                    destroy_entity(doc, e)
            restore_entity_from_payload(doc, snap.payload)
    else:
        # Redo: apply forward
        for snap in delta.removed:
            uid = _uid_from_snapshot(snap)
            if uid:
                e = find_entity_by_uid(doc, uid)
                if e:
                    destroy_entity(doc, e)
            else:
                e = doc.entitydb.get(snap.handle)
                if e and getattr(e, "is_alive", True):
                    destroy_entity(doc, e)
        for snap in delta.added:
            restore_entity_from_payload(doc, snap.payload)
        for snap in delta.modified_after:
            uid = _uid_from_snapshot(snap)
            if uid:
                e = find_entity_by_uid(doc, uid)
                if e:
                    destroy_entity(doc, e)
            restore_entity_from_payload(doc, snap.payload)


@dataclass
class HistoryService:
    undo_stack: list[DocumentDelta] = field(default_factory=list)
    redo_stack: list[DocumentDelta] = field(default_factory=list)

    def push(self, delta: DocumentDelta) -> None:
        self.undo_stack.append(delta)
        self.redo_stack.clear()

    def undo(self, diagram) -> bool:
        if not self.undo_stack:
            return False
        delta = self.undo_stack.pop()
        apply_delta(diagram.doc, delta, undo=True)
        self.redo_stack.append(delta)
        diagram.rebuild_index()
        return True

    def redo(self, diagram) -> bool:
        if not self.redo_stack:
            return False
        delta = self.redo_stack.pop()
        apply_delta(diagram.doc, delta, undo=False)
        self.undo_stack.append(delta)
        diagram.rebuild_index()
        return True
