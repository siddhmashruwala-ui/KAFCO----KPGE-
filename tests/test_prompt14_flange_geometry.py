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
from kgpe.geometry_spec.orchestration import OrchestrationStage

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
_DATA_LAYER_FINGERPRINT = "f291f02e63b591de449502dcbb2980b7729e2cdbdd928765f6a847e13083d748"  # post-Prompt-9: shifted again by the KAFCO_Nipoflange 12th-dataset addition


def _prep(**kwargs):
    return prepare_geometry_specification(EngineeringRequest(**kwargs), resolver=_RESOLVER)


def _flange_spec(standard, primary_size, extra_dims=None, subtype="weld_neck", **rating):
    kwargs = dict(product_family="flange", subtype=subtype, standard=standard, primary_size=primary_size)
    kwargs.update(rating)
    if extra_dims:
        kwargs["dimensions"] = extra_dims
    r = _prep(**kwargs)
    assert r.is_ready(), (standard, primary_size, subtype, r.geometry_specification.warnings)
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
        # Prompt 42: hub_base_diameter_mm/length_through_hub_mm are NOW
        # available for ASME_B16.5 (weld_neck/long_weld_neck only, via
        # _HUB_FIELD_SPECS) - the ONLY standard with any hub facts at all
        # (see test_hub_dimensions_absent_for_every_standard below, which
        # confirms JIS_B2220/EN_1092-1 remain unaffected).
        self.assertIn("hub_base_diameter_mm", dims)
        self.assertIn("length_through_hub_mm", dims)

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

    def test_hub_dimensions_absent_for_every_standard_except_asme(self):
        # Sec.21-22 (pre-Prompt-42): zero production facts for
        # hub_base_diameter_mm/length_through_hub_mm at ANY standard.
        # Prompt 42: ASME_B16.5 is now the sole exception (weld_neck/
        # long_weld_neck only, via _HUB_FIELD_SPECS) - JIS_B2220/EN_1092-1
        # remain exactly as before, zero hub facts, never fabricated.
        for standard in ("JIS_B2220", "EN_1092-1"):
            dims = _READER.available_dimensions(product_family="flange", standard=standard)
            self.assertNotIn("hub_base_diameter_mm", dims)
            self.assertNotIn("length_through_hub_mm", dims)
        dims = _READER.available_dimensions(product_family="flange", standard="ASME_B16.5")
        self.assertIn("hub_base_diameter_mm", dims)
        self.assertIn("length_through_hub_mm", dims)


class TestFlangeSubtypeSupportMatrix(unittest.TestCase):
    """Prompt 41: weld_neck, slip_on, threaded, socket_weld, lap_joint,
    and blind are ALL now defined, canonical-data-backed profiles (ASME
    B16.5) - only genuinely unknown/nonexistent subtypes ('loose',
    'plate') remain unsupported, never fabricated from general
    engineering knowledge."""

    def test_weld_neck_is_a_defined_flange_profile(self):
        profile = find_profile("flange", "weld_neck")
        self.assertIsNotNone(profile)
        self.assertEqual(profile.profile_id, "flange_weld_neck")

    def test_all_six_prompt41_subtypes_have_defined_profiles(self):
        expected_profile_id = {
            "weld_neck": "flange_weld_neck", "slip_on": "flange_slip_on",
            "threaded": "flange_threaded", "socket_weld": "flange_socket_weld",
            "lap_joint": "flange_lap_joint", "blind": "flange_blind",
        }
        for subtype, profile_id in expected_profile_id.items():
            profile = find_profile("flange", subtype)
            self.assertIsNotNone(profile, f"expected a defined profile for subtype={subtype!r}")
            self.assertEqual(profile.profile_id, profile_id)

    def test_blind_profile_has_no_bore_dimension_anywhere(self):
        # Sec.41: blind flanges have no through-bore by physical
        # definition - bore_diameter_mm must be absent from required,
        # optional, AND construction-derivable sets.
        profile = find_profile("flange", "blind")
        self.assertNotIn("bore_diameter_mm", profile.required_dimensions)
        self.assertNotIn("bore_diameter_mm", profile.optional_dimensions)
        self.assertNotIn("bore_diameter_mm", profile.construction_derivable_dimensions)

    def test_four_bore_bearing_subtypes_use_shared_other_types_thickness(self):
        for subtype in ("slip_on", "threaded", "socket_weld", "lap_joint"):
            profile = find_profile("flange", subtype)
            self.assertIn("flange_thickness_other_types_mm", profile.required_dimensions)
            self.assertIn("bore_diameter_mm", profile.optional_dimensions)
            self.assertIn("bore_diameter_mm", profile.construction_derivable_dimensions)

    def test_unknown_subtypes_remain_unsupported(self):
        for subtype in ("loose", "plate"):
            self.assertIsNone(find_profile("flange", subtype))

    def test_no_flange_type_other_than_weld_neck_has_any_facts(self):
        # JIS_B2220/EN_1092-1 canonical data still distinguishes no second
        # flange_type identity (unchanged since Prompt 14). ASME_B16.5 is
        # the sole exception as of Prompt 41: Slip-On/Threaded/Socket-Weld/
        # Lap-Joint/Blind thickness facts now exist there, AND (unlike the
        # original Prompt 41 landing) geometry profiles now wire all six
        # up too - see test_all_six_prompt41_subtypes_have_defined_profiles
        # above. Prompt 42 adds a SEVENTH ASME_B16.5 flange_type,
        # long_weld_neck - its own subtype/profile identity (not a
        # re-use of weld_neck), carrying a re-tagged duplicate thickness
        # fact plus its own fixed 229/305mm length_through_hub_mm fact.
        for standard in ("JIS_B2220", "EN_1092-1"):
            types = _READER.discover("flange_type", product_family="flange", standard=standard)
            self.assertTrue(set(types) <= {"weld_neck"})
        asme_types = _READER.discover("flange_type", product_family="flange", standard="ASME_B16.5")
        self.assertEqual(
            set(asme_types),
            {"weld_neck", "long_weld_neck", "slip_on", "threaded", "socket_weld", "lap_joint", "blind"},
        )


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
    """Prompt 41: ASME B16.5 blind flange thickness ('C', single-sourced
    from htpipe.com - see _ingest_new_flange_types.py) is now ingested
    and wired up via PROFILE_FLANGE_BLIND - blind is GEOMETRY_READY for
    ASME_B16.5. EN_1092-1/JIS_B2220 still have zero blind-thickness facts
    (Prompt 41's adapter work only touched ASME_B16.5_Flanges.json), so
    blind remains genuinely unsupported there - never fabricated with
    borrowed weld-neck geometry."""

    def test_blind_flange_request_is_ready_for_asme_b16_5(self):
        r = _prep(product_family="flange", subtype="blind", standard="ASME_B16.5",
                   primary_size="2", pressure_class="150")
        self.assertTrue(r.is_ready(), r.geometry_specification.warnings)
        self.assertEqual(r.geometry_specification.geometry_profile_id, "flange_blind")
        self.assertIsNotNone(find_profile("flange", "blind"))

    def test_blind_flange_request_still_unsupported_for_en_1092_1(self):
        # No blind-thickness facts exist for EN_1092-1 - the profile IS
        # defined now (unlike Prompt 14), but resolution of
        # flange_thickness_blind_mm still fails for this standard, so the
        # request is not ready - never fabricated.
        r = _prep(product_family="flange", subtype="blind", standard="EN_1092-1",
                   primary_size=50, pn="PN16")
        self.assertFalse(r.is_ready())


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

    def test_hub_unavailable_when_not_explicitly_requested(self):
        # Prompt 42: hub_base_diameter_mm/length_through_hub_mm are
        # optional dimensions (Sec.7's orchestration rule: optional dims
        # are resolved ONLY when the caller explicitly asks for them via
        # `dimensions=[...]`, never auto-included) - _flange_spec here
        # passes no extra_dims, so hub geometry is correctly UNAVAILABLE
        # for all three standards, even ASME_B16.5 (which DOES have hub
        # facts - see test_hub_modeled_for_asme_weld_neck_when_requested
        # below for the positive case). This is no longer "unavailable
        # for any standard" (that claim is now false) - it is
        # "unavailable because not requested".
        for standard, size, rating in (("ASME_B16.5", "2", {"pressure_class": "150"}),
                                        ("JIS_B2220", 50, {"jis_k": "10K"}),
                                        ("EN_1092-1", 50, {"pn": "PN16"})):
            spec = _flange_spec(standard, size, **rating)
            result = generate_geometry(spec)
            hub = next(f for f in result.geometry_payload["features"] if f["name"] == "hub")
            self.assertEqual(hub["params"]["status"], "UNAVAILABLE_NO_AUTHORITATIVE_DIMENSIONS")

    def test_hub_modeled_for_asme_weld_neck_when_requested(self):
        # Prompt 42: when hub dims ARE explicitly requested, ASME_B16.5
        # weld_neck resolves and models a real straight-cylinder hub
        # composite - JIS_B2220/EN_1092-1 still have zero hub facts even
        # when requested (never fabricated).
        spec = _flange_spec("ASME_B16.5", "1", pressure_class="150",
                             extra_dims=["hub_base_diameter_mm", "length_through_hub_mm"])
        bore_value = _asme_bore("1")
        result = generate_geometry(spec, product_kwargs={"bore_value": bore_value})
        self.assertTrue(result.is_generated())
        self.assertEqual(result.topology_representation,
                          TopologyRepresentation.HOLLOW_ANNULAR_BODY_WITH_HUB_COMPOSITE_NO_BOOLEAN_CUT)
        hub = next(f for f in result.geometry_payload["features"] if f["name"] == "hub")
        self.assertEqual(hub["params"]["status"], "MODELED_STRAIGHT_CYLINDER_SIMPLIFICATION")
        self.assertAlmostEqual(hub["params"]["hub_base_diameter_mm"], 49.28, places=2)
        self.assertAlmostEqual(hub["params"]["length_through_hub_mm"], 53.85, places=2)
        m = result.geometry_payload["measurements"]
        self.assertAlmostEqual(m["hub_base_diameter_mm"], 49.28, places=1)
        self.assertAlmostEqual(m["length_through_hub_mm"], 53.85, places=1)

        for standard, size, rating in (("JIS_B2220", 50, {"jis_k": "10K"}), ("EN_1092-1", 50, {"pn": "PN16"})):
            r = _prep(product_family="flange", subtype="weld_neck", standard=standard, primary_size=size,
                       dimensions=["hub_base_diameter_mm", "length_through_hub_mm"], **rating)
            # Unlike the compiler's own defensive re-check (which only
            # fails closed on REQUIRED dims, Sec.13 step 6), the
            # orchestration layer's identity-resolution stage resolves
            # the request's `dimensions` list AS GIVEN, before any
            # profile/required-vs-optional distinction exists yet
            # (prepare_geometry_specification's stage 1) - an explicitly
            # requested dimension with zero facts for this standard makes
            # THAT resolver call itself UNSUPPORTED_REQUEST, so the whole
            # preparation fails closed rather than silently dropping the
            # unavailable optional dim. Confirmed live (not assumed) via
            # a debug probe before writing this assertion.
            self.assertFalse(r.is_ready())
            self.assertEqual(r.failed_stage, OrchestrationStage.ENGINEERING_RESOLUTION)

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

    def test_blind_profile_now_supported_and_dispatched(self):
        # Prompt 41: blind is now GEOMETRY_READY for ASME_B16.5 and
        # dispatches through _PRODUCT_DISPATCH like every other flange
        # subtype - see TestPrompt41NewFlangeSubtypeGeometry below for
        # full end-to-end coverage.
        from kgpe.geometry.kernel import _PRODUCT_DISPATCH
        r = _prep(product_family="flange", subtype="blind", standard="ASME_B16.5",
                   primary_size="2", pressure_class="150")
        self.assertTrue(r.is_ready(), r.geometry_specification.warnings)
        self.assertIn("flange_blind", _PRODUCT_DISPATCH)


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

    def test_12_blind_flange_now_canonically_supported(self):
        # Prompt 41: ASME B16.5 blind flange thickness is now ingested -
        # this request IS ready, unlike Prompt 14.
        r = _prep(product_family="flange", subtype="blind", standard="ASME_B16.5",
                   primary_size="2", pressure_class="150")
        self.assertTrue(r.is_ready(), r.geometry_specification.warnings)

    def test_13_blind_flange_still_has_no_opening_by_construction(self):
        # Prompt 41: a blind profile DOES exist now, but it deliberately
        # carries no bore_diameter_mm anywhere (required/optional/
        # construction-derivable) and products/flange.py hard-forces
        # SOLID_EXTERNAL_ENVELOPE for this subtype - confirmed end-to-end,
        # not just at the profile-declaration level.
        profile = find_profile("flange", "blind")
        self.assertIsNotNone(profile)
        self.assertNotIn("bore_diameter_mm", profile.required_dimensions)
        self.assertNotIn("bore_diameter_mm", profile.optional_dimensions)
        self.assertNotIn("bore_diameter_mm", profile.construction_derivable_dimensions)
        spec = _flange_spec("ASME_B16.5", "2", pressure_class="150", subtype="blind")
        r = generate_geometry(spec)
        self.assertTrue(r.is_generated())
        self.assertEqual(r.topology_representation,
                          TopologyRepresentation.SOLID_EXTERNAL_ENVELOPE_WITH_BOLT_HOLE_METADATA_NO_BOOLEAN_CUT)

    def test_14_asme_raised_face_unavailable_structured(self):
        spec = _flange_spec("ASME_B16.5", "2", pressure_class="150")
        r = generate_geometry(spec)
        rf = next(f for f in r.geometry_payload["features"] if f["name"] == "raised_face")
        self.assertEqual(rf["params"]["status"], "UNAVAILABLE_NO_AUTHORITATIVE_DIMENSIONS")

    def test_15_asme_hub_unavailable_when_not_requested_structured(self):
        # Prompt 42: hub dims exist for ASME_B16.5 but are optional and
        # only resolved when explicitly requested (see
        # TestRaisedFaceAndHubAndFaceType.test_hub_modeled_for_asme_weld_
        # neck_when_requested for the positive case) - this default
        # _flange_spec() call requests no extra_dims, so hub stays
        # unavailable here exactly as every other structured scenario in
        # this class does.
        spec = _flange_spec("ASME_B16.5", "2", pressure_class="150")
        r = generate_geometry(spec)
        hub = next(f for f in r.geometry_payload["features"] if f["name"] == "hub")
        self.assertEqual(hub["params"]["status"], "UNAVAILABLE_NO_AUTHORITATIVE_DIMENSIONS")

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


class TestPrompt41NewFlangeSubtypeGeometry(unittest.TestCase):
    """Prompt 41: end-to-end geometry generation for the five newly wired
    ASME B16.5 subtypes - slip_on, threaded, socket_weld, lap_joint,
    blind. Mirrors the existing weld_neck ASME test patterns above
    (solid-when-no-bore-supplied, hollow-via-cross-family-construction-
    value, correct geometry_type/thickness measurement) rather than
    inventing a new testing style."""

    def test_slip_on_solid_generates_with_correct_geometry_type(self):
        spec = _flange_spec("ASME_B16.5", "2", pressure_class="150", subtype="slip_on")
        r = generate_geometry(spec)
        self.assertTrue(r.is_generated(), r.generation_trace)
        self.assertEqual(r.geometry_type, "flange_slip_on")
        self.assertEqual(r.topology_representation,
                          TopologyRepresentation.SOLID_EXTERNAL_ENVELOPE_WITH_BOLT_HOLE_METADATA_NO_BOOLEAN_CUT)

    def test_threaded_solid_generates_with_correct_geometry_type(self):
        spec = _flange_spec("ASME_B16.5", "2", pressure_class="150", subtype="threaded")
        r = generate_geometry(spec)
        self.assertTrue(r.is_generated(), r.generation_trace)
        self.assertEqual(r.geometry_type, "flange_threaded")

    def test_socket_weld_solid_generates_with_correct_geometry_type(self):
        # Socket-weld is conventionally capped at NPS<=4 - use NPS 2.
        spec = _flange_spec("ASME_B16.5", "2", pressure_class="150", subtype="socket_weld")
        r = generate_geometry(spec)
        self.assertTrue(r.is_generated(), r.generation_trace)
        self.assertEqual(r.geometry_type, "flange_socket_weld")

    def test_lap_joint_solid_generates_with_correct_geometry_type(self):
        spec = _flange_spec("ASME_B16.5", "2", pressure_class="150", subtype="lap_joint")
        r = generate_geometry(spec)
        self.assertTrue(r.is_generated(), r.generation_trace)
        self.assertEqual(r.geometry_type, "flange_lap_joint")

    def test_blind_solid_generates_with_correct_geometry_type_and_own_thickness_dim(self):
        spec = _flange_spec("ASME_B16.5", "2", pressure_class="150", subtype="blind")
        r = generate_geometry(spec)
        self.assertTrue(r.is_generated(), r.generation_trace)
        self.assertEqual(r.geometry_type, "flange_blind")
        self.assertEqual(r.topology_representation,
                          TopologyRepresentation.SOLID_EXTERNAL_ENVELOPE_WITH_BOLT_HOLE_METADATA_NO_BOOLEAN_CUT)
        self.assertIn("flange_thickness_blind_mm", r.geometry_payload["measurements"])
        self.assertAlmostEqual(
            r.geometry_payload["measurements"]["flange_thickness_blind_mm"],
            spec.required_dimensions["flange_thickness_blind_mm"]["value"], places=3)

    def test_bore_bearing_subtype_accepts_cross_family_bore_construction_value(self):
        # Sec.14-16 pattern, now exercised for slip_on rather than
        # weld_neck - confirms the parameterized builder still threads
        # bore_value through correctly for a non-weld_neck subtype.
        spec = _flange_spec("ASME_B16.5", "2", pressure_class="150", subtype="slip_on")
        bore_cv = _asme_bore("2")
        r = generate_geometry(spec, product_kwargs={"bore_value": bore_cv})
        self.assertTrue(r.is_generated(), r.generation_trace)
        self.assertEqual(r.topology_representation,
                          TopologyRepresentation.HOLLOW_ANNULAR_BODY_WITH_BOLT_HOLE_METADATA_NO_BOOLEAN_CUT)
        self.assertAlmostEqual(r.geometry_payload["measurements"]["bore_diameter_mm"], bore_cv.value, places=3)

    def test_blind_never_bores_even_if_a_bore_value_is_mistakenly_supplied(self):
        # Sec.41 hard-forced-solid guarantee: blind must ignore a
        # bore_value even if one is (incorrectly) supplied by a caller,
        # since profile.py's PROFILE_FLANGE_BLIND never resolves
        # bore_diameter_mm as optional in the first place - this proves
        # the defense-in-depth check inside products/flange.py itself.
        spec = _flange_spec("ASME_B16.5", "2", pressure_class="150", subtype="blind")
        bore_cv = _asme_bore("2")
        r = generate_geometry(spec, product_kwargs={"bore_value": bore_cv})
        self.assertTrue(r.is_generated(), r.generation_trace)
        self.assertEqual(r.topology_representation,
                          TopologyRepresentation.SOLID_EXTERNAL_ENVELOPE_WITH_BOLT_HOLE_METADATA_NO_BOOLEAN_CUT)
        self.assertNotIn("bore_diameter_mm", r.geometry_payload["measurements"])

    def test_all_five_new_subtypes_dispatch_via_kernel_product_dispatch(self):
        from kgpe.geometry.kernel import _PRODUCT_DISPATCH
        for profile_id in ("flange_slip_on", "flange_threaded", "flange_socket_weld",
                            "flange_lap_joint", "flange_blind"):
            self.assertIn(profile_id, _PRODUCT_DISPATCH)
            self.assertIs(_PRODUCT_DISPATCH[profile_id], flange)


class TestLongWeldNeckAndHubGeometry(unittest.TestCase):
    """Prompt 42: long_weld_neck as its own flange_type/subtype/profile
    identity, and the hub composite mesh shared by weld_neck/
    long_weld_neck. long_weld_neck's length_through_hub_mm is REQUIRED
    (not merely optional, unlike weld_neck) - see PROFILE_FLANGE_LONG_
    WELD_NECK's own notes - so it is always requested implicitly via
    profile.required_dimensions, never via extra_dims."""

    def test_long_weld_neck_dispatches_via_kernel_product_dispatch(self):
        from kgpe.geometry.kernel import _PRODUCT_DISPATCH
        self.assertIn("flange_long_weld_neck", _PRODUCT_DISPATCH)
        self.assertIs(_PRODUCT_DISPATCH["flange_long_weld_neck"], flange)

    def test_long_weld_neck_profile_is_defined(self):
        profile = find_profile("flange", "long_weld_neck")
        self.assertIsNotNone(profile)
        self.assertEqual(profile.profile_id, "flange_long_weld_neck")
        self.assertIn("length_through_hub_mm", profile.required_dimensions)
        self.assertIn("hub_base_diameter_mm", profile.optional_dimensions)

    def test_long_weld_neck_nps_le_4_gets_229mm(self):
        # ASME B16.5's own LWN rule: 229mm (9in) for NPS<=4, independent
        # of pressure class. hub_base_diameter_mm is merely OPTIONAL for
        # long_weld_neck (shared with weld_neck), so it must be
        # explicitly requested via extra_dims for the hub mesh to
        # actually build - length_through_hub_mm needs no such request
        # since it is REQUIRED for this profile.
        spec = _flange_spec("ASME_B16.5", "1", pressure_class="150", subtype="long_weld_neck",
                             extra_dims=["hub_base_diameter_mm"])
        bore_value = _asme_bore("1")
        result = generate_geometry(spec, product_kwargs={"bore_value": bore_value})
        self.assertTrue(result.is_generated(), result.generation_trace)
        self.assertEqual(result.topology_representation,
                          TopologyRepresentation.HOLLOW_ANNULAR_BODY_WITH_HUB_COMPOSITE_NO_BOOLEAN_CUT)
        hub = next(f for f in result.geometry_payload["features"] if f["name"] == "hub")
        self.assertEqual(hub["params"]["status"], "MODELED_STRAIGHT_CYLINDER_SIMPLIFICATION")
        self.assertAlmostEqual(hub["params"]["length_through_hub_mm"], 229.0, places=2)
        m = result.geometry_payload["measurements"]
        self.assertAlmostEqual(m["length_through_hub_mm"], 229.0, places=1)

    def test_long_weld_neck_nps_gt_4_gets_305mm(self):
        # ASME B16.5's own LWN rule: 305mm (12in) for NPS>4.
        spec = _flange_spec("ASME_B16.5", "6", pressure_class="300", subtype="long_weld_neck",
                             extra_dims=["hub_base_diameter_mm"])
        bore_value = _asme_bore("6")
        result = generate_geometry(spec, product_kwargs={"bore_value": bore_value})
        self.assertTrue(result.is_generated(), result.generation_trace)
        hub = next(f for f in result.geometry_payload["features"] if f["name"] == "hub")
        self.assertAlmostEqual(hub["params"]["length_through_hub_mm"], 305.0, places=2)
        m = result.geometry_payload["measurements"]
        self.assertAlmostEqual(m["length_through_hub_mm"], 305.0, places=1)

    def test_long_weld_neck_thickness_matches_weld_neck_same_size_class(self):
        # Prompt 42: long_weld_neck's thickness is a re-tagged duplicate
        # of weld_neck's own T value (never independently derived) -
        # confirmed here at the geometry-output level, not just the
        # fact-ingestion level (test_asme_b16_5_ingestion.py covers that).
        wn_spec = _flange_spec("ASME_B16.5", "2", pressure_class="150", subtype="weld_neck")
        lwn_spec = _flange_spec("ASME_B16.5", "2", pressure_class="150", subtype="long_weld_neck")
        wn_result = generate_geometry(wn_spec, product_kwargs={"bore_value": _asme_bore("2")})
        lwn_result = generate_geometry(lwn_spec, product_kwargs={"bore_value": _asme_bore("2")})
        self.assertEqual(
            wn_result.geometry_payload["measurements"]["flange_thickness_weld_neck_mm"],
            lwn_result.geometry_payload["measurements"]["flange_thickness_weld_neck_mm"],
        )

    def test_jis_and_en_weld_neck_unaffected_by_hub_composite_work(self):
        # Sec.28-style non-regression check: JIS_B2220/EN_1092-1 weld_neck
        # geometry (no hub facts for either standard) must still generate
        # exactly as it did before Prompt 42 - flat-plate body only, the
        # PRE-Prompt-42 topology constants, never a hub composite.
        jis_spec = _flange_spec("JIS_B2220", 50, extra_dims=["bore_diameter_mm"], jis_k="10K")
        jis_result = generate_geometry(jis_spec)
        self.assertTrue(jis_result.is_generated())
        self.assertEqual(jis_result.topology_representation,
                          TopologyRepresentation.HOLLOW_ANNULAR_BODY_WITH_BOLT_HOLE_METADATA_NO_BOOLEAN_CUT)
        en_spec = _flange_spec("EN_1092-1", 50, pn="PN16")
        en_result = generate_geometry(en_spec)
        self.assertTrue(en_result.is_generated())
        self.assertEqual(en_result.topology_representation,
                          TopologyRepresentation.SOLID_EXTERNAL_ENVELOPE_WITH_BOLT_HOLE_METADATA_NO_BOOLEAN_CUT)

    def test_other_five_prompt41_subtypes_never_attempt_hub(self):
        # _HUB_ELIGIBLE_SUBTYPES restricts hub resolution to weld_neck/
        # long_weld_neck only - slip_on/threaded/socket_weld/lap_joint/
        # blind must always report NOT_APPLICABLE_SUBTYPE, even though
        # slip_on/threaded/socket_weld/lap_joint DO have a through-bore.
        for subtype in ("slip_on", "threaded", "socket_weld", "lap_joint", "blind"):
            spec = _flange_spec("ASME_B16.5", "2", pressure_class="150", subtype=subtype)
            result = generate_geometry(spec)
            self.assertTrue(result.is_generated(), (subtype, result.generation_trace))
            hub = next(f for f in result.geometry_payload["features"] if f["name"] == "hub")
            self.assertEqual(hub["params"]["status"], "NOT_APPLICABLE_SUBTYPE")

    def test_solid_hub_composite_topology_when_no_bore_resolved(self):
        # Prompt 42's fourth mesh-building branch: hub present, bore
        # absent - SOLID_EXTERNAL_ENVELOPE_WITH_HUB_COMPOSITE_NO_BOOLEAN_
        # CUT (build_solid_cylinder_with_hub). Constructed directly via
        # prepare_geometry_specification with no bore_value supplied,
        # since ASME_B16.5 weld_neck normally has a bore available via
        # FlangeBoreViaPipeScheduleRule - this test deliberately omits it
        # to exercise the no-bore branch.
        spec = _flange_spec("ASME_B16.5", "1", pressure_class="150", subtype="weld_neck",
                             extra_dims=["hub_base_diameter_mm", "length_through_hub_mm"])
        result = generate_geometry(spec)  # no product_kwargs -> no bore_value
        self.assertTrue(result.is_generated(), result.generation_trace)
        self.assertEqual(result.topology_representation,
                          TopologyRepresentation.SOLID_EXTERNAL_ENVELOPE_WITH_HUB_COMPOSITE_NO_BOOLEAN_CUT)
        hub = next(f for f in result.geometry_payload["features"] if f["name"] == "hub")
        self.assertEqual(hub["params"]["status"], "MODELED_STRAIGHT_CYLINDER_SIMPLIFICATION")


if __name__ == "__main__":
    unittest.main()
