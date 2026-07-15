# -*- coding: utf-8 -*-
"""
kgpe.geometry.pipeline
==========================
Prompt 12 Sec.29-30: the single end-to-end convenience path

    EngineeringRequest -> prepare_geometry_specification() (Prompt 11)
        -> GeometryKernel.generate() (Prompt 12) -> GeometryResult

This module does not add any new resolution/compilation/generation logic
of its own - it only sequences the two already-existing, already-frozen
public entry points (`kgpe.geometry_spec.prepare_geometry_specification`
and `kgpe.geometry.kernel.GeometryKernel.generate`) and preserves EVERY
intermediate stage result and fingerprint on the returned `PipelineResult`
(Sec.29: engineering resolution status, geometry-specification readiness,
geometry generation status, data-layer fingerprint, geometry-specification
fingerprint, and geometry fingerprint - all simultaneously, never
collapsed into a single opaque "ok/fail" flag). Sec.30: an early-stage
failure (engineering resolution / profile selection / dimension
resolution / geometry compilation) is never masked as, or confused with, a
later geometry-generation failure - `failed_stage` always names exactly
which stage produced the final non-success outcome, and generation is
never attempted at all unless the geometry specification is GEOMETRY_READY.
"""
from dataclasses import dataclass
from typing import Optional

from ..geometry_spec import prepare_geometry_specification, OrchestrationStage
from .kernel import GeometryKernel
from .result import GeometryResult, GeometryGenerationStatus


class PipelineStage(OrchestrationStage):
    """Sec.29: extends geometry_spec's own stage vocabulary with the ONE
    additional stage this package introduces - never redefines or renames
    any Prompt-11 stage name."""
    GEOMETRY_GENERATION = "GEOMETRY_GENERATION"


@dataclass
class PipelineResult:
    identity_resolution: object
    dimension_resolution: Optional[object]
    geometry_specification: object
    geometry_result: Optional[GeometryResult]
    failed_stage: Optional[str]

    def is_generated(self):
        return self.geometry_result is not None and self.geometry_result.is_generated()

    def to_dict(self):
        return {
            "identity_resolution": self.identity_resolution.to_dict(),
            "dimension_resolution": self.dimension_resolution.to_dict() if self.dimension_resolution else None,
            "geometry_specification": self.geometry_specification.to_dict(),
            "geometry_result": self.geometry_result.to_dict() if self.geometry_result else None,
            "failed_stage": self.failed_stage,
        }


def run_pipeline(request, resolver=None, generation_parameters=None) -> PipelineResult:
    prep = prepare_geometry_specification(request, resolver=resolver)

    if not prep.is_ready():
        # Sec.30: an upstream (Prompt 11 or earlier) failure - geometry
        # generation is never attempted, and `failed_stage` names the
        # ORIGINAL failing stage exactly as prepare_geometry_specification
        # reported it (never overwritten/relabeled as a generation failure).
        return PipelineResult(
            identity_resolution=prep.identity_resolution,
            dimension_resolution=prep.dimension_resolution,
            geometry_specification=prep.geometry_specification,
            geometry_result=None,
            failed_stage=prep.failed_stage,
        )

    geometry_result = GeometryKernel().generate(prep.geometry_specification, generation_parameters)
    failed_stage = None if geometry_result.is_generated() else PipelineStage.GEOMETRY_GENERATION

    return PipelineResult(
        identity_resolution=prep.identity_resolution,
        dimension_resolution=prep.dimension_resolution,
        geometry_specification=prep.geometry_specification,
        geometry_result=geometry_result,
        failed_stage=failed_stage,
    )
