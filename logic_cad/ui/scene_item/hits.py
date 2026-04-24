"""Scene-space hit distances in DXF millimeters (scene coordinates = DXF mm).

``DEFAULT_SCENE_HIT_TOL_MM`` is shared by wire parallel-segment pick, user-line
endpoint pick, and OSNAP candidate selection so interaction tolerances stay aligned.
"""

from __future__ import annotations

DEFAULT_SCENE_HIT_TOL_MM: float = 3.0
