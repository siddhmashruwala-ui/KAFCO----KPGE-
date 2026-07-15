# -*- coding: utf-8 -*-
"""
kgpe.geometry_spec.orchestration
====================================
Prompt 11 Sec.14-16: `prepare_geometry_specification(request)` performs
resolve -> compile without collapsing the architectural boundary. It
issues TWO resolver calls, never one opaque merged step:

  1. `identity_resolution` - resolves the request AS GIVEN (this alone
     tells us product_family/subtype/standard, needed to select a
     geometry profile).
  2. If a profile applies: `dimension_resolution` - re-resolves the SAME
     request with `dimensions` overridden to the profile's required
     dimensions, plus any of the profile's optional dimensions the
     ORIGINAL caller explicitly asked for (Sec.7: "optional ... where
     explicitly included" - never auto-included).

Both resolution results are preserved on the returned
`GeometryPreparationResult`, never discarded (Sec.14), along with a
`failed_stage` field that names exactly which stage produced a non-ready
outcome, if any.
"""
from dataclasses import dataclass, field, replace
from typing import Optional, List

from ..resolver import EngineeringRequest, EngineeringResolver, ResolvedEngineeringSpecification, ResolutionStatus
from ..contract.canonical_reader import build_canonical_reader
from ..contract.snapshot import registry_fingerprint
from .profile import find_profile
from .compiler import GeometrySpecificationCompiler
from .spec import GeometrySpecification

# EngineeringRequest fields that carry a RATING value (Sec.14 of Prompt 10:
# kept as separate explicit fields so the caller states which rating
# SYSTEM a value belongs to). Used only by _attempt_rating_relaxation()
# below - never by the identity/dimension resolve calls themselves.
_RATING_REQUEST_FIELDS = ("pressure_class", "schedule", "pn", "jis_k", "wall_designation")


class OrchestrationStage:
    ENGINEERING_RESOLUTION = "ENGINEERING_RESOLUTION"
    PROFILE_SELECTION = "PROFILE_SELECTION"
    DIMENSION_RESOLUTION = "DIMENSION_RESOLUTION"
    GEOMETRY_COMPILATION = "GEOMETRY_COMPILATION"


def _default_resolver():
    reader, _ = build_canonical_reader()
    fingerprint = registry_fingerprint(reader.registry)
    return EngineeringResolver(reader, fingerprint)


def _copy_request_with_dimensions(request, dimensions):
    d = request.to_dict()
    d["dimensions"] = list(dimensions)
    return EngineeringRequest.from_dict(d)


def _relaxed_rating_request(request, dims):
    d = request.to_dict()
    for f in _RATING_REQUEST_FIELDS:
        d[f] = None
    d["dimensions"] = list(dims)
    return EngineeringRequest.from_dict(d)


def _attempt_rating_relaxation(resolver, dim_request, needed, dimension_resolution):
    """Orchestration-level fallback (built entirely on top of the public
    `resolver.resolve()` API - never modifies kgpe.resolver.engine).

    kgpe.resolver.engine.EngineeringResolver applies ONE shared
    `base_criteria` (including any resolved rating value) to EVERY
    dimension requested in a single resolve() call. Some canonical
    dimensions are genuinely rating-independent (e.g. a pipe's
    outside_diameter_mm does not vary by schedule - only
    wall_thickness_mm does; confirmed live: read(outside_diameter_mm,
    nps='6') -> EXACT_MATCH, read(outside_diameter_mm, nps='6',
    schedule='SCH40') -> NO_MATCH). When such a dimension comes back
    UNSUPPORTED purely because an inapplicable rating filter was
    attached, this retries that ONE dimension alone with rating fields
    cleared (identity/size criteria unchanged) - the exact same
    "relax one over-scoped filter and retry" principle already
    established inside kgpe.resolver.engine itself for the subtype
    field (Sec.10's shared cross-subtype OD handling), just applied to
    the rating field, and implemented here rather than in engine.py.
    This can only ever RECOVER a dimension the resolver would already
    resolve EXACT under relaxed criteria - it never arbitrates ambiguity,
    quarantine, or genuinely missing data differently than the resolver
    itself would.
    """
    resolved = dict(dimension_resolution.resolved_dimensions)
    missing = [d for d in needed if d not in resolved]
    if not missing:
        return dimension_resolution
    trace = list(dimension_resolution.trace)
    recovered_any = False
    for dim in missing:
        relaxed_request = _relaxed_rating_request(dim_request, [dim])
        relaxed_result = resolver.resolve(relaxed_request)
        if relaxed_result.status == ResolutionStatus.RESOLVED and dim in relaxed_result.resolved_dimensions:
            resolved[dim] = relaxed_result.resolved_dimensions[dim]
            trace.append(f"orchestration rating-relaxation recovered {dim!r} (rating-independent "
                          f"dimension - rating filter cleared for this dimension's retry only)")
            recovered_any = True
    if not recovered_any:
        return dimension_resolution
    still_missing = [d for d in needed if d not in resolved]
    if still_missing:
        # Partial recovery only - preserve the ORIGINAL (worse) status so
        # the compiler still fails closed, but keep the merged dims/trace
        # for transparency (Sec.14 - never hide which stage/dimension
        # actually failed).
        return replace(dimension_resolution, resolved_dimensions=resolved, trace=trace)
    return replace(dimension_resolution, status=ResolutionStatus.RESOLVED, resolved_dimensions=resolved,
                    trace=trace, missing_criteria=[], ambiguous_candidates={}, unsupported_reason=None,
                    quarantine_details=[])


@dataclass
class GeometryPreparationResult:
    identity_resolution: ResolvedEngineeringSpecification
    dimension_resolution: Optional[ResolvedEngineeringSpecification]
    geometry_specification: GeometrySpecification
    failed_stage: Optional[str]

    def is_ready(self):
        return self.geometry_specification.is_ready()

    def to_dict(self):
        return {
            "identity_resolution": self.identity_resolution.to_dict(),
            "dimension_resolution": self.dimension_resolution.to_dict() if self.dimension_resolution else None,
            "geometry_specification": self.geometry_specification.to_dict(),
            "failed_stage": self.failed_stage,
        }


def prepare_geometry_specification(request, resolver=None):
    if resolver is None:
        resolver = _default_resolver()
    compiler = GeometrySpecificationCompiler()

    identity_resolution = resolver.resolve(request)
    if identity_resolution.status != ResolutionStatus.RESOLVED:
        spec = compiler.compile(identity_resolution, profile=None)
        return GeometryPreparationResult(identity_resolution, None, spec, OrchestrationStage.ENGINEERING_RESOLUTION)

    profile = find_profile(identity_resolution.product_family, identity_resolution.subtype)
    if profile is None:
        spec = compiler.compile(identity_resolution, profile=None)
        return GeometryPreparationResult(identity_resolution, None, spec, OrchestrationStage.PROFILE_SELECTION)

    explicit_requested = set(request.dimensions or [])
    needed = sorted(profile.required_dimensions | (explicit_requested & profile.optional_dimensions))
    dim_request = _copy_request_with_dimensions(request, needed)
    dimension_resolution = resolver.resolve(dim_request)
    if dimension_resolution.status != ResolutionStatus.RESOLVED:
        dimension_resolution = _attempt_rating_relaxation(resolver, dim_request, needed, dimension_resolution)

    spec = compiler.compile(dimension_resolution, profile=profile)
    failed_stage = None
    if not spec.is_ready():
        failed_stage = (OrchestrationStage.DIMENSION_RESOLUTION
                         if dimension_resolution.status != ResolutionStatus.RESOLVED
                         else OrchestrationStage.GEOMETRY_COMPILATION)
    return GeometryPreparationResult(identity_resolution, dimension_resolution, spec, failed_stage)


# ---------------------------------------------------------------------------
# Sec.15-16: batch semantics. A batch is an ORDERED collection of
# independently-resolved objects, NOT an assembly/piping system - each
# item is resolved/compiled fully independently, and one item's failure
# (or even an unexpected exception) never corrupts another item's result.
# ---------------------------------------------------------------------------
class BatchStatus:
    ALL_READY = "ALL_READY"
    PARTIALLY_READY = "PARTIALLY_READY"
    NONE_READY = "NONE_READY"


ALL_BATCH_STATUSES = frozenset({BatchStatus.ALL_READY, BatchStatus.PARTIALLY_READY, BatchStatus.NONE_READY})


@dataclass
class BatchGeometryPreparationResult:
    items: List[GeometryPreparationResult] = field(default_factory=list)
    batch_status: str = BatchStatus.NONE_READY

    def to_dict(self):
        return {"batch_status": self.batch_status, "items": [it.to_dict() for it in self.items]}


def _isolated_failure_item(exc):
    """Sec.15: build a structured failure item instead of letting an
    unexpected exception propagate and corrupt the rest of the batch."""
    from ..resolver.spec import ResolvedEngineeringSpecification
    failure_spec = ResolvedEngineeringSpecification(
        status=ResolutionStatus.MALFORMED_REQUEST,
        warnings=[f"Unhandled exception while preparing this batch item: {exc!r}"],
    )
    geom = GeometrySpecificationCompiler().compile(failure_spec, profile=None)
    return GeometryPreparationResult(failure_spec, None, geom, OrchestrationStage.ENGINEERING_RESOLUTION)


def prepare_geometry_specifications_batch(requests, resolver=None):
    if resolver is None:
        resolver = _default_resolver()

    items = []
    for request in requests:
        try:
            item = prepare_geometry_specification(request, resolver=resolver)
        except Exception as e:
            item = _isolated_failure_item(e)
        items.append(item)

    ready_count = sum(1 for it in items if it.is_ready())
    if len(items) > 0 and ready_count == len(items):
        status = BatchStatus.ALL_READY
    elif ready_count == 0:
        status = BatchStatus.NONE_READY
    else:
        status = BatchStatus.PARTIALLY_READY
    return BatchGeometryPreparationResult(items=items, batch_status=status)
