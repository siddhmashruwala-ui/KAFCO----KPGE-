# -*- coding: utf-8 -*-
"""
kgpe.geometry_spec.spec
===========================
Prompt 11 Sec.7/18: `GeometrySpecification` - the stable, serializable
geometry-INPUT contract. This is a validated engineering identity plus a
set of resolved canonical dimensions and their provenance - it contains no
mesh vertices/triangles/CAD solids/rendering colours/camera/lighting/
visual defaults. Producing one never generates geometry.
"""
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any

from .fingerprint import GEOMETRY_SPEC_SCHEMA_VERSION


@dataclass
class GeometrySpecification:
    readiness_status: str
    schema_version: str = GEOMETRY_SPEC_SCHEMA_VERSION

    engineering_object_identity: Optional[Dict[str, Any]] = None
    required_dimensions: Dict[str, Any] = field(default_factory=dict)
    optional_dimensions: Dict[str, Any] = field(default_factory=dict)

    data_layer_fingerprint: Optional[str] = None
    geometry_specification_fingerprint: Optional[str] = None
    geometry_profile_id: Optional[str] = None
    geometry_profile_version: Optional[str] = None

    source_verification_summary: Dict[str, Any] = field(default_factory=dict)
    compilation_trace: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def is_ready(self):
        from .readiness import GeometryReadinessStatus
        return self.readiness_status == GeometryReadinessStatus.GEOMETRY_READY

    def to_dict(self):
        return asdict(self)
