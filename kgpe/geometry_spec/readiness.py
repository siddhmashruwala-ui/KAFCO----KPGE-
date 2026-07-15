# -*- coding: utf-8 -*-
"""
kgpe.geometry_spec.readiness
================================
Prompt 11 Sec.8: small, explicit geometry-readiness vocabulary. The
`GeometrySpecificationCompiler` fails closed - every negative outcome maps
to one of these specific statuses, never one generic failure code.
"""
from ..resolver.spec import ResolutionStatus


class GeometryReadinessStatus:
    GEOMETRY_READY = "GEOMETRY_READY"
    ENGINEERING_SPEC_INCOMPLETE = "ENGINEERING_SPEC_INCOMPLETE"
    ENGINEERING_SPEC_AMBIGUOUS = "ENGINEERING_SPEC_AMBIGUOUS"
    ENGINEERING_DATA_QUARANTINED = "ENGINEERING_DATA_QUARANTINED"
    MANUFACTURER_CONTEXT_REQUIRED = "MANUFACTURER_CONTEXT_REQUIRED"
    GEOMETRY_PROFILE_UNAVAILABLE = "GEOMETRY_PROFILE_UNAVAILABLE"
    UNSUPPORTED_GEOMETRY_REQUEST = "UNSUPPORTED_GEOMETRY_REQUEST"


ALL_GEOMETRY_READINESS_STATUSES = frozenset({
    GeometryReadinessStatus.GEOMETRY_READY,
    GeometryReadinessStatus.ENGINEERING_SPEC_INCOMPLETE,
    GeometryReadinessStatus.ENGINEERING_SPEC_AMBIGUOUS,
    GeometryReadinessStatus.ENGINEERING_DATA_QUARANTINED,
    GeometryReadinessStatus.MANUFACTURER_CONTEXT_REQUIRED,
    GeometryReadinessStatus.GEOMETRY_PROFILE_UNAVAILABLE,
    GeometryReadinessStatus.UNSUPPORTED_GEOMETRY_REQUEST,
})

# Maps an upstream (non-RESOLVED) ResolutionStatus directly to the
# corresponding readiness status - the compiler rejects before profile
# selection whenever engineering resolution itself did not succeed
# (Sec.13 step 1).
_RESOLUTION_STATUS_TO_READINESS = {
    ResolutionStatus.INCOMPLETE_REQUEST: GeometryReadinessStatus.ENGINEERING_SPEC_INCOMPLETE,
    ResolutionStatus.AMBIGUOUS_REQUEST: GeometryReadinessStatus.ENGINEERING_SPEC_AMBIGUOUS,
    ResolutionStatus.UNSUPPORTED_REQUEST: GeometryReadinessStatus.UNSUPPORTED_GEOMETRY_REQUEST,
    ResolutionStatus.MALFORMED_REQUEST: GeometryReadinessStatus.UNSUPPORTED_GEOMETRY_REQUEST,
    ResolutionStatus.QUARANTINED_ENGINEERING_DATA: GeometryReadinessStatus.ENGINEERING_DATA_QUARANTINED,
    ResolutionStatus.MANUFACTURER_CONTEXT_REQUIRED: GeometryReadinessStatus.MANUFACTURER_CONTEXT_REQUIRED,
}


def readiness_for_resolution_status(resolution_status):
    return _RESOLUTION_STATUS_TO_READINESS.get(
        resolution_status, GeometryReadinessStatus.UNSUPPORTED_GEOMETRY_REQUEST)
