# -*- coding: utf-8 -*-
"""
tests/test_prompt11_geometry_handoff.py
===========================================
Prompt 11 Sec.26: automated tests for kgpe.geometry_spec - the engineering
specification orchestration and geometry-handoff layer built on top of the
frozen canonical data layer (Prompt 9) and the resolution engine (Prompt
10). Standard-library `unittest` only.
"""
import os
import subprocess
import sys
import unittest

from kgpe.contract.canonical_reader import build_canonical_reader
from kgpe.contract.snapshot import registry_fingerprint
from kgpe.resolver import EngineeringRequest, EngineeringResolver, ResolutionStatus
from kgpe.geometry_spec import (
    EngineeringObjectIdentity, IdentityConstructionError, ResolvedDimension, EngineeringDimensionBundle,
    GeometryReadinessStatus, ALL_GEOMETRY_READINESS_STATUSES, readiness_for_resolution_status,
    GeometryProfile, PROFILE_REGISTRY, find_profile, all_profiles,
    MFR_NOT_APPLICABLE, MFR_REQUIRED, GeometrySpecification,
    GeometrySpecificationCompiler, compile_geometry_specification,
    OrchestrationStage, prepare_geometry_specification,
    BatchStatus, ALL_BATCH_STATUSES, prepare_geometry_specifications_batch,
    compute_geometry_specification_fingerprint, GEOMETRY_SPEC_SCHEMA_VERSION,
)
from kgpe.geometry_spec import discovery as disc
from kgpe.geometry_spec import coverage as cov
from kgpe.resolver.spec import ResolvedEngineeringSpecification

_READER, _ = build_canonical_reader()
_FINGERPRINT = registry_fingerprint(_READER.registry)
_RESOLVER = EngineeringResolver(_READER, _FINGERPRINT)


def _prep(**kwargs):
    return prepare_geometry_specification(EngineeringRequest(**kwargs), resolver=_RESOLVER)


class TestFirstClassDiscovery(unittest.TestCase):
    def test_product_families_live(self):
        fams = disc.discover_product_families(_READER)
        self.assertIn("pipe", fams)
        self.assertIn("flange", fams)
        self.assertEqual(fams, sorted(fams))

    def test_standards_filtered_by_family(self):
        standards = disc.discover_standards(_READER, product_family="pipe")
        self.assertIn("ASME_B36.10M", standards)
        self.assertNotIn("ASME_B16.5", standards)

    def test_subtypes_independent_of_dimension_request(self):
        # Sec.3's named Prompt-10 limitation - subtype discovery must work
        # WITHOUT any dimensions being requested at all.
        subtypes = disc.discover_subtypes(_READER, "buttweld_fitting", standard="ASME_B16.9")
        self.assertIn("elbow_90_lr", subtypes)
        self.assertIn("tee_equal", subtypes)
        self.assertIn("cap", subtypes)

    def test_sizes_scoped_by_standard(self):
        sizes = disc.discover_sizes(_READER, "pipe", "ASME_B36.10M")
        self.assertIn("nps", sizes)
        self.assertIn("6", sizes["nps"])

    def test_ratings_discovery(self):
        ratings = disc.discover_ratings(_READER, "flange", "ASME_B16.5", subtype="weld_neck")
        self.assertIn("class_key", ratings)
        self.assertIn("150", ratings["class_key"])

    def test_manufacturer_profiles_discovery(self):
        profiles = disc.discover_manufacturer_profiles(_READER, product_family="olet")
        self.assertEqual(profiles, ["Bonney Forge"])

    def test_dimensions_discovery(self):
        dims = disc.discover_dimensions(_READER, "pipe", "ASME_B36.10M")
        self.assertIn("outside_diameter_mm", dims)
        self.assertIn("wall_thickness_mm", dims)

    def test_reducer_pairs_discovery(self):
        pairs = disc.discover_reducer_pairs(_READER, "buttweld_fitting", "ASME_B16.9",
                                             subtype="reducer_concentric")
        self.assertIn(("6", "4"), pairs)

    def test_run_branch_pairs_discovery(self):
        pairs = disc.discover_run_branch_pairs(_READER, "olet", "MSS_SP97", subtype="weldolet")
        self.assertIn(("6", "6"), pairs)

    def test_geometry_profile_available(self):
        self.assertTrue(disc.discover_geometry_profile_available("pipe", None))
        self.assertFalse(disc.discover_geometry_profile_available("nonexistent_family", None))

    def test_progressive_discovery_never_picks_a_default(self):
        result = disc.progressive_discovery(_READER, product_family="flange", standard="ASME_B16.5",
                                              subtype="weld_neck")
        self.assertIn("dimensions", result)
        self.assertIn("geometry_profile_available", result)
        self.assertTrue(result["geometry_profile_available"])


class TestEngineeringObjectIdentity(unittest.TestCase):
    def test_from_resolved_spec_requires_resolved_status(self):
        bad = ResolvedEngineeringSpecification(status=ResolutionStatus.INCOMPLETE_REQUEST)
        with self.assertRaises(IdentityConstructionError):
            EngineeringObjectIdentity.from_resolved_spec(bad)

    def test_from_resolved_spec_populates_only_applicable_fields(self):
        spec = ResolvedEngineeringSpecification(
            status=ResolutionStatus.RESOLVED, product_family="pipe", standard="ASME_B36.10M",
            size_system="nps", sizes={"nps": "6"}, rating_system="SCHEDULE", rating_value="SCH40",
        )
        identity = EngineeringObjectIdentity.from_resolved_spec(spec)
        self.assertEqual(identity.primary_size, "6")
        self.assertEqual(identity.schedule, "SCH40")
        self.assertIsNone(identity.large_end_size)
        self.assertIsNone(identity.pressure_class)
        as_dict = identity.as_dict()
        self.assertNotIn("large_end_size", as_dict)
        self.assertIn("primary_size", as_dict)

    def test_reducer_identity_uses_large_small_end_fields(self):
        spec = ResolvedEngineeringSpecification(
            status=ResolutionStatus.RESOLVED, product_family="buttweld_fitting",
            subtype="reducer_concentric", standard="ASME_B16.9", size_system="nps",
            sizes={"large_end_nps": "6", "small_end_nps": "4"},
        )
        identity = EngineeringObjectIdentity.from_resolved_spec(spec)
        self.assertEqual(identity.large_end_size, "6")
        self.assertEqual(identity.small_end_size, "4")
        self.assertIsNone(identity.primary_size)

    def test_run_branch_identity(self):
        spec = ResolvedEngineeringSpecification(
            status=ResolutionStatus.RESOLVED, product_family="olet", subtype="weldolet",
            standard="MSS_SP97", size_system="nps", sizes={"run_nps": "6", "branch_nps": "6"},
        )
        identity = EngineeringObjectIdentity.from_resolved_spec(spec)
        self.assertEqual(identity.run_size, "6")
        self.assertEqual(identity.branch_size, "6")

    def test_display_label_deterministic_and_non_empty(self):
        spec = ResolvedEngineeringSpecification(
            status=ResolutionStatus.RESOLVED, product_family="pipe", standard="ASME_B36.10M",
            size_system="nps", sizes={"nps": "6"}, rating_system="SCHEDULE", rating_value="SCH40",
        )
        identity = EngineeringObjectIdentity.from_resolved_spec(spec)
        label1 = identity.display_label
        label2 = identity.display_label
        self.assertEqual(label1, label2)
        self.assertIn("pipe", label1)

    def test_to_dict_includes_none_fields(self):
        identity = EngineeringObjectIdentity(product_family="pipe")
        full = identity.to_dict()
        self.assertIn("large_end_size", full)
        self.assertIsNone(full["large_end_size"])


class TestDimensionBundle(unittest.TestCase):
    def test_resolved_dimension_from_resolved_dict(self):
        d = {"value": 168.3, "unit": "mm", "verification_status": "VERIFIED_AUTHORITATIVE",
             "source_file": "Pipes/ASME_B36.10M_B36.19M_Pipes.json"}
        rd = ResolvedDimension.from_resolved_dict("outside_diameter_mm", d)
        self.assertEqual(rd.value, 168.3)
        self.assertEqual(rd.unit, "mm")
        self.assertIn("VERIFIED_AUTHORITATIVE", rd.provenance_summary)

    def test_bundle_never_reduces_to_bare_floats(self):
        bundle = EngineeringDimensionBundle()
        bundle.add(ResolvedDimension("outside_diameter_mm", 168.3, "mm", "VERIFIED_AUTHORITATIVE",
                                      "Pipes/x.json", "..."))
        self.assertIn("outside_diameter_mm", bundle)
        entry = bundle["outside_diameter_mm"]
        self.assertEqual(entry.verification_status, "VERIFIED_AUTHORITATIVE")
        numeric = bundle.numeric_values()
        self.assertEqual(numeric, {"outside_diameter_mm": 168.3})
        full = bundle.to_dict()
        self.assertEqual(full["outside_diameter_mm"]["unit"], "mm")

    def test_bundle_names_sorted(self):
        bundle = EngineeringDimensionBundle()
        bundle.add(ResolvedDimension("z_dim", 1, "mm", "VERIFIED_AUTHORITATIVE"))
        bundle.add(ResolvedDimension("a_dim", 2, "mm", "VERIFIED_AUTHORITATIVE"))
        self.assertEqual(bundle.names(), ["a_dim", "z_dim"])


class TestReadinessVocabulary(unittest.TestCase):
    def test_all_seven_statuses_present(self):
        self.assertEqual(len(ALL_GEOMETRY_READINESS_STATUSES), 7)

    def test_resolution_status_mapping_is_specific_not_generic(self):
        mapped = {readiness_for_resolution_status(s) for s in (
            ResolutionStatus.INCOMPLETE_REQUEST, ResolutionStatus.AMBIGUOUS_REQUEST,
            ResolutionStatus.UNSUPPORTED_REQUEST, ResolutionStatus.QUARANTINED_ENGINEERING_DATA,
            ResolutionStatus.MANUFACTURER_CONTEXT_REQUIRED,
        )}
        self.assertEqual(len(mapped), 5)  # each maps to a DIFFERENT readiness status


class TestGeometryProfileRegistry(unittest.TestCase):
    def test_find_profile_pipe(self):
        profile = find_profile("pipe", None)
        self.assertIsNotNone(profile)
        self.assertEqual(profile.profile_id, "pipe")

    def test_find_profile_none_for_unknown(self):
        # pipe has subtypes=None (applies regardless of subtype - pipe has
        # no subtype concept at all), so a bogus subtype there still
        # matches the pipe profile by design. A family that DOES scope by
        # subtype (buttweld_fitting) correctly returns None for an unknown one.
        self.assertIsNone(find_profile("buttweld_fitting", "nonexistent_subtype"))
        self.assertIsNone(find_profile("nonexistent_family", None))

    def test_find_profile_flange_weld_neck(self):
        profile = find_profile("flange", "weld_neck")
        self.assertEqual(profile.profile_id, "flange_weld_neck")
        self.assertIn("bore_diameter_mm", profile.required_dimensions)

    def test_olet_body_requires_manufacturer_context(self):
        profile = find_profile("olet", "weldolet")
        self.assertEqual(profile.manufacturer_specific, MFR_REQUIRED)

    def test_pipe_profile_not_manufacturer_specific(self):
        profile = find_profile("pipe", None)
        self.assertEqual(profile.manufacturer_specific, MFR_NOT_APPLICABLE)

    def test_all_profiles_have_unique_ids(self):
        ids = [p.profile_id for p in all_profiles()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_profile_never_imports_dimension_library_or_adapters(self):
        import kgpe.geometry_spec.profile as profile_mod
        with open(profile_mod.__file__, encoding="utf-8") as fh:
            for line in fh.readlines():
                stripped = line.strip()
                if stripped.startswith("import ") or stripped.startswith("from "):
                    self.assertNotIn("dimension_library", stripped)
                    self.assertNotIn("adapters", stripped)

    def test_profile_to_dict_serializable(self):
        profile = find_profile("pipe", None)
        d = profile.to_dict()
        self.assertEqual(d["profile_id"], "pipe")
        self.assertIsInstance(d["required_dimensions"], list)


class TestGeometrySpecificationCompiler(unittest.TestCase):
    def test_rejects_non_resolved_spec(self):
        bad = ResolvedEngineeringSpecification(status=ResolutionStatus.INCOMPLETE_REQUEST)
        spec = compile_geometry_specification(bad)
        self.assertEqual(spec.readiness_status, GeometryReadinessStatus.ENGINEERING_SPEC_INCOMPLETE)
        self.assertFalse(spec.is_ready())

    def test_profile_unavailable(self):
        good = ResolvedEngineeringSpecification(status=ResolutionStatus.RESOLVED,
                                                  product_family="nonexistent_family")
        spec = compile_geometry_specification(good)
        self.assertEqual(spec.readiness_status, GeometryReadinessStatus.GEOMETRY_PROFILE_UNAVAILABLE)

    def test_required_dimension_missing_fails_closed(self):
        spec_in = ResolvedEngineeringSpecification(
            status=ResolutionStatus.RESOLVED, product_family="pipe", standard="ASME_B36.10M",
            size_system="nps", sizes={"nps": "6"},
            resolved_dimensions={"outside_diameter_mm": {"value": 168.3, "unit": "mm",
                                  "verification_status": "VERIFIED_AUTHORITATIVE", "source_file": "x.json"}},
        )
        spec = compile_geometry_specification(spec_in)
        self.assertEqual(spec.readiness_status, GeometryReadinessStatus.ENGINEERING_SPEC_INCOMPLETE)
        self.assertTrue(any("wall_thickness_mm" in w for w in spec.warnings))

    def test_manufacturer_context_required_without_profile(self):
        spec_in = ResolvedEngineeringSpecification(
            status=ResolutionStatus.RESOLVED, product_family="olet", subtype="weldolet",
            standard="MSS_SP97", manufacturer_profile=None,
        )
        spec = compile_geometry_specification(spec_in)
        self.assertEqual(spec.readiness_status, GeometryReadinessStatus.MANUFACTURER_CONTEXT_REQUIRED)

    def test_successful_compile_produces_geometry_ready(self):
        result = _prep(product_family="pipe", standard="ASME_B36.10M", primary_size="6", schedule="Sch40")
        spec = result.geometry_specification
        self.assertEqual(spec.readiness_status, GeometryReadinessStatus.GEOMETRY_READY)
        self.assertTrue(spec.is_ready())
        self.assertEqual(spec.schema_version, GEOMETRY_SPEC_SCHEMA_VERSION)
        self.assertIn("outside_diameter_mm", spec.required_dimensions)
        self.assertIn("wall_thickness_mm", spec.required_dimensions)
        self.assertIsNotNone(spec.geometry_specification_fingerprint)
        self.assertEqual(spec.data_layer_fingerprint, _FINGERPRINT)

    def test_geometry_specification_never_contains_mesh_fields(self):
        result = _prep(product_family="pipe", standard="ASME_B36.10M", primary_size="6", schedule="Sch40")
        d = result.geometry_specification.to_dict()
        for forbidden in ("vertices", "triangles", "mesh", "camera", "lighting", "color", "solid"):
            self.assertNotIn(forbidden, d)

    def test_compiler_never_reads_source_json_or_imports_adapters(self):
        import kgpe.geometry_spec.compiler as compiler_mod
        with open(compiler_mod.__file__, encoding="utf-8") as fh:
            for line in fh.readlines():
                stripped = line.strip()
                if stripped.startswith("import ") or stripped.startswith("from "):
                    self.assertNotIn("dimension_library", stripped)
                    self.assertNotIn("adapters", stripped)
                    self.assertNotIn("json", stripped.lower())


class TestOrchestration(unittest.TestCase):
    def test_engineering_resolution_failure_stage(self):
        result = _prep(product_family="pipe", standard="ASME_B36.10M")  # no size
        self.assertEqual(result.failed_stage, OrchestrationStage.ENGINEERING_RESOLUTION)
        self.assertIsNone(result.dimension_resolution)

    def test_profile_selection_failure_stage(self):
        # coupling_sw is a real, directly-resolvable ASME_B16.11 canonical
        # subtype with canonical data, but no geometry profile is defined
        # for it (profile.py only covers elbow/tee/cross and cap_sw for
        # socketweld_fitting) - a genuine GEOMETRY_PROFILE_UNAVAILABLE case
        # reached through the real orchestration path.
        result = _prep(product_family="socketweld_fitting", subtype="coupling_sw",
                        standard="ASME_B16.11", primary_size="2", pressure_class="3000")
        self.assertEqual(result.identity_resolution.status, ResolutionStatus.RESOLVED)
        self.assertEqual(result.failed_stage, OrchestrationStage.PROFILE_SELECTION)
        self.assertEqual(result.geometry_specification.readiness_status,
                          GeometryReadinessStatus.GEOMETRY_PROFILE_UNAVAILABLE)

    def test_dimension_resolution_failure_preserves_both_results(self):
        result = _prep(product_family="buttweld_fitting", subtype="reducer_concentric",
                        standard="ASME_B16.9", large_end_size="6", small_end_size="4")
        self.assertEqual(result.failed_stage, OrchestrationStage.DIMENSION_RESOLUTION)
        self.assertEqual(result.identity_resolution.status, ResolutionStatus.RESOLVED)
        self.assertIsNotNone(result.dimension_resolution)
        self.assertNotEqual(result.dimension_resolution.status, ResolutionStatus.RESOLVED)

    def test_successful_orchestration_preserves_both_resolutions(self):
        result = _prep(product_family="pipe", standard="ASME_B36.10M", primary_size="6", schedule="Sch40")
        self.assertIsNone(result.failed_stage)
        self.assertEqual(result.identity_resolution.status, ResolutionStatus.RESOLVED)
        self.assertEqual(result.dimension_resolution.status, ResolutionStatus.RESOLVED)
        self.assertTrue(result.is_ready())

    def test_optional_dimension_only_included_when_explicitly_requested(self):
        req_without = EngineeringRequest(product_family="buttweld_fitting", subtype="elbow_90_lr",
                                          standard="ASME_B16.9", primary_size="6")
        result_without = prepare_geometry_specification(req_without, resolver=_RESOLVER)
        self.assertNotIn("wall_thickness_mm", result_without.geometry_specification.optional_dimensions)

    def test_rating_relaxation_recovers_rating_independent_dimension(self):
        # pipe OD does not vary by schedule - must still resolve GEOMETRY_READY
        # even though schedule is supplied (Sec.25 scenario 1).
        result = _prep(product_family="pipe", standard="ASME_B36.10M", primary_size="6", schedule="Sch40")
        self.assertTrue(result.is_ready())
        self.assertIn("outside_diameter_mm", result.dimension_resolution.resolved_dimensions)

    def test_to_dict_serializable(self):
        result = _prep(product_family="pipe", standard="ASME_B36.10M", primary_size="6", schedule="Sch40")
        d = result.to_dict()
        self.assertIn("geometry_specification", d)
        self.assertIn("failed_stage", d)


class TestBatchSemantics(unittest.TestCase):
    def test_batch_all_ready(self):
        batch = prepare_geometry_specifications_batch([
            EngineeringRequest(product_family="pipe", standard="ASME_B36.10M", primary_size="6", schedule="Sch40"),
            EngineeringRequest(product_family="buttweld_fitting", subtype="elbow_90_lr",
                                standard="ASME_B16.9", primary_size="6"),
        ], resolver=_RESOLVER)
        self.assertEqual(batch.batch_status, BatchStatus.ALL_READY)
        self.assertTrue(all(it.is_ready() for it in batch.items))

    def test_batch_mixed_preserves_order_and_isolates_failure(self):
        batch = prepare_geometry_specifications_batch([
            EngineeringRequest(product_family="pipe", standard="ASME_B36.10M", primary_size="6", schedule="Sch40"),
            EngineeringRequest(product_family="buttweld_fitting", subtype="reducer_concentric",
                                standard="ASME_B16.9", large_end_size="6", small_end_size="4"),
            EngineeringRequest(product_family="buttweld_fitting", subtype="tee_equal",
                                standard="ASME_B16.9", primary_size="4"),
        ], resolver=_RESOLVER)
        self.assertEqual(batch.batch_status, BatchStatus.PARTIALLY_READY)
        self.assertEqual([it.is_ready() for it in batch.items], [True, False, True])

    def test_batch_none_ready(self):
        batch = prepare_geometry_specifications_batch([
            EngineeringRequest(product_family="pipe", standard="ASME_B36.10M"),
            EngineeringRequest(product_family="buttweld_fitting", subtype="reducer_concentric",
                                standard="ASME_B16.9", large_end_size="6", small_end_size="4"),
        ], resolver=_RESOLVER)
        self.assertEqual(batch.batch_status, BatchStatus.NONE_READY)

    def test_batch_status_vocabulary_is_small_and_explicit(self):
        self.assertEqual(ALL_BATCH_STATUSES, {"ALL_READY", "PARTIALLY_READY", "NONE_READY"})

    def test_batch_isolates_unexpected_exceptions(self):
        class ExplodingRequest:
            dimensions = []
            def to_dict(self):
                raise RuntimeError("boom")
        batch = prepare_geometry_specifications_batch(
            [EngineeringRequest(product_family="pipe", standard="ASME_B36.10M", primary_size="6",
                                 schedule="Sch40"), ExplodingRequest()],
            resolver=_RESOLVER)
        self.assertEqual(len(batch.items), 2)
        self.assertTrue(batch.items[0].is_ready())
        self.assertFalse(batch.items[1].is_ready())


class TestDeterministicFingerprint(unittest.TestCase):
    def test_identical_inputs_produce_identical_fingerprint(self):
        r1 = _prep(product_family="buttweld_fitting", subtype="elbow_90_lr",
                    standard="ASME_B16.9", primary_size="6")
        r2 = _prep(product_family="buttweld_fitting", subtype="elbow_90_lr",
                    standard="ASME_B16.9", primary_size="6")
        self.assertEqual(r1.geometry_specification.geometry_specification_fingerprint,
                          r2.geometry_specification.geometry_specification_fingerprint)

    def test_mutated_size_changes_fingerprint(self):
        r1 = _prep(product_family="buttweld_fitting", subtype="elbow_90_lr",
                    standard="ASME_B16.9", primary_size="6")
        r2 = _prep(product_family="buttweld_fitting", subtype="elbow_90_lr",
                    standard="ASME_B16.9", primary_size="4")
        self.assertNotEqual(r1.geometry_specification.geometry_specification_fingerprint,
                             r2.geometry_specification.geometry_specification_fingerprint)

    def test_fingerprint_excludes_trace_and_is_pure_function_of_content(self):
        identity = EngineeringObjectIdentity(product_family="pipe", standard="ASME_B36.10M",
                                              size_system="nps", primary_size="6")
        bundle = EngineeringDimensionBundle()
        bundle.add(ResolvedDimension("outside_diameter_mm", 168.3, "mm", "VERIFIED_AUTHORITATIVE"))
        fp1 = compute_geometry_specification_fingerprint(
            GEOMETRY_SPEC_SCHEMA_VERSION, identity, bundle, EngineeringDimensionBundle(), "abc123", "pipe", "1")
        fp2 = compute_geometry_specification_fingerprint(
            GEOMETRY_SPEC_SCHEMA_VERSION, identity, bundle, EngineeringDimensionBundle(), "abc123", "pipe", "1")
        self.assertEqual(fp1, fp2)

    def test_fingerprint_sensitive_to_data_layer_fingerprint(self):
        identity = EngineeringObjectIdentity(product_family="pipe", standard="ASME_B36.10M")
        bundle = EngineeringDimensionBundle()
        fp1 = compute_geometry_specification_fingerprint(
            GEOMETRY_SPEC_SCHEMA_VERSION, identity, bundle, bundle, "fingerprint-A", "pipe", "1")
        fp2 = compute_geometry_specification_fingerprint(
            GEOMETRY_SPEC_SCHEMA_VERSION, identity, bundle, bundle, "fingerprint-B", "pipe", "1")
        self.assertNotEqual(fp1, fp2)

    def test_fingerprint_sensitive_to_profile_version(self):
        identity = EngineeringObjectIdentity(product_family="pipe")
        bundle = EngineeringDimensionBundle()
        fp1 = compute_geometry_specification_fingerprint(
            GEOMETRY_SPEC_SCHEMA_VERSION, identity, bundle, bundle, "fp", "pipe", "1")
        fp2 = compute_geometry_specification_fingerprint(
            GEOMETRY_SPEC_SCHEMA_VERSION, identity, bundle, bundle, "fp", "pipe", "2")
        self.assertNotEqual(fp1, fp2)

    def test_geometry_ready_result_binds_data_layer_and_own_fingerprint(self):
        result = _prep(product_family="pipe", standard="ASME_B36.10M", primary_size="6", schedule="Sch40")
        spec = result.geometry_specification
        self.assertEqual(spec.data_layer_fingerprint, _FINGERPRINT)
        self.assertEqual(len(spec.geometry_specification_fingerprint), 64)  # sha256 hex


class TestGeometryProfileCoverageMatrix(unittest.TestCase):
    def test_matrix_uses_only_the_small_explicit_vocabulary(self):
        rows = cov.geometry_profile_coverage_matrix(_READER)
        self.assertTrue(rows)
        statuses = {r["geometry_readiness_status"] for r in rows}
        self.assertTrue(statuses <= cov.ALL_PROFILE_COVERAGE_STATUSES)

    def test_pipe_row_is_profile_ready(self):
        rows = cov.geometry_profile_coverage_matrix(_READER)
        pipe_rows = [r for r in rows if r["product_family"] == "pipe"]
        self.assertTrue(pipe_rows)
        for row in pipe_rows:
            self.assertEqual(row["geometry_readiness_status"], cov.PROFILE_READY)

    def test_flange_weld_neck_asme_row_blocked_by_missing_bore(self):
        rows = cov.geometry_profile_coverage_matrix(_READER)
        wn_rows = [r for r in rows if r["product_family"] == "flange" and r["subtype"] == "weld_neck"]
        self.assertEqual(len(wn_rows), 1)
        row = wn_rows[0]
        self.assertIn("bore_diameter_mm", row["missing_required_dimensions"])
        self.assertNotEqual(row["geometry_readiness_status"], cov.PROFILE_READY)

    def test_olet_body_rows_flag_manufacturer_context(self):
        rows = cov.geometry_profile_coverage_matrix(_READER)
        weldolet_rows = [r for r in rows if r["product_family"] == "olet" and r["subtype"] == "weldolet"]
        self.assertTrue(weldolet_rows)
        self.assertTrue(weldolet_rows[0]["manufacturer_context_required"])

    def test_undefined_profile_rows_marked_not_yet_defined(self):
        rows = cov.geometry_profile_coverage_matrix(_READER)
        coupling_rows = [r for r in rows if r["subtype"] == "coupling_sw"]
        self.assertTrue(coupling_rows)
        self.assertEqual(coupling_rows[0]["geometry_readiness_status"], cov.PROFILE_NOT_YET_DEFINED)


class TestConstructionRuleRegisterAndCompatibilityMapping(unittest.TestCase):
    def test_register_entries_have_required_fields(self):
        for entry in cov.CONSTRUCTION_RULE_REQUIREMENT_REGISTER:
            for key in ("product_family", "missing_geometric_concept", "authoritative_dimensions_available",
                        "legacy_behaviour", "future_rule_required", "blocks_geometry_generation_now"):
                self.assertIn(key, entry)

    def test_reducer_gap_is_registered_and_blocking(self):
        reducer_entries = [e for e in cov.CONSTRUCTION_RULE_REQUIREMENT_REGISTER
                            if "reducer" in e["subtype"]]
        self.assertTrue(reducer_entries)
        self.assertTrue(reducer_entries[0]["blocks_geometry_generation_now"])

    def test_compatibility_mapping_covers_pipe_flange_buttweld_olet(self):
        paths = {e["existing_geometry_path"].split(" ")[0] for e in cov.EXISTING_GEOMETRY_COMPATIBILITY_MAPPING}
        self.assertIn("pipe", paths)
        self.assertIn("flange", paths)
        self.assertIn("olet", paths)

    def test_olet_marked_not_backward_compatible(self):
        olet_entries = [e for e in cov.EXISTING_GEOMETRY_COMPATIBILITY_MAPPING
                         if e["existing_geometry_path"].startswith("olet")]
        self.assertTrue(olet_entries)
        self.assertFalse(olet_entries[0]["backward_compatible_adapter_possible"])


class TestRepresentativeScenarios(unittest.TestCase):
    """Sec.25: all 20 representative scenarios, using only real supported
    canonical values (never fabricated)."""

    def test_01_asme_b36_pipe_geometry_ready(self):
        r = _prep(product_family="pipe", standard="ASME_B36.10M", primary_size="6", schedule="Sch40")
        self.assertEqual(r.geometry_specification.readiness_status, GeometryReadinessStatus.GEOMETRY_READY)

    def test_02_fully_specified_asme_b16_5_wn_flange(self):
        r = _prep(product_family="flange", subtype="weld_neck", standard="ASME_B16.5",
                   primary_size="2", pressure_class="150")
        # Sec.3 finding: bore_diameter_mm has no ASME_B16.5 authoritative fact.
        self.assertEqual(r.geometry_specification.readiness_status,
                          GeometryReadinessStatus.UNSUPPORTED_GEOMETRY_REQUEST)
        self.assertIn("bore_diameter_mm", r.dimension_resolution.unsupported_reason)

    def test_03_flange_blocked_by_missing_authoritative_bore(self):
        rows = cov.geometry_profile_coverage_matrix(_READER)
        wn_asme = [r for r in rows if r["product_family"] == "flange" and r["subtype"] == "weld_neck"][0]
        self.assertIn("bore_diameter_mm", wn_asme["missing_required_dimensions"])
        self.assertNotEqual(wn_asme["geometry_readiness_status"], cov.PROFILE_READY)
        # JIS_B2220 (same subtype) IS ready, confirming the block is standard-specific.
        r_jis = _prep(product_family="flange", subtype="weld_neck", standard="JIS_B2220",
                       primary_size=50, jis_k="10K")
        self.assertTrue(r_jis.is_ready())

    def test_04_asme_b16_9_elbow_geometry_spec(self):
        r = _prep(product_family="buttweld_fitting", subtype="elbow_90_lr",
                   standard="ASME_B16.9", primary_size="6")
        self.assertTrue(r.is_ready())
        self.assertIn("centre_to_end_mm", r.geometry_specification.required_dimensions)

    def test_05_asme_b16_9_equal_tee_geometry_spec(self):
        r = _prep(product_family="buttweld_fitting", subtype="tee_equal",
                   standard="ASME_B16.9", primary_size="4")
        self.assertTrue(r.is_ready())
        self.assertIn("tee_run_centre_to_end_mm", r.geometry_specification.required_dimensions)
        self.assertIn("tee_branch_centre_to_end_mm", r.geometry_specification.required_dimensions)

    def test_06_asme_b16_9_reducer_profile_assessment(self):
        r = _prep(product_family="buttweld_fitting", subtype="reducer_concentric",
                   standard="ASME_B16.9", large_end_size="6", small_end_size="4")
        self.assertEqual(r.geometry_specification.readiness_status,
                          GeometryReadinessStatus.UNSUPPORTED_GEOMETRY_REQUEST)
        self.assertIn("end_to_end_mm", r.dimension_resolution.resolved_dimensions)
        self.assertIn("outside_diameter_mm", r.dimension_resolution.unsupported_reason)

    def test_07_asme_b16_9_cap_geometry_spec(self):
        r = _prep(product_family="buttweld_fitting", subtype="cap", standard="ASME_B16.9", primary_size="4")
        self.assertTrue(r.is_ready())
        self.assertIn("cap_length_standard_wall_mm", r.geometry_specification.required_dimensions)

    def test_08_socketweld_fitting_profile_assessment(self):
        r = _prep(product_family="socketweld_fitting", subtype="elbow_90_sw",
                   standard="ASME_B16.11", primary_size="2", pressure_class="3000")
        self.assertEqual(r.geometry_specification.readiness_status,
                          GeometryReadinessStatus.UNSUPPORTED_GEOMETRY_REQUEST)
        self.assertIn("outside_diameter_mm", r.dimension_resolution.unsupported_reason)
        # but socketweld_cap IS fully data-ready:
        r_cap = _prep(product_family="socketweld_fitting", subtype="cap_sw",
                       standard="ASME_B16.11", primary_size="2", pressure_class="3000")
        self.assertTrue(r_cap.is_ready())

    def test_09_mss_sp97_standard_only_manufacturer_context_required(self):
        r = _prep(product_family="olet", subtype="weldolet", standard="MSS_SP97",
                   run_size="6", branch_size="6")
        self.assertEqual(r.geometry_specification.readiness_status,
                          GeometryReadinessStatus.MANUFACTURER_CONTEXT_REQUIRED)

    def test_10_mss_sp97_with_bonney_forge_context_ready(self):
        r = _prep(product_family="olet", subtype="weldolet", standard="MSS_SP97",
                   run_size="6", branch_size="6", manufacturer_profile="Bonney Forge",
                   allow_manufacturer_specific=True)
        self.assertTrue(r.is_ready())


    def test_11_quarantined_required_dimension_blocks_readiness(self):
        r = _prep(product_family="buttweld_fitting", subtype="elbow_90_lr",
                   standard="ASME_B16.9", primary_size="8")  # NPS8 OD is quarantined
        self.assertEqual(r.geometry_specification.readiness_status,
                          GeometryReadinessStatus.ENGINEERING_DATA_QUARANTINED)

    def test_12_quarantined_unrelated_dimension_does_not_over_block(self):
        # Confirmed at the resolver level: requesting ONLY the tee run/branch
        # dims at NPS8 (excluding the quarantined outside_diameter_mm)
        # resolves cleanly RESOLVED - the quarantine is scoped to the OD
        # identity only, never propagating to an unrelated dimension at the
        # same size.
        req = EngineeringRequest(product_family="buttweld_fitting", subtype="tee_equal",
                                  standard="ASME_B16.9", primary_size="8",
                                  dimensions=["tee_run_centre_to_end_mm", "tee_branch_centre_to_end_mm"])
        spec = _RESOLVER.resolve(req)
        self.assertEqual(spec.status, ResolutionStatus.RESOLVED)
        self.assertIn("tee_run_centre_to_end_mm", spec.resolved_dimensions)
        # The FULL buttweld_tee_equal PROFILE also requires outside_diameter_mm
        # (matching legacy rules/buttweld.py's actual feature set) - so full
        # geometry-spec compilation for an NPS8 tee correctly stays blocked,
        # demonstrating scoped (not over-broad, not under-broad) quarantine.
        r_full = _prep(product_family="buttweld_fitting", subtype="tee_equal",
                        standard="ASME_B16.9", primary_size="8")
        self.assertEqual(r_full.geometry_specification.readiness_status,
                          GeometryReadinessStatus.ENGINEERING_DATA_QUARANTINED)

    def test_13_incomplete_request_fails_before_compilation(self):
        r = _prep(product_family="pipe", standard="ASME_B36.10M", schedule="Sch40")  # no size at all
        self.assertEqual(r.failed_stage, OrchestrationStage.ENGINEERING_RESOLUTION)
        self.assertEqual(r.geometry_specification.readiness_status,
                          GeometryReadinessStatus.ENGINEERING_SPEC_INCOMPLETE)

    def test_14_ambiguous_request_fails_before_compilation(self):
        r = _prep(product_family="flange", subtype="weld_neck", primary_size="2")  # no standard - 3 apply
        self.assertEqual(r.failed_stage, OrchestrationStage.ENGINEERING_RESOLUTION)
        self.assertEqual(r.geometry_specification.readiness_status,
                          GeometryReadinessStatus.ENGINEERING_SPEC_AMBIGUOUS)

    def test_15_unsupported_request_fails_before_compilation(self):
        r = _prep(product_family="pipe", standard="NOT_A_REAL_STANDARD", primary_size="6")
        self.assertEqual(r.failed_stage, OrchestrationStage.ENGINEERING_RESOLUTION)
        self.assertEqual(r.geometry_specification.readiness_status,
                          GeometryReadinessStatus.UNSUPPORTED_GEOMETRY_REQUEST)

    def test_16_single_successful_orchestration(self):
        r = _prep(product_family="buttweld_fitting", subtype="elbow_90_lr",
                   standard="ASME_B16.9", primary_size="6")
        self.assertIsNone(r.failed_stage)
        self.assertTrue(r.is_ready())

    def test_17_batch_all_ready(self):
        batch = prepare_geometry_specifications_batch([
            EngineeringRequest(product_family="pipe", standard="ASME_B36.10M", primary_size="6", schedule="Sch40"),
            EngineeringRequest(product_family="buttweld_fitting", subtype="cap",
                                standard="ASME_B16.9", primary_size="4"),
        ], resolver=_RESOLVER)
        self.assertEqual(batch.batch_status, BatchStatus.ALL_READY)

    def test_18_batch_mixed_success_failure(self):
        batch = prepare_geometry_specifications_batch([
            EngineeringRequest(product_family="pipe", standard="ASME_B36.10M", primary_size="6", schedule="Sch40"),
            EngineeringRequest(product_family="olet", subtype="weldolet", standard="MSS_SP97",
                                run_size="6", branch_size="6"),  # no mfr context
        ], resolver=_RESOLVER)
        self.assertEqual(batch.batch_status, BatchStatus.PARTIALLY_READY)

    def test_19_repeated_identical_compilation_byte_identical(self):
        r1 = _prep(product_family="buttweld_fitting", subtype="cap", standard="ASME_B16.9", primary_size="4")
        r2 = _prep(product_family="buttweld_fitting", subtype="cap", standard="ASME_B16.9", primary_size="4")
        import json
        self.assertEqual(json.dumps(r1.geometry_specification.to_dict(), sort_keys=True),
                          json.dumps(r2.geometry_specification.to_dict(), sort_keys=True))

    def test_20_controlled_dimension_mutation_changes_fingerprint(self):
        r1 = _prep(product_family="buttweld_fitting", subtype="cap", standard="ASME_B16.9", primary_size="4")
        r2 = _prep(product_family="buttweld_fitting", subtype="cap", standard="ASME_B16.9", primary_size="6")
        self.assertNotEqual(r1.geometry_specification.geometry_specification_fingerprint,
                             r2.geometry_specification.geometry_specification_fingerprint)


class TestSchemaAndProfileVersioning(unittest.TestCase):
    def test_geometry_spec_carries_schema_version(self):
        r = _prep(product_family="pipe", standard="ASME_B36.10M", primary_size="6", schedule="Sch40")
        self.assertEqual(r.geometry_specification.schema_version, GEOMETRY_SPEC_SCHEMA_VERSION)

    def test_geometry_spec_carries_profile_id_and_version(self):
        r = _prep(product_family="pipe", standard="ASME_B36.10M", primary_size="6", schedule="Sch40")
        self.assertEqual(r.geometry_specification.geometry_profile_id, "pipe")
        self.assertEqual(r.geometry_specification.geometry_profile_version, "1")


class TestTraceabilityChain(unittest.TestCase):
    def test_source_file_present_in_verification_summary(self):
        r = _prep(product_family="pipe", standard="ASME_B36.10M", primary_size="6", schedule="Sch40")
        summary = r.geometry_specification.source_verification_summary
        self.assertTrue(any("Pipes" in f for f in summary["source_files"]))

    def test_compilation_trace_documents_profile_selection(self):
        r = _prep(product_family="pipe", standard="ASME_B36.10M", primary_size="6", schedule="Sch40")
        self.assertTrue(any("profile selected" in line for line in r.geometry_specification.compilation_trace))

    def test_fingerprint_traces_back_to_data_layer_fingerprint(self):
        r = _prep(product_family="pipe", standard="ASME_B36.10M", primary_size="6", schedule="Sch40")
        self.assertEqual(r.geometry_specification.data_layer_fingerprint, _FINGERPRINT)


class TestExistingDemoUnchanged(unittest.TestCase):
    def test_demo_runs_unchanged_and_passes_determinism_check(self):
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        demo_path = os.path.join(repo_root, "examples", "demo.py")
        result = subprocess.run([sys.executable, demo_path], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("DETERMINISM CHECK", result.stdout)
        self.assertIn("PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
