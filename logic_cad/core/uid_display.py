"""Display-only helpers for long identifiers (full values stay in DXF / model state)."""


def format_uid_display(uid: str | None) -> str:
    """First 8 hex chars of a UUID (hyphens stripped). Non-UUID strings: up to 8 chars as-is."""
    if not uid:
        return "—"
    compact = str(uid).replace("-", "").strip()
    if not compact:
        return "—"
    frag = compact[:8]
    return frag.lower() if frag.isalnum() else frag
