"""WireService: LWPOLYLINE wiring, Manhattan routing, bridges."""

from __future__ import annotations

from logic_cad.core.services.wire_service.mixins.bridge import WireServiceBridgeMixin
from logic_cad.core.services.wire_service.mixins.branch import WireServiceBranchMixin
from logic_cad.core.services.wire_service.mixins.connection import WireServiceConnectionMixin
from logic_cad.core.services.wire_service.mixins.core import WireServiceCoreMixin
from logic_cad.core.services.wire_service.mixins.gate_input import WireServiceGateInputMixin
from logic_cad.core.services.wire_service.mixins.maintenance import WireServiceMaintenanceMixin


class WireService(
    WireServiceCoreMixin,
    WireServiceGateInputMixin,
    WireServiceConnectionMixin,
    WireServiceBridgeMixin,
    WireServiceBranchMixin,
    WireServiceMaintenanceMixin,
):
    """Wires (LWPOLYLINE), Manhattan route, bridges."""
