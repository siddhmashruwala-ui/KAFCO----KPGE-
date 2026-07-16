# -*- coding: utf-8 -*-
"""
kgpe.geometry.kernel
========================
Prompt 12 Sec.3/5: `GeometryKernel.generate()` / `generate_geometry()` -
the ONE public entry point of the new geometry kernel. Accepts only an
already-compiled `kgpe.geometry_spec.GeometrySpecification` (never a raw
string, never a raw `EngineeringRequest`). Never resolves engineering
requests, never reads source JSON, never imports a source adapter, never
uses `dimension_library.py`. Every outcome is a structured `GeometryResult`
- the public boundary never raises.
"""
from ..geometry_spec import GeometryReadinessStatus
from .result import GeometryResult, GeometryGenerationStatus
from .parameters import GenerationParameters
from .validation import validate_mesh_structure, validate_dimensions
from .fingerprint import compute_geometry_fingerprint
from .version import GEOMETRY_KERNEL_VERSION
from .product_api import GeometryInputError, ConstructionRuleUnavailableError
from .ports import validate_ports, PortValidationError
from .products import pipe as pipe_product
from .products import buttweld_elbow as buttweld_elbow_product
from .products import tee as tee_product
from .products import cap as cap_product
from .products import reducer as reducer_product
from .products import flange as flange_product
from .products import socketweld_elbow_tee as socketweld_elbow_tee_product
from .products import socketweld_coupling as socketweld_coupling_product
from .products import socketweld_cap as socketweld_cap_product
from .products import olet as olet_product

# Prompt 13 Sec.32/Prompt 14 Sec.35: expanded ONLY for successfully
# implemented and validated product profiles - reducer_concentric/
# reducer_eccentric BOTH resolve to the single "buttweld_reducer"
# geometry_profile_id (Prompt 11 profile.py); products/reducer.py itself
# distinguishes them via the engineering identity's subtype field.
# "flange_weld_neck" (Prompt 14) is the ONE flange geometry_profile_id
# defined (Prompt 11) - it serves ASME_B16.5/JIS_B2220/EN_1092-1 alike;
# products/flange.py itself distinguishes standard-specific bore/raised-
# face availability via the resolved dimensions actually present.
# Prompt 15 Sec.17: expanded for ASME B16.11 socket-weld elbow/45/tee/
# cross ("socketweld_elbow_tee" - one profile, one module, internally
# subtype-dispatched exactly like flange.py's standard-dispatch),
# coupling/half-coupling ("socketweld_coupling", a NEW Prompt 15 profile -
# no Prompt 11 profile covered this subtype pair), cap
# ("socketweld_cap") and MSS SP-97 weldolet/sockolet/threadolet
# ("olet_body"). elbolet/latrolet/sweepolet/nippolet and
# "olet_outlet_height" (insufficient dims for any envelope - height-only)
# remain UNDISPATCHED - genuinely unsupported/insufficient, never
# fabricated.
_PRODUCT_DISPATCH = {
    "pipe": pipe_product,
    "buttweld_elbow": buttweld_elbow_product,
    "buttweld_tee_equal": tee_product,
    "buttweld_cap": cap_product,
    "buttweld_reducer": reducer_product,
    "flange_weld_neck": flange_product,
    "socketweld_elbow_tee": socketweld_elbow_tee_product,
    "socketweld_coupling": socketweld_coupling_product,
    "socketweld_cap": socketweld_cap_product,
    "olet_body": olet_product,
}


def _base_result(status, geometry_spec, trace, **kwargs):
    return GeometryResult(
        generation_status=status,
        geometry_specification_fingerprint=geometry_spec.geometry_specification_fingerprint,
        data_layer_fingerprint=geometry_spec.data_layer_fingerprint,
        geometry_kernel_version=GEOMETRY_KERNEL_VERSION,
        generation_trace=trace, **kwargs,
    )


class GeometryKernel:
    def generate(self, geometry_specification, generation_parameters=None, product_kwargs=None) -> GeometryResult:
        """Prompt 13 Sec.8: `product_kwargs` is an optional dict of
        ALREADY-RESOLVED extra inputs a specific product builder needs
        beyond `(geometry_spec, generation_parameters)` - e.g. elbow's
        `wall_thickness_value`, cap's `actual_wall_thickness_value`,
        reducer's `large_od_value`/`small_od_value`/`eccentric`/
        `orientation`. Every value in it MUST already be resolved (a
        `ConstructionValue`, a plain flag, etc.) - the kernel never
        resolves anything itself."""
        trace = []
        try:
            params = generation_parameters or GenerationParameters()
        except ValueError as e:
            return _base_result(GeometryGenerationStatus.GEOMETRY_GENERATION_FAILED, geometry_specification,
                                 [f"invalid generation_parameters: {e}"], warnings=[str(e)])
        trace.append(f"generation_parameters: {params.to_dict()}")

        if geometry_specification.readiness_status != GeometryReadinessStatus.GEOMETRY_READY:
            trace.append(f"geometry specification not ready: {geometry_specification.readiness_status}")
            return _base_result(GeometryGenerationStatus.GEOMETRY_SPEC_NOT_READY, geometry_specification, trace,
                                 warnings=list(geometry_specification.warnings))

        profile_id = geometry_specification.geometry_profile_id
        product_module = _PRODUCT_DISPATCH.get(profile_id)
        if product_module is None:
            trace.append(f"no new-kernel product builder registered for profile_id={profile_id!r}")
            return _base_result(GeometryGenerationStatus.UNSUPPORTED_GEOMETRY_PROFILE, geometry_specification, trace)

        try:
            build_result = product_module.build(geometry_specification, params, **(product_kwargs or {}))
        except GeometryInputError as e:
            trace.append(str(e))
            return _base_result(GeometryGenerationStatus.INVALID_ENGINEERING_DIMENSIONS, geometry_specification,
                                 trace, warnings=[str(e)])
        except ConstructionRuleUnavailableError as e:
            trace.append(str(e))
            return _base_result(GeometryGenerationStatus.CONSTRUCTION_RULE_UNAVAILABLE, geometry_specification,
                                 trace, warnings=[str(e)])
        except Exception as e:  # Sec.5: the public boundary never raises
            trace.append(f"unexpected error during generation: {e!r}")
            return _base_result(GeometryGenerationStatus.GEOMETRY_GENERATION_FAILED, geometry_specification,
                                 trace, warnings=[repr(e)])

        return self._validate_and_finish(geometry_specification, build_result, params, trace)

    def _validate_and_finish(self, geometry_specification, build_result, params, trace):
        mesh = build_result.mesh
        trace.extend(build_result.trace)

        structural = validate_mesh_structure(mesh, expected_feature_count=len(build_result.features),
                                              features=build_result.features)
        dimensional = validate_dimensions(build_result.measurements, build_result.expected_dimensions)

        # Prompt 13 Sec.6: validate any connection ports the product
        # builder exposed - a genuinely malformed port is a programmer
        # defect (never an expected engineering outcome), so it is
        # reported the same way an unexpected exception is (Sec.5).
        try:
            validate_ports(build_result.ports)
        except PortValidationError as e:
            trace.append(f"port validation failed: {e}")
            return _base_result(GeometryGenerationStatus.GEOMETRY_GENERATION_FAILED, geometry_specification,
                                 trace, warnings=[str(e)])

        if not structural.passed or not dimensional.passed:
            trace.append("geometry validation failed - see dimensional/geometry validation summaries")
            return _base_result(
                GeometryGenerationStatus.GEOMETRY_VALIDATION_FAILED, geometry_specification, trace,
                geometry_type=build_result.geometry_type,
                dimensional_validation_summary=dimensional.to_dict(),
                geometry_validation_summary=structural.to_dict(),
                construction_rule_versions={cv.rule_id: cv.rule_version for cv in build_result.construction_values},
                topology_representation=build_result.topology_representation,
                connection_ports=[p.to_dict() for p in build_result.ports],
            )

        geometry_fp = compute_geometry_fingerprint(mesh, params, GEOMETRY_KERNEL_VERSION)
        topology_summary = {
            "vertex_count": mesh.vertex_count(),
            "face_count": mesh.face_count(),
            "bounding_box": mesh.bounding_box(),
            "feature_count": len(build_result.features),
            "feature_names": [f["name"] for f in build_result.features],
        }
        geometry_payload = {
            "mesh": mesh.to_dict(),
            "features": build_result.features,
            "construction_values": [cv.to_dict() for cv in build_result.construction_values],
            "measurements": build_result.measurements,
            "ports": [p.to_dict() for p in build_result.ports],
        }
        trace.append(f"geometry generated successfully: {topology_summary['vertex_count']} vertices, "
                     f"{topology_summary['face_count']} faces")

        return _base_result(
            GeometryGenerationStatus.GEOMETRY_GENERATED, geometry_specification, trace,
            geometry_type=build_result.geometry_type,
            geometry_fingerprint=geometry_fp,
            topology_summary=topology_summary,
            dimensional_validation_summary=dimensional.to_dict(),
            geometry_validation_summary=structural.to_dict(),
            construction_rule_versions={cv.rule_id: cv.rule_version for cv in build_result.construction_values},
            geometry_payload=geometry_payload,
            topology_representation=build_result.topology_representation,
            connection_ports=[p.to_dict() for p in build_result.ports],
        )


def generate_geometry(geometry_specification, generation_parameters=None, product_kwargs=None) -> GeometryResult:
    """Sec.5: module-level convenience function - equivalent to
    `GeometryKernel().generate(geometry_specification, generation_parameters, product_kwargs)`."""
    return GeometryKernel().generate(geometry_specification, generation_parameters, product_kwargs)
