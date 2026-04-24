"""Public entry for the wire LWPOLYLINE service (:class:`WireService`).

Geometry and port helpers are not re-exported here; import from
``logic_cad.core.routing`` (e.g. ``wire_polyline_geometry``, ``wire_path_metrics``)
or ``logic_cad.core.model.wire_port_helpers`` as needed.
"""

from __future__ import annotations

from logic_cad.core.services.wire_service.service import WireService

__all__ = ["WireService"]
