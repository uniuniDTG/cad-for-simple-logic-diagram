"""Point formatting for routing debug logs (package-internal)."""


def fmt_pt(pt: tuple[float, float]) -> str:
    return f"({pt[0]:.1f},{pt[1]:.1f})"
