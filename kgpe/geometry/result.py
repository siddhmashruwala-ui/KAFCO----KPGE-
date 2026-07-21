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
    # Prompt 14 Sec.12-13/31: a hollow annular body (through-bore flange)
    # whose bolt holes are represented as deterministic FEATURE METADATA
    # (position/diameter/bolt-circle layout - see kgpe.geometry.
    # bolt_pattern.BoltPattern) rather than as actual boolean-cut geometry
    # in the mesh - the mesh surface itself remains a plain solid annular
    # disc, never claimed as boolean-cut or watertight-with-holes.
    HOLLOW_ANNULAR_BODY_WITH_BOLT_HOLE_METADATA_NO_BOOLEAN_CUT = \
        "HOLLOW_ANNULAR_BODY_WITH_BOLT_HOLE_METADATA_NO_BOOLEAN_CUT"
    # Prompt 14 Sec.8/31: same as above but for a flange body with no
    # resolved bore (external-envelope solid disc) that STILL carries a
    # bolt-hole metadata pattern - distinguished from the buttweld-elbow's
    # plain SOLID_EXTERNAL_ENVELOPE (which has no bolt pattern at all).
    SOLID_EXTERNAL_ENVELOPE_WITH_BOLT_HOLE_METADATA_NO_BOOLEAN_CUT = \
        "SOLID_EXTERNAL_ENVELOPE_WITH_BOLT_HOLE_METADATA_NO_BOOLEAN_CUT"
    # Prompt 15 Sec.13: socket-weld/olet bodies whose socket cavities (or,
    # for olets, run/branch interfaces) are represented as deterministic
    # FEATURE METADATA (kgpe.geometry.socket_geometry.SocketGeometry /
    # kgpe.geometry.outlet_geometry.OutletGeometry) rather than boolean-
    # cut into the mesh - mirrors the bolt-hole-metadata pattern exactly.
    # SOLID form: a single straight/cap body (coupling, half-coupling,
    # cap). MULTI_FEATURE form: two-or-more overlapping arms (elbow, tee,
    # cross) - non-manifold at the intersection, exactly like
    # DETERMINISTIC_MULTI_FEATURE_MESH_NON_MANIFOLD_AT_INTERSECTION, but
    # explicitly naming the additional socket metadata.
    SOLID_EXTERNAL_ENVELOPE_WITH_SOCKET_METADATA_NO_BOOLEAN_CUT = \
        "SOLID_EXTERNAL_ENVELOPE_WITH_SOCKET_METADATA_NO_BOOLEAN_CUT"
    MULTI_FEATURE_MESH_WITH_SOCKET_METADATA_NO_BOOLEAN_CUT = \
        "MULTI_FEATURE_MESH_WITH_SOCKET_METADATA_NO_BOOLEAN_CUT"
    # Prompt 15 Sec.13: an olet's construction-derived frustum envelope
    # (base OD -> branch bore diameter) with run/branch interface
    # metadata attached - never claimed as an MSS SP-97-published
    # contour (see OletReinforcementEnvelopeConstructionRule).
    CONSTRUCTION_DERIVED_ENVELOPE_WITH_INTERFACE_METADATA_NO_BOOLEAN_CUT = \
        "CONSTRUCTION_DERIVED_ENVELOPE_WITH_INTERFACE_METADATA_NO_BOOLEAN_CUT"
    # Prompt 42: a weld-neck/long-weld-neck flange body WITH a modeled hub
    # (kgpe.geometry.builders.build_hollow_cylinder_with_hub /
    # build_solid_cylinder_with_hub) - two coaxially-stacked cylindrical
    # solids (flat body + straight-cylinder hub, see products/flange.py's
    # module docstring for the taper simplification) touching at one
    # shared interface plane, never boolean-fused. Distinguished from the
    # plain (no-hub) HOLLOW_ANNULAR_BODY_.../SOLID_EXTERNAL_ENVELOPE_...
    # variants above, which remain the correct classification whenever
    # hub facts are unavailable (JIS_B2220, EN_1092-1, all five Prompt 41
    # non-weld-neck-family subtypes).
    HOLLOW_ANNULAR_BODY_WITH_HUB_COMPOSITE_NO_BOOLEAN_CUT = \
        "HOLLOW_ANNULAR_BODY_WITH_HUB_COMPOSITE_NO_BOOLEAN_CUT"
    SOLID_EXTERNAL_ENVELOPE_WITH_HUB_COMPOSITE_NO_BOOLEAN_CUT = \
        "SOLID_EXTERNAL_ENVELOPE_WITH_HUB_COMPOSITE_NO_BOOLEAN_CUT"
    # 2026-07-21 (nipoflange product generator): a single continuous
    # revolved solid built from a construction-derived profile (flange
    # disc + hub fillet + barrel [+ reducing transition + weldolet outlet
    # body] + weld bevel, per kgpe.geometry.transition_rules.
    # NipoflangeNeckAllocationRule), closed with honest flat discs at
    # both ends. No bore is modeled (purchaser-specified per the KAFCO
    # source's own Note 4 - never fabricated) and no boolean cuts are
    # performed anywhere.
    SOLID_REVOLVED_COMPOSITE_CONSTRUCTION_ENVELOPE_NO_BOOLEAN_CUT = \
        "SOLID_REVOLVED_COMPOSITE_CONSTRUCTION_ENVELOPE_NO_BOOLEAN_CUT"
    # 2026-07-21 (nipoflange rule v4): same construction-derived revolved
    # composite, but with a genuine through-bore wall (derived from the
    # order's stated schedule via cross-family pipe ID) and annular
    # closures at both ends - still no boolean cuts anywhere.
    HOLLOW_REVOLVED_COMPOSITE_CONSTRUCTION_ENVELOPE_NO_BOOLEAN_CUT = \
        "HOLLOW_REVOLVED_COMPOSITE_CONSTRUCTION_ENVELOPE_NO_BOOLEAN_CUT"


ALL_TOPOLOGY_REPRESENTATIONS = frozenset({
    TopologyRepresentation.HOLLOW_SWEPT_SOLID,
    TopologyRepresentation.SOLID_EXTERNAL_ENVELOPE,
    TopologyRepresentation.DETERMINISTIC_MULTI_FEATURE_MESH_NON_MANIFOLD_AT_INTERSECTION,
    TopologyRepresentation.HOLLOW_ANNULAR_BODY_WITH_BOLT_HOLE_METADATA_NO_BOOLEAN_CUT,
    TopologyRepresentation.SOLID_EXTERNAL_ENVELOPE_WITH_BOLT_HOLE_METADATA_NO_BOOLEAN_CUT,
    TopologyRepresentation.SOLID_EXTERNAL_ENVELOPE_WITH_SOCKET_METADATA_NO_BOOLEAN_CUT,
    TopologyRepresentation.MULTI_FEATURE_MESH_WITH_SOCKET_METADATA_NO_BOOLEAN_CUT,
    TopologyRepresentation.CONSTRUCTION_DERIVED_ENVELOPE_WITH_INTERFACE_METADATA_NO_BOOLEAN_CUT,
    TopologyRepresentation.HOLLOW_ANNULAR_BODY_WITH_HUB_COMPOSITE_NO_BOOLEAN_CUT,
    TopologyRepresentation.SOLID_EXTERNAL_ENVELOPE_WITH_HUB_COMPOSITE_NO_BOOLEAN_CUT,
    TopologyRepresentation.SOLID_REVOLVED_COMPOSITE_CONSTRUCTION_ENVELOPE_NO_BOOLEAN_CUT,
    TopologyRepresentation.HOLLOW_REVOLVED_COMPOSITE_CONSTRUCTION_ENVELOPE_NO_BOOLEAN_CUT,
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
