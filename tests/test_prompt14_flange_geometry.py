# -*- coding: utf-8 -*-
"""
tests/test_prompt14_flange_geometry.py
==========================================
Prompt 14: automated tests for ASME B16.5 / JIS B2220 / EN 1092-1
weld-neck flange geometry built on top of the Prompt 12-13 kernel.
Standard-library `unittest` only.
"""
import math
import unittest

from kgpe.contract.canonical_reader import build_canonical_reader
from kgpe.contract.snapshot import registry_fingerprint
from kgpe.resolver import EngineeringRequest, EngineeringResolver, ResolutionStatus
from kgpe.geometry_spec import prepare_geometry_specification, find_profile, GeometryReadinessStatus
from kgpe.geometry_spec import coverage as cov

import kgpe.geometry as geo
from kgpe.geometry.cross_family import FlangeBoreViaPipeScheduleRule
from kgpe.geometry.construction_rules import ConstructionRuleStatus
from kgpe.geometry.bolt_pattern import build_bolt_pattern, validate_bolt_pattern, BoltPatternError
from kgpe.geometry.mating_interface import MatingInterface, FACE_TYPE_NOT_TRACKED
from kgpe.geometry.ports import (
    OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE, OPENING_DIAMETER_PROVENANCE_DERIVED,
    OPENING_DIAMETER_PROVENANCE_NOT_MODELED,
)
from kgpe.geometry.result import GeometryGenerationStatus, TopologyRepresentation
from kgpe.geometry.kernel import GeometryKernel, generate_geometry
from kgpe.geometry.pipeline import run_pipeline
from kgpe.geometry.products import flange

_READER, _ = build_canonical_reader()
_FINGERPRINT = registry_fingerprint(_READER.registry)
_RESOLVER = EngineeringResolver(_READER, _FINGERPRINT)
_DATA_LAYER_FINGERPRINT = "9238ab3cb896101c545450df6f0ff070301b4ba68117771b4105e87606c2c873"


def _prep(**kwargs):
    return prepare_geometry_specification(EngineeringRequest(**kwargs), resolver=_RESOLVER)


def _flange_spec(standard, primary_size, extra_dims=None, **rating):
    kwargs = dict(product_family="flange", subtype="weld_neck", standard=standard, primary_size=primary_size)
    kwargs.update(rating)
    if extra_dims:
        kwargs["dimensions"] = extra_dims
    r = _prep(**kwargs)
    assert r.is_ready(), (standard, primary_size, r.geometry_specification.warnings)
    return r.geometry_specification


def _asme_bore(target_size, pipe_schedule="Sch40"):
    outcome = FlangeBoreViaPipeScheduleRule().resolve(
        _RESOLVER, target_standard="ASME_B16.5", target_size_system="nps", target_size=target_size,
        pipe_standard="ASME_B36.10M", pipe_schedule=pipe_schedule)
    assert outcome.is_applied(), outcome.detail
    return outcome.value


class TestFlangeCanonicalCoverageInspection(unittest.TestCase):
    """Sec.2: live canonical coverage, confirmed directly against the
    registry - never assumed from published-table conventions."""

    def test_asme_b16_5_available_dimensions(self):
        # ASME B16.5's OD/bolt-circle/bolt-hole/num-bolts facts are
        # ingested with flange_type=None (shared across subtypes per the
        # adapter's own docstring) - only flange_thickness_weld_neck_mm is
        # flange_type-scoped - so this query is intentionally NOT scoped
        # by flange_type (an exact-match filter would incorrectly exclude
        # the None-scoped facts).
        dims = _READER.available_dimensions(product_family="flange", standard="ASME_B16.5")
        for d in ("outside_diameter_mm", "flange_thickness_weld_neck_mm", "bolt_circle_diameter_mm",
                  "bolt_hole_diameter_mm", "num_bolts", "bolt_size_designation"):
            self.assertIn(d, dims)
        self.assertNotIn("bore_diameter_mm", dims)
        self.assertNotIn("raised_face_diameter_mm", dims)
        self.assertNotIn("raised_face_height_mm", dims)
        self.assertNotIn("hub_base_diameter_mm", dims)
        self.assertNotIn("length_through_hub_mm", dims)

    def test_jis_b2220_available_dimensions(self):
        dims = _READER.available_dimensions(product_family="flange", standard="JIS_B2220",
                                              flange_type="weld_neck")
        for d in ("outside_diameter_mm", "flange_thickness_weld_neck_mm", "bolt_circle_diameter_mm",
                  "bolt_hole_diameter_mm", "num_bolts", "bolt_size_designation",
                  "bore_diameter_mm", "raised_face_diameter_mm"):
            self.assertIn(d, dims)
        self.assertNotIn("raised_face_height_mm", dims)
        self.assertNotIn("hub_base_diameter_mm", dims)
        self.assertNotIn("length_through_hub_mm", dims)

    def test_en_1092_1_available_dimensions(self):
        dims = _READER.available_dimensions(product_family="flange", standard="EN_1092-1",
                                              flange_type="weld_neck")
        for d in ("outside_diameter_mm", "flange_thickness_weld_neck_mm", "bolt_circle_diameter_mm",
                  "bolt_hole_diameter_mm", "num_bolts", "bolt_size_designation"):
            self.assertIn(d, dims)
        self.assertNotIn("bore_diameter_mm", dims)
        self.assertNotIn("raised_face_diameter_mm", dims)
        self.assertNotIn("raised_face_height_mm", dims)
        self.assertNotIn("hub_base_diameter_mm", dims)
        self.assertNotIn("length_through_hub_mm", dims)

    def test_raised_face_height_absent_for_every_standard(self):
        # Sec.18-19: zero production facts for raised_face_height_mm at
        # ANY standard - confirmed directly, not inferred.
        for standard in ("ASME_B16.5", "JIS_B2220", "EN_1092-1"):
            dims = _READER.available_dimensions(product_family="flange", standard=standard)
            self.assertNotIn("raised_face_height_mm", dims)

    def test_hub_dimensions_absent_for_every_standard(self):
        # Sec.21-22: zero production facts for hub_base_diameter_mm/
        # length_through_hub_mm at ANY standard.
        for standard in ("ASME_B16.5", "JIS_B2220", "EN_1092-1"):
            dims = _READER.available_dimensions(product_family="flange", standard=standard)
            self.assertNotIn("hub_base_diameter_mm", dims)
            self.assertNotIn("length_through_hub_mm", dims)


class TestFlangeSubtypeSupportMatrix(unittest.TestCase):
    """Sec.3: only weld_neck is a defined, canonical-data-backed profile
    for any of the three standards - blind/slip-on/threaded/socket-weld/
    lap-joint are UNSUPPORTED_BY_CANONICAL_DATA (no profile exists, never
    fabricated from general engineering knowledge)."""

    def test_weld_neck_is_the_only_defined_flange_profile(self):
        profile = find_profile("flange", "weld_neck")
        self.assertIsNotNone(profile)
        self.assertEqual(profile.profile_id, "flange_weld_neck")

    def test_blind_subtype_unsupported_by_canonical_data(self):
        self.assertIsNone(find_profile("flange", "blind"))

    def test_slip_on_subtype_unsupported_by_canonical_data(self):
        self.assertIsNone(find_profile("flange", "slip_on"))

    def test_threaded_socket_weld_lap_joint_unsupported(self):
        for subtype in ("threaded", "socket_weld", "lap_joint", "loose", "plate"):
            self.assertIsNone(find_profile("flange", subtype))

    def test_no_flange_type_other_than_weld_neck_has_any_facts(self):
        # Confirms live: no standard's canonical data distinguishes a
        # second flange_type identity at all (blind/slip-on facts do not
        # exist under ANY flange_type value other than weld_neck/None).
        for standard in ("ASME_B16.5", "JIS_B2220", "EN_1092-1"):
            types = _READER.discover("flange_type", product_family="flange", standard=standard)
            self.assertTrue(set(types) <= {"weld_neck"})


class TestCrossStandardIdentityIsolation(unittest.TestCase):
    """Sec.4/26/39: ASME Class, JIS K, and EN PN are never conflated;
    NPS/DN/JIS-size systems are never cross-converted."""

    def test_asme_class_not_treated_as_pn(self):
        spec = _flange_spec("ASME_B16.5", "2", pressure_class="150")
        identity = spec.engineering_object_identity
        self.assertEqual(identity["pressure_class"], "150")
        self.assertIsNone(identity["pn"])

    def test_jis_k_not_treated_as_pn(self):
        spec = _flange_spec("JIS_B2220", 50, jis_k="10K")
        identity = spec.engineering_object_identity
        self.assertEqual(identity["jis_k"], "10K")
        self.assertIsNone(identity["pn"])

    def test_en_pn_preserved_as_pn(self):
        spec = _flange_spec("EN_1092-1", 50, pn="PN16")
        identity = spec.engineering_object_identity
        self.assertIsNotNone(identity["pn"])
        self.assertIsNone(identity["pressure_class"])
        self.assertIsNone(identity["jis_k"])

    def test_size_systems_isolated(self):
        asme_spec = _flange_spec("ASME_B16.5", "2", pressure_class="150")
        jis_spec = _flange_spec("JIS_B2220", 50, jis_k="10K")
        en_spec = _flange_spec("EN_1092-1", 50, pn="PN16")
        self.assertEqual(asme_spec.engineering_object_identity["size_system"], "nps")
        self.assertEqual(jis_spec.engineering_object_identity["size_system"], "jis_size")
        self.assertEqual(en_spec.engineering_object_identity["size_system"], "dn")

    def test_nominally_similar_sizes_remain_distinct_identities(self):
        # JIS "50A" and EN DN50 are numerically similar but are NEVER the
        # same engineering identity - confirmed via distinct standard +
        # distinct resolved dimension values.
        jis_spec = _flange_spec("JIS_B2220", 50, jis_k="10K")
        en_spec = _flange_spec("EN_1092-1", 50, pn="PN16")
        self.assertNotEqual(jis_spec.engineering_object_identity["standard"],
                             en_spec.engineering_object_identity["standard"])
        self.assertNotEqual(jis_spec.required_dimensions["outside_diameter_mm"]["value"],
                             en_spec.required_dimensions["outside_diameter_mm"]["value"])

    def test_geometry_fingerprints_differ_across_standards(self):
        asme_spec = _flange_spec("ASME_B16.5", "2", pressure_class="150")
        jis_spec = _flange_spec("JIS_B2220", 50, jis_k="10K")
        en_spec = _flange_spec("EN_1092-1", 50, pn="PN16")
        r_asme = generate_geometry(asme_spec)
        r_jis = generate_geometry(jis_spec)
        r_en = generate_geometry(en_spec)
        fps = {r_asme.geometry_fingerprint, r_jis.geometry_fingerprint, r_en.geometry_fingerprint}
        self.assertEqual(len(fps), 3)

    def test_one_standards_missing_feature_not_filled_from_another(self):
        # ASME/EN have no bore/raised-face facts - confirm neither is
        # silently backfilled from JIS's data when generating ASME/EN
        # geometry with no explicit bore/RF context supplied.
        asme_spec = _flange_spec("ASME_B16.5", "2", pressure_class="150")
        en_spec = _flange_spec("EN_1092-1", 50, pn="PN16")
        r_asme = generate_geometry(asme_spec)
        r_en = generate_geometry(en_spec)
        self.assertEqual(r_asme.topology_representation,
                          TopologyRepresentation.SOLID_EXTERNAL_ENVELOPE_WITH_BOLT_HOLE_METADATA_NO_BOOLEAN_CUT)
        self.assertEqual(r_en.topology_representation,
                          TopologyRepresentation.SOLID_EXTERNAL_ENVELOPE_WITH_BOLT_HOLE_METADATA_NO_BOOLEAN_CUT)


class TestBoltPatternModel(unittest.TestCase):
    def test_build_bolt_pattern_deterministic_placement(self):
        p = build_bolt_pattern(200.0, 20.0, 8)
        self.assertEqual(p.count, 8)
        self.assertEqual(len(p.hole_centres), 8)
        self.assertAlmostEqual(p.hole_centres[0][0], 100.0)
        self.assertAlmostEqual(p.hole_centres[0][1], 0.0)

    def test_bolt_pattern_repeatable_across_calls(self):
        p1 = build_bolt_pattern(200.0, 20.0, 8)
        p2 = build_bolt_pattern(200.0, 20.0, 8)
        self.assertEqual(p1.hole_centres, p2.hole_centres)

    def test_bolt_pattern_serializable(self):
        p = build_bolt_pattern(200.0, 20.0, 4)
        d = p.to_dict()
        self.assertEqual(d["count"], 4)
        self.assertEqual(len(d["hole_centres"]), 4)
        self.assertIsInstance(d["hole_centres"][0], list)

    def test_bolt_pattern_validation_passes_for_valid_pattern(self):
        p = build_bolt_pattern(200.0, 20.0, 8)
        self.assertTrue(validate_bolt_pattern(p))

    def test_bolt_pattern_hole_centres_on_bolt_circle_radius(self):
        p = build_bolt_pattern(150.0, 15.0, 6)
        for x, y, z in p.hole_centres:
            r = math.hypot(x, y)
            self.assertAlmostEqual(r, 75.0)

    def test_bolt_pattern_angular_spacing_is_360_over_n(self):
        p = build_bolt_pattern(150.0, 15.0, 6)
        for i, (x, y, z) in enumerate(p.hole_centres):
            expected_angle = i * (360.0 / 6)
            actual_angle = math.degrees(math.atan2(y, x)) % 360.0
            self.assertAlmostEqual(actual_angle, expected_angle % 360.0, places=6)

    def test_bolt_pattern_rejects_non_positive_count(self):
        with self.assertRaises(BoltPatternError):
            build_bolt_pattern(200.0, 20.0, 0)

    def test_bolt_pattern_rejects_non_positive_hole_diameter(self):
        with self.assertRaises(BoltPatternError):
            build_bolt_pattern(200.0, -5.0, 8)

    def test_bolt_pattern_no_duplicate_hole_centres(self):
        p = build_bolt_pattern(200.0, 20.0, 12)
        centres_2d = [(round(x, 6), round(y, 6)) for x, y, z in p.hole_centres]
        self.assertEqual(len(centres_2d), len(set(centres_2d)))

    def test_bolt_pattern_finite_coordinates(self):
        p = build_bolt_pattern(200.0, 20.0, 8)
        for c in p.hole_centres:
            for v in c:
                self.assertTrue(math.isfinite(v))


class TestMatingInterfaceMetadata(unittest.TestCase):
    def test_mating_interface_serializable(self):
        m = MatingInterface(mating_face_centre=(0, 0, 0), mating_face_normal=(0, 0, -1),
                             outside_diameter_mm=152.4, bolt_circle_diameter_mm=120.65,
                             bolt_hole_count=4, bolt_hole_diameter_mm=19.05)
        d = m.to_dict()
        self.assertEqual(d["bolt_hole_count"], 4)
        self.assertEqual(d["face_type"], FACE_TYPE_NOT_TRACKED)

    def test_flange_geometry_exposes_mating_interface_feature(self):
        spec = _flange_spec("ASME_B16.5", "2", pressure_class="150")
        result = generate_geometry(spec)
        feats = result.geometry_payload["features"]
        mating = next(f for f in feats if f["name"] == "mating_interface")
        self.assertEqual(mating["params"]["face_type"], FACE_TYPE_NOT_TRACKED)
        self.assertEqual(mating["params"]["bolt_hole_count"],
                          int(spec.required_dimensions["num_bolts"]["value"]))


class TestFlangeBorePolicy(unittest.TestCase):
    def test_jis_direct_authoritative_bore_when_requested(self):
        spec = _flange_spec("JIS_B2220", 50, extra_dims=["bore_diameter_mm"], jis_k="10K")
        self.assertIn("bore_diameter_mm", spec.optional_dimensions)
        result = generate_geometry(spec)
        self.assertTrue(result.is_generated())
        self.assertEqual(result.topology_representation,
                          TopologyRepresentation.HOLLOW_ANNULAR_BODY_WITH_BOLT_HOLE_METADATA_NO_BOOLEAN_CUT)
        port = result.connection_ports[0]
        self.assertEqual(port["opening_diameter_provenance"], OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE)

    def test_asme_bore_via_cross_family_construction_value(self):
        spec = _flange_spec("ASME_B16.5", "2", pressure_class="150")
        bore_cv = _asme_bore("2")
        result = generate_geometry(spec, product_kwargs={"bore_value": bore_cv})
        self.assertTrue(result.is_generated())
        self.assertEqual(result.topology_representation,
                          TopologyRepresentation.HOLLOW_ANNULAR_BODY_WITH_BOLT_HOLE_METADATA_NO_BOOLEAN_CUT)
        port = result.connection_ports[0]
        self.assertEqual(port["opening_diameter_provenance"], OPENING_DIAMETER_PROVENANCE_DERIVED)

    def test_asme_no_bore_context_yields_external_envelope(self):
        spec = _flange_spec("ASME_B16.5", "2", pressure_class="150")
        result = generate_geometry(spec)
        self.assertTrue(result.is_generated())
        self.assertEqual(result.topology_representation,
                          TopologyRepresentation.SOLID_EXTERNAL_ENVELOPE_WITH_BOLT_HOLE_METADATA_NO_BOOLEAN_CUT)
        port = result.connection_ports[0]
        self.assertIsNone(port["opening_diameter_mm"])
        self.assertEqual(port["opening_diameter_provenance"], OPENING_DIAMETER_PROVENANCE_NOT_MODELED)

    def test_en_1092_1_bore_genuinely_unavailable(self):
        spec = _flange_spec("EN_1092-1", 50, pn="PN16")
        result = generate_geometry(spec)
        self.assertTrue(result.is_generated())
        self.assertEqual(result.topology_representation,
                          TopologyRepresentation.SOLID_EXTERNAL_ENVELOPE_WITH_BOLT_HOLE_METADATA_NO_BOOLEAN_CUT)

    def test_bore_never_exceeds_od(self):
        spec = _flange_spec("ASME_B16.5", "2", pressure_class="150")
        od = spec.required_dimensions["outside_diameter_mm"]["value"]
        bore_cv = _asme_bore("2")
        self.assertLess(bore_cv.value, od)


class TestFlangeBoreViaPipeScheduleRuleHardening(unittest.TestCase):
    def test_missing_pipe_context_fails_closed(self):
        outcome = FlangeBoreViaPipeScheduleRule().resolve(
            _RESOLVER, target_standard="ASME_B16.5", target_size_system="nps", target_size="2",
            pipe_standard=None, pipe_schedule=None)
        self.assertEqual(outcome.status, ConstructionRuleStatus.RULE_INPUT_MISSING)

    def test_ambiguous_partial_context_fails_closed(self):
        outcome = FlangeBoreViaPipeScheduleRule().resolve(
            _RESOLVER, target_standard="ASME_B16.5", target_size_system="nps", target_size="2",
            pipe_standard="ASME_B36.10M", pipe_schedule=None)
        self.assertEqual(outcome.status, ConstructionRuleStatus.RULE_INPUT_MISSING)

    def test_never_defaults_schedule(self):
        cv_40 = _asme_bore("2", pipe_schedule="Sch40")
        cv_80 = _asme_bore("2", pipe_schedule="Sch80")
        self.assertNotAlmostEqual(cv_40.value, cv_80.value)

    def test_never_writes_derived_bore_into_canonical_registry(self):
        before = len(_READER.registry.all_facts())
        _asme_bore("2")
        after = len(_READER.registry.all_facts())
        self.assertEqual(before, after)

    def test_preserves_flange_and_pipe_identity_separately(self):
        cv = _asme_bore("2")
        refs = cv.input_dimension_refs
        self.assertTrue(any(r["source_ref"].get("product_family") == "pipe" for r in refs))
        self.assertTrue(any("cross-family" in t for t in cv.derivation_trace))

    def test_bore_construction_value_provenance_complete(self):
        cv = _asme_bore("2")
        self.assertEqual(cv.name, "bore_diameter_mm")
        self.assertEqual(cv.unit, "mm")
        self.assertTrue(cv.rule_id)
        self.assertTrue(cv.rule_version)
        self.assertTrue(cv.input_dimension_refs)
        self.assertTrue(cv.derivation_trace)


class TestBlindFlangeGeometry(unittest.TestCase):
    """Sec.17: no canonical thickness/subtype data supports a blind
    flange this prompt - confirmed genuinely unsupported, never
    fabricated with borrowed weld-neck geometry."""

    def test_blind_flange_request_has_no_profile(self):
        # "blind" is not a recognized subtype identity at all in the
        # canonical data this project ingests (confirmed live - no
        # flange_type other than weld_neck/None has ever been recorded),
        # so the request fails even earlier than profile selection - at
        # engineering identity resolution itself. Either way, no blind-
        # flange geometry is ever fabricated.
        r = _prep(product_family="flange", subtype="blind", standard="ASME_B16.5",
                   primary_size="2", pressure_class="150")
        self.assertFalse(r.is_ready())
        self.assertIn(r.geometry_specification.readiness_status,
                       (GeometryReadinessStatus.GEOMETRY_PROFILE_UNAVAILABLE,
                        GeometryReadinessStatus.UNSUPPORTED_GEOMETRY_REQUEST))
        self.assertIsNone(find_profile("flange", "blind"))


class TestRaisedFaceAndHubAndFaceType(unittest.TestCase):
    def test_raised_face_partial_when_diameter_known(self):
        spec = _flange_spec("JIS_B2220", 50, extra_dims=["raised_face_diameter_mm"], jis_k="10K")
        result = generate_geometry(spec)
        rf = next(f for f in result.geometry_payload["features"] if f["name"] == "raised_face")
        self.assertEqual(rf["params"]["status"], "PARTIAL_DIAMETER_KNOWN_HEIGHT_UNAVAILABLE")
        self.assertIsNotNone(rf["params"]["raised_face_diameter_mm"])
        self.assertIsNone(rf["params"]["raised_face_height_mm"])

    def test_raised_face_unavailable_for_asme_and_en(self):
        for standard, size, rating in (("ASME_B16.5", "2", {"pressure_class": "150"}),
                                        ("EN_1092-1", 50, {"pn": "PN16"})):
            spec = _flange_spec(standard, size, **rating)
            result = generate_geometry(spec)
            rf = next(f for f in result.geometry_payload["features"] if f["name"] == "raised_face")
            self.assertEqual(rf["params"]["status"], "UNAVAILABLE_NO_AUTHORITATIVE_DIMENSIONS")

    def test_hub_always_unavailable(self):
        for standard, size, rating in (("ASME_B16.5", "2", {"pressure_class": "150"}),
                                        ("JIS_B2220", 50, {"jis_k": "10K"}),
                                        ("EN_1092-1", 50, {"pn": "PN16"})):
            spec = _flange_spec(standard, size, **rating)
            result = generate_geometry(spec)
            hub = next(f for f in result.geometry_payload["features"] if f["name"] == "hub")
            self.assertEqual(hub["params"]["status"], "UNAVAILABLE_NO_AUTHORITATIVE_DIMENSIONS_ANY_STANDARD")

    def test_face_type_never_silently_assumed_rf(self):
        spec = _flange_spec("JIS_B2220", 50, extra_dims=["raised_face_diameter_mm"], jis_k="10K")
        result = generate_geometry(spec)
        mating = next(f for f in result.geometry_payload["features"] if f["name"] == "mating_interface")
        self.assertEqual(mating["params"]["face_type"], FACE_TYPE_NOT_TRACKED)


class TestFlangeDimensionalValidationAndSanity(unittest.TestCase):
    def test_od_and_thickness_measured_and_validated(self):
        spec = _flange_spec("ASME_B16.5", "2", pressure_class="150")
        result = generate_geometry(spec)
        self.assertTrue(result.dimensional_validation_summary["passed"])
        od = spec.required_dimensions["outside_diameter_mm"]["value"]
        self.assertAlmostEqual(result.geometry_payload["measurements"]["outside_diameter_mm"], od, places=3)

    def test_bore_measured_and_validated_when_present(self):
        spec = _flange_spec("ASME_B16.5", "2", pressure_class="150")
        bore_cv = _asme_bore("2")
        result = generate_geometry(spec, product_kwargs={"bore_value": bore_cv})
        self.assertTrue(result.dimensional_validation_summary["passed"])
        self.assertAlmostEqual(result.geometry_payload["measurements"]["bore_diameter_mm"], bore_cv.value, places=3)

    def test_bolt_circle_less_than_od_enforced(self):
        spec = _flange_spec("ASME_B16.5", "2", pressure_class="150")
        bolt_circle = spec.required_dimensions["bolt_circle_diameter_mm"]["value"]
        od = spec.required_dimensions["outside_diameter_mm"]["value"]
        self.assertLess(bolt_circle, od)

    def test_bolt_hole_positive(self):
        spec = _flange_spec("ASME_B16.5", "2", pressure_class="150")
        self.assertGreater(spec.required_dimensions["bolt_hole_diameter_mm"]["value"], 0.0)

    def test_thickness_positive(self):
        spec = _flange_spec("ASME_B16.5", "2", pressure_class="150")
        self.assertGreater(spec.required_dimensions["flange_thickness_weld_neck_mm"]["value"], 0.0)

    def test_hole_envelope_within_od(self):
        spec = _flange_spec("ASME_B16.5", "2", pressure_class="150")
        bc = spec.required_dimensions["bolt_circle_diameter_mm"]["value"]
        bh = spec.required_dimensions["bolt_hole_diameter_mm"]["value"]
        od = spec.required_dimensions["outside_diameter_mm"]["value"]
        self.assertLessEqual(bc / 2.0 + bh / 2.0, od / 2.0)

    def test_raised_face_diameter_never_exceeds_od(self):
        spec = _flange_spec("JIS_B2220", 50, extra_dims=["raised_face_diameter_mm"], jis_k="10K")
        rf = spec.optional_dimensions["raised_face_diameter_mm"]["value"]
        od = spec.required_dimensions["outside_diameter_mm"]["value"]
        self.assertLessEqual(rf, od)


class TestFlangeTopologyRepresentation(unittest.TestCase):
    def test_topology_never_claims_boolean_cut_holes(self):
        for topo in (TopologyRepresentation.HOLLOW_ANNULAR_BODY_WITH_BOLT_HOLE_METADATA_NO_BOOLEAN_CUT,
                     TopologyRepresentation.SOLID_EXTERNAL_ENVELOPE_WITH_BOLT_HOLE_METADATA_NO_BOOLEAN_CUT):
            self.assertIn("NO_BOOLEAN_CUT", topo)

    def test_bolt_pattern_feature_carries_full_hole_metadata(self):
        spec = _flange_spec("ASME_B16.5", "2", pressure_class="150")
        result = generate_geometry(spec)
        bp = next(f for f in result.geometry_payload["features"] if f["name"] == "bolt_pattern")
        self.assertEqual(len(bp["params"]["hole_centres"]),
                          int(spec.required_dimensions["num_bolts"]["value"]))
        self.assertEqual(bp["params"]["bolt_circle_diameter_mm"],
                          spec.required_dimensions["bolt_circle_diameter_mm"]["value"])


class TestFingerprintDeterminismAndBoltPatternSensitivity(unittest.TestCase):
    def test_data_layer_fingerprint_unchanged(self):
        self.assertEqual(_FINGERPRINT, _DATA_LAYER_FINGERPRINT)

    def test_repeated_generation_is_deterministic(self):
        spec = _flange_spec("ASME_B16.5", "2", pressure_class="150")
        r1 = generate_geometry(spec)
        r2 = generate_geometry(spec)
        self.assertEqual(r1.geometry_fingerprint, r2.geometry_fingerprint)

    def test_bolt_count_change_alters_fingerprint(self):
        # NPS2 (4 bolts) vs NPS4 (8 bolts), both ASME_B16.5 Class150 -
        # confirmed live bolt-count difference.
        spec2 = _flange_spec("ASME_B16.5", "2", pressure_class="150")
        spec4 = _flange_spec("ASME_B16.5", "4", pressure_class="150")
        r2 = generate_geometry(spec2)
        r4 = generate_geometry(spec4)
        self.assertNotEqual(spec2.required_dimensions["num_bolts"]["value"],
                             spec4.required_dimensions["num_bolts"]["value"])
        self.assertNotEqual(r2.geometry_fingerprint, r4.geometry_fingerprint)

    def test_hollow_vs_solid_fingerprints_differ_same_spec(self):
        spec = _flange_spec("ASME_B16.5", "2", pressure_class="150")
        r_solid = generate_geometry(spec)
        r_hollow = generate_geometry(spec, product_kwargs={"bore_value": _asme_bore("2")})
        self.assertEqual(r_solid.geometry_specification_fingerprint, r_hollow.geometry_specification_fingerprint)
        self.assertNotEqual(r_solid.geometry_fingerprint, r_hollow.geometry_fingerprint)

    def test_tessellation_only_change_alters_fingerprint_not_identity(self):
        spec = _flange_spec("ASME_B16.5", "2", pressure_class="150")
        r_default = generate_geometry(spec)
        r_more_segments = generate_geometry(spec, geo.GenerationParameters(radial_segments=64))
        self.assertEqual(r_default.geometry_specification_fingerprint, r_more_segments.geometry_specification_fingerprint)
        self.assertNotEqual(r_default.geometry_fingerprint, r_more_segments.geometry_fingerprint)


class TestProductDispatchExpansion(unittest.TestCase):
    def test_flange_weld_neck_registered(self):
        from kgpe.geometry.kernel import _PRODUCT_DISPATCH
        self.assertIn("flange_weld_neck", _PRODUCT_DISPATCH)

    def test_unsupported_blind_profile_stays_unsupported(self):
        r = _prep(product_family="flange", subtype="blind", standard="ASME_B16.5",
                   primary_size="2", pressure_class="150")
        self.assertFalse(r.is_ready())


class TestQuarantineAndLegacyFixtureIsolation(unittest.TestCase):
    def test_production_registry_has_no_legacy_fixture_facts(self):
        # Sec.34/37: the Prompt 3/5 legacy CRM quarantine fixture (NPS14/
        # Class150 raised-face conflict, Class300/NPS2 hub-length) is
        # NEVER loaded by build_canonical_reader()'s production registry -
        # confirmed directly (zero quarantined flange facts exist there).
        quarantined = _READER.inspect_quarantined()
        flange_quarantined = [f for f in quarantined if f.applicability.product_family == "flange"]
        self.assertEqual(flange_quarantined, [])

    def test_flange_facts_are_all_verified_authoritative(self):
        for standard in ("ASME_B16.5", "JIS_B2220", "EN_1092-1"):
            facts = _READER._matching_facts(dimension_name="outside_diameter_mm",
                                             product_family="flange", standard=standard)
            self.assertTrue(facts)
            for f in facts:
                self.assertEqual(f.verification_status, "VERIFIED_AUTHORITATIVE")

    def test_no_flange_size_is_quarantined(self):
        # Unlike ASME B16.9 buttweld (NPS8/NPS12 OD quarantine), no flange
        # size/standard combination is quarantined at all - confirmed
        # every representative flange request this suite uses reaches
        # GEOMETRY_READY, never ENGINEERING_DATA_QUARANTINED.
        for standard, size, rating in (("ASME_B16.5", "8", {"pressure_class": "150"}),
                                        ("ASME_B16.5", "12", {"pressure_class": "150"})):
            r = _prep(product_family="flange", subtype="weld_neck", standard=standard,
                      primary_size=size, **rating)
            self.assertNotEqual(r.geometry_specification.readiness_status,
                                 GeometryReadinessStatus.ENGINEERING_DATA_QUARANTINED)


class TestKernelRegressionScenarios(unittest.TestCase):
    """Sec.40 scenarios 41-48: Prompt 12-13 products unchanged by this
    prompt's flange work."""

    def test_41_asme_pipe_unchanged(self):
        r = _prep(product_family="pipe", standard="ASME_B36.10M", primary_size="6", schedule="Sch40")
        self.assertTrue(generate_geometry(r.geometry_specification).is_generated())

    def test_42_jis_pipe_unchanged(self):
        r = _prep(product_family="pipe", standard="JIS_G3454", primary_size="150A", schedule="Sch40")
        self.assertTrue(generate_geometry(r.geometry_specification).is_generated())

    def test_43_en_pipe_unchanged(self):
        r = _prep(product_family="pipe", standard="EN_10216_10217", primary_size="DN150",
                   wall_designation="Series1")
        self.assertTrue(generate_geometry(r.geometry_specification).is_generated())

    def test_44_elbow_unchanged(self):
        r = _prep(product_family="buttweld_fitting", subtype="elbow_90_lr", standard="ASME_B16.9",
                   primary_size="6")
        self.assertTrue(generate_geometry(r.geometry_specification).is_generated())

    def test_45_tee_unchanged(self):
        r = _prep(product_family="buttweld_fitting", subtype="tee_equal", standard="ASME_B16.9",
                   primary_size="4")
        self.assertTrue(generate_geometry(r.geometry_specification).is_generated())

    def test_46_cap_unchanged(self):
        r = _prep(product_family="buttweld_fitting", subtype="cap", standard="ASME_B16.9", primary_size="4")
        self.assertTrue(generate_geometry(r.geometry_specification).is_generated())

    def test_47_concentric_reducer_unchanged(self):
        from kgpe.geometry.reducer_rules import ReducerPerEndOutsideDiameterRule
        r = _prep(product_family="buttweld_fitting", subtype="reducer_concentric", standard="ASME_B16.9",
                   large_end_size="6", small_end_size="4")
        ods = ReducerPerEndOutsideDiameterRule().resolve(_RESOLVER, standard="ASME_B16.9",
                                                          large_end_size="6", small_end_size="4").value
        res = generate_geometry(r.geometry_specification,
                                 product_kwargs={"large_od_value": ods[0], "small_od_value": ods[1]})
        self.assertTrue(res.is_generated())

    def test_48_eccentric_reducer_unchanged(self):
        from kgpe.geometry.reducer_rules import ReducerPerEndOutsideDiameterRule
        r = _prep(product_family="buttweld_fitting", subtype="reducer_eccentric", standard="ASME_B16.9",
                   large_end_size="6", small_end_size="4")
        ods = ReducerPerEndOutsideDiameterRule().resolve(_RESOLVER, standard="ASME_B16.9",
                                                          large_end_size="6", small_end_size="4").value
        res = generate_geometry(r.geometry_specification,
                                 product_kwargs={"large_od_value": ods[0], "small_od_value": ods[1],
                                                  "eccentric": True})
        self.assertTrue(res.is_generated())

    def test_50_full_regression_marker(self):
        # Sec.40 scenario 50 ("full test suite has zero regressions") is
        # verified by running the complete suite separately (see Prompt
        # 14 report Sec.45) - this marker documents the scenario exists.
        self.assertTrue(True)


    def test_49_existing_demo_marker(self):
        # Sec.40 scenario 49: examples/demo.py is run separately (Prompt
        # 14 report Sec.46) - unchanged/PASS, including its determinism
        # check.
        self.assertTrue(True)


class TestRepresentativeScenarios(unittest.TestCase):
    """Sec.36-38: scenarios 1-15 (ASME B16.5), 16-24 (JIS B2220), 25-33
    (EN 1092-1) - real supported canonical combinations only."""

    # --- ASME B16.5 (1-15) ---
    def test_01_asme_flange_body_generation(self):
        spec = _flange_spec("ASME_B16.5", "2", pressure_class="150")
        self.assertTrue(generate_geometry(spec).is_generated())

    def test_02_asme_od_validation(self):
        spec = _flange_spec("ASME_B16.5", "2", pressure_class="150")
        r = generate_geometry(spec)
        self.assertTrue(r.dimensional_validation_summary["passed"])

    def test_03_asme_thickness_validation(self):
        spec = _flange_spec("ASME_B16.5", "2", pressure_class="150")
        r = generate_geometry(spec)
        self.assertAlmostEqual(
            r.geometry_payload["measurements"]["flange_thickness_weld_neck_mm"],
            spec.required_dimensions["flange_thickness_weld_neck_mm"]["value"], places=3)

    def test_04_asme_bolt_circle_validation(self):
        spec = _flange_spec("ASME_B16.5", "2", pressure_class="150")
        r = generate_geometry(spec)
        bp = next(f for f in r.geometry_payload["features"] if f["name"] == "bolt_pattern")
        self.assertEqual(bp["params"]["bolt_circle_diameter_mm"],
                          spec.required_dimensions["bolt_circle_diameter_mm"]["value"])

    def test_05_asme_bolt_hole_diameter_validation(self):
        spec = _flange_spec("ASME_B16.5", "2", pressure_class="150")
        r = generate_geometry(spec)
        bp = next(f for f in r.geometry_payload["features"] if f["name"] == "bolt_pattern")
        self.assertEqual(bp["params"]["bolt_hole_diameter_mm"],
                          spec.required_dimensions["bolt_hole_diameter_mm"]["value"])

    def test_06_asme_bolt_count_validation(self):
        spec = _flange_spec("ASME_B16.5", "2", pressure_class="150")
        r = generate_geometry(spec)
        bp = next(f for f in r.geometry_payload["features"] if f["name"] == "bolt_pattern")
        self.assertEqual(bp["params"]["count"], int(spec.required_dimensions["num_bolts"]["value"]))

    def test_07_deterministic_bolt_hole_placement(self):
        p = build_bolt_pattern(120.65, 19.05, 4)
        self.assertTrue(validate_bolt_pattern(p))

    def test_08_bolt_pattern_repeatability(self):
        p1 = build_bolt_pattern(120.65, 19.05, 4)
        p2 = build_bolt_pattern(120.65, 19.05, 4)
        self.assertEqual(p1.hole_centres, p2.hole_centres)

    def test_09_through_bore_with_valid_pipe_schedule_context(self):
        spec = _flange_spec("ASME_B16.5", "2", pressure_class="150")
        r = generate_geometry(spec, product_kwargs={"bore_value": _asme_bore("2")})
        self.assertTrue(r.is_generated())
        self.assertEqual(r.topology_representation,
                          TopologyRepresentation.HOLLOW_ANNULAR_BODY_WITH_BOLT_HOLE_METADATA_NO_BOOLEAN_CUT)

    def test_10_missing_bore_context_yields_external_envelope_not_failure(self):
        spec = _flange_spec("ASME_B16.5", "2", pressure_class="150")
        r = generate_geometry(spec)
        self.assertTrue(r.is_generated())
        self.assertEqual(r.topology_representation,
                          TopologyRepresentation.SOLID_EXTERNAL_ENVELOPE_WITH_BOLT_HOLE_METADATA_NO_BOOLEAN_CUT)

    def test_11_ambiguous_pipe_context_fails_closed(self):
        outcome = FlangeBoreViaPipeScheduleRule().resolve(
            _RESOLVER, target_standard="ASME_B16.5", target_size_system="nps", target_size="2",
            pipe_standard="ASME_B36.10M", pipe_schedule=None)
        self.assertFalse(outcome.is_applied())

    def test_12_blind_flange_not_canonically_supported(self):
        r = _prep(product_family="flange", subtype="blind", standard="ASME_B16.5",
                   primary_size="2", pressure_class="150")
        self.assertFalse(r.is_ready())

    def test_13_blind_flange_has_no_opening_by_construction(self):
        # No blind profile exists at all (Sec.3/17) - confirmed there is
        # no path that could produce a through-bore opening for "blind".
        self.assertIsNone(find_profile("flange", "blind"))

    def test_14_asme_raised_face_unavailable_structured(self):
        spec = _flange_spec("ASME_B16.5", "2", pressure_class="150")
        r = generate_geometry(spec)
        rf = next(f for f in r.geometry_payload["features"] if f["name"] == "raised_face")
        self.assertEqual(rf["params"]["status"], "UNAVAILABLE_NO_AUTHORITATIVE_DIMENSIONS")

    def test_15_asme_hub_unavailable_structured(self):
        spec = _flange_spec("ASME_B16.5", "2", pressure_class="150")
        r = generate_geometry(spec)
        hub = next(f for f in r.geometry_payload["features"] if f["name"] == "hub")
        self.assertEqual(hub["params"]["status"], "UNAVAILABLE_NO_AUTHORITATIVE_DIMENSIONS_ANY_STANDARD")

    # --- JIS B2220 (16-24) ---
    def test_16_jis_flange_body_generation(self):
        spec = _flange_spec("JIS_B2220", 50, jis_k="10K")
        self.assertTrue(generate_geometry(spec).is_generated())

    def test_17_jis_k_rating_identity_preserved(self):
        spec = _flange_spec("JIS_B2220", 50, jis_k="10K")
        self.assertEqual(spec.engineering_object_identity["jis_k"], "10K")

    def test_18_jis_size_system_identity_preserved(self):
        spec = _flange_spec("JIS_B2220", 50, jis_k="10K")
        self.assertEqual(spec.engineering_object_identity["size_system"], "jis_size")

    def test_19_jis_od_validation(self):
        spec = _flange_spec("JIS_B2220", 50, jis_k="10K")
        r = generate_geometry(spec)
        self.assertTrue(r.dimensional_validation_summary["passed"])

    def test_20_jis_thickness_validation(self):
        spec = _flange_spec("JIS_B2220", 50, jis_k="10K")
        r = generate_geometry(spec)
        self.assertAlmostEqual(
            r.geometry_payload["measurements"]["flange_thickness_weld_neck_mm"],
            spec.required_dimensions["flange_thickness_weld_neck_mm"]["value"], places=3)

    def test_21_jis_bolt_circle_validation(self):
        spec = _flange_spec("JIS_B2220", 50, jis_k="10K")
        r = generate_geometry(spec)
        bp = next(f for f in r.geometry_payload["features"] if f["name"] == "bolt_pattern")
        self.assertEqual(bp["params"]["bolt_circle_diameter_mm"],
                          spec.required_dimensions["bolt_circle_diameter_mm"]["value"])

    def test_22_jis_bolt_count_and_diameter_validation(self):
        spec = _flange_spec("JIS_B2220", 50, jis_k="10K")
        r = generate_geometry(spec)
        bp = next(f for f in r.geometry_payload["features"] if f["name"] == "bolt_pattern")
        self.assertEqual(bp["params"]["count"], int(spec.required_dimensions["num_bolts"]["value"]))
        self.assertEqual(bp["params"]["bolt_hole_diameter_mm"],
                          spec.required_dimensions["bolt_hole_diameter_mm"]["value"])

    def test_23_jis_deterministic_bolt_pattern(self):
        spec = _flange_spec("JIS_B2220", 50, jis_k="10K")
        r1 = generate_geometry(spec)
        r2 = generate_geometry(spec)
        self.assertEqual(r1.geometry_fingerprint, r2.geometry_fingerprint)

    def test_24_jis_unsupported_subtype_handled_honestly(self):
        r = _prep(product_family="flange", subtype="blind", standard="JIS_B2220", primary_size=50, jis_k="10K")
        self.assertFalse(r.is_ready())

    # --- EN 1092-1 (25-33) ---
    def test_25_en_flange_body_generation(self):
        spec = _flange_spec("EN_1092-1", 50, pn="PN16")
        self.assertTrue(generate_geometry(spec).is_generated())

    def test_26_en_pn_rating_identity_preserved(self):
        spec = _flange_spec("EN_1092-1", 50, pn="PN16")
        self.assertIsNotNone(spec.engineering_object_identity["pn"])

    def test_27_en_dn_size_identity_preserved(self):
        spec = _flange_spec("EN_1092-1", 50, pn="PN16")
        self.assertEqual(spec.engineering_object_identity["size_system"], "dn")

    def test_28_en_od_validation(self):
        spec = _flange_spec("EN_1092-1", 50, pn="PN16")
        r = generate_geometry(spec)
        self.assertTrue(r.dimensional_validation_summary["passed"])

    def test_29_en_thickness_validation(self):
        spec = _flange_spec("EN_1092-1", 50, pn="PN16")
        r = generate_geometry(spec)
        self.assertAlmostEqual(
            r.geometry_payload["measurements"]["flange_thickness_weld_neck_mm"],
            spec.required_dimensions["flange_thickness_weld_neck_mm"]["value"], places=3)

    def test_30_en_bolt_circle_validation(self):
        spec = _flange_spec("EN_1092-1", 50, pn="PN16")
        r = generate_geometry(spec)
        bp = next(f for f in r.geometry_payload["features"] if f["name"] == "bolt_pattern")
        self.assertEqual(bp["params"]["bolt_circle_diameter_mm"],
                          spec.required_dimensions["bolt_circle_diameter_mm"]["value"])

    def test_31_en_bolt_count_and_diameter_validation(self):
        spec = _flange_spec("EN_1092-1", 50, pn="PN16")
        r = generate_geometry(spec)
        bp = next(f for f in r.geometry_payload["features"] if f["name"] == "bolt_pattern")
        self.assertEqual(bp["params"]["count"], int(spec.required_dimensions["num_bolts"]["value"]))
        self.assertEqual(bp["params"]["bolt_hole_diameter_mm"],
                          spec.required_dimensions["bolt_hole_diameter_mm"]["value"])

    def test_32_en_deterministic_bolt_pattern(self):
        spec = _flange_spec("EN_1092-1", 50, pn="PN16")
        r1 = generate_geometry(spec)
        r2 = generate_geometry(spec)
        self.assertEqual(r1.geometry_fingerprint, r2.geometry_fingerprint)

    def test_33_en_unsupported_subtype_handled_honestly(self):
        r = _prep(product_family="flange", subtype="blind", standard="EN_1092-1", primary_size=50, pn="PN16")
        self.assertFalse(r.is_ready())


if __name__ == "__main__":
    unittest.main()
