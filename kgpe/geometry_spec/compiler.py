# -*- coding: utf-8 -*-
"""
kgpe.geometry_spec.compiler
===============================
Prompt 11 Sec.13: `GeometrySpecificationCompiler` / `compile_geometry_
specification()` - accepts RESOLVED engineering output only (never raw
user text), never reads source JSON, never imports adapters, never calls
dimension_library.py, never chooses standards, never generates geometry.

Because `EngineeringResolver.resolve()` (Prompt 10) already aggregates
every explicitly-requested dimension's outcome into ONE overall
ResolutionStatus - and that status can only be RESOLVED when EVERY
requested dimension resolved to an EXACT authoritative match - a resolved
spec with status RESOLVED is, by construction, guaranteed to carry every
dimension that was requested of it. This compiler still defensively
re-checks required-dimension presence (Sec.28 item 9: fail closed), so it
behaves correctly even when called directly (e.g. by tests) with a
manually-built resolved specification.
"""
from ..resolver.spec import ResolvedEngineeringSpecification, ResolutionStatus
from .identity import EngineeringObjectIdentity, IdentityConstructionError
from .dimension_bundle import ResolvedDimension, EngineeringDimensionBundle
from .readiness import GeometryReadinessStatus, readiness_for_resolution_status
from .profile import find_profile, MFR_REQUIRED, GeometryProfile
from .fingerprint import GEOMETRY_SPEC_SCHEMA_VERSION, compute_geometry_specification_fingerprint
from .spec import GeometrySpecification


def _failure_spec(readiness, trace, warnings=None, profile=None, identity=None, data_layer_fingerprint=None):
    return GeometrySpecification(
        readiness_status=readiness,
        engineering_object_identity=identity.to_dict() if identity else None,
        geometry_profile_id=profile.profile_id if profile else None,
        geometry_profile_version=profile.version if profile else None,
        data_layer_fingerprint=data_layer_fingerprint,
        compilation_trace=list(trace), warnings=list(warnings or []),
    )


class GeometrySpecificationCompiler:
    """Sec.13 steps 1-9, in order. Never generates geometry."""

    def compile(self, resolved_spec: ResolvedEngineeringSpecification, profile: GeometryProfile = None) -> GeometrySpecification:
        trace = [f"compiling from resolution status={resolved_spec.status!r}"]

        # Step 1: verify the engineering resolution status.
        if resolved_spec.status != ResolutionStatus.RESOLVED:
            readiness = readiness_for_resolution_status(resolved_spec.status)
            trace.append(f"engineering resolution did not succeed - readiness={readiness}")
            return _failure_spec(readiness, trace, resolved_spec.warnings, profile,
                                  data_layer_fingerprint=resolved_spec.data_layer_fingerprint)

        try:
            identity = EngineeringObjectIdentity.from_resolved_spec(resolved_spec)
        except IdentityConstructionError as e:
            trace.append(str(e))
            return _failure_spec(GeometryReadinessStatus.UNSUPPORTED_GEOMETRY_REQUEST, trace,
                                  resolved_spec.warnings, profile,
                                  data_layer_fingerprint=resolved_spec.data_layer_fingerprint)

        # Step 2: identify the applicable geometry profile.
        if profile is None:
            profile = find_profile(resolved_spec.product_family, resolved_spec.subtype)
        if profile is None:
            trace.append(f"no geometry profile defined for product_family={resolved_spec.product_family!r} "
                          f"subtype={resolved_spec.subtype!r}")
            return _failure_spec(GeometryReadinessStatus.GEOMETRY_PROFILE_UNAVAILABLE, trace,
                                  resolved_spec.warnings, None, identity=identity,
                                  data_layer_fingerprint=resolved_spec.data_layer_fingerprint)
        trace.append(f"profile selected: {profile.profile_id} v{profile.version}")

        # Step 5: preserve manufacturer context where required.
        if profile.manufacturer_specific == MFR_REQUIRED and not resolved_spec.manufacturer_profile:
            trace.append("profile requires manufacturer context but the resolved spec carries none")
            return _failure_spec(GeometryReadinessStatus.MANUFACTURER_CONTEXT_REQUIRED, trace,
                                  resolved_spec.warnings, profile, identity=identity,
                                  data_layer_fingerprint=resolved_spec.data_layer_fingerprint)

        # Steps 3-4/6: determine required dimensions, ensure they are
        # resolved authoritatively (fail closed if missing - this also
        # transitively covers quarantine rejection, since a quarantined
        # required dimension would already have made resolved_spec.status
        # != RESOLVED at the resolver layer, Sec.13 step 6).
        resolved_dims = resolved_spec.resolved_dimensions
        missing_required = sorted(d for d in profile.required_dimensions if d not in resolved_dims)
        if missing_required:
            trace.append(f"required dimension(s) not present in resolved specification: {missing_required}")
            return _failure_spec(
                GeometryReadinessStatus.ENGINEERING_SPEC_INCOMPLETE, trace,
                resolved_spec.warnings + [f"Missing required dimension(s) for profile "
                                          f"{profile.profile_id!r}: {missing_required}"],
                profile, identity=identity, data_layer_fingerprint=resolved_spec.data_layer_fingerprint)

        required_bundle = EngineeringDimensionBundle()
        for name in sorted(profile.required_dimensions):
            required_bundle.add(ResolvedDimension.from_resolved_dict(name, resolved_dims[name]))

        optional_bundle = EngineeringDimensionBundle()
        for name in sorted(profile.optional_dimensions):
            if name in resolved_dims:
                optional_bundle.add(ResolvedDimension.from_resolved_dict(name, resolved_dims[name]))
        trace.append(f"required dimensions bound: {required_bundle.names()}")
        if len(optional_bundle):
            trace.append(f"optional dimensions bound: {optional_bundle.names()}")

        # Steps 7-9: bind data-layer fingerprint, produce a deterministic
        # geometry-specification fingerprint, construct the geometry-ready spec.
        fp = compute_geometry_specification_fingerprint(
            GEOMETRY_SPEC_SCHEMA_VERSION, identity, required_bundle, optional_bundle,
            resolved_spec.data_layer_fingerprint, profile.profile_id, profile.version,
        )
        trace.append(f"geometry specification fingerprint: {fp}")

        statuses = sorted({d.verification_status for d in required_bundle} |
                           {d.verification_status for d in optional_bundle})
        source_files = sorted({d.source_file for d in required_bundle if d.source_file} |
                               {d.source_file for d in optional_bundle if d.source_file})
        summary = {"verification_statuses": statuses, "source_files": source_files,
                   "manufacturer_profile": identity.manufacturer_profile}

        return GeometrySpecification(
            readiness_status=GeometryReadinessStatus.GEOMETRY_READY,
            engineering_object_identity=identity.to_dict(),
            required_dimensions=required_bundle.to_dict(),
            optional_dimensions=optional_bundle.to_dict(),
            data_layer_fingerprint=resolved_spec.data_layer_fingerprint,
            geometry_specification_fingerprint=fp,
            geometry_profile_id=profile.profile_id, geometry_profile_version=profile.version,
            source_verification_summary=summary,
            compilation_trace=trace, warnings=list(resolved_spec.warnings),
        )


def compile_geometry_specification(resolved_spec, profile=None):
    """Sec.13: the module-level convenience entry point."""
    return GeometrySpecificationCompiler().compile(resolved_spec, profile)
