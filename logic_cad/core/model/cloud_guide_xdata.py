"""Encode/decode revision-cloud guide vertices and pitch in LD_APP XDATA."""

from __future__ import annotations

import json

# DXF XDATA 1000 strings are often limited to 255 chars; stay below for safety.
_CLOUD_PATH_CHUNK_SIZE = 200

CLOUD_SEG_KEY = "cloud_seg"
CLOUD_PATH_KEY_PREFIX = "cloud_path_"


def build_cloud_pitch_xdata_extra(
    segment_length: float,
    guide_vertices: list[tuple[float, float]],
) -> dict[str, str]:
    """Build ``extra`` for :func:`build_ld_app_tags` for USER_CLOUD pitch + guides.

    Args:
        segment_length: Last applied ``revcloud.points(..., segment_length=...)`` value.
        guide_vertices: User outline passed to ``revcloud.points`` (same order as creation).

    Returns:
        String-only map suitable for ``build_ld_app_tags(..., extra=...)``.
    """
    seg = max(1e-3, float(segment_length))
    payload = [[round(float(x), 6), round(float(y), 6)] for x, y in guide_vertices]
    raw = json.dumps(payload, separators=(",", ":"))
    extra: dict[str, str] = {CLOUD_SEG_KEY: f"{float(seg):.12g}"}
    if len(raw) <= _CLOUD_PATH_CHUNK_SIZE:
        extra[CLOUD_PATH_KEY_PREFIX + "0"] = raw
        return extra
    chunks: list[str] = []
    for i in range(0, len(raw), _CLOUD_PATH_CHUNK_SIZE):
        chunks.append(raw[i : i + _CLOUD_PATH_CHUNK_SIZE])
    for idx, part in enumerate(chunks):
        extra[CLOUD_PATH_KEY_PREFIX + str(idx)] = part
    return extra


def parse_cloud_segment_mm(xdata: dict[str, str]) -> float | None:
    """Return stored segment length (mm) if ``cloud_seg`` is present and valid.

    Args:
        xdata: LD_APP dictionary from :func:`read_ld_app_dict`.

    Returns:
        Parsed segment length, or None if missing or invalid.
    """
    raw = xdata.get(CLOUD_SEG_KEY)
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return max(1e-3, float(raw))
    except (TypeError, ValueError):
        return None


def parse_cloud_guide_vertices(xdata: dict[str, str]) -> list[tuple[float, float]] | None:
    """Decode guide vertices from chunked ``cloud_path_*`` keys.

    Args:
        xdata: LD_APP dictionary from :func:`read_ld_app_dict`.

    Returns:
        Guide polyline vertices, or None if missing or invalid JSON.
    """
    parts: list[str] = []
    idx = 0
    while True:
        key = CLOUD_PATH_KEY_PREFIX + str(idx)
        if key not in xdata:
            break
        parts.append(xdata[key])
        idx += 1
    if not parts:
        return None
    raw = "".join(parts)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    out: list[tuple[float, float]] = []
    for item in data:
        if (
            isinstance(item, (list, tuple))
            and len(item) >= 2
            and isinstance(item[0], (int, float))
            and isinstance(item[1], (int, float))
        ):
            out.append((float(item[0]), float(item[1])))
    if len(out) < 2:
        return None
    return out


def strip_cloud_pitch_keys(xdata: dict[str, str]) -> dict[str, str]:
    """Return a copy of *xdata* without cloud pitch / path keys (for merging).

    Args:
        xdata: Arbitrary LD_APP key-value map.

    Returns:
        New dict without ``cloud_seg`` or ``cloud_path_*`` entries.
    """
    drop = {CLOUD_SEG_KEY}
    for k in list(xdata.keys()):
        if k.startswith(CLOUD_PATH_KEY_PREFIX):
            drop.add(k)
    return {k: v for k, v in xdata.items() if k not in drop}
