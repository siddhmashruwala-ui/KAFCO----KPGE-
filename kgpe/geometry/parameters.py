# -*- coding: utf-8 -*-
"""
kgpe.geometry.parameters
============================
Prompt 12 Sec.19: generation-only parameters - explicitly NOT engineering
-standard dimensions, and kept entirely separate from `EngineeringRequest`
/`ResolvedEngineeringSpecification`/`GeometrySpecification`. These
parameters affect the resulting mesh (and therefore the geometry
fingerprint - Sec.19/27) but never affect engineering identity or
resolution.
"""
from dataclasses import dataclass, asdict
from typing import Optional

from .version import GENERATION_PARAMETER_SCHEMA_VERSION
from .tessellation import DEFAULT_RADIAL_SEGMENTS, DEFAULT_SWEEP_SEGMENTS, validate_tessellation

# Sec.18: pipe segment length is a DISPLAY/GENERATION parameter, never an
# ASME/JIS/EN authoritative dimension. Named and versioned explicitly so
# no caller can mistake it for canonical engineering truth.
DEFAULT_PIPE_SEGMENT_LENGTH_MM = 300.0
PIPE_SEGMENT_LENGTH_LABEL = "GEOMETRY_DISPLAY_PARAMETER_NOT_AUTHORITATIVE"


@dataclass(frozen=True)
class GenerationParameters:
    schema_version: str = GENERATION_PARAMETER_SCHEMA_VERSION
    pipe_segment_length_mm: float = DEFAULT_PIPE_SEGMENT_LENGTH_MM
    radial_segments: int = DEFAULT_RADIAL_SEGMENTS
    sweep_segments: int = DEFAULT_SWEEP_SEGMENTS

    def __post_init__(self):
        validate_tessellation(self.radial_segments, self.sweep_segments)
        if not (self.pipe_segment_length_mm > 0):
            raise ValueError(f"pipe_segment_length_mm must be positive, got {self.pipe_segment_length_mm!r}")

    def to_dict(self):
        return asdict(self)
