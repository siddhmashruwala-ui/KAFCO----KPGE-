# -*- coding: utf-8 -*-
"""
tests/test_prompt12_geometry_kernel.py
==========================================
Prompt 12 Sec.36: automated tests for kgpe.geometry - the parametric
geometry kernel built on top of the frozen canonical data layer
(Prompt 9), resolution engine (Prompt 10), and geometry-specification
handoff layer (Prompt 11). Standard-library `unittest` only.
"""
import math
import unittest

from kgpe.contract.canonical_reader import build_canonical_reader
from kgpe.contract.snapshot import registry_fingerprint
from kgpe.resolver import EngineeringRequest, EngineeringResolver, ResolutionStatus
from kgpe.geometry_spec import (
    prepare_geometry_specification, GeometrySpecification, GeometryReadinessStatus,
)

from kgpe.geometry.policy import (
    LENGTH_UNIT, COORDINATE_CONVENTION, LINEAR_TOLERANCE_MM, NEAR_ZERO_MM,
    is_effectively_zero, within_tolerance, round_for_fingerprint,
)
from kgpe.geometry.primitives import (
    InvalidPrimitiveInputError, vec_add, vec_sub, vec_length, vec_normalize, vec_cross,
    circle_ring, straight_axis_frame, arc_sweep_frames, validate_positive, validate_segment_count,
)
from kgpe.geometry.mesh import Mesh
from kgpe.geometry.builders import build_hollow_cylinder, build_arc_swept_solid
from kgpe.geometry.construction_value import ConstructionValue, PROVENANCE_LABEL_DERIVED
from kgpe.geometry.construction_rules import (
    ConstructionRuleStatus, PipeBoreConstructionRule,
)
from kgpe.geometry.cross_family import FlangeBoreViaPipeScheduleRule
from kgpe.geometry.tessellation import (
    MIN_RADIAL_SEGMENTS, MIN_SWEEP_SEGMENTS, DEFAULT_RADIAL_SEGMENTS, DEFAULT_SWEEP_SEGMENTS,
    validate_tessellation,
)
from kgpe.geometry.parameters import GenerationParameters, DEFAULT_PIPE_SEGMENT_LENGTH_MM
from kgpe.geometry.validation import validate_mesh_structure, validate_dimensions
from kgpe.geometry.measurement import measure_radial_distance, measure_axial_length, measure_bend_radius
from kgpe.geometry.fingerprint import compute_geometry_fingerprint
from kgpe.geometry.result import GeometryGenerationStatus, ALL_GEOMETRY_GENERATION_STATUSES, GeometryResult
from kgpe.geometry.product_api import GeometryInputError, ConstructionRuleUnavailableError
from kgpe.geometry.products import pipe as pipe_product
from kgpe.geometry.products import buttweld_elbow as elbow_product
from kgpe.geometry.kernel import GeometryKernel, generate_geometry
from kgpe.geometry.pipeline import PipelineStage, PipelineResult, run_pipeline
import kgpe.geometry as geo

_READER, _ = build_canonical_reader()
_FINGERPRINT = registry_fingerprint(_READER.registry)
_RESOLVER = EngineeringResolver(_READER, _FINGERPRINT)


def _prep(**kwargs):
    return prepare_geometry_specification(EngineeringRequest(**kwargs), resolver=_RESOLVER)


def _asme_pipe_spec(primary_size="6", schedule="Sch40"):
    result = _prep(product_family="pipe", standard="ASME_B36.10M", primary_size=primary_size, schedule=schedule)
    assert result.is_ready(), result.geometry_specification.warnings
    return result.geometry_specification


def _asme_elbow_spec(primary_size="6"):
    result = _prep(product_family="buttweld_fitting", subtype="elbow_90_lr",
                   standard="ASME_B16.9", primary_size=primary_size)
    assert result.is_ready(), result.geometry_specification.warnings
    return result.geometry_specification


class TestPolicy(unittest.TestCase):
    def test_length_unit_is_mm(self):
        self.assertEqual(LENGTH_UNIT, "mm")

    def test_coordinate_convention_fields(self):
        self.assertEqual(COORDINATE_CONVENTION["primary_product_axis"], "+Z")
        self.assertEqual(COORDINATE_CONVENTION["handedness"], "right_handed")
        self.assertEqual(COORDINATE_CONVENTION["origin"], "start_face_centreline")

    def test_is_effectively_zero(self):
        self.assertTrue(is_effectively_zero(1e-12))
        self.assertFalse(is_effectively_zero(0.001))

    def test_within_tolerance(self):
        self.assertTrue(within_tolerance(10.0, 10.0 + LINEAR_TOLERANCE_MM / 2))
        self.assertFalse(within_tolerance(10.0, 10.1))

    def test_round_for_fingerprint_deterministic(self):
        self.assertEqual(round_for_fingerprint(1.0000001234), round_for_fingerprint(1.0000001235))


class TestPrimitives(unittest.TestCase):
    def test_vec_ops(self):
        self.assertEqual(vec_add((1, 2, 3), (1, 1, 1)), (2, 3, 4))
        self.assertEqual(vec_sub((1, 2, 3), (1, 1, 1)), (0, 1, 2))
        self.assertAlmostEqual(vec_length((3, 4, 0)), 5.0)

    def test_vec_normalize_zero_vector_raises(self):
        with self.assertRaises(InvalidPrimitiveInputError):
            vec_normalize((0.0, 0.0, 0.0))

    def test_validate_positive_rejects_negative_and_zero(self):
        with self.assertRaises(InvalidPrimitiveInputError):
            validate_positive(-1.0, "x")
        with self.assertRaises(InvalidPrimitiveInputError):
            validate_positive(0.0, "x")
        self.assertEqual(validate_positive(5.0, "x"), 5.0)

    def test_validate_segment_count(self):
        with self.assertRaises(InvalidPrimitiveInputError):
            validate_segment_count(2, "n", minimum=3)
        self.assertEqual(validate_segment_count(8, "n", minimum=3), 8)

    def test_circle_ring_deterministic_seam_and_radius(self):
        u, v, _ = straight_axis_frame()
        pts1 = circle_ring((0, 0, 0), u, v, 10.0, 16)
        pts2 = circle_ring((0, 0, 0), u, v, 10.0, 16)
        self.assertEqual(pts1, pts2)
        self.assertEqual(len(pts1), 16)
        self.assertAlmostEqual(pts1[0][0], 10.0, places=9)
        self.assertAlmostEqual(pts1[0][1], 0.0, places=9)
        for p in pts1:
            r = math.hypot(p[0], p[1])
            self.assertAlmostEqual(r, 10.0, places=9)

    def test_circle_ring_rejects_invalid_radius(self):
        u, v, _ = straight_axis_frame()
        with self.assertRaises(InvalidPrimitiveInputError):
            circle_ring((0, 0, 0), u, v, -1.0, 8)

    def test_arc_sweep_frames_endpoints(self):
        frames = arc_sweep_frames(bend_radius=100.0, total_angle_rad=math.pi / 2.0, sweep_segments=16)
        self.assertEqual(len(frames), 17)
        start, end = frames[0], frames[-1]
        self.assertAlmostEqual(start["center"][0], 0.0, places=9)
        self.assertAlmostEqual(start["center"][2], 0.0, places=9)
        self.assertAlmostEqual(start["tangent"][2], 1.0, places=9)  # entering +Z
        self.assertAlmostEqual(end["center"][0], 100.0, places=9)
        self.assertAlmostEqual(end["center"][2], 100.0, places=9)
        self.assertAlmostEqual(end["tangent"][0], 1.0, places=9)  # leaving +X
        pivot = (100.0, 0.0, 0.0)
        for frame in frames:
            cx, cy, cz = frame["center"]
            dist = math.sqrt((cx - pivot[0]) ** 2 + (cy - pivot[1]) ** 2 + (cz - pivot[2]) ** 2)
            self.assertAlmostEqual(dist, 100.0, places=6)

    def test_arc_sweep_frames_rejects_non_positive_angle(self):
        with self.assertRaises(InvalidPrimitiveInputError):
            arc_sweep_frames(bend_radius=100.0, total_angle_rad=0.0, sweep_segments=4)


class TestMesh(unittest.TestCase):
    def test_add_vertex_and_triangle(self):
        m = Mesh()
        i0 = m.add_vertex((0, 0, 0))
        i1 = m.add_vertex((1, 0, 0))
        i2 = m.add_vertex((0, 1, 0))
        m.add_triangle(i0, i1, i2)
        self.assertEqual(m.vertex_count(), 3)
        self.assertEqual(m.face_count(), 1)

    def test_add_quad_splits_deterministically(self):
        m = Mesh()
        idx = m.add_vertices([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)])
        m.add_quad(*idx)
        self.assertEqual(m.face_count(), 2)
        self.assertEqual(m.faces, [(idx[0], idx[1], idx[2]), (idx[0], idx[2], idx[3])])

    def test_bounding_box(self):
        m = Mesh()
        m.add_vertices([(-1, -2, -3), (4, 5, 6)])
        bbox = m.bounding_box()
        self.assertEqual(bbox["min"], (-1, -2, -3))
        self.assertEqual(bbox["max"], (4, 5, 6))

    def test_triangle_area(self):
        m = Mesh()
        idx = m.add_vertices([(0, 0, 0), (2, 0, 0), (0, 2, 0)])
        self.assertAlmostEqual(m.triangle_area((idx[0], idx[1], idx[2])), 2.0)

    def test_degenerate_faces_detected(self):
        m = Mesh()
        idx = m.add_vertices([(0, 0, 0), (0, 0, 0), (0, 0, 0)])
        m.add_triangle(*idx)
        self.assertEqual(len(m.degenerate_faces()), 1)

    def test_has_non_finite_coordinates(self):
        m = Mesh()
        m.add_vertex((0, 0, 0))
        self.assertFalse(m.has_non_finite_coordinates())
        m.vertices.append((float("nan"), 0, 0))
        self.assertTrue(m.has_non_finite_coordinates())

    def test_invalid_indices_detected(self):
        m = Mesh()
        idx = m.add_vertices([(0, 0, 0), (1, 0, 0), (0, 1, 0)])
        m.add_triangle(idx[0], idx[1], 99)
        self.assertEqual(len(m.invalid_indices()), 1)

    def test_to_dict_roundtrip_shape(self):
        m = Mesh()
        idx = m.add_vertices([(0, 0, 0), (1, 0, 0), (0, 1, 0)])
        m.add_triangle(*idx)
        d = m.to_dict()
        self.assertEqual(d["vertex_count"], 3)
        self.assertEqual(d["face_count"], 1)
        self.assertEqual(d["units"], "mm")


class TestBuilders(unittest.TestCase):
    def test_build_hollow_cylinder_shape(self):
        mesh, features = build_hollow_cylinder(outer_radius=50.0, inner_radius=40.0, length=300.0,
                                                 radial_segments=16)
        names = [f["name"] for f in features]
        self.assertEqual(names, ["outer_cylindrical_wall", "inner_cylindrical_wall_bore",
                                  "end_cap_start", "end_cap_end"])
        self.assertEqual(mesh.vertex_count(), 16 * 4)
        self.assertFalse(mesh.has_non_finite_coordinates())
        self.assertEqual(len(mesh.invalid_indices()), 0)
        self.assertEqual(len(mesh.degenerate_faces()), 0)
        bbox = mesh.bounding_box()
        self.assertAlmostEqual(bbox["max"][2] - bbox["min"][2], 300.0, places=6)

    def test_build_hollow_cylinder_deterministic(self):
        m1, _ = build_hollow_cylinder(50.0, 40.0, 300.0, 16)
        m2, _ = build_hollow_cylinder(50.0, 40.0, 300.0, 16)
        self.assertEqual(m1.vertices, m2.vertices)
        self.assertEqual(m1.faces, m2.faces)

    def test_build_arc_swept_solid_shape(self):
        mesh, features = build_arc_swept_solid(outer_radius=30.0, bend_radius=150.0,
                                                 total_angle_rad=math.pi / 2.0,
                                                 radial_segments=16, sweep_segments=8)
        names = [f["name"] for f in features]
        self.assertEqual(names, ["swept_outer_profile", "end_cap_start", "end_cap_end"])
        self.assertFalse(mesh.has_non_finite_coordinates())
        self.assertEqual(len(mesh.invalid_indices()), 0)
        self.assertEqual(len(mesh.degenerate_faces()), 0)


class TestConstructionValue(unittest.TestCase):
    def test_provenance_label_and_frozen(self):
        cv = ConstructionValue(name="bore_diameter_mm", value=100.0, unit="mm",
                                rule_id="r", rule_version="1")
        self.assertEqual(cv.provenance_label, PROVENANCE_LABEL_DERIVED)
        with self.assertRaises(Exception):
            cv.value = 200.0  # frozen dataclass


class TestPipeBoreConstructionRule(unittest.TestCase):
    def setUp(self):
        self.rule = PipeBoreConstructionRule()

    def test_apply_success(self):
        outcome = self.rule.apply(od_value=168.3, od_unit="mm", od_source_ref={"name": "od"},
                                   wt_value=7.11, wt_unit="mm", wt_source_ref={"name": "wt"})
        self.assertTrue(outcome.is_applied())
        self.assertAlmostEqual(outcome.value.value, 168.3 - 2 * 7.11)
        self.assertEqual(outcome.value.rule_id, "pipe_bore_from_od_wall_thickness")

    def test_apply_rejects_wt_too_large(self):
        outcome = self.rule.apply(od_value=10.0, od_unit="mm", od_source_ref={},
                                   wt_value=20.0, wt_unit="mm", wt_source_ref={})
        self.assertEqual(outcome.status, ConstructionRuleStatus.RULE_UNSUPPORTED)

    def test_apply_rejects_missing_input(self):
        outcome = self.rule.apply(od_value=None, od_unit="mm", od_source_ref={},
                                   wt_value=5.0, wt_unit="mm", wt_source_ref={})
        self.assertEqual(outcome.status, ConstructionRuleStatus.RULE_INPUT_MISSING)

    def test_apply_rejects_non_mm_unit(self):
        outcome = self.rule.apply(od_value=100.0, od_unit="in", od_source_ref={},
                                   wt_value=5.0, wt_unit="mm", wt_source_ref={})
        self.assertEqual(outcome.status, ConstructionRuleStatus.RULE_UNSUPPORTED)

    def test_apply_rejects_negative_values(self):
        outcome = self.rule.apply(od_value=-100.0, od_unit="mm", od_source_ref={},
                                   wt_value=5.0, wt_unit="mm", wt_source_ref={})
        self.assertEqual(outcome.status, ConstructionRuleStatus.RULE_UNSUPPORTED)

    def test_apply_rejects_non_finite(self):
        outcome = self.rule.apply(od_value=float("nan"), od_unit="mm", od_source_ref={},
                                   wt_value=5.0, wt_unit="mm", wt_source_ref={})
        self.assertEqual(outcome.status, ConstructionRuleStatus.RULE_UNSUPPORTED)


class TestCrossFamilyDependencyRule(unittest.TestCase):
    def test_flange_bore_via_pipe_schedule_applies(self):
        rule = FlangeBoreViaPipeScheduleRule()
        outcome = rule.resolve(_RESOLVER, target_standard="ASME_B16.5", target_size_system="nps",
                                target_size="6", pipe_standard="ASME_B36.10M", pipe_schedule="Sch40")
        self.assertTrue(outcome.is_applied())
        self.assertEqual(outcome.value.name, "bore_diameter_mm")
        self.assertTrue(any("cross-family" in t for t in outcome.value.derivation_trace))

    def test_flange_bore_rejects_non_nps_size_system(self):
        rule = FlangeBoreViaPipeScheduleRule()
        outcome = rule.resolve(_RESOLVER, target_standard="EN_1092-1", target_size_system="dn",
                                target_size="150", pipe_standard="EN_10216_10217", pipe_schedule="Series1")
        self.assertEqual(outcome.status, ConstructionRuleStatus.RULE_NOT_APPLICABLE)

    def test_flange_bore_rejects_missing_pipe_context(self):
        rule = FlangeBoreViaPipeScheduleRule()
        outcome = rule.resolve(_RESOLVER, target_standard="ASME_B16.5", target_size_system="nps",
                                target_size="6", pipe_standard=None, pipe_schedule=None)
        self.assertEqual(outcome.status, ConstructionRuleStatus.RULE_INPUT_MISSING)

    def test_flange_bore_wired_into_kernel_dispatch_in_prompt_14(self):
        # Sec.16 (Prompt 12): this rule was proven standalone only, not
        # yet invoked by kernel dispatch. Prompt 14 Sec.15/38 wires it
        # into kgpe.geometry.products.flange for ASME_B16.5 (the only
        # standard where this rule's own NPS-only scope applies) - the
        # rule itself is unchanged, only the dispatch wiring is new.
        import kgpe.geometry.kernel as kernel_module
        self.assertIn("flange_weld_neck", kernel_module._PRODUCT_DISPATCH)


class TestTessellation(unittest.TestCase):
    def test_defaults_meet_minimums(self):
        self.assertGreaterEqual(DEFAULT_RADIAL_SEGMENTS, MIN_RADIAL_SEGMENTS)
        self.assertGreaterEqual(DEFAULT_SWEEP_SEGMENTS, MIN_SWEEP_SEGMENTS)

    def test_validate_tessellation_rejects_below_minimum(self):
        with self.assertRaises(ValueError):
            validate_tessellation(MIN_RADIAL_SEGMENTS - 1, DEFAULT_SWEEP_SEGMENTS)
        with self.assertRaises(ValueError):
            validate_tessellation(DEFAULT_RADIAL_SEGMENTS, MIN_SWEEP_SEGMENTS - 1)

    def test_validate_tessellation_accepts_defaults(self):
        validate_tessellation(DEFAULT_RADIAL_SEGMENTS, DEFAULT_SWEEP_SEGMENTS)  # no raise


class TestGenerationParameters(unittest.TestCase):
    def test_defaults(self):
        p = GenerationParameters()
        self.assertEqual(p.pipe_segment_length_mm, DEFAULT_PIPE_SEGMENT_LENGTH_MM)
        self.assertEqual(p.radial_segments, DEFAULT_RADIAL_SEGMENTS)
        self.assertEqual(p.sweep_segments, DEFAULT_SWEEP_SEGMENTS)

    def test_rejects_invalid_segment_length(self):
        with self.assertRaises(ValueError):
            GenerationParameters(pipe_segment_length_mm=0.0)
        with self.assertRaises(ValueError):
            GenerationParameters(pipe_segment_length_mm=-5.0)

    def test_rejects_invalid_tessellation(self):
        with self.assertRaises(ValueError):
            GenerationParameters(radial_segments=2)

    def test_to_dict_contains_schema_version(self):
        d = GenerationParameters().to_dict()
        self.assertIn("schema_version", d)


class TestMeasurementAndValidation(unittest.TestCase):
    def test_measure_radial_distance(self):
        mesh, features = build_hollow_cylinder(50.0, 40.0, 300.0, 16)
        outer = next(f for f in features if f["name"] == "outer_cylindrical_wall")
        idxs = range(outer["vertex_range"][0], outer["vertex_range"][1] + 1)
        self.assertAlmostEqual(measure_radial_distance(mesh, idxs), 50.0, places=6)

    def test_measure_axial_length(self):
        mesh, _ = build_hollow_cylinder(50.0, 40.0, 300.0, 16)
        self.assertAlmostEqual(measure_axial_length(mesh, axis="z"), 300.0, places=6)

    def test_measure_bend_radius(self):
        mesh, features = build_arc_swept_solid(30.0, 150.0, math.pi / 2.0, 16, 8)
        start = next(f for f in features if f["name"] == "end_cap_start")
        end = next(f for f in features if f["name"] == "end_cap_end")
        r = measure_bend_radius(mesh, [start["vertex_range"][0], end["vertex_range"][0]], pivot=(150.0, 0.0, 0.0))
        self.assertAlmostEqual(r, 150.0, places=6)

    def test_validate_mesh_structure_passes_for_good_mesh(self):
        mesh, features = build_hollow_cylinder(50.0, 40.0, 300.0, 16)
        result = validate_mesh_structure(mesh, expected_feature_count=len(features), features=features)
        self.assertTrue(result.passed)

    def test_validate_mesh_structure_flags_degenerate(self):
        m = Mesh()
        idx = m.add_vertices([(0, 0, 0), (0, 0, 0), (0, 0, 0)])
        m.add_triangle(*idx)
        result = validate_mesh_structure(m)
        self.assertFalse(result.passed)

    def test_validate_mesh_structure_flags_wrong_feature_count(self):
        mesh, features = build_hollow_cylinder(50.0, 40.0, 300.0, 16)
        result = validate_mesh_structure(mesh, expected_feature_count=999, features=features)
        self.assertFalse(result.passed)

    def test_validate_dimensions_pass_and_fail(self):
        ok = validate_dimensions({"od": 100.0}, {"od": 100.0})
        self.assertTrue(ok.passed)
        bad = validate_dimensions({"od": 99.0}, {"od": 100.0})
        self.assertFalse(bad.passed)

    def test_validate_dimensions_missing_measurement_fails(self):
        result = validate_dimensions({}, {"od": 100.0})
        self.assertFalse(result.passed)


class TestFingerprint(unittest.TestCase):
    def test_deterministic_same_inputs(self):
        mesh, _ = build_hollow_cylinder(50.0, 40.0, 300.0, 16)
        params = GenerationParameters()
        fp1 = compute_geometry_fingerprint(mesh, params, "v1")
        fp2 = compute_geometry_fingerprint(mesh, params, "v1")
        self.assertEqual(fp1, fp2)

    def test_sensitive_to_kernel_version(self):
        mesh, _ = build_hollow_cylinder(50.0, 40.0, 300.0, 16)
        params = GenerationParameters()
        fp1 = compute_geometry_fingerprint(mesh, params, "v1")
        fp2 = compute_geometry_fingerprint(mesh, params, "v2")
        self.assertNotEqual(fp1, fp2)

    def test_sensitive_to_generation_parameters(self):
        mesh, _ = build_hollow_cylinder(50.0, 40.0, 300.0, 16)
        fp1 = compute_geometry_fingerprint(mesh, GenerationParameters(), "v1")
        fp2 = compute_geometry_fingerprint(mesh, GenerationParameters(pipe_segment_length_mm=500.0), "v1")
        self.assertNotEqual(fp1, fp2)

    def test_sensitive_to_mesh_mutation(self):
        mesh1, _ = build_hollow_cylinder(50.0, 40.0, 300.0, 16)
        mesh2, _ = build_hollow_cylinder(51.0, 40.0, 300.0, 16)
        params = GenerationParameters()
        fp1 = compute_geometry_fingerprint(mesh1, params, "v1")
        fp2 = compute_geometry_fingerprint(mesh2, params, "v1")
        self.assertNotEqual(fp1, fp2)

    def test_excludes_no_timestamp_field(self):
        mesh, _ = build_hollow_cylinder(50.0, 40.0, 300.0, 16)
        fp1 = compute_geometry_fingerprint(mesh, GenerationParameters(), "v1")
        import time
        time.sleep(0.01)
        fp2 = compute_geometry_fingerprint(mesh, GenerationParameters(), "v1")
        self.assertEqual(fp1, fp2)


class TestGeometryResult(unittest.TestCase):
    def test_all_statuses_registered(self):
        expected = {
            "GEOMETRY_GENERATED", "GEOMETRY_SPEC_NOT_READY", "UNSUPPORTED_GEOMETRY_PROFILE",
            "CONSTRUCTION_RULE_UNAVAILABLE", "INVALID_ENGINEERING_DIMENSIONS",
            "GEOMETRY_VALIDATION_FAILED", "GEOMETRY_GENERATION_FAILED",
        }
        self.assertEqual(set(ALL_GEOMETRY_GENERATION_STATUSES), expected)

    def test_is_generated(self):
        r = GeometryResult(generation_status=GeometryGenerationStatus.GEOMETRY_GENERATED)
        self.assertTrue(r.is_generated())
        r2 = GeometryResult(generation_status=GeometryGenerationStatus.GEOMETRY_SPEC_NOT_READY)
        self.assertFalse(r2.is_generated())

    def test_to_dict_contains_no_rendering_fields(self):
        r = GeometryResult(generation_status=GeometryGenerationStatus.GEOMETRY_GENERATED)
        d = r.to_dict()
        for forbidden in ("color", "camera", "lighting"):
            self.assertNotIn(forbidden, d)


class TestPipeProductBuilder(unittest.TestCase):
    def test_build_success_derives_bore(self):
        spec = _asme_pipe_spec()
        result = pipe_product.build(spec, GenerationParameters())
        self.assertEqual(result.geometry_type, "pipe_segment")
        self.assertEqual(len(result.construction_values), 1)
        cv = result.construction_values[0]
        self.assertEqual(cv.rule_id, "pipe_bore_from_od_wall_thickness")
        od = spec.required_dimensions["outside_diameter_mm"]["value"]
        wt = spec.required_dimensions["wall_thickness_mm"]["value"]
        self.assertAlmostEqual(cv.value, od - 2 * wt, places=6)

    def test_build_missing_dimension_raises_geometry_input_error(self):
        bad_spec = GeometrySpecification(
            readiness_status=GeometryReadinessStatus.GEOMETRY_READY,
            required_dimensions={"outside_diameter_mm": {"value": 100.0, "unit": "mm", "source_file": "x"}},
            geometry_profile_id="pipe",
        )
        with self.assertRaises(GeometryInputError):
            pipe_product.build(bad_spec, GenerationParameters())

    def test_build_invalid_dimensions_raises_construction_rule_unavailable(self):
        bad_spec = GeometrySpecification(
            readiness_status=GeometryReadinessStatus.GEOMETRY_READY,
            required_dimensions={
                "outside_diameter_mm": {"value": 10.0, "unit": "mm", "source_file": "x"},
                "wall_thickness_mm": {"value": 20.0, "unit": "mm", "source_file": "x"},
            },
            geometry_profile_id="pipe",
        )
        with self.assertRaises(ConstructionRuleUnavailableError):
            pipe_product.build(bad_spec, GenerationParameters())

    def test_default_segment_length_used_when_not_specified(self):
        spec = _asme_pipe_spec()
        result = pipe_product.build(spec, GenerationParameters())
        self.assertAlmostEqual(result.expected_dimensions["length_mm"], DEFAULT_PIPE_SEGMENT_LENGTH_MM)

    def test_custom_segment_length_honored(self):
        spec = _asme_pipe_spec()
        result = pipe_product.build(spec, GenerationParameters(pipe_segment_length_mm=750.0))
        self.assertAlmostEqual(result.expected_dimensions["length_mm"], 750.0)


class TestButtweldElbowProductBuilder(unittest.TestCase):
    def test_build_success_uses_centre_to_end_as_bend_radius(self):
        spec = _asme_elbow_spec()
        result = elbow_product.build(spec, GenerationParameters())
        self.assertEqual(result.geometry_type, "buttweld_elbow_90_lr")
        self.assertEqual(result.construction_values, [])  # no rule needed
        cte = spec.required_dimensions["centre_to_end_mm"]["value"]
        self.assertAlmostEqual(result.expected_dimensions["centre_to_end_mm"], cte)

    def test_build_missing_dimension_raises(self):
        bad_spec = GeometrySpecification(
            readiness_status=GeometryReadinessStatus.GEOMETRY_READY,
            required_dimensions={"outside_diameter_mm": {"value": 100.0, "unit": "mm", "source_file": "x"}},
            geometry_profile_id="buttweld_elbow",
        )
        with self.assertRaises(GeometryInputError):
            elbow_product.build(bad_spec, GenerationParameters())


class TestGeometryKernel(unittest.TestCase):
    def test_pipe_generation_end_to_end(self):
        spec = _asme_pipe_spec()
        result = GeometryKernel().generate(spec)
        self.assertEqual(result.generation_status, GeometryGenerationStatus.GEOMETRY_GENERATED)
        self.assertTrue(result.is_generated())
        self.assertEqual(result.geometry_type, "pipe_segment")
        self.assertIsNotNone(result.geometry_fingerprint)
        self.assertEqual(result.geometry_kernel_version, "geometry-kernel-2026.07.15")
        self.assertEqual(result.data_layer_fingerprint, _FINGERPRINT)
        self.assertEqual(result.geometry_specification_fingerprint, spec.geometry_specification_fingerprint)
        self.assertTrue(result.dimensional_validation_summary["passed"])
        self.assertTrue(result.geometry_validation_summary["passed"])
        self.assertIn("pipe_bore_from_od_wall_thickness", result.construction_rule_versions)
        self.assertIsNotNone(result.geometry_payload)
        self.assertIn("mesh", result.geometry_payload)

    def test_module_level_convenience_function_equivalent(self):
        spec = _asme_pipe_spec()
        r1 = GeometryKernel().generate(spec)
        r2 = generate_geometry(spec)
        self.assertEqual(r1.geometry_fingerprint, r2.geometry_fingerprint)
        self.assertEqual(r1.generation_status, r2.generation_status)

    def test_elbow_generation_end_to_end(self):
        spec = _asme_elbow_spec()
        result = generate_geometry(spec)
        self.assertEqual(result.generation_status, GeometryGenerationStatus.GEOMETRY_GENERATED)
        self.assertEqual(result.geometry_type, "buttweld_elbow_90_lr")
        self.assertTrue(result.dimensional_validation_summary["passed"])

    def test_repeated_generation_is_deterministic(self):
        spec = _asme_pipe_spec()
        r1 = generate_geometry(spec)
        r2 = generate_geometry(spec)
        self.assertEqual(r1.geometry_fingerprint, r2.geometry_fingerprint)
        self.assertEqual(r1.topology_summary, r2.topology_summary)

    def test_not_ready_spec_returns_structured_status(self):
        spec = GeometrySpecification(readiness_status=GeometryReadinessStatus.ENGINEERING_SPEC_INCOMPLETE)
        result = generate_geometry(spec)
        self.assertEqual(result.generation_status, GeometryGenerationStatus.GEOMETRY_SPEC_NOT_READY)
        self.assertFalse(result.is_generated())

    def test_unsupported_profile_returns_structured_status(self):
        # "flange_weld_neck" was this test's placeholder unsupported-
        # profile example at Prompt 12 time; Prompt 14 wired it into
        # dispatch, so it was switched to "olet_body" - which Prompt 15
        # then ALSO wired into dispatch. Switched again to
        # "olet_outlet_height" (still genuinely unwired - insufficient
        # dims for any envelope, see geometry_spec/profile.py) - the
        # test's actual subject is dispatch-miss handling, not any
        # specific profile identity.
        spec = GeometrySpecification(readiness_status=GeometryReadinessStatus.GEOMETRY_READY,
                                      geometry_profile_id="olet_outlet_height")
        result = generate_geometry(spec)
        self.assertEqual(result.generation_status, GeometryGenerationStatus.UNSUPPORTED_GEOMETRY_PROFILE)

    def test_missing_required_dimensions_returns_invalid_engineering_dimensions(self):
        spec = GeometrySpecification(readiness_status=GeometryReadinessStatus.GEOMETRY_READY,
                                      required_dimensions={}, geometry_profile_id="pipe")
        result = generate_geometry(spec)
        self.assertEqual(result.generation_status, GeometryGenerationStatus.INVALID_ENGINEERING_DIMENSIONS)

    def test_construction_rule_unavailable_returns_structured_status(self):
        spec = GeometrySpecification(
            readiness_status=GeometryReadinessStatus.GEOMETRY_READY,
            required_dimensions={
                "outside_diameter_mm": {"value": 10.0, "unit": "mm", "source_file": "x"},
                "wall_thickness_mm": {"value": 20.0, "unit": "mm", "source_file": "x"},
            },
            geometry_profile_id="pipe",
        )
        result = generate_geometry(spec)
        self.assertEqual(result.generation_status, GeometryGenerationStatus.CONSTRUCTION_RULE_UNAVAILABLE)

    def test_invalid_generation_parameters_do_not_raise_at_boundary(self):
        spec = _asme_pipe_spec()
        # A malformed GenerationParameters-like object is never accepted by
        # generate() itself (type is enforced by dataclass construction
        # upstream) - this proves the kernel boundary handles a
        # None-vs-explicit default distinction cleanly rather than raising.
        result = generate_geometry(spec, None)
        self.assertTrue(result.is_generated())

    def test_kernel_never_raises_on_unexpected_internal_error(self):
        # Simulate an unexpected internal failure via a profile id that
        # dispatches to a product module, then monkeypatch it to explode -
        # verifies the broad Exception catch-all -> GEOMETRY_GENERATION_FAILED
        # (Sec.5: "the public boundary never raises").
        import kgpe.geometry.kernel as kernel_module

        class _ExplodingProduct:
            @staticmethod
            def build(geometry_spec, generation_parameters):
                raise RuntimeError("simulated unexpected failure")

        original = dict(kernel_module._PRODUCT_DISPATCH)
        kernel_module._PRODUCT_DISPATCH["pipe"] = _ExplodingProduct
        try:
            spec = _asme_pipe_spec()
            result = GeometryKernel().generate(spec)
            self.assertEqual(result.generation_status, GeometryGenerationStatus.GEOMETRY_GENERATION_FAILED)
        finally:
            kernel_module._PRODUCT_DISPATCH.clear()
            kernel_module._PRODUCT_DISPATCH.update(original)

    def test_generation_parameter_mutation_changes_fingerprint_not_engineering_identity(self):
        spec = _asme_pipe_spec()
        r_default = generate_geometry(spec)
        r_custom = generate_geometry(spec, GenerationParameters(radial_segments=64))
        self.assertNotEqual(r_default.geometry_fingerprint, r_custom.geometry_fingerprint)
        self.assertEqual(r_default.geometry_specification_fingerprint, r_custom.geometry_specification_fingerprint)

    def test_segment_length_mutation_changes_fingerprint(self):
        spec = _asme_pipe_spec()
        r_default = generate_geometry(spec)
        r_custom = generate_geometry(spec, GenerationParameters(pipe_segment_length_mm=500.0))
        self.assertNotEqual(r_default.geometry_fingerprint, r_custom.geometry_fingerprint)

    def test_dimension_mutation_changes_fingerprint(self):
        spec_a = _asme_pipe_spec(primary_size="6", schedule="Sch40")
        spec_b = _asme_pipe_spec(primary_size="8", schedule="Sch40")
        r_a = generate_geometry(spec_a)
        r_b = generate_geometry(spec_b)
        self.assertNotEqual(r_a.geometry_fingerprint, r_b.geometry_fingerprint)
        self.assertNotEqual(spec_a.geometry_specification_fingerprint, spec_b.geometry_specification_fingerprint)

    def test_jis_pipe_generation(self):
        result = _prep(product_family="pipe", standard="JIS_G3454", primary_size="150A", schedule="Sch40")
        self.assertTrue(result.is_ready())
        geo_result = generate_geometry(result.geometry_specification)
        self.assertTrue(geo_result.is_generated())

    def test_en_pipe_generation(self):
        result = _prep(product_family="pipe", standard="EN_10216_10217", primary_size="DN150",
                        wall_designation="Series1")
        self.assertTrue(result.is_ready())
        geo_result = generate_geometry(result.geometry_specification)
        self.assertTrue(geo_result.is_generated())


class TestPipeline(unittest.TestCase):
    def test_full_pipeline_pipe_success(self):
        req = EngineeringRequest(product_family="pipe", standard="ASME_B36.10M",
                                  primary_size="6", schedule="Sch40")
        result = run_pipeline(req, resolver=_RESOLVER)
        self.assertTrue(result.is_generated())
        self.assertIsNone(result.failed_stage)
        self.assertEqual(result.identity_resolution.status, ResolutionStatus.RESOLVED)
        self.assertTrue(result.geometry_specification.is_ready())
        self.assertTrue(result.geometry_result.is_generated())

    def test_pipeline_preserves_all_fingerprints_simultaneously(self):
        req = EngineeringRequest(product_family="pipe", standard="ASME_B36.10M",
                                  primary_size="6", schedule="Sch40")
        result = run_pipeline(req, resolver=_RESOLVER)
        self.assertEqual(result.geometry_specification.data_layer_fingerprint, _FINGERPRINT)
        self.assertIsNotNone(result.geometry_specification.geometry_specification_fingerprint)
        self.assertIsNotNone(result.geometry_result.geometry_fingerprint)
        self.assertEqual(result.geometry_result.data_layer_fingerprint, _FINGERPRINT)
        self.assertEqual(result.geometry_result.geometry_specification_fingerprint,
                          result.geometry_specification.geometry_specification_fingerprint)

    def test_pipeline_early_stage_failure_never_attempts_generation(self):
        req = EngineeringRequest(product_family="nonexistent_family")
        result = run_pipeline(req, resolver=_RESOLVER)
        self.assertFalse(result.is_generated())
        self.assertIsNone(result.geometry_result)
        self.assertEqual(result.failed_stage, PipelineStage.ENGINEERING_RESOLUTION)

    def test_pipeline_failed_stage_is_never_relabeled_as_generation_failure(self):
        # A profile-selection failure (no geometry profile for this family/
        # subtype pair) must be reported as PROFILE_SELECTION, never
        # GEOMETRY_GENERATION - generation is never attempted at all.
        req = EngineeringRequest(product_family="olet", subtype="weldolet", standard="MSS_SP97")
        result = run_pipeline(req, resolver=_RESOLVER)
        self.assertIsNone(result.geometry_result)
        self.assertNotEqual(result.failed_stage, PipelineStage.GEOMETRY_GENERATION)

    def test_pipeline_to_dict_shape(self):
        req = EngineeringRequest(product_family="pipe", standard="ASME_B36.10M",
                                  primary_size="6", schedule="Sch40")
        result = run_pipeline(req, resolver=_RESOLVER)
        d = result.to_dict()
        self.assertIn("geometry_result", d)
        self.assertIn("geometry_specification", d)
        self.assertIn("failed_stage", d)


class TestPackageInitExports(unittest.TestCase):
    def test_key_public_names_exported(self):
        for name in ("Mesh", "GeometryKernel", "generate_geometry", "GeometryResult",
                     "GeometryGenerationStatus", "GenerationParameters", "PipelineResult", "run_pipeline"):
            self.assertTrue(hasattr(geo, name), f"kgpe.geometry missing expected export {name!r}")

    def test_package_never_imports_legacy_generator_dispatch(self):
        # Sec.2/Constraint: the new kernel is strictly additive and must
        # never route through kgpe/generator.py's _DISPATCH.
        import kgpe.geometry.kernel as kernel_module
        self.assertFalse(hasattr(kernel_module, "_DISPATCH"))


class TestLegacyIsolationAndDemo(unittest.TestCase):
    def test_legacy_generator_dispatch_still_intact(self):
        from kgpe.generator import _DISPATCH
        self.assertIn("pipe", _DISPATCH)

    def test_legacy_generator_module_still_importable_and_untouched(self):
        # Sec.2/Constraint: importing the new kgpe.geometry package must
        # never disturb kgpe.generator's own public surface. Exact
        # request/response behaviour of the legacy generator is already
        # covered by Prompts 1-3's own demo/tests - only import-time
        # co-existence is asserted here.
        from kgpe import generator
        self.assertTrue(hasattr(generator, "generate_geometry"))
        self.assertTrue(callable(generator.generate_geometry))

    def test_data_layer_fingerprint_unchanged(self):
        self.assertEqual(
            _FINGERPRINT,
            "9238ab3cb896101c545450df6f0ff070301b4ba68117771b4105e87606c2c873",
        )


if __name__ == "__main__":
    unittest.main()
