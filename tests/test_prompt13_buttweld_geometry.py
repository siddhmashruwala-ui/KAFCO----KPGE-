# -*- coding: utf-8 -*-
"""
tests/test_prompt13_buttweld_geometry.py
============================================
Prompt 13 Sec.38: automated tests for the core ASME B16.9 buttweld
geometry expansion (elbow generalization + hollow mode, tee, cap,
concentric/eccentric reducer) built on top of the Prompt 12 kernel.
Standard-library `unittest` only.
"""
import math
import unittest

from kgpe.contract.canonical_reader import build_canonical_reader
from kgpe.contract.snapshot import registry_fingerprint
from kgpe.resolver import EngineeringRequest, EngineeringResolver, ResolutionStatus
from kgpe.geometry_spec import prepare_geometry_specification, GeometrySpecification, GeometryReadinessStatus

import kgpe.geometry as geo
from kgpe.geometry.wall_context import WallContext, WallContextError
from kgpe.geometry.cross_family import ButtweldWallViaPipeScheduleRule
from kgpe.geometry.reducer_rules import ReducerPerEndOutsideDiameterRule
from kgpe.geometry.construction_rules import ConstructionRuleStatus, CapLengthSelectionRule
from kgpe.geometry.transition_rules import (
    TeeBranchBlendingRule, CapProfileConstructionRule, ConcentricReducerTransitionRule,
    EccentricReducerOffsetRule,
)
from kgpe.geometry.ports import ConnectionPort, validate_port, validate_ports, PortValidationError
from kgpe.geometry.result import GeometryGenerationStatus, TopologyRepresentation
from kgpe.geometry.kernel import GeometryKernel, generate_geometry
from kgpe.geometry.pipeline import run_pipeline, PipelineStage
from kgpe.geometry.products import buttweld_elbow, tee, cap, reducer

_READER, _ = build_canonical_reader()
_FINGERPRINT = registry_fingerprint(_READER.registry)
_RESOLVER = EngineeringResolver(_READER, _FINGERPRINT)


def _prep(**kwargs):
    return prepare_geometry_specification(EngineeringRequest(**kwargs), resolver=_RESOLVER)


def _elbow_spec(subtype="elbow_90_lr", size="6"):
    r = _prep(product_family="buttweld_fitting", subtype=subtype, standard="ASME_B16.9", primary_size=size)
    assert r.is_ready(), r.geometry_specification.warnings
    return r.geometry_specification


def _tee_spec(size="6"):
    r = _prep(product_family="buttweld_fitting", subtype="tee_equal", standard="ASME_B16.9", primary_size=size)
    assert r.is_ready()
    return r.geometry_specification


def _cap_spec(size="6", with_heavy_wall_dims=False):
    kwargs = dict(product_family="buttweld_fitting", subtype="cap", standard="ASME_B16.9", primary_size=size)
    if with_heavy_wall_dims:
        kwargs["dimensions"] = ["cap_length_heavy_wall_mm", "cap_wall_thickness_threshold_mm"]
    r = _prep(**kwargs)
    assert r.is_ready()
    return r.geometry_specification


def _reducer_spec(subtype="reducer_concentric", large="6", small="4"):
    r = _prep(product_family="buttweld_fitting", subtype=subtype, standard="ASME_B16.9",
              large_end_size=large, small_end_size=small)
    assert r.is_ready()
    return r.geometry_specification


def _reducer_ods(large="6", small="4", standard="ASME_B16.9"):
    outcome = ReducerPerEndOutsideDiameterRule().resolve(_RESOLVER, standard=standard,
                                                          large_end_size=large, small_end_size=small)
    assert outcome.is_applied(), outcome.detail
    return outcome.value  # (large_cv, small_cv)


def _wall_value(fitting_size="6", pipe_standard="ASME_B36.10M", schedule="Sch40"):
    outcome = ButtweldWallViaPipeScheduleRule().resolve(
        _RESOLVER, fitting_standard="ASME_B16.9", fitting_size=fitting_size,
        wall_context=WallContext(pipe_standard=pipe_standard, pipe_schedule=schedule))
    assert outcome.is_applied(), outcome.detail
    return outcome.value


class TestWallContext(unittest.TestCase):
    def test_requires_pipe_standard(self):
        with self.assertRaises(WallContextError):
            WallContext(pipe_standard=None, pipe_schedule="Sch40")

    def test_requires_schedule_or_wall_designation(self):
        with self.assertRaises(WallContextError):
            WallContext(pipe_standard="ASME_B36.10M")

    def test_rejects_both_schedule_and_wall_designation(self):
        with self.assertRaises(WallContextError):
            WallContext(pipe_standard="EN_10216_10217", pipe_schedule="Sch40", pipe_wall_designation="Series1")

    def test_valid_construction(self):
        wc = WallContext(pipe_standard="ASME_B36.10M", pipe_schedule="Sch40")
        self.assertEqual(wc.pipe_schedule, "Sch40")


class TestButtweldWallViaPipeScheduleRule(unittest.TestCase):
    def test_applies_for_explicit_schedule(self):
        cv = _wall_value("6", "ASME_B36.10M", "Sch40")
        self.assertAlmostEqual(cv.value, 7.11)
        self.assertEqual(cv.name, "wall_thickness_mm")
        self.assertEqual(cv.rule_id, "buttweld_wall_via_pipe_schedule_cross_reference")

    def test_none_wall_context_is_input_missing(self):
        outcome = ButtweldWallViaPipeScheduleRule().resolve(
            _RESOLVER, fitting_standard="ASME_B16.9", fitting_size="6", wall_context=None)
        self.assertEqual(outcome.status, ConstructionRuleStatus.RULE_INPUT_MISSING)

    def test_different_schedule_gives_different_wall(self):
        cv40 = _wall_value("6", "ASME_B36.10M", "Sch40")
        cv160 = _wall_value("6", "ASME_B36.10M", "Sch160")
        self.assertNotAlmostEqual(cv40.value, cv160.value)


class TestReducerPerEndOutsideDiameterRule(unittest.TestCase):
    def test_resolves_both_ends_independently(self):
        large_cv, small_cv = _reducer_ods("6", "4")
        self.assertAlmostEqual(large_cv.value, 168.3)
        self.assertAlmostEqual(small_cv.value, 114.3)
        self.assertEqual(large_cv.name, "large_end_outside_diameter_mm")
        self.assertEqual(small_cv.name, "small_end_outside_diameter_mm")

    def test_never_swaps_ends(self):
        large_cv, small_cv = _reducer_ods("6", "3")
        self.assertGreater(large_cv.value, small_cv.value)
        self.assertEqual(large_cv.name, "large_end_outside_diameter_mm")
        self.assertEqual(small_cv.name, "small_end_outside_diameter_mm")

    def test_quarantined_large_end_blocks(self):
        outcome = ReducerPerEndOutsideDiameterRule().resolve(
            _RESOLVER, standard="ASME_B16.9", large_end_size="8", small_end_size="6")
        self.assertEqual(outcome.status, ConstructionRuleStatus.RULE_BLOCKED_QUARANTINE)

    def test_quarantined_small_end_blocks(self):
        outcome = ReducerPerEndOutsideDiameterRule().resolve(
            _RESOLVER, standard="ASME_B16.9", large_end_size="12", small_end_size="8")
        self.assertEqual(outcome.status, ConstructionRuleStatus.RULE_BLOCKED_QUARANTINE)


class TestConnectionPorts(unittest.TestCase):
    def test_valid_port_passes(self):
        p = ConnectionPort(port_id="inlet", role="inlet", position=(0, 0, 0), direction=(0, 0, -1))
        validate_port(p)  # no raise

    def test_rejects_non_unit_direction(self):
        p = ConnectionPort(port_id="x", role="inlet", position=(0, 0, 0), direction=(0, 0, -2))
        with self.assertRaises(PortValidationError):
            validate_port(p)

    def test_rejects_non_finite_position(self):
        p = ConnectionPort(port_id="x", role="inlet", position=(float("nan"), 0, 0), direction=(0, 0, -1))
        with self.assertRaises(PortValidationError):
            validate_port(p)

    def test_rejects_non_positive_opening_diameter(self):
        p = ConnectionPort(port_id="x", role="inlet", position=(0, 0, 0), direction=(0, 0, -1),
                            opening_diameter_mm=-5.0)
        with self.assertRaises(PortValidationError):
            validate_port(p)

    def test_rejects_missing_role(self):
        p = ConnectionPort(port_id="x", role="", position=(0, 0, 0), direction=(0, 0, -1))
        with self.assertRaises(PortValidationError):
            validate_port(p)


class TestTransitionRules(unittest.TestCase):
    def test_tee_branch_blending_rule_declares_no_blend(self):
        rule = TeeBranchBlendingRule()
        self.assertFalse(rule.is_exact_engineering_envelope)
        self.assertIn("no", rule.description.lower())

    def test_cap_profile_rule_declares_flat_disc(self):
        rule = CapProfileConstructionRule()
        self.assertFalse(rule.is_exact_engineering_envelope)

    def test_concentric_transition_linear_interpolation(self):
        rule = ConcentricReducerTransitionRule()
        self.assertAlmostEqual(rule.radius_at(100.0, 50.0, 200.0, 0.0), 100.0)
        self.assertAlmostEqual(rule.radius_at(100.0, 50.0, 200.0, 200.0), 50.0)
        self.assertAlmostEqual(rule.radius_at(100.0, 50.0, 200.0, 100.0), 75.0)

    def test_eccentric_offset_flat_on_bottom_default(self):
        rule = EccentricReducerOffsetRule()
        offset, orientation = rule.offset(84.15, 57.15)
        self.assertAlmostEqual(offset, 27.0)
        self.assertEqual(orientation, EccentricReducerOffsetRule.ORIENTATION_FLAT_ON_BOTTOM)

    def test_eccentric_offset_flat_on_top_is_opposite_sign(self):
        rule = EccentricReducerOffsetRule()
        offset_bottom, _ = rule.offset(84.15, 57.15, EccentricReducerOffsetRule.ORIENTATION_FLAT_ON_BOTTOM)
        offset_top, _ = rule.offset(84.15, 57.15, EccentricReducerOffsetRule.ORIENTATION_FLAT_ON_TOP)
        self.assertAlmostEqual(offset_bottom, -offset_top)

    def test_eccentric_offset_rejects_unknown_orientation(self):
        with self.assertRaises(ValueError):
            EccentricReducerOffsetRule().offset(84.15, 57.15, "SIDEWAYS")


class TestCapLengthSelectionRule(unittest.TestCase):
    def test_no_wall_context_uses_standard_length(self):
        rule = CapLengthSelectionRule()
        outcome = rule.apply(standard_length_value=89.0, standard_length_unit="mm")
        self.assertEqual(outcome.status, ConstructionRuleStatus.RULE_NOT_APPLICABLE)
        self.assertAlmostEqual(outcome.value.value, 89.0)

    def test_actual_wall_below_threshold_selects_standard(self):
        rule = CapLengthSelectionRule()
        outcome = rule.apply(standard_length_value=89.0, standard_length_unit="mm", actual_wall_thickness_mm=5.0,
                              heavy_wall_length_entry={"value": 102.0, "unit": "mm"},
                              wall_threshold_entry={"value": 10.92, "unit": "mm"})
        self.assertEqual(outcome.status, ConstructionRuleStatus.RULE_APPLIED)
        self.assertAlmostEqual(outcome.value.value, 89.0)

    def test_actual_wall_above_threshold_selects_heavy(self):
        rule = CapLengthSelectionRule()
        outcome = rule.apply(standard_length_value=89.0, standard_length_unit="mm", actual_wall_thickness_mm=18.26,
                              heavy_wall_length_entry={"value": 102.0, "unit": "mm"},
                              wall_threshold_entry={"value": 10.92, "unit": "mm"})
        self.assertEqual(outcome.status, ConstructionRuleStatus.RULE_APPLIED)
        self.assertAlmostEqual(outcome.value.value, 102.0)

    def test_actual_wall_without_heavy_dims_fails_closed(self):
        rule = CapLengthSelectionRule()
        outcome = rule.apply(standard_length_value=89.0, standard_length_unit="mm", actual_wall_thickness_mm=18.26)
        self.assertEqual(outcome.status, ConstructionRuleStatus.RULE_INPUT_MISSING)


class TestElbowGeneralizationAndHollow(unittest.TestCase):
    def test_all_five_subtypes_generate_external(self):
        for subtype in ("elbow_90_lr", "elbow_45_lr", "elbow_90_3d", "elbow_45_3d", "elbow_90_sr"):
            spec = _elbow_spec(subtype)
            result = generate_geometry(spec)
            self.assertTrue(result.is_generated(), f"{subtype}: {result.warnings}")
            self.assertEqual(result.topology_representation, TopologyRepresentation.SOLID_EXTERNAL_ENVELOPE)
            self.assertEqual(len(result.connection_ports), 2)

    def test_backward_compatible_90_lr_geometry_type_unchanged(self):
        spec = _elbow_spec("elbow_90_lr")
        result = generate_geometry(spec)
        self.assertEqual(result.geometry_type, "buttweld_elbow_90_lr")

    def test_45_degree_subtype_sweeps_45_degrees(self):
        spec = _elbow_spec("elbow_45_lr")
        result = generate_geometry(spec)
        self.assertTrue(result.dimensional_validation_summary["passed"])

    def test_hollow_mode_with_wall_context(self):
        spec = _elbow_spec("elbow_90_lr")
        wt_cv = _wall_value("6")
        result = generate_geometry(spec, product_kwargs={"wall_thickness_value": wt_cv})
        self.assertTrue(result.is_generated())
        self.assertEqual(result.topology_representation, TopologyRepresentation.HOLLOW_SWEPT_SOLID)
        self.assertIn("bore_diameter_mm", result.geometry_payload["measurements"])
        self.assertTrue(result.dimensional_validation_summary["passed"])

    def test_solid_mode_never_fabricates_wall(self):
        spec = _elbow_spec("elbow_90_lr")
        result = generate_geometry(spec)
        self.assertEqual(result.topology_representation, TopologyRepresentation.SOLID_EXTERNAL_ENVELOPE)
        self.assertNotIn("bore_diameter_mm", result.geometry_payload["measurements"])
        for p in result.connection_ports:
            self.assertIsNone(p["opening_diameter_mm"])

    def test_unrecognized_subtype_raises_geometry_input_error(self):
        bad_spec = GeometrySpecification(
            readiness_status=GeometryReadinessStatus.GEOMETRY_READY,
            engineering_object_identity={"subtype": "elbow_return_180"},
            required_dimensions={"outside_diameter_mm": {"value": 100.0, "unit": "mm"},
                                  "centre_to_end_mm": {"value": 50.0, "unit": "mm"}},
            geometry_profile_id="buttweld_elbow",
        )
        from kgpe.geometry.product_api import GeometryInputError
        with self.assertRaises(GeometryInputError):
            buttweld_elbow.build(bad_spec, geo.GenerationParameters())


class TestElbowQuarantineEnforcement(unittest.TestCase):
    def test_quarantined_nps8_blocks_all_subtypes(self):
        for subtype in ("elbow_90_lr", "elbow_45_lr", "elbow_90_3d", "elbow_45_3d", "elbow_90_sr"):
            r = _prep(product_family="buttweld_fitting", subtype=subtype, standard="ASME_B16.9", primary_size="8")
            self.assertFalse(r.is_ready(), f"{subtype} NPS8 should be blocked")
            self.assertEqual(r.dimension_resolution.status, ResolutionStatus.QUARANTINED_ENGINEERING_DATA)

    def test_quarantined_nps12_blocks_all_subtypes(self):
        for subtype in ("elbow_90_lr", "elbow_45_lr", "elbow_90_3d", "elbow_45_3d", "elbow_90_sr"):
            r = _prep(product_family="buttweld_fitting", subtype=subtype, standard="ASME_B16.9", primary_size="12")
            self.assertFalse(r.is_ready())
            self.assertEqual(r.dimension_resolution.status, ResolutionStatus.QUARANTINED_ENGINEERING_DATA)

    def test_neighboring_size_generates_normally(self):
        r = _prep(product_family="buttweld_fitting", subtype="elbow_90_lr", standard="ASME_B16.9", primary_size="6")
        self.assertTrue(r.is_ready())
        result = generate_geometry(r.geometry_specification)
        self.assertTrue(result.is_generated())

    def test_never_picks_one_conflicting_value_or_neighbor(self):
        # Confirms the quarantine truly blocks - no silent fallback value
        # ever appears as a resolved outside_diameter_mm at NPS8/NPS12.
        r8 = _prep(product_family="buttweld_fitting", subtype="elbow_90_lr", standard="ASME_B16.9", primary_size="8")
        self.assertNotIn("outside_diameter_mm", r8.dimension_resolution.resolved_dimensions)


class TestTeeGeometry(unittest.TestCase):
    def test_successful_generation(self):
        spec = _tee_spec("6")
        result = generate_geometry(spec)
        self.assertTrue(result.is_generated())
        self.assertEqual(result.topology_representation,
                          TopologyRepresentation.DETERMINISTIC_MULTI_FEATURE_MESH_NON_MANIFOLD_AT_INTERSECTION)

    def test_run_centre_to_end_validated(self):
        spec = _tee_spec("6")
        result = generate_geometry(spec)
        checks = {c["name"]: c for c in result.dimensional_validation_summary["checks"]}
        self.assertTrue(checks["dimension:tee_run_centre_to_end_mm"]["passed"])

    def test_branch_centre_to_end_validated(self):
        spec = _tee_spec("6")
        result = generate_geometry(spec)
        checks = {c["name"]: c for c in result.dimensional_validation_summary["checks"]}
        self.assertTrue(checks["dimension:tee_branch_centre_to_end_mm"]["passed"])

    def test_three_ports_with_distinct_roles(self):
        spec = _tee_spec("6")
        result = generate_geometry(spec)
        roles = sorted(p["role"] for p in result.connection_ports)
        self.assertEqual(roles, ["branch", "run_inlet", "run_outlet"])

    def test_no_fabricated_blend_radius_in_trace(self):
        spec = _tee_spec("6")
        result = generate_geometry(spec)
        self.assertTrue(any("no ASME-published or construction-derived blend" in t
                             for t in result.generation_trace + [t for cv in
                             result.geometry_payload["construction_values"] for t in cv.get("derivation_trace", [])]))


class TestCapGeometry(unittest.TestCase):
    def test_standard_length_generation(self):
        spec = _cap_spec("6")
        result = generate_geometry(spec)
        self.assertTrue(result.is_generated())
        self.assertEqual(result.topology_representation, TopologyRepresentation.SOLID_EXTERNAL_ENVELOPE)
        self.assertAlmostEqual(result.geometry_payload["measurements"]["selected_cap_length_mm"], 89.0)

    def test_heavy_wall_selected_when_actual_wall_exceeds_threshold(self):
        spec = _cap_spec("6", with_heavy_wall_dims=True)
        wt_cv = _wall_value("6", "ASME_B36.10M", "Sch160")
        result = generate_geometry(spec, product_kwargs={"actual_wall_thickness_value": wt_cv})
        self.assertTrue(result.is_generated())
        self.assertAlmostEqual(result.geometry_payload["measurements"]["selected_cap_length_mm"], 102.0)

    def test_standard_selected_when_actual_wall_below_threshold(self):
        spec = _cap_spec("6", with_heavy_wall_dims=True)
        wt_cv = _wall_value("6", "ASME_B36.10M", "Sch40")
        result = generate_geometry(spec, product_kwargs={"actual_wall_thickness_value": wt_cv})
        self.assertTrue(result.is_generated())
        self.assertAlmostEqual(result.geometry_payload["measurements"]["selected_cap_length_mm"], 89.0)

    def test_missing_wall_context_handled_safely(self):
        # actual wall supplied but heavy-wall dims not requested -> fails closed
        spec = _cap_spec("6", with_heavy_wall_dims=False)
        wt_cv = _wall_value("6", "ASME_B36.10M", "Sch160")
        result = generate_geometry(spec, product_kwargs={"actual_wall_thickness_value": wt_cv})
        self.assertEqual(result.generation_status, GeometryGenerationStatus.CONSTRUCTION_RULE_UNAVAILABLE)

    def test_single_open_end_port(self):
        spec = _cap_spec("6")
        result = generate_geometry(spec)
        self.assertEqual(len(result.connection_ports), 1)
        self.assertEqual(result.connection_ports[0]["role"], "open_end")


class TestReducerGeometry(unittest.TestCase):
    def test_concentric_successful_generation(self):
        spec = _reducer_spec("reducer_concentric", "6", "4")
        large_cv, small_cv = _reducer_ods("6", "4")
        result = generate_geometry(spec, product_kwargs={"large_od_value": large_cv, "small_od_value": small_cv})
        self.assertTrue(result.is_generated())
        self.assertEqual(result.topology_representation, TopologyRepresentation.SOLID_EXTERNAL_ENVELOPE)

    def test_large_small_od_validated(self):
        spec = _reducer_spec("reducer_concentric", "6", "4")
        large_cv, small_cv = _reducer_ods("6", "4")
        result = generate_geometry(spec, product_kwargs={"large_od_value": large_cv, "small_od_value": small_cv})
        checks = {c["name"]: c for c in result.dimensional_validation_summary["checks"]}
        self.assertTrue(checks["dimension:large_end_outside_diameter_mm"]["passed"])
        self.assertTrue(checks["dimension:small_end_outside_diameter_mm"]["passed"])

    def test_length_validated(self):
        spec = _reducer_spec("reducer_concentric", "6", "4")
        large_cv, small_cv = _reducer_ods("6", "4")
        result = generate_geometry(spec, product_kwargs={"large_od_value": large_cv, "small_od_value": small_cv})
        checks = {c["name"]: c for c in result.dimensional_validation_summary["checks"]}
        self.assertTrue(checks["dimension:length_mm"]["passed"])

    def test_concentric_axis_remains_coincident(self):
        spec = _reducer_spec("reducer_concentric", "6", "4")
        large_cv, small_cv = _reducer_ods("6", "4")
        result = generate_geometry(spec, product_kwargs={"large_od_value": large_cv, "small_od_value": small_cv})
        for port in result.connection_ports:
            self.assertAlmostEqual(port["position"][0], 0.0)
            self.assertAlmostEqual(port["position"][1], 0.0)

    def test_eccentric_successful_generation(self):
        spec = _reducer_spec("reducer_eccentric", "6", "4")
        large_cv, small_cv = _reducer_ods("6", "4")
        result = generate_geometry(spec, product_kwargs={"large_od_value": large_cv, "small_od_value": small_cv})
        self.assertTrue(result.is_generated())

    def test_eccentric_offset_validated(self):
        spec = _reducer_spec("reducer_eccentric", "6", "4")
        large_cv, small_cv = _reducer_ods("6", "4")
        result = generate_geometry(spec, product_kwargs={"large_od_value": large_cv, "small_od_value": small_cv})
        checks = {c["name"]: c for c in result.dimensional_validation_summary["checks"]}
        self.assertTrue(checks["dimension:eccentric_offset_mm"]["passed"])

    def test_eccentric_orientation_deterministic_across_calls(self):
        spec = _reducer_spec("reducer_eccentric", "6", "4")
        large_cv, small_cv = _reducer_ods("6", "4")
        r1 = generate_geometry(spec, product_kwargs={"large_od_value": large_cv, "small_od_value": small_cv})
        r2 = generate_geometry(spec, product_kwargs={"large_od_value": large_cv, "small_od_value": small_cv})
        self.assertEqual(r1.geometry_fingerprint, r2.geometry_fingerprint)

    def test_port_role_identity_preserved_not_generic(self):
        spec = _reducer_spec("reducer_concentric", "6", "4")
        large_cv, small_cv = _reducer_ods("6", "4")
        result = generate_geometry(spec, product_kwargs={"large_od_value": large_cv, "small_od_value": small_cv})
        roles = sorted(p["role"] for p in result.connection_ports)
        self.assertEqual(roles, ["large_end", "small_end"])

    def test_reducer_involving_quarantined_nps8_blocked(self):
        r = _prep(product_family="buttweld_fitting", subtype="reducer_concentric", standard="ASME_B16.9",
                  large_end_size="8", small_end_size="6")
        outcome = ReducerPerEndOutsideDiameterRule().resolve(_RESOLVER, standard="ASME_B16.9",
                                                              large_end_size="8", small_end_size="6")
        self.assertEqual(outcome.status, ConstructionRuleStatus.RULE_BLOCKED_QUARANTINE)

    def test_reducer_involving_quarantined_nps12_blocked(self):
        outcome = ReducerPerEndOutsideDiameterRule().resolve(_RESOLVER, standard="ASME_B16.9",
                                                              large_end_size="12", small_end_size="6")
        self.assertEqual(outcome.status, ConstructionRuleStatus.RULE_BLOCKED_QUARANTINE)

    def test_unaffected_reducer_pair_generates_normally(self):
        spec = _reducer_spec("reducer_concentric", "6", "3")
        large_cv, small_cv = _reducer_ods("6", "3")
        result = generate_geometry(spec, product_kwargs={"large_od_value": large_cv, "small_od_value": small_cv})
        self.assertTrue(result.is_generated())

    def test_missing_od_values_raises_geometry_input_error(self):
        spec = _reducer_spec("reducer_concentric", "6", "4")
        from kgpe.geometry.product_api import GeometryInputError
        with self.assertRaises(GeometryInputError):
            reducer.build(spec, geo.GenerationParameters())


class TestDispatchExpansion(unittest.TestCase):
    def test_new_profiles_registered(self):
        from kgpe.geometry.kernel import _PRODUCT_DISPATCH
        for profile_id in ("buttweld_tee_equal", "buttweld_cap", "buttweld_reducer"):
            self.assertIn(profile_id, _PRODUCT_DISPATCH)

    def test_unimplemented_profile_still_structured_unsupported(self):
        # "flange_weld_neck" was this test's placeholder unsupported-
        # profile example at Prompt 13 time; Prompt 14 wired it into
        # dispatch, so it was switched to "olet_body" - which Prompt 15
        # then ALSO wired into dispatch. Switched again to
        # "olet_outlet_height" (still genuinely unwired - insufficient
        # dims for any envelope, see geometry_spec/profile.py).
        spec = GeometrySpecification(readiness_status=GeometryReadinessStatus.GEOMETRY_READY,
                                      geometry_profile_id="olet_outlet_height")
        result = generate_geometry(spec)
        self.assertEqual(result.generation_status, GeometryGenerationStatus.UNSUPPORTED_GEOMETRY_PROFILE)

    def test_olet_still_unsupported(self):
        # Prompt 15 wired "olet_body" into dispatch (weldolet/sockolet/
        # threadolet) - this test now uses "olet_outlet_height" (the
        # height-only MSS official-table profile, insufficient alone for
        # any envelope - still genuinely unwired) to keep testing a real
        # olet-family profile that remains unsupported.
        spec = GeometrySpecification(readiness_status=GeometryReadinessStatus.GEOMETRY_READY,
                                      geometry_profile_id="olet_outlet_height")
        result = generate_geometry(spec)
        self.assertEqual(result.generation_status, GeometryGenerationStatus.UNSUPPORTED_GEOMETRY_PROFILE)


class TestEndToEndPipelines(unittest.TestCase):
    def test_elbow_pipeline(self):
        req = EngineeringRequest(product_family="buttweld_fitting", subtype="elbow_90_lr",
                                  standard="ASME_B16.9", primary_size="6")
        result = run_pipeline(req, resolver=_RESOLVER)
        self.assertTrue(result.is_generated())
        self.assertEqual(result.geometry_specification.data_layer_fingerprint, _FINGERPRINT)

    def test_tee_pipeline(self):
        req = EngineeringRequest(product_family="buttweld_fitting", subtype="tee_equal",
                                  standard="ASME_B16.9", primary_size="6")
        result = run_pipeline(req, resolver=_RESOLVER)
        self.assertTrue(result.is_generated())

    def test_cap_pipeline(self):
        req = EngineeringRequest(product_family="buttweld_fitting", subtype="cap",
                                  standard="ASME_B16.9", primary_size="6")
        result = run_pipeline(req, resolver=_RESOLVER)
        self.assertTrue(result.is_generated())

    def test_concentric_reducer_pipeline(self):
        req = EngineeringRequest(product_family="buttweld_fitting", subtype="reducer_concentric",
                                  standard="ASME_B16.9", large_end_size="6", small_end_size="4")
        large_cv, small_cv = _reducer_ods("6", "4")
        result = run_pipeline(req, resolver=_RESOLVER,
                               product_kwargs={"large_od_value": large_cv, "small_od_value": small_cv})
        self.assertTrue(result.is_generated())

    def test_eccentric_reducer_pipeline(self):
        req = EngineeringRequest(product_family="buttweld_fitting", subtype="reducer_eccentric",
                                  standard="ASME_B16.9", large_end_size="6", small_end_size="4")
        large_cv, small_cv = _reducer_ods("6", "4")
        result = run_pipeline(req, resolver=_RESOLVER,
                               product_kwargs={"large_od_value": large_cv, "small_od_value": small_cv})
        self.assertTrue(result.is_generated())

    def test_pipe_generation_unaffected_by_prompt13(self):
        req = EngineeringRequest(product_family="pipe", standard="ASME_B36.10M", primary_size="6", schedule="Sch40")
        result = run_pipeline(req, resolver=_RESOLVER)
        self.assertTrue(result.is_generated())
        self.assertEqual(result.geometry_result.geometry_type, "pipe_segment")


class TestTopologyHonesty(unittest.TestCase):
    def test_elbow_solid_is_external_envelope(self):
        result = generate_geometry(_elbow_spec("elbow_90_lr"))
        self.assertEqual(result.topology_representation, TopologyRepresentation.SOLID_EXTERNAL_ENVELOPE)

    def test_elbow_hollow_is_hollow_swept_solid(self):
        result = generate_geometry(_elbow_spec("elbow_90_lr"),
                                    product_kwargs={"wall_thickness_value": _wall_value("6")})
        self.assertEqual(result.topology_representation, TopologyRepresentation.HOLLOW_SWEPT_SOLID)

    def test_tee_is_multi_feature_non_manifold(self):
        result = generate_geometry(_tee_spec("6"))
        self.assertEqual(result.topology_representation,
                          TopologyRepresentation.DETERMINISTIC_MULTI_FEATURE_MESH_NON_MANIFOLD_AT_INTERSECTION)

    def test_never_claims_hollow_without_bore(self):
        result = generate_geometry(_elbow_spec("elbow_90_lr"))
        self.assertNotEqual(result.topology_representation, TopologyRepresentation.HOLLOW_SWEPT_SOLID)
        self.assertNotIn("bore_diameter_mm", result.geometry_payload["measurements"])


class TestFingerprintAndRuleVersionReproducibility(unittest.TestCase):
    def test_hollow_vs_solid_different_fingerprints(self):
        spec = _elbow_spec("elbow_90_lr")
        r_solid = generate_geometry(spec)
        r_hollow = generate_geometry(spec, product_kwargs={"wall_thickness_value": _wall_value("6")})
        self.assertNotEqual(r_solid.geometry_fingerprint, r_hollow.geometry_fingerprint)
        # engineering identity (geometry_specification_fingerprint) is unchanged -
        # only downstream generation input (wall context) differed.
        self.assertEqual(r_solid.geometry_specification_fingerprint, r_hollow.geometry_specification_fingerprint)

    def test_concentric_vs_eccentric_different_fingerprints(self):
        large_cv, small_cv = _reducer_ods("6", "4")
        r_conc = generate_geometry(_reducer_spec("reducer_concentric", "6", "4"),
                                    product_kwargs={"large_od_value": large_cv, "small_od_value": small_cv})
        r_ecc = generate_geometry(_reducer_spec("reducer_eccentric", "6", "4"),
                                   product_kwargs={"large_od_value": large_cv, "small_od_value": small_cv})
        self.assertNotEqual(r_conc.geometry_fingerprint, r_ecc.geometry_fingerprint)

    def test_tessellation_change_alters_fingerprint_not_identity(self):
        spec = _tee_spec("6")
        r_default = generate_geometry(spec)
        r_custom = generate_geometry(spec, geo.GenerationParameters(radial_segments=64))
        self.assertNotEqual(r_default.geometry_fingerprint, r_custom.geometry_fingerprint)
        self.assertEqual(spec.geometry_specification_fingerprint, spec.geometry_specification_fingerprint)

    def test_repeated_generation_deterministic(self):
        spec = _cap_spec("6")
        r1 = generate_geometry(spec)
        r2 = generate_geometry(spec)
        self.assertEqual(r1.geometry_fingerprint, r2.geometry_fingerprint)

    def test_construction_rule_versions_recorded(self):
        result = generate_geometry(_cap_spec("6"))
        self.assertIn("cap_length_selection_standard_vs_heavy_wall", result.construction_rule_versions)
        self.assertIn("cap_flat_disc_closure", result.construction_rule_versions)


class TestPrompt12BackwardCompatibility(unittest.TestCase):
    def test_pipe_bore_derivation_unchanged(self):
        req = EngineeringRequest(product_family="pipe", standard="ASME_B36.10M", primary_size="6", schedule="Sch40")
        result = run_pipeline(req, resolver=_RESOLVER)
        self.assertAlmostEqual(result.geometry_result.geometry_payload["measurements"]["bore_diameter_mm"], 154.08)

    def test_elbow_90_lr_default_request_still_generates(self):
        spec = _elbow_spec("elbow_90_lr")
        result = generate_geometry(spec)
        self.assertTrue(result.is_generated())
        self.assertEqual(result.geometry_type, "buttweld_elbow_90_lr")


class TestFullRegressionAndDemo(unittest.TestCase):
    def test_data_layer_fingerprint_unchanged(self):
        self.assertEqual(_FINGERPRINT, "9301f07c27b8d7bb864fbc56a7999e13e241e40809ddf26d9a0c4981658d261b")  # Prompt 42: shifted by new ASME B16.5 hub/long_weld_neck facts

    def test_legacy_generator_untouched(self):
        from kgpe.generator import _DISPATCH
        self.assertIn("pipe", _DISPATCH)


if __name__ == "__main__":
    unittest.main()
