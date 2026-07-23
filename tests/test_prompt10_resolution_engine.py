# -*- coding: utf-8 -*-
"""
tests/test_prompt10_resolution_engine.py
============================================
Prompt 10 Sec.30: comprehensive automated tests for the deterministic
engineering specification-resolution engine. Builds one frozen
CanonicalReader/EngineeringResolver at module scope (read-only throughout)
and exercises request/spec serialization, alias normalization, product-
family/subtype/standard/size/rating resolution, multi-size role handling,
dimension-set resolution, progressive resolution, ambiguity, quarantine
scoping, manufacturer-context handling, resolution trace, fingerprint
binding, all 20 representative scenarios, and full regression. unittest
only - no pytest.
"""
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from kgpe.contract.canonical_reader import build_canonical_reader
from kgpe.contract.snapshot import registry_fingerprint
from kgpe.resolver.request import EngineeringRequest
from kgpe.resolver.spec import ResolvedEngineeringSpecification, ResolutionStatus, ALL_RESOLUTION_STATUSES
from kgpe.resolver.engine import EngineeringResolver, resolve_engineering_request
from kgpe.resolver import aliases as A

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

_READER, _COUNTS = build_canonical_reader()
_FINGERPRINT = registry_fingerprint(_READER.registry)
_RESOLVER = EngineeringResolver(_READER, _FINGERPRINT)


def resolve(**kwargs):
    return _RESOLVER.resolve(EngineeringRequest(**kwargs))


class TestRequestModelSerialization(unittest.TestCase):
    def test_to_dict_roundtrip(self):
        req = EngineeringRequest(product_family="flange", primary_size="2", pressure_class="150")
        d = req.to_dict()
        self.assertEqual(d["product_family"], "flange")
        self.assertEqual(d["primary_size"], "2")

    def test_from_dict_rejects_unknown_field(self):
        with self.assertRaises(ValueError):
            EngineeringRequest.from_dict({"not_a_real_field": 1})

    def test_from_dict_accepts_known_fields(self):
        req = EngineeringRequest.from_dict({"product_family": "pipe", "primary_size": "6"})
        self.assertEqual(req.product_family, "pipe")

    def test_dimensions_defaults_to_empty_list_not_none_shared_mutable(self):
        r1 = EngineeringRequest()
        r2 = EngineeringRequest()
        r1.dimensions.append("x")
        self.assertEqual(r2.dimensions, [])


class TestResolvedSpecSerialization(unittest.TestCase):
    def test_to_dict_is_plain_json_serializable(self):
        import json
        spec = resolve(product_family="flange", subtype="WN", standard="ASME B16.5",
                        primary_size="2", pressure_class="150", dimensions=["flange_thickness_weld_neck_mm"])
        blob = json.dumps(spec.to_dict())
        self.assertIn("RESOLVED", blob)

    def test_is_resolved_helper(self):
        spec = resolve(product_family="pipe", standard="ASME_B36.10M", primary_size="6",
                        dimensions=["outside_diameter_mm"])
        self.assertTrue(spec.is_resolved())


class TestResolutionStatusVocabulary(unittest.TestCase):
    def test_exactly_seven_statuses(self):
        self.assertEqual(len(ALL_RESOLUTION_STATUSES), 7)

    def test_no_generic_failed_status(self):
        self.assertNotIn("FAILED", ALL_RESOLUTION_STATUSES)

    def test_expected_statuses_present(self):
        expected = {"RESOLVED", "INCOMPLETE_REQUEST", "AMBIGUOUS_REQUEST", "UNSUPPORTED_REQUEST",
                    "MALFORMED_REQUEST", "QUARANTINED_ENGINEERING_DATA", "MANUFACTURER_CONTEXT_REQUIRED"}
        self.assertEqual(set(ALL_RESOLUTION_STATUSES), expected)


class TestAliasNormalization(unittest.TestCase):
    def test_product_family_aliases(self):
        self.assertEqual(A.normalize_product_family_alias("Flange"), "flange")
        self.assertEqual(A.normalize_product_family_alias("Socket Weld"), "socketweld_fitting")

    def test_standard_aliases(self):
        self.assertEqual(A.normalize_standard_alias("ASME B16.5"), "ASME_B16.5")
        self.assertEqual(A.normalize_standard_alias("ASME_B16.5"), "ASME_B16.5")
        self.assertEqual(A.normalize_standard_alias("b16.5"), "ASME_B16.5")

    def test_subtype_alias_scoped_by_family(self):
        self.assertEqual(A.normalize_subtype_alias("WN", "flange"), "weld_neck")
        self.assertEqual(A.normalize_subtype_alias("cap", "buttweld_fitting"), "cap")
        self.assertEqual(A.normalize_subtype_alias("cap", "socketweld_fitting"), "cap_sw")

    def test_unknown_alias_raises_keyerror(self):
        with self.assertRaises(KeyError):
            A.normalize_standard_alias("NOT_A_REAL_STANDARD")
        with self.assertRaises(KeyError):
            A.normalize_product_family_alias("widget")

    def test_unknown_alias_rejected_end_to_end(self):
        spec = resolve(product_family="flange", standard="TOTALLY_MADE_UP_STANDARD", primary_size="2",
                        dimensions=["outside_diameter_mm"])
        self.assertEqual(spec.status, ResolutionStatus.UNSUPPORTED_REQUEST)
        self.assertIn("Unknown standard alias", spec.unsupported_reason)


class TestProductFamilyResolution(unittest.TestCase):
    def test_missing_product_family_is_incomplete(self):
        spec = resolve(standard="ASME B16.5", primary_size="2")
        self.assertEqual(spec.status, ResolutionStatus.INCOMPLETE_REQUEST)
        self.assertIn("product_family", spec.missing_criteria)

    def test_unknown_product_family_is_unsupported(self):
        spec = resolve(product_family="widget", primary_size="2")
        self.assertEqual(spec.status, ResolutionStatus.UNSUPPORTED_REQUEST)


class TestSubtypeResolution(unittest.TestCase):
    def test_canonical_subtype_passthrough(self):
        spec = resolve(product_family="buttweld", standard="ASME B16.9", subtype="elbow_90_lr",
                        primary_size="6", dimensions=["centre_to_end_mm"])
        self.assertEqual(spec.subtype, "elbow_90_lr")
        self.assertEqual(spec.status, ResolutionStatus.RESOLVED)

    def test_unknown_subtype_alias_is_unsupported(self):
        spec = resolve(product_family="buttweld", standard="ASME B16.9", subtype="not_a_real_fitting",
                        primary_size="6", dimensions=["centre_to_end_mm"])
        self.assertEqual(spec.status, ResolutionStatus.UNSUPPORTED_REQUEST)


class TestStandardResolution(unittest.TestCase):
    def test_standard_inferred_when_unique(self):
        spec = resolve(product_family="buttweld", subtype="elbow_90_lr", primary_size="6",
                        dimensions=["centre_to_end_mm"])
        self.assertEqual(spec.status, ResolutionStatus.RESOLVED)
        self.assertEqual(spec.standard, "ASME_B16.9")

    def test_standard_ambiguous_when_multiple(self):
        spec = resolve(product_family="flange", primary_size="2", pressure_class="150")
        self.assertEqual(spec.status, ResolutionStatus.AMBIGUOUS_REQUEST)
        self.assertIn("standard", spec.ambiguous_candidates)
        # KAFCO_NIPOFLANGE added post-Prompt-9: NPS "2" Class 150 also
        # matches KAFCO's own Nipoflange catalog data (BranchNPS 1/2"-2",
        # ANSI 150#-2500#) - a real fourth candidate standard, not a defect.
        self.assertEqual(set(spec.ambiguous_candidates["standard"]),
                          {"ASME_B16.5", "JIS_B2220", "EN_1092-1", "KAFCO_NIPOFLANGE"})

    def test_standard_never_defaults_to_asme(self):
        spec = resolve(product_family="flange", primary_size="2")
        self.assertNotEqual(spec.standard, "ASME_B16.5")

    def test_unsupported_standard_for_family(self):
        spec = resolve(product_family="flange", standard="ASME B16.9", primary_size="2")
        self.assertEqual(spec.status, ResolutionStatus.UNSUPPORTED_REQUEST)


class TestSizeSystemResolution(unittest.TestCase):
    def test_size_system_inferred_for_asme(self):
        spec = resolve(product_family="pipe", standard="ASME_B36.10M", primary_size="6",
                        dimensions=["outside_diameter_mm"])
        self.assertEqual(spec.size_system, "nps")
        self.assertEqual(spec.sizes, {"nps": "6"})

    def test_size_system_inferred_for_en(self):
        spec = resolve(product_family="flange", standard="EN 1092-1", primary_size="50", pn="PN16",
                        dimensions=["outside_diameter_mm"])
        self.assertEqual(spec.size_system, "dn")
        self.assertEqual(spec.sizes, {"dn": "DN50"})

    def test_size_system_inferred_for_jis(self):
        spec = resolve(product_family="flange", standard="JIS B2220", primary_size="50", jis_k="10K",
                        dimensions=["outside_diameter_mm"])
        self.assertEqual(spec.size_system, "jis_size")
        self.assertEqual(spec.sizes, {"jis_size": "50A"})

    def test_malformed_size_value(self):
        spec = resolve(product_family="pipe", standard="ASME_B36.10M", primary_size="not-a-size",
                        dimensions=["outside_diameter_mm"])
        self.assertEqual(spec.status, ResolutionStatus.MALFORMED_REQUEST)

    def test_missing_size_is_incomplete(self):
        spec = resolve(product_family="pipe", standard="ASME_B36.10M", dimensions=["outside_diameter_mm"])
        self.assertEqual(spec.status, ResolutionStatus.INCOMPLETE_REQUEST)


class TestRatingSystemResolution(unittest.TestCase):
    def test_missing_rating_returns_incomplete_with_options(self):
        spec = resolve(product_family="flange", subtype="WN", standard="ASME B16.5", primary_size="2",
                        dimensions=["flange_thickness_weld_neck_mm"])
        self.assertEqual(spec.status, ResolutionStatus.INCOMPLETE_REQUEST)
        self.assertIn("class_key", spec.missing_criteria)
        self.assertTrue(spec.available_options["class_key"])

    def test_wrong_rating_field_ignored_with_warning(self):
        spec = resolve(product_family="flange", subtype="WN", standard="ASME B16.5", primary_size="2",
                        pn="PN16", dimensions=["flange_thickness_weld_neck_mm"])
        self.assertTrue(any("does not apply" in w for w in spec.warnings))

    def test_no_generic_bare_number_interpreted_without_context(self):
        spec = resolve(product_family="flange", subtype="WN", standard="ASME B16.5", primary_size="2",
                        pn="150", dimensions=["flange_thickness_weld_neck_mm"])
        self.assertEqual(spec.status, ResolutionStatus.INCOMPLETE_REQUEST)


class TestMultiSizeResolution(unittest.TestCase):
    def test_reducer_roles_preserved_independently(self):
        spec = resolve(product_family="buttweld", standard="ASME B16.9", subtype="reducer_concentric",
                        large_end_size="6", small_end_size="4", dimensions=["end_to_end_mm"])
        self.assertEqual(spec.sizes, {"large_end_nps": "6", "small_end_nps": "4"})

    def test_reversed_reducer_pair_rejected(self):
        spec = resolve(product_family="buttweld", standard="ASME B16.9", subtype="reducer_concentric",
                        large_end_size="4", small_end_size="6", dimensions=["end_to_end_mm"])
        self.assertEqual(spec.status, ResolutionStatus.MALFORMED_REQUEST)
        self.assertTrue(any("Reversed reducer pair" in w for w in spec.warnings))

    def test_6x4_not_treated_as_4x6(self):
        a = resolve(product_family="buttweld", standard="ASME B16.9", subtype="reducer_concentric",
                     large_end_size="6", small_end_size="4", dimensions=["end_to_end_mm"])
        self.assertEqual(a.status, ResolutionStatus.RESOLVED)
        self.assertNotEqual(a.sizes.get("large_end_nps"), "4")

    def test_branch_run_roles_preserved(self):
        spec = resolve(product_family="olet", standard="MSS SP-97", subtype="weldolet_reducing",
                        run_size="6", schedule="STD", dimensions=["branch_outlet_height_mm"])
        self.assertEqual(spec.sizes, {"run_nps": "6"})


class TestDimensionSetResolution(unittest.TestCase):
    def test_explicit_dimension_resolution(self):
        spec = resolve(product_family="pipe", standard="ASME_B36.10M", primary_size="6", schedule="Sch40",
                        dimensions=["wall_thickness_mm"])
        self.assertEqual(spec.status, ResolutionStatus.RESOLVED)
        self.assertIn("wall_thickness_mm", spec.resolved_dimensions)

    def test_available_dimension_discovery_excludes_quarantined_and_manufacturer(self):
        spec = resolve(product_family="olet", standard="MSS SP-97", subtype="sockolet", branch_size="2")
        self.assertEqual(spec.status, ResolutionStatus.RESOLVED)
        self.assertNotIn("olet_height_mm", spec.available_dimensions)

    def test_available_dimension_discovery_includes_with_manufacturer_optin(self):
        spec = resolve(product_family="olet", standard="MSS SP-97", subtype="sockolet", branch_size="2",
                        allow_manufacturer_specific=True)
        self.assertIn("olet_height_mm", spec.available_dimensions)

    def test_asme_b16_11_available_dimensions_never_include_od(self):
        spec = resolve(product_family="socketweld", standard="ASME B16.11", subtype="elbow_90_sw", primary_size="2")
        self.assertNotIn("outside_diameter_mm", spec.available_dimensions)


class TestObjectVsDimensionCompleteness(unittest.TestCase):
    def test_pipe_od_does_not_require_schedule(self):
        spec = resolve(product_family="pipe", standard="ASME_B36.10M", primary_size="6",
                        dimensions=["outside_diameter_mm"])
        self.assertEqual(spec.status, ResolutionStatus.RESOLVED)

    def test_pipe_wall_thickness_requires_schedule(self):
        spec = resolve(product_family="pipe", standard="ASME_B36.10M", primary_size="6",
                        dimensions=["wall_thickness_mm"])
        self.assertEqual(spec.status, ResolutionStatus.INCOMPLETE_REQUEST)


class TestProgressiveResolution(unittest.TestCase):
    def test_incomplete_reports_missing_and_options_together(self):
        spec = resolve(product_family="pipe", standard="ASME_B36.10M", primary_size="6",
                        dimensions=["wall_thickness_mm"])
        self.assertEqual(spec.missing_criteria, ["schedule"])
        self.assertIn("SCH40", spec.available_options["schedule"])

    def test_partial_normalization_preserved_in_incomplete_result(self):
        spec = resolve(product_family="flange", subtype="WN", standard="ASME B16.5", primary_size="2",
                        dimensions=["flange_thickness_weld_neck_mm"])
        self.assertEqual(spec.product_family, "flange")
        self.assertEqual(spec.standard, "ASME_B16.5")
        self.assertEqual(spec.sizes, {"nps": "2"})


class TestAmbiguityHandling(unittest.TestCase):
    def test_ambiguous_never_picks_first(self):
        spec = resolve(product_family="flange", primary_size="2", pressure_class="150")
        self.assertEqual(spec.status, ResolutionStatus.AMBIGUOUS_REQUEST)
        self.assertIsNone(spec.standard)
        self.assertGreater(len(spec.ambiguous_candidates.get("standard", [])), 1)

    def test_ambiguity_distinct_from_incomplete(self):
        ambiguous = resolve(product_family="flange", primary_size="2", pressure_class="150")
        incomplete = resolve(product_family="pipe", standard="ASME_B36.10M", primary_size="6",
                              dimensions=["wall_thickness_mm"])
        self.assertEqual(ambiguous.status, ResolutionStatus.AMBIGUOUS_REQUEST)
        self.assertEqual(incomplete.status, ResolutionStatus.INCOMPLETE_REQUEST)


class TestQuarantineBehaviour(unittest.TestCase):
    def test_quarantined_dimension_blocked(self):
        spec = resolve(product_family="buttweld", standard="ASME B16.9", primary_size="8",
                        dimensions=["outside_diameter_mm"])
        self.assertEqual(spec.status, ResolutionStatus.QUARANTINED_ENGINEERING_DATA)
        self.assertEqual(len(spec.quarantine_details), 2)
        self.assertTrue(all(d["conflict_id"] == "CONFLICT-ASME_B16.9-outside_diameter_mm-NPS8"
                             for d in spec.quarantine_details))

    def test_scoped_quarantine_does_not_block_neighboring_dimension(self):
        spec = resolve(product_family="buttweld", standard="ASME B16.9", subtype="elbow_90_lr", primary_size="8",
                        dimensions=["centre_to_end_mm"])
        self.assertEqual(spec.status, ResolutionStatus.RESOLVED)

    def test_scoped_quarantine_does_not_block_neighboring_nps(self):
        spec = resolve(product_family="buttweld", standard="ASME B16.9", primary_size="6",
                        dimensions=["outside_diameter_mm"])
        self.assertEqual(spec.status, ResolutionStatus.RESOLVED)

    def test_quarantine_and_unrelated_dimension_together(self):
        spec = resolve(product_family="buttweld", standard="ASME B16.9", subtype="elbow_90_lr", primary_size="8",
                        dimensions=["outside_diameter_mm", "centre_to_end_mm"])
        self.assertEqual(spec.status, ResolutionStatus.QUARANTINED_ENGINEERING_DATA)
        self.assertIn("centre_to_end_mm", spec.resolved_dimensions)

    def test_en_10253_quarantine(self):
        spec = resolve(product_family="buttweld", standard="EN 10253", size_system="dn", primary_size="450",
                        dimensions=["outside_diameter_mm"])
        self.assertEqual(spec.status, ResolutionStatus.QUARANTINED_ENGINEERING_DATA)


class TestManufacturerSpecificBehaviour(unittest.TestCase):
    def test_context_required_without_profile(self):
        spec = resolve(product_family="olet", standard="MSS SP-97", subtype="sockolet", branch_size="2",
                        dimensions=["olet_height_mm"])
        self.assertEqual(spec.status, ResolutionStatus.MANUFACTURER_CONTEXT_REQUIRED)
        self.assertEqual(spec.available_manufacturer_profiles, ["Bonney Forge"])

    def test_valid_manufacturer_context_resolves(self):
        spec = resolve(product_family="olet", standard="MSS SP-97", subtype="sockolet", branch_size="2",
                        manufacturer_profile="Bonney Forge", dimensions=["olet_height_mm"])
        self.assertEqual(spec.status, ResolutionStatus.RESOLVED)
        self.assertEqual(spec.resolved_dimensions["olet_height_mm"]["verification_status"],
                          "VERIFIED_MANUFACTURER_SPECIFIC")

    def test_invalid_manufacturer_profile_no_match(self):
        spec = resolve(product_family="olet", standard="MSS SP-97", subtype="sockolet", branch_size="2",
                        manufacturer_profile="Not A Real Manufacturer", dimensions=["olet_height_mm"])
        self.assertIn(spec.status, (ResolutionStatus.UNSUPPORTED_REQUEST, ResolutionStatus.MANUFACTURER_CONTEXT_REQUIRED))
        self.assertNotIn("olet_height_mm", spec.resolved_dimensions)

    def test_never_silently_defaults_to_bonney_forge(self):
        spec = resolve(product_family="olet", standard="MSS SP-97", subtype="sockolet", branch_size="2",
                        dimensions=["olet_height_mm"])
        self.assertNotEqual(spec.status, ResolutionStatus.RESOLVED)


class TestResolutionTrace(unittest.TestCase):
    def test_trace_is_nonempty_and_json_safe(self):
        import json
        spec = resolve(product_family="flange", subtype="WN", standard="ASME B16.5", primary_size="2",
                        pressure_class="150", dimensions=["flange_thickness_weld_neck_mm"])
        self.assertTrue(spec.trace)
        json.dumps(spec.trace)

    def test_trace_has_no_timestamps(self):
        spec = resolve(product_family="pipe", standard="ASME_B36.10M", primary_size="6",
                        dimensions=["outside_diameter_mm"])
        for line in spec.trace:
            self.assertNotIn("202", line)


class TestFingerprintBinding(unittest.TestCase):
    def test_every_resolution_carries_current_fingerprint(self):
        spec = resolve(product_family="pipe", standard="ASME_B36.10M", primary_size="6",
                        dimensions=["outside_diameter_mm"])
        self.assertEqual(spec.data_layer_fingerprint, _FINGERPRINT)

    def test_fingerprint_present_even_on_failure_paths(self):
        spec = resolve(product_family="widget")
        self.assertEqual(spec.data_layer_fingerprint, _FINGERPRINT)


class TestNoDirectAdapterDependency(unittest.TestCase):
    def test_resolver_module_does_not_import_adapters_or_dimension_library(self):
        # Checks actual IMPORT STATEMENTS only - engine.py's own docstring
        # legitimately explains "no dimension_library.py lookup" as
        # documentation of this very constraint, which must not itself
        # trip the check (same false-positive class as Prompt 9's
        # "nipoflange mentioned in a docstring" finding).
        for fn in ("request.py", "spec.py", "aliases.py", "engine.py", "__init__.py"):
            path = os.path.join(_ROOT, "kgpe", "resolver", fn)
            with open(path, "r", encoding="utf-8") as fh:
                lines = fh.readlines()
            for line in lines:
                s = line.strip()
                if s.startswith("import ") or s.startswith("from "):
                    self.assertNotIn("adapters", s, f"{path}: {s!r}")
                    self.assertNotIn("dimension_library", s, f"{path}: {s!r}")
                self.assertFalse(s.startswith("import json"), f"{path}: {s!r}")
            self.assertNotIn("AI-Readable", "".join(lines))


class TestRepresentativeScenarios(unittest.TestCase):
    """Sec.29: all 20 representative resolution scenarios, against real
    source-supported combinations only - no fabricated values."""

    def test_01_fully_specified_asme_b16_5_wn_flange(self):
        spec = resolve(product_family="flange", subtype="WN", standard="ASME B16.5", primary_size="2",
                        pressure_class="150", dimensions=["flange_thickness_weld_neck_mm"])
        self.assertEqual(spec.status, ResolutionStatus.RESOLVED)
        self.assertAlmostEqual(spec.resolved_dimensions["flange_thickness_weld_neck_mm"]["value"], 17.53)

    def test_02_flange_missing_pressure_class(self):
        spec = resolve(product_family="flange", subtype="WN", standard="ASME B16.5", primary_size="2",
                        dimensions=["flange_thickness_weld_neck_mm"])
        self.assertEqual(spec.status, ResolutionStatus.INCOMPLETE_REQUEST)

    def test_03_pipe_od_schedule_not_required(self):
        spec = resolve(product_family="pipe", standard="ASME_B36.10M", primary_size="6",
                        dimensions=["outside_diameter_mm"])
        self.assertEqual(spec.status, ResolutionStatus.RESOLVED)

    def test_04_pipe_wall_thickness_missing_schedule(self):
        spec = resolve(product_family="pipe", standard="ASME_B36.10M", primary_size="6",
                        dimensions=["wall_thickness_mm"])
        self.assertEqual(spec.status, ResolutionStatus.INCOMPLETE_REQUEST)

    def test_05_fully_specified_pipe_wall_thickness(self):
        spec = resolve(product_family="pipe", standard="ASME_B36.10M", primary_size="6", schedule="Sch40",
                        dimensions=["wall_thickness_mm"])
        self.assertEqual(spec.status, ResolutionStatus.RESOLVED)
        self.assertAlmostEqual(spec.resolved_dimensions["wall_thickness_mm"]["value"], 7.11)

    def test_06_jis_flange_with_k_rating(self):
        spec = resolve(product_family="flange", standard="JIS B2220", primary_size="50", jis_k="10K",
                        dimensions=["outside_diameter_mm"])
        self.assertEqual(spec.status, ResolutionStatus.RESOLVED)

    def test_07_en_flange_with_pn(self):
        spec = resolve(product_family="flange", standard="EN 1092-1", primary_size="50", pn="PN16",
                        dimensions=["outside_diameter_mm"])
        self.assertEqual(spec.status, ResolutionStatus.RESOLVED)

    def test_08_asme_b16_9_elbow(self):
        spec = resolve(product_family="buttweld", standard="ASME B16.9", subtype="ELBOW 90", primary_size="6",
                        dimensions=["outside_diameter_mm", "centre_to_end_mm"])
        self.assertEqual(spec.status, ResolutionStatus.RESOLVED)

    def test_09_asme_b16_9_reducer_large_small(self):
        spec = resolve(product_family="buttweld", standard="ASME B16.9", subtype="REDUCER",
                        large_end_size="6", small_end_size="4", dimensions=["end_to_end_mm"])
        self.assertEqual(spec.status, ResolutionStatus.RESOLVED)

    def test_10_reversed_reducer_pair(self):
        spec = resolve(product_family="buttweld", standard="ASME B16.9", subtype="REDUCER",
                        large_end_size="4", small_end_size="6", dimensions=["end_to_end_mm"])
        self.assertEqual(spec.status, ResolutionStatus.MALFORMED_REQUEST)

    def test_11_mss_sp97_official_branch_height(self):
        spec = resolve(product_family="olet", standard="MSS SP-97", subtype="WELDOLET REDUCING",
                        run_size="6", schedule="STD", dimensions=["branch_outlet_height_mm"])
        self.assertEqual(spec.status, ResolutionStatus.RESOLVED)

    def test_12_mss_sp97_manufacturer_dim_no_context(self):
        spec = resolve(product_family="olet", standard="MSS SP-97", subtype="SOCKOLET",
                        branch_size="2", dimensions=["olet_height_mm"])
        self.assertEqual(spec.status, ResolutionStatus.MANUFACTURER_CONTEXT_REQUIRED)

    def test_13_mss_sp97_manufacturer_dim_with_bonney_forge(self):
        spec = resolve(product_family="olet", standard="MSS SP-97", subtype="SOCKOLET",
                        branch_size="2", manufacturer_profile="Bonney Forge", dimensions=["olet_height_mm"])
        self.assertEqual(spec.status, ResolutionStatus.RESOLVED)

    def test_14_unsupported_standard_product_combination(self):
        spec = resolve(product_family="flange", standard="ASME B16.9", primary_size="2",
                        dimensions=["outside_diameter_mm"])
        self.assertEqual(spec.status, ResolutionStatus.UNSUPPORTED_REQUEST)

    def test_15_ambiguous_omitted_standard(self):
        spec = resolve(product_family="flange", primary_size="2", pressure_class="150",
                        dimensions=["outside_diameter_mm"])
        self.assertEqual(spec.status, ResolutionStatus.AMBIGUOUS_REQUEST)

    def test_16_quarantined_asme_b16_9_od(self):
        spec = resolve(product_family="buttweld", standard="ASME B16.9", primary_size="8",
                        dimensions=["outside_diameter_mm"])
        self.assertEqual(spec.status, ResolutionStatus.QUARANTINED_ENGINEERING_DATA)

    def test_17_neighboring_non_quarantined_dimension(self):
        spec = resolve(product_family="buttweld", standard="ASME B16.9", subtype="ELBOW 90", primary_size="8",
                        dimensions=["centre_to_end_mm"])
        self.assertEqual(spec.status, ResolutionStatus.RESOLVED)

    def test_18_quarantined_en_10253_dimension(self):
        spec = resolve(product_family="buttweld", standard="EN 10253", size_system="dn", primary_size="450",
                        dimensions=["outside_diameter_mm"])
        self.assertEqual(spec.status, ResolutionStatus.QUARANTINED_ENGINEERING_DATA)

    def test_19_unknown_alias(self):
        spec = resolve(product_family="flange", standard="TOTALLY_MADE_UP_STANDARD", primary_size="2",
                        dimensions=["outside_diameter_mm"])
        self.assertEqual(spec.status, ResolutionStatus.UNSUPPORTED_REQUEST)

    def test_20_deterministic_repeated_resolution(self):
        req = EngineeringRequest(product_family="flange", subtype="WN", standard="ASME B16.5", primary_size="2",
                                  pressure_class="150", dimensions=["flange_thickness_weld_neck_mm"])
        a = resolve_engineering_request(req, resolver=_RESOLVER)
        b = resolve_engineering_request(req, resolver=_RESOLVER)
        self.assertEqual(a.to_dict(), b.to_dict())


class TestPublicEntryPoint(unittest.TestCase):
    def test_resolve_engineering_request_builds_fresh_reader_when_none_given(self):
        spec = resolve_engineering_request(EngineeringRequest(
            product_family="pipe", standard="ASME_B36.10M", primary_size="6", dimensions=["outside_diameter_mm"]))
        self.assertEqual(spec.status, ResolutionStatus.RESOLVED)
        self.assertEqual(spec.data_layer_fingerprint, _FINGERPRINT)

    def test_malformed_request_type_does_not_raise(self):
        spec = resolve_engineering_request({"product_family": "flange"}, resolver=_RESOLVER)
        self.assertEqual(spec.status, ResolutionStatus.MALFORMED_REQUEST)

    def test_malformed_dimensions_type_does_not_raise(self):
        spec = _RESOLVER.resolve(EngineeringRequest(product_family="pipe", standard="ASME_B36.10M",
                                                     primary_size="6", dimensions="not_a_list"))
        self.assertEqual(spec.status, ResolutionStatus.MALFORMED_REQUEST)


class TestExistingDemoUnchanged(unittest.TestCase):
    def test_demo_runs_and_determinism_check_passes(self):
        demo_path = os.path.join(_ROOT, "examples", "demo.py")
        result = subprocess.run([sys.executable, demo_path], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DETERMINISM CHECK", result.stdout)
        self.assertIn("PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
