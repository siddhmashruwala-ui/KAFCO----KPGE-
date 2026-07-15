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
from .builders import build_hollow_cylinder, build_arc_swept_solid
from .construction_value import ConstructionValue, PROVENANCE_LABEL_DERIVED
from .construction_rules import (
    ConstructionRuleStatus, ALL_CONSTRUCTION_RULE_STATUSES, ConstructionRuleOutcome,
    ConstructionRule, PipeBoreConstructionRule,
)
from .cross_family import CrossFamilyDependencyRule, FlangeBoreViaPipeScheduleRule
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
from .result import GeometryGenerationStatus, ALL_GEOMETRY_GENERATION_STATUSES, GeometryResult
from .product_api import GeometryInputError, ConstructionRuleUnavailableError, ProductGeometryBuild
from .kernel import GeometryKernel, generate_geometry
from .pipeline import PipelineResult, run_pipeline

GEOMETRY_PACKAGE_SCHEMA_VERSION = "geometry-kernel-package-2026.07.15"

__all__ = [
    "GEOMETRY_RESULT_SCHEMA_VERSION", "GEOMETRY_KERNEL_VERSION", "GENERATION_PARAMETER_SCHEMA_VERSION",
    "LENGTH_UNIT", "COORDINATE_CONVENTION", "LINEAR_TOLERANCE_MM", "NEAR_ZERO_MM", "ANGULAR_TOLERANCE_RAD",
    "DEGENERATE_AREA_THRESHOLD_MM2", "FINGERPRINT_ROUNDING_DECIMALS",
    "is_effectively_zero", "within_tolerance", "round_for_fingerprint", "degrees_to_radians",
    "Mesh", "build_hollow_cylinder", "build_arc_swept_solid",
    "ConstructionValue", "PROVENANCE_LABEL_DERIVED",
    "ConstructionRuleStatus", "ALL_CONSTRUCTION_RULE_STATUSES", "ConstructionRuleOutcome",
    "ConstructionRule", "PipeBoreConstructionRule",
    "CrossFamilyDependencyRule", "FlangeBoreViaPipeScheduleRule",
    "MIN_RADIAL_SEGMENTS", "MIN_SWEEP_SEGMENTS", "DEFAULT_RADIAL_SEGMENTS", "DEFAULT_SWEEP_SEGMENTS",
    "validate_tessellation",
    "GenerationParameters", "DEFAULT_PIPE_SEGMENT_LENGTH_MM", "PIPE_SEGMENT_LENGTH_LABEL",
    "ValidationCheck", "ValidationResult", "validate_mesh_structure", "validate_dimensions",
    "measure_radial_distance", "measure_axial_length", "measure_bend_radius",
    "compute_geometry_fingerprint",
    "GeometryGenerationStatus", "ALL_GEOMETRY_GENERATION_STATUSES", "GeometryResult",
    "GeometryInputError", "ConstructionRuleUnavailableError", "ProductGeometryBuild",
    "GeometryKernel", "generate_geometry",
    "PipelineResult", "run_pipeline",
    "GEOMETRY_PACKAGE_SCHEMA_VERSION",
]
