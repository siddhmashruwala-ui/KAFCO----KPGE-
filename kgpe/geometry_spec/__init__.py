# -*- coding: utf-8 -*-
"""
kgpe.geometry_spec - Engineering Specification Orchestration and Geometry
Handoff (Phase 3 / Prompt 11).

Completes Phase 3 by defining the stable boundary between engineering
resolution and parametric geometry generation:

    EngineeringRequest -> EngineeringResolver -> ResolvedEngineeringSpecification
        -> GeometrySpecificationCompiler -> GeometrySpecification -> (future Geometry Kernel)

This package stops at GeometrySpecification. It never generates geometry,
never modifies kgpe/generator.py or kgpe/rules/*.py, and never modifies the
frozen canonical data layer (Prompt 9) or the resolver (Prompt 10) - it is
built strictly ON TOP of both.
"""
from .identity import EngineeringObjectIdentity, IdentityConstructionError
from .dimension_bundle import ResolvedDimension, EngineeringDimensionBundle
from .readiness import GeometryReadinessStatus, ALL_GEOMETRY_READINESS_STATUSES, readiness_for_resolution_status
from .profile import (
    GeometryProfile, PROFILE_REGISTRY, find_profile, all_profiles, PROFILE_SCHEMA_VERSION,
    MFR_NOT_APPLICABLE, MFR_OPTIONAL, MFR_REQUIRED,
)
from .spec import GeometrySpecification
from .fingerprint import GEOMETRY_SPEC_SCHEMA_VERSION, compute_geometry_specification_fingerprint
from .compiler import GeometrySpecificationCompiler, compile_geometry_specification
from .orchestration import (
    OrchestrationStage, GeometryPreparationResult, prepare_geometry_specification,
    BatchStatus, ALL_BATCH_STATUSES, BatchGeometryPreparationResult, prepare_geometry_specifications_batch,
)
from . import discovery
from . import coverage

GEOMETRY_SPEC_PACKAGE_SCHEMA_VERSION = "geometry-spec-package-2026.07.15"

__all__ = [
    "EngineeringObjectIdentity", "IdentityConstructionError",
    "ResolvedDimension", "EngineeringDimensionBundle",
    "GeometryReadinessStatus", "ALL_GEOMETRY_READINESS_STATUSES", "readiness_for_resolution_status",
    "GeometryProfile", "PROFILE_REGISTRY", "find_profile", "all_profiles", "PROFILE_SCHEMA_VERSION",
    "MFR_NOT_APPLICABLE", "MFR_OPTIONAL", "MFR_REQUIRED",
    "GeometrySpecification", "GEOMETRY_SPEC_SCHEMA_VERSION", "compute_geometry_specification_fingerprint",
    "GeometrySpecificationCompiler", "compile_geometry_specification",
    "OrchestrationStage", "GeometryPreparationResult", "prepare_geometry_specification",
    "BatchStatus", "ALL_BATCH_STATUSES", "BatchGeometryPreparationResult", "prepare_geometry_specifications_batch",
    "discovery", "coverage", "GEOMETRY_SPEC_PACKAGE_SCHEMA_VERSION",
]
