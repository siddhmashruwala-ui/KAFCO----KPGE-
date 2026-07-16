# -*- coding: utf-8 -*-
"""
kgpe.geometry - Parametric Geometry Kernel and Deterministic Construction
Rules (Phase 4 / Prompt 12).

    GeometrySpecification (kgpe.geometry_spec) -> GeometryKernel.generate()
        -> GeometryResult (mesh + features + construction values + fingerprint)

This package is strictly additive: it never modifies kgpe/generator.py,
kgpe/schema.py, kgpe/rules/*.py, kgpe/dimension_library.py, the frozen
canonical data layer (Prompt 9), the resolver (Prompt 10), or geometry_spec
(Prompt 11) - it consumes GeometrySpecification as its ONLY input contract
and is built strictly on top of all of the above. Public boundary
(`GeometryKernel.generate()` / `generate_geometry()`) never raises - every
outcome is a structured `GeometryResult`.
"""
from .version import (
    GEOMETRY_RESULT_SCHEMA_VERSION, GEOMETRY_KERNEL_VERSION, GENERATION_PARAMETER_SCHEMA_VERSION,
)
from .policy import (
    LENGTH_UNIT, COORDINATE_CONVENTION, LINEAR_TOLERANCE_MM, NEAR_ZERO_MM, ANGULAR_TOLERANCE_RAD,
    DEGENERATE_AREA_THRESHOLD_MM2, FINGERPRINT_ROUNDING_DECIMALS,
    is_effectively_zero, within_tolerance, round_for_fingerprint, degrees_to_radians,
)
from .mesh import Mesh
from .builders import (
    build_hollow_cylinder, build_arc_swept_solid, build_arc_swept_hollow_solid,
    build_solid_cylinder, build_cap_solid, build_frustum_solid, build_tee_multi_feature,
    build_two_arm_multi_feature, build_cross_multi_feature,
)
from .construction_value import ConstructionValue, PROVENANCE_LABEL_DERIVED
from .construction_rules import (
    ConstructionRuleStatus, ALL_CONSTRUCTION_RULE_STATUSES, ConstructionRuleOutcome,
    ConstructionRule, PipeBoreConstructionRule, CapLengthSelectionRule,
    OletReinforcementEnvelopeConstructionRule,
)
from .cross_family import (
    CrossFamilyDependencyRule, FlangeBoreViaPipeScheduleRule, ButtweldWallViaPipeScheduleRule,
    SocketweldBodyOutsideDiameterViaPipeRule,
)
from .socket_geometry import (
    SocketGeometry, SocketFeatureValue, SocketGeometryError, build_socket_geometry, validate_socket_geometry,
    SOCKET_STATUS_AUTHORITATIVE, SOCKET_STATUS_CONSTRUCTION_DERIVED, SOCKET_STATUS_DEPENDENCY_DERIVED,
    SOCKET_STATUS_UNAVAILABLE, ALL_SOCKET_FEATURE_STATUSES,
)
from .outlet_geometry import (
    OutletGeometry, OutletFeatureValue, OutletGeometryError, build_outlet_geometry, validate_outlet_geometry,
    OUTLET_STATUS_AUTHORITATIVE, OUTLET_STATUS_CONSTRUCTION_DERIVED, OUTLET_STATUS_DEPENDENCY_DERIVED,
    OUTLET_STATUS_UNAVAILABLE, ALL_OUTLET_FEATURE_STATUSES,
)
from .reducer_rules import ReducerPerEndOutsideDiameterRule
from .wall_context import WallContext, WallContextError
from .ports import (
    ConnectionPort, PortValidationError, validate_port, validate_ports,
    OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE, OPENING_DIAMETER_PROVENANCE_DERIVED,
    OPENING_DIAMETER_PROVENANCE_NOT_MODELED,
)
from .transition_rules import (
    TeeBranchBlendingRule, CapProfileConstructionRule, ConcentricReducerTransitionRule,
    EccentricReducerOffsetRule,
)
from .tessellation import (
    MIN_RADIAL_SEGMENTS, MIN_SWEEP_SEGMENTS, DEFAULT_RADIAL_SEGMENTS, DEFAULT_SWEEP_SEGMENTS,
    validate_tessellation,
)
from .parameters import (
    GenerationParameters, DEFAULT_PIPE_SEGMENT_LENGTH_MM, PIPE_SEGMENT_LENGTH_LABEL,
)
from .validation import ValidationCheck, ValidationResult, validate_mesh_structure, validate_dimensions
from .measurement import measure_radial_distance, measure_axial_length, measure_bend_radius
from .fingerprint import compute_geometry_fingerprint
from .result import (
    GeometryGenerationStatus, ALL_GEOMETRY_GENERATION_STATUSES, GeometryResult,
    TopologyRepresentation, ALL_TOPOLOGY_REPRESENTATIONS,
)
from .product_api import GeometryInputError, ConstructionRuleUnavailableError, ProductGeometryBuild
from .bolt_pattern import BoltPattern, BoltPatternError, build_bolt_pattern, validate_bolt_pattern
from .mating_interface import (
    MatingInterface, FACE_TYPE_NOT_TRACKED, FACE_TYPE_RAISED_FACE, FACE_TYPE_FLAT_FACE, ALL_FACE_TYPES,
)
from .kernel import GeometryKernel, generate_geometry
from .pipeline import PipelineStage, PipelineResult, run_pipeline
from .products import pipe as product_pipe
from .products import buttweld_elbow as product_buttweld_elbow
from .products import tee as product_tee
from .products import cap as product_cap
from .products import reducer as product_reducer
from .products import flange as product_flange
from .products import socketweld_elbow_tee as product_socketweld_elbow_tee
from .products import socketweld_coupling as product_socketweld_coupling
from .products import socketweld_cap as product_socketweld_cap
from .products import olet as product_olet

GEOMETRY_PACKAGE_SCHEMA_VERSION = "geometry-kernel-package-2026.07.16-p15"

__all__ = [
    "GEOMETRY_RESULT_SCHEMA_VERSION", "GEOMETRY_KERNEL_VERSION", "GENERATION_PARAMETER_SCHEMA_VERSION",
    "LENGTH_UNIT", "COORDINATE_CONVENTION", "LINEAR_TOLERANCE_MM", "NEAR_ZERO_MM", "ANGULAR_TOLERANCE_RAD",
    "DEGENERATE_AREA_THRESHOLD_MM2", "FINGERPRINT_ROUNDING_DECIMALS",
    "is_effectively_zero", "within_tolerance", "round_for_fingerprint", "degrees_to_radians",
    "Mesh", "build_hollow_cylinder", "build_arc_swept_solid", "build_arc_swept_hollow_solid",
    "build_solid_cylinder", "build_cap_solid", "build_frustum_solid", "build_tee_multi_feature",
    "build_two_arm_multi_feature", "build_cross_multi_feature",
    "ConstructionValue", "PROVENANCE_LABEL_DERIVED",
    "ConstructionRuleStatus", "ALL_CONSTRUCTION_RULE_STATUSES", "ConstructionRuleOutcome",
    "ConstructionRule", "PipeBoreConstructionRule", "CapLengthSelectionRule",
    "OletReinforcementEnvelopeConstructionRule",
    "CrossFamilyDependencyRule", "FlangeBoreViaPipeScheduleRule", "ButtweldWallViaPipeScheduleRule",
    "SocketweldBodyOutsideDiameterViaPipeRule",
    "SocketGeometry", "SocketFeatureValue", "SocketGeometryError", "build_socket_geometry",
    "validate_socket_geometry", "SOCKET_STATUS_AUTHORITATIVE", "SOCKET_STATUS_CONSTRUCTION_DERIVED",
    "SOCKET_STATUS_DEPENDENCY_DERIVED", "SOCKET_STATUS_UNAVAILABLE", "ALL_SOCKET_FEATURE_STATUSES",
    "OutletGeometry", "OutletFeatureValue", "OutletGeometryError", "build_outlet_geometry",
    "validate_outlet_geometry", "OUTLET_STATUS_AUTHORITATIVE", "OUTLET_STATUS_CONSTRUCTION_DERIVED",
    "OUTLET_STATUS_DEPENDENCY_DERIVED", "OUTLET_STATUS_UNAVAILABLE", "ALL_OUTLET_FEATURE_STATUSES",
    "ReducerPerEndOutsideDiameterRule", "WallContext", "WallContextError",
    "ConnectionPort", "PortValidationError", "validate_port", "validate_ports",
    "OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE", "OPENING_DIAMETER_PROVENANCE_DERIVED",
    "OPENING_DIAMETER_PROVENANCE_NOT_MODELED",
    "TeeBranchBlendingRule", "CapProfileConstructionRule", "ConcentricReducerTransitionRule",
    "EccentricReducerOffsetRule",
    "MIN_RADIAL_SEGMENTS", "MIN_SWEEP_SEGMENTS", "DEFAULT_RADIAL_SEGMENTS", "DEFAULT_SWEEP_SEGMENTS",
    "validate_tessellation",
    "GenerationParameters", "DEFAULT_PIPE_SEGMENT_LENGTH_MM", "PIPE_SEGMENT_LENGTH_LABEL",
    "ValidationCheck", "ValidationResult", "validate_mesh_structure", "validate_dimensions",
    "measure_radial_distance", "measure_axial_length", "measure_bend_radius",
    "compute_geometry_fingerprint",
    "GeometryGenerationStatus", "ALL_GEOMETRY_GENERATION_STATUSES", "GeometryResult",
    "TopologyRepresentation", "ALL_TOPOLOGY_REPRESENTATIONS",
    "GeometryInputError", "ConstructionRuleUnavailableError", "ProductGeometryBuild",
    "BoltPattern", "BoltPatternError", "build_bolt_pattern", "validate_bolt_pattern",
    "MatingInterface", "FACE_TYPE_NOT_TRACKED", "FACE_TYPE_RAISED_FACE", "FACE_TYPE_FLAT_FACE", "ALL_FACE_TYPES",
    "GeometryKernel", "generate_geometry",
    "PipelineStage", "PipelineResult", "run_pipeline",
    "product_pipe", "product_buttweld_elbow", "product_tee", "product_cap", "product_reducer", "product_flange",
    "product_socketweld_elbow_tee", "product_socketweld_coupling", "product_socketweld_cap", "product_olet",
    "GEOMETRY_PACKAGE_SCHEMA_VERSION",
]
