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
from .products import pipe as pipe_product
from .products import buttweld_elbow as buttweld_elbow_product

_PRODUCT_DISPATCH = {
    "pipe": pipe_product,
    "buttweld_elbow": buttweld_elbow_product,
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
    def generate(self, geometry_specification, generation_parameters=None) -> GeometryResult:
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
            build_result = product_module.build(geometry_specification, params)
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

        if not structural.passed or not dimensional.passed:
            trace.append("geometry validation failed - see dimensional/geometry validation summaries")
            return _base_result(
                GeometryGenerationStatus.GEOMETRY_VALIDATION_FAILED, geometry_specification, trace,
                geometry_type=build_result.geometry_type,
                dimensional_validation_summary=dimensional.to_dict(),
                geometry_validation_summary=structural.to_dict(),
                construction_rule_versions={cv.rule_id: cv.rule_version for cv in build_result.construction_values},
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
        )


def generate_geometry(geometry_specification, generation_parameters=None) -> GeometryResult:
    """Sec.5: module-level convenience function - equivalent to
    `GeometryKernel().generate(geometry_specification, generation_parameters)`."""
    return GeometryKernel().generate(geometry_specification, generation_parameters)
