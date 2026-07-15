# -*- coding: utf-8 -*-
"""
kgpe.geometry.result
========================
Prompt 12 Sec.4-5: `GeometryResult` (the stable, serializable output of
the geometry kernel) and the geometry-generation status vocabulary. No
rendering-specific styling (colours/lighting/camera/UI state) is ever
included - this is engineering geometry, not a hologram payload.
"""
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any

from .version import GEOMETRY_RESULT_SCHEMA_VERSION


class GeometryGenerationStatus:
    GEOMETRY_GENERATED = "GEOMETRY_GENERATED"
    GEOMETRY_SPEC_NOT_READY = "GEOMETRY_SPEC_NOT_READY"
    UNSUPPORTED_GEOMETRY_PROFILE = "UNSUPPORTED_GEOMETRY_PROFILE"
    CONSTRUCTION_RULE_UNAVAILABLE = "CONSTRUCTION_RULE_UNAVAILABLE"
    INVALID_ENGINEERING_DIMENSIONS = "INVALID_ENGINEERING_DIMENSIONS"
    GEOMETRY_VALIDATION_FAILED = "GEOMETRY_VALIDATION_FAILED"
    GEOMETRY_GENERATION_FAILED = "GEOMETRY_GENERATION_FAILED"


class TopologyRepresentation:
    """Prompt 13 Sec.29: honest topology/representation classification -
    a product builder must self-report exactly one of these; the kernel
    never infers or defaults one on the builder's behalf."""
    HOLLOW_SWEPT_SOLID = "HOLLOW_SWEPT_SOLID"
    SOLID_EXTERNAL_ENVELOPE = "SOLID_EXTERNAL_ENVELOPE"
    DETERMINISTIC_MULTI_FEATURE_MESH_NON_MANIFOLD_AT_INTERSECTION = \
        "DETERMINISTIC_MULTI_FEATURE_MESH_NON_MANIFOLD_AT_INTERSECTION"


ALL_TOPOLOGY_REPRESENTATIONS = frozenset({
    TopologyRepresentation.HOLLOW_SWEPT_SOLID,
    TopologyRepresentation.SOLID_EXTERNAL_ENVELOPE,
    TopologyRepresentation.DETERMINISTIC_MULTI_FEATURE_MESH_NON_MANIFOLD_AT_INTERSECTION,
})


ALL_GEOMETRY_GENERATION_STATUSES = frozenset({
    GeometryGenerationStatus.GEOMETRY_GENERATED, GeometryGenerationStatus.GEOMETRY_SPEC_NOT_READY,
    GeometryGenerationStatus.UNSUPPORTED_GEOMETRY_PROFILE, GeometryGenerationStatus.CONSTRUCTION_RULE_UNAVAILABLE,
    GeometryGenerationStatus.INVALID_ENGINEERING_DIMENSIONS, GeometryGenerationStatus.GEOMETRY_VALIDATION_FAILED,
    GeometryGenerationStatus.GEOMETRY_GENERATION_FAILED,
})


@dataclass
class GeometryResult:
    generation_status: str
    schema_version: str = GEOMETRY_RESULT_SCHEMA_VERSION
    geometry_type: Optional[str] = None

    geometry_specification_fingerprint: Optional[str] = None
    data_layer_fingerprint: Optional[str] = None
    geometry_kernel_version: Optional[str] = None
    construction_rule_versions: Dict[str, str] = field(default_factory=dict)
    geometry_fingerprint: Optional[str] = None

    topology_summary: Dict[str, Any] = field(default_factory=dict)
    dimensional_validation_summary: Dict[str, Any] = field(default_factory=dict)
    geometry_validation_summary: Dict[str, Any] = field(default_factory=dict)

    # Prompt 13 Sec.29: explicit, honest topology/representation
    # classification - e.g. "HOLLOW_SWEPT_SOLID", "SOLID_EXTERNAL_ENVELOPE",
    # "DETERMINISTIC_MULTI_FEATURE_MESH_NON_MANIFOLD_AT_INTERSECTION".
    # None for Prompt 12 results (field added additively - never breaks
    # existing GeometryResult construction/serialization).
    topology_representation: Optional[str] = None
    # Prompt 13 Sec.5: deterministic connection-port metadata (list of
    # kgpe.geometry.ports.ConnectionPort.to_dict()). Empty for products
    # that don't yet expose ports (e.g. Prompt 12's pipe/elbow).
    connection_ports: List[Dict[str, Any]] = field(default_factory=list)

    generation_trace: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    geometry_payload: Optional[Dict[str, Any]] = None

    def is_generated(self):
        return self.generation_status == GeometryGenerationStatus.GEOMETRY_GENERATED

    def to_dict(self):
        return asdict(self)
