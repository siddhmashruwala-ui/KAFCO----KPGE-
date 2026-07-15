# -*- coding: utf-8 -*-
"""
kgpe.geometry.ports
=======================
Prompt 13 Sec.5-6: a reusable `ConnectionPort` model - deterministic
geometry metadata describing where a generated fitting connects to
neighbouring pipe/fittings. This is metadata ONLY (Sec.5: "do not build
assembly connectivity yet") - no assembly placement, no mating logic, no
UI. Every product builder that exposes ports returns a list of these,
validated by `validate_port()`/`validate_ports()` before being attached to
a `GeometryResult`.
"""
from dataclasses import dataclass, field, asdict
from typing import Optional, Tuple, Dict, Any

from .primitives import vec_length
from .policy import NEAR_ZERO_MM, is_effectively_zero

OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE = "AUTHORITATIVE_ENGINEERING_DIMENSION"
OPENING_DIAMETER_PROVENANCE_DERIVED = "DERIVED_CONSTRUCTION_VALUE"
OPENING_DIAMETER_PROVENANCE_NOT_MODELED = "NOT_MODELED"


@dataclass(frozen=True)
class ConnectionPort:
    port_id: str
    role: str
    position: Tuple[float, float, float]
    direction: Tuple[float, float, float]  # outward-facing unit vector
    size_identity: Dict[str, Any] = field(default_factory=dict)  # e.g. {"size_system": "nps", "size": "6"}
    opening_diameter_mm: Optional[float] = None
    opening_diameter_provenance: str = OPENING_DIAMETER_PROVENANCE_NOT_MODELED

    def to_dict(self):
        return asdict(self)


class PortValidationError(Exception):
    """Raised for a genuinely malformed port (non-finite position, zero-
    length direction) - a programmer error in a product builder, never an
    expected engineering outcome."""
    pass


def validate_port(port: ConnectionPort):
    """Sec.6: port positions finite, direction normalized (unit length),
    opening diameter positive when present, role identity preserved
    (non-empty). Raises PortValidationError on a genuine defect - product
    builders should never emit an invalid port in the first place."""
    import math
    for v in port.position:
        if not math.isfinite(v):
            raise PortValidationError(f"Port {port.port_id!r} position has non-finite coordinate: {port.position!r}")
    for v in port.direction:
        if not math.isfinite(v):
            raise PortValidationError(f"Port {port.port_id!r} direction has non-finite coordinate: {port.direction!r}")
    length = vec_length(port.direction)
    if abs(length - 1.0) > 1e-6:
        raise PortValidationError(
            f"Port {port.port_id!r} direction is not a unit vector (length={length!r}): {port.direction!r}")
    if not port.role:
        raise PortValidationError(f"Port {port.port_id!r} has no role identity.")
    if port.opening_diameter_mm is not None and port.opening_diameter_mm <= NEAR_ZERO_MM:
        raise PortValidationError(
            f"Port {port.port_id!r} opening_diameter_mm must be positive when present, "
            f"got {port.opening_diameter_mm!r}.")
    return True


def validate_ports(ports):
    for p in ports:
        validate_port(p)
    return True
