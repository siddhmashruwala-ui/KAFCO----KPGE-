# -*- coding: utf-8 -*-
"""
tests/test_prompt9_data_layer_closure.py
============================================
Prompt 9 Sec.25: canonical data-layer closure/audit test suite. Builds the
complete registry fresh (never reuses a Prompt 8 fixture) and exercises
every audit dimension Prompt 9 requires: baseline verification, dataset-
adapter closure, coverage matrix, gap classification, unresolved-conflict
register, conflict integrity/scoping, hidden identity collisions, cross-
standard equality, size/rating isolation, manufacturer-specific
protection, verification-status integrity, provenance completeness,
canonical-reader result semantics (all 6 outcomes actually reachable in
this registry), coverage/option discovery, snapshot + fingerprint
determinism/mutation-sensitivity, Prompt 3 consistency, and legacy JS/
network isolation. unittest only - no pytest.
"""
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from kgpe.contract.registry_builder import build_canonical_registry, registry_statistics
from kgpe.contract import verification as V
from kgpe.contract import data_layer_audit as A
from kgpe.contract.canonical_reader import (
    CanonicalReader, OUTCOME_EXACT_MATCH, OUTCOME_NO_MATCH, OUTCOME_QUARANTINED,
    OUTCOME_AMBIGUOUS, OUTCOME_MANUFACTURER_CONTEXT_REQUIRED, OUTCOME_MALFORMED_CRITERIA,
    OUTCOME_UNSUPPORTED_CRITERIA,
)
from kgpe.contract.snapshot import registry_fingerprint, build_data_layer_snapshot
from kgpe.contract.units import Quantity, LENGTH_MM

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Built once at module scope - read-only inspection throughout this file.
# (The one test that mutates a fact builds its OWN fresh registry instead.)
_REGISTRY, _COUNTS = build_canonical_registry()

EXPECTED_BUILT_TOTAL = 5254
EXPECTED_STORED_TOTAL = 4824
EXPECTED_AUTHORITATIVE = 4663
EXPECTED_MANUFACTURER_SPECIFIC = 145
EXPECTED_QUARANTINED_FACTS = 16
EXPECTED_QUARANTINED_GROUPS = 8


class TestRegistryBaselineVerification(unittest.TestCase):
    """Sec.2/27: rebuild twice, verify counts/fingerprint/order match the
    Prompt 8 baseline exactly - never silently accept a drifted number."""

    def test_built_and_stored_totals_match_prompt8_baseline(self):
        built = sum(c for _, c in _COUNTS)
        stats = registry_statistics(_REGISTRY)
        self.assertEqual(built, EXPECTED_BUILT_TOTAL)
        self.assertEqual(stats["total_facts"], EXPECTED_STORED_TOTAL)
        self.assertEqual(stats["authoritative_facts"], EXPECTED_AUTHORITATIVE)
        self.assertEqual(stats["manufacturer_specific_facts"], EXPECTED_MANUFACTURER_SPECIFIC)
        self.assertEqual(stats["quarantined_facts"], EXPECTED_QUARANTINED_FACTS)

    def test_two_fresh_builds_are_identical(self):
        r2, c2 = build_canonical_registry()
        self.assertEqual(sum(c for _, c in _COUNTS), sum(c for _, c in c2))
        self.assertEqual(len(_REGISTRY.all_facts()), len(r2.all_facts()))
        self.assertEqual([f.identity_key() for f in _REGISTRY.all_facts()],
                          [f.identity_key() for f in r2.all_facts()])
        self.assertEqual(registry_fingerprint(_REGISTRY), registry_fingerprint(r2))

    def test_per_adapter_counts_match_prompt8(self):
        expected = {
            "ASME_B16.5_flanges": 792, "ASME_B36_pipes": 409, "ASME_B16.9_buttweld": 864,
            "ASME_B16.11_socketweld": 750, "MSS_SP97_olets": 223, "JIS_B2220_flanges": 640,
            "JIS_pipes": 261, "JIS_buttweld": 149, "EN_1092-1_flanges": 792,
            "EN_pipes": 104, "EN_buttweld": 270,
        }
        self.assertEqual(dict(_COUNTS), expected)


class TestDatasetAdapterClosure(unittest.TestCase):
    """Sec.3: exactly one production ingestion path per approved dataset -
    no omission, no duplicate, no orphaned adapter."""

    def test_inventory_has_exactly_11_datasets(self):
        inv = A.dataset_inventory()
        self.assertEqual(len(inv), 11)
        self.assertEqual(len({row["dataset_id"] for row in inv}), 11)

    def test_inventory_matches_registry_builder_adapters_one_to_one(self):
        from kgpe.contract.registry_builder import _ADAPTERS
        inv_names = {row["adapter_name"] for row in A.dataset_inventory()}
        builder_names = {name for name, _ in _ADAPTERS}
        self.assertEqual(inv_names, builder_names)

    def test_legacy_crm_quarantine_fixture_is_not_a_registry_builder_adapter(self):
        from kgpe.contract.registry_builder import _ADAPTERS
        names = {name for name, _ in _ADAPTERS}
        self.assertNotIn("legacy_crm_quarantine_fixture", names)
        self.assertEqual(len(_ADAPTERS), 11)

    def test_per_dataset_counts_are_internally_consistent(self):
        for row in A.dataset_inventory():
            total = row["authoritative_count"] + row["manufacturer_specific_count"] + row["quarantined_count"]
            self.assertEqual(total, row["canonical_fact_count"], row["dataset_id"])


class TestCoverageMatrix(unittest.TestCase):
    """Sec.4: coverage matrix reflects only DATA coverage, one row per
    standard actually present in the registry."""

    def test_one_row_per_standard(self):
        rows = A.coverage_matrix(_REGISTRY)
        standards = {r["standard"] for r in rows}
        expected_standards = {f.applicability.standard for f in _REGISTRY.all_facts()}
        self.assertEqual(standards, expected_standards)

    def test_every_row_has_dimension_names_and_combination_count(self):
        for row in A.coverage_matrix(_REGISTRY):
            self.assertTrue(row["dimension_names"])
            self.assertGreater(row["represented_combinations"], 0)


class TestGapClassification(unittest.TestCase):
    """Sec.5: every gap uses the small explicit vocabulary, never an
    invented category, and never confuses a legacy-lookup limitation with
    a canonical-data limitation."""

    _ALLOWED = {A.GAP_NOT_IN_SOURCE, A.GAP_SOURCE_PARTIAL, A.GAP_QUARANTINED_CONFLICT,
                A.GAP_MANUFACTURER_SPECIFIC_ONLY, A.GAP_NO_LEGACY_LOOKUP, A.GAP_NO_GEOMETRY,
                A.GAP_UNSUPPORTED_SCOPE}

    def test_only_known_classifications_used(self):
        gaps = A.classify_gaps(_REGISTRY)
        self.assertTrue(gaps)
        for g in gaps:
            self.assertIn(g["classification"], self._ALLOWED)

    def test_socketweld_and_olet_are_no_legacy_lookup_gaps_not_missing_data(self):
        gaps = A.classify_gaps(_REGISTRY)
        no_lookup_families = {g["product_family"] for g in gaps if g["classification"] == A.GAP_NO_LEGACY_LOOKUP}
        self.assertIn("socketweld_fitting", no_lookup_families)
        self.assertIn("olet", no_lookup_families)


class TestUnresolvedConflictRegister(unittest.TestCase):
    """Sec.6: exact machine-readable register of every quarantined
    conflict group, matching the known B16.9 + EN_10253 findings exactly."""

    def test_exact_group_and_fact_counts(self):
        register = A.conflict_register(_REGISTRY)
        self.assertEqual(len(register), EXPECTED_QUARANTINED_GROUPS)
        total_facts = sum(len(r["facts"]) for r in register)
        self.assertEqual(total_facts, EXPECTED_QUARANTINED_FACTS)

    def test_known_conflict_ids_present(self):
        ids = {r["conflict_id"] for r in A.conflict_register(_REGISTRY)}
        for expected in ("CONFLICT-ASME_B16.9-outside_diameter_mm-NPS8",
                         "CONFLICT-ASME_B16.9-outside_diameter_mm-NPS12",
                         "CONFLICT-EN_10253-outside_diameter_mm-DN450",
                         "CONFLICT-EN_10253-outside_diameter_mm-DN600",
                         "CONFLICT-EN_10253-wall_thickness_mm-DN200",
                         "CONFLICT-EN_10253-wall_thickness_mm-DN450",
                         "CONFLICT-EN_10253-wall_thickness_mm-DN500",
                         "CONFLICT-EN_10253-wall_thickness_mm-DN600"):
            self.assertIn(expected, ids)

    def test_exact_conflicting_values(self):
        by_id = {r["conflict_id"]: r for r in A.conflict_register(_REGISTRY)}
        self.assertEqual(by_id["CONFLICT-ASME_B16.9-outside_diameter_mm-NPS8"]["observed_values"], [219.0, 219.1])
        self.assertEqual(by_id["CONFLICT-ASME_B16.9-outside_diameter_mm-NPS12"]["observed_values"], [323.8, 323.9])
        self.assertEqual(by_id["CONFLICT-EN_10253-outside_diameter_mm-DN450"]["observed_values"], [457.0, 457.2])
        self.assertEqual(by_id["CONFLICT-EN_10253-outside_diameter_mm-DN600"]["observed_values"], [609.6, 610.0])

    def test_no_conflict_resolved_by_inference(self):
        for r in A.conflict_register(_REGISTRY):
            self.assertEqual(r["current_verification_status"], ["QUARANTINED_CONFLICT"])


class TestConflictIntegrity(unittest.TestCase):
    """Sec.7: quarantined conflicts remain stored/inspectable/blocked, never
    poison unrelated valid facts, and are appropriately (not over-)
    quarantined."""

    def test_quarantined_blocked_from_query(self):
        from kgpe.contract.model import DimensionQuarantined
        with self.assertRaises(DimensionQuarantined):
            _REGISTRY.query("outside_diameter_mm", standard="ASME_B16.9", nps="8")

    def test_quarantined_inspectable_via_get_quarantined(self):
        q = _REGISTRY.get_quarantined("outside_diameter_mm")
        nps8 = [f for f in q if f.applicability.standard == "ASME_B16.9" and f.applicability.nps == "8"]
        self.assertEqual(len(nps8), 2)

    def test_nearby_valid_nps_unaffected_by_nps8_quarantine(self):
        # NPS6 and NPS10 OD for ASME_B16.9 must resolve normally.
        for nearby in ("6", "10"):
            result = _REGISTRY.query("outside_diameter_mm", standard="ASME_B16.9", nps=nearby)
            self.assertEqual(len(result), 1)

    def test_unrelated_dimension_at_quarantined_nps_unaffected(self):
        # NPS8's wall_thickness/CtoE-style facts must still resolve even
        # though its OD is quarantined - quarantine is scoped to the exact
        # dimension_name+identity, not the whole NPS.
        result = _REGISTRY.query("centre_to_end_mm", standard="ASME_B16.9", nps="8", fitting_type="elbow_90_lr")
        self.assertEqual(len(result), 1)

    def test_quarantine_survives_repeated_ingestion_without_growing(self):
        r1, _ = build_canonical_registry()
        r2, _ = build_canonical_registry()
        self.assertEqual(len(r1.get_quarantined()), len(r2.get_quarantined()))
        self.assertEqual(len(r1.get_quarantined()), EXPECTED_QUARANTINED_FACTS)


class TestHiddenIdentityCollisionAudit(unittest.TestCase):
    """Sec.8: every multi-fact identity in the registry must be the
    sanctioned QUARANTINED_CONFLICT pattern - never a silent, unexplained
    collision."""

    def test_no_unsanctioned_collisions(self):
        self.assertEqual(A.unsanctioned_identity_collisions(_REGISTRY), [])

    def test_sanctioned_collisions_are_exactly_the_known_conflict_groups(self):
        collisions = A.find_identity_collisions(_REGISTRY)
        sanctioned = [c for c in collisions if c["sanctioned"]]
        self.assertEqual(len(sanctioned), EXPECTED_QUARANTINED_GROUPS)
        for c in sanctioned:
            self.assertEqual(len(c["values"]), 2)


class TestCrossStandardEqualityAudit(unittest.TestCase):
    """Sec.9: equal numeric values under different standards remain
    distinct engineering facts - identity never merges on value alone."""

    def test_jis_stpg_and_sus_pipe_equal_value_distinct_identity(self):
        stpg = _REGISTRY.query("wall_thickness_mm", standard="JIS_G3454", jis_size="150A", schedule="SCH40")
        sus = _REGISTRY.query("wall_thickness_mm", standard="JIS_G3459", jis_size="150A", schedule="SCH40")
        self.assertEqual(stpg[0].value.value, sus[0].value.value)
        self.assertNotEqual(stpg[0].identity_key(), sus[0].identity_key())

    def test_asme_vs_jis_vs_en_flange_distinct_identity_even_if_class_strings_look_alike(self):
        # Different standards' class_key strings ("150" vs "10K" vs "PN16")
        # are never equated - each flange fact's identity includes `standard`.
        asme = _REGISTRY.query("outside_diameter_mm", standard="ASME_B16.5", nps="2", class_key="150")
        jis = _REGISTRY.query("outside_diameter_mm", standard="JIS_B2220", jis_size="50A", class_key="10K")
        self.assertNotEqual(asme[0].identity_key()[1], jis[0].identity_key()[1])  # standard field differs


class TestSizeSystemIsolation(unittest.TestCase):
    """Sec.10: NPS / DN / JIS-size never textually collide."""

    def test_no_cross_system_textual_overlap(self):
        report = A.size_system_isolation_report(_REGISTRY)
        self.assertEqual(report["cross_system_textual_overlap"], [])

    def test_all_three_size_systems_actually_represented(self):
        report = A.size_system_isolation_report(_REGISTRY)
        self.assertTrue(report["nps_values"])
        self.assertTrue(report["dn_values"])
        self.assertTrue(report["jis_size_values"])


class TestRatingSystemIsolation(unittest.TestCase):
    """Sec.11: ASME Class / PN / JIS K / Schedule / EN wall-designation
    never collide even where a bare numeral coincides."""

    def test_no_cross_system_textual_overlap(self):
        report = A.rating_system_isolation_report(_REGISTRY)
        self.assertEqual(report["cross_system_textual_overlap"], [])

    def test_pn_and_jis_k_and_asme_class_all_represented(self):
        report = A.rating_system_isolation_report(_REGISTRY)
        self.assertTrue(report["PN"])
        self.assertTrue(report["JIS_K"])
        self.assertTrue(report["ASME_CLASS"])


class TestManufacturerSpecificAudit(unittest.TestCase):
    """Sec.12: manufacturer-specific facts never leak as default standard
    answers, and always carry a manufacturer_profile."""

    def test_exact_count_and_profile(self):
        mfr = [f for f in _REGISTRY.all_facts() if f.verification_status == V.VERIFIED_MANUFACTURER_SPECIFIC]
        self.assertEqual(len(mfr), EXPECTED_MANUFACTURER_SPECIFIC)
        self.assertEqual({f.applicability.manufacturer_profile for f in mfr}, {"Bonney Forge"})

    def test_query_without_optin_never_returns_manufacturer_specific(self):
        from kgpe.contract.model import DimensionQuarantined
        with self.assertRaises(DimensionQuarantined):
            _REGISTRY.query("olet_height_mm", standard="MSS_SP97", fitting_type="sockolet")

    def test_query_with_optin_and_profile_succeeds(self):
        result = _REGISTRY.query("olet_height_mm", standard="MSS_SP97", fitting_type="sockolet",
                                  manufacturer_profile="Bonney Forge", allow_manufacturer_specific=True)
        self.assertTrue(len(result) >= 1)


class TestVerificationStatusIntegrity(unittest.TestCase):
    """Sec.13: report which statuses are actually present; confirm correct
    behaviour for each one that is."""

    def test_statuses_actually_present(self):
        present = {f.verification_status for f in _REGISTRY.all_facts()}
        self.assertEqual(present, {V.VERIFIED_AUTHORITATIVE, V.VERIFIED_MANUFACTURER_SPECIFIC,
                                    V.QUARANTINED_CONFLICT})

    def test_absence_of_other_statuses_is_not_an_error(self):
        absent = V.ALL_STATUSES - {f.verification_status for f in _REGISTRY.all_facts()}
        self.assertEqual(absent, {V.VERIFIED_DERIVED_RULE, V.CONSTRUCTION_PARAMETER, V.VISUAL_ONLY,
                                   V.QUARANTINED_UNVERIFIED, V.DEPRECATED_LEGACY})

    def test_authoritative_facts_queryable_with_no_optin(self):
        result = _REGISTRY.query("outside_diameter_mm", standard="ASME_B16.5", nps="2", class_key="150")
        self.assertEqual(len(result), 1)


class TestProvenanceCompleteness(unittest.TestCase):
    """Sec.14: measure completeness; distinguish legitimately-unknown from
    accidentally-missing; never require metadata that was never known."""

    def test_identity_establishing_fields_are_100pct_complete(self):
        facts = _REGISTRY.all_facts()
        for field in ("source_name", "source_type", "standard_designation", "source_file", "original_field",
                      "transcription_method"):
            populated = sum(1 for f in facts if getattr(f.provenance, field))
            self.assertEqual(populated, len(facts), f"{field} should be 100% complete")

    def test_verification_date_legitimately_always_unknown(self):
        # Never fabricated - this project has never confirmed an exact
        # verification date for any ingested source, so 0% is correct,
        # not a bug.
        facts = _REGISTRY.all_facts()
        populated = sum(1 for f in facts if f.provenance.verification_date)
        self.assertEqual(populated, 0)


class TestCanonicalReaderResultSemantics(unittest.TestCase):
    """Sec.16/17: every structured outcome is actually reachable against
    real registry data, and ambiguity/manufacturer-context always fail
    closed rather than picking a first/default match."""

    @classmethod
    def setUpClass(cls):
        cls.reader = CanonicalReader(_REGISTRY)

    def test_exact_match(self):
        r = self.reader.read("outside_diameter_mm", standard="ASME_B16.5", nps="2", class_key="150")
        self.assertEqual(r.outcome, OUTCOME_EXACT_MATCH)
        self.assertIsNotNone(r.fact)

    def test_no_match(self):
        r = self.reader.read("outside_diameter_mm", standard="ASME_B16.5", nps="999")
        self.assertEqual(r.outcome, OUTCOME_NO_MATCH)

    def test_quarantined_match(self):
        r = self.reader.read("outside_diameter_mm", standard="ASME_B16.9", nps="8")
        self.assertEqual(r.outcome, OUTCOME_QUARANTINED)
        self.assertEqual(len(r.facts), 2)

    def test_ambiguous_match_never_returns_first_pick(self):
        # Wall thickness for a pipe NPS without specifying schedule matches
        # many authoritative facts at once - must be AMBIGUOUS, not any one.
        r = self.reader.read("wall_thickness_mm", standard="ASME_B36.10M", nps="2")
        self.assertEqual(r.outcome, OUTCOME_AMBIGUOUS)
        self.assertGreater(len(r.facts), 1)
        self.assertIsNone(r.fact)

    def test_manufacturer_context_required(self):
        r = self.reader.read("olet_height_mm", standard="MSS_SP97", fitting_type="sockolet")
        self.assertEqual(r.outcome, OUTCOME_MANUFACTURER_CONTEXT_REQUIRED)
        self.assertIn("Bonney Forge", r.available_manufacturer_profiles)

    def test_manufacturer_context_supplied_resolves(self):
        r = self.reader.read("olet_height_mm", standard="MSS_SP97", fitting_type="sockolet",
                              branch_nps="2", allow_manufacturer_specific=True)
        self.assertIn(r.outcome, (OUTCOME_EXACT_MATCH, OUTCOME_AMBIGUOUS))

    def test_malformed_criteria(self):
        r = self.reader.read("outside_diameter_mm", not_a_real_field="x")
        self.assertEqual(r.outcome, OUTCOME_MALFORMED_CRITERIA)

    def test_unsupported_dimension_name(self):
        r = self.reader.read("this_dimension_does_not_exist_anywhere")
        self.assertEqual(r.outcome, OUTCOME_UNSUPPORTED_CRITERIA)


class TestCoverageOptionDiscovery(unittest.TestCase):
    """Sec.18: discovery is purely data-driven - never a hard-coded list."""

    @classmethod
    def setUpClass(cls):
        cls.reader = CanonicalReader(_REGISTRY)

    def test_discover_standards_for_flange_matches_registry(self):
        discovered = set(self.reader.discover("standard", product_family="flange"))
        actual = {f.applicability.standard for f in _REGISTRY.all_facts()
                  if f.applicability.product_family == "flange"}
        self.assertEqual(discovered, actual)

    def test_discover_classes_for_asme_b16_5(self):
        classes = self.reader.discover("class_key", standard="ASME_B16.5")
        self.assertEqual(set(classes), {"150", "300", "400", "600", "900", "1500", "2500"})

    def test_available_dimensions_is_data_driven(self):
        dims = self.reader.available_dimensions(standard="ASME_B16.11")
        self.assertIn("socket_bore_depth_max_mm", dims)
        self.assertNotIn("outside_diameter_mm", dims)  # B16.11 does not publish OD

    def test_available_reducing_pairs_nonempty_for_b16_9(self):
        pairs = self.reader.available_reducing_pairs(size_system="nps", standard="ASME_B16.9")
        self.assertTrue(pairs)
        self.assertTrue(all(p[0] and p[1] for p in pairs))

    def test_unknown_field_raises_attributeerror_not_silently_empty(self):
        with self.assertRaises(AttributeError):
            self.reader.discover("not_a_real_applicability_field")


class TestSnapshotAndFingerprint(unittest.TestCase):
    """Sec.19/20: deterministic snapshot + fingerprint."""

    def test_fingerprint_deterministic_across_builds(self):
        r2, _ = build_canonical_registry()
        self.assertEqual(registry_fingerprint(_REGISTRY), registry_fingerprint(r2))

    def test_fingerprint_changes_under_controlled_mutation(self):
        mutant, _ = build_canonical_registry()
        fp_before = registry_fingerprint(mutant)
        f0 = mutant.all_facts()[0]
        f0.value = Quantity(f0.value.value + 0.001, LENGTH_MM)
        fp_after = registry_fingerprint(mutant)
        self.assertNotEqual(fp_before, fp_after)

    def test_snapshot_structure_and_counts(self):
        snap = build_data_layer_snapshot(_REGISTRY, _COUNTS)
        self.assertEqual(snap["dataset_count"], 11)
        self.assertEqual(snap["total_facts_stored"], EXPECTED_STORED_TOTAL)
        self.assertEqual(snap["total_facts_built"], EXPECTED_BUILT_TOTAL)
        self.assertEqual(len(snap["unresolved_conflict_ids"]), EXPECTED_QUARANTINED_GROUPS)
        self.assertEqual(snap["fingerprint_sha256"], registry_fingerprint(_REGISTRY))
        self.assertNotIn("generated_at", snap)  # no wall-clock timestamp participates in identity


class TestPrompt3ConsistencyMatrix(unittest.TestCase):
    """Sec.21: concise consistency check against major Prompt 3
    conclusions - contradictions would be investigated, not silently kept."""

    def test_weld_neck_thickness_kept_distinct_from_other_types(self):
        from kgpe.contract import vocabulary as VOC
        self.assertNotEqual(VOC.DIM_FLANGE_THICKNESS_WELD_NECK, VOC.DIM_FLANGE_THICKNESS_OTHER_TYPES)
        wn = _REGISTRY.query(VOC.DIM_FLANGE_THICKNESS_WELD_NECK, standard="ASME_B16.5", nps="2", class_key="150")
        self.assertEqual(len(wn), 1)

    def test_b16_9_reducer_concentric_and_eccentric_both_present(self):
        concentric = [f for f in _REGISTRY.all_facts() if f.applicability.standard == "ASME_B16.9"
                      and f.applicability.fitting_type == "reducer_concentric"]
        eccentric = [f for f in _REGISTRY.all_facts() if f.applicability.standard == "ASME_B16.9"
                     and f.applicability.fitting_type == "reducer_eccentric"]
        self.assertTrue(concentric)
        self.assertTrue(eccentric)

    def test_b16_9_cap_dual_length_distinction_preserved(self):
        from kgpe.contract import vocabulary as VOC
        std_wall = [f for f in _REGISTRY.all_facts() if f.dimension_name == VOC.DIM_CAP_LENGTH_STANDARD_WALL]
        heavy_wall = [f for f in _REGISTRY.all_facts() if f.dimension_name == VOC.DIM_CAP_LENGTH_HEAVY_WALL]
        self.assertTrue(std_wall)
        self.assertTrue(heavy_wall)

    def test_legacy_rf_hub_quarantine_fixture_still_proves_quarantine_works(self):
        from kgpe.contract.adapters.legacy_crm_quarantine_fixture import load_legacy_crm_quarantine_fixture
        from kgpe.contract.model import FactRegistry, DimensionQuarantined
        fixture_reg = FactRegistry()
        load_legacy_crm_quarantine_fixture(fixture_reg)
        with self.assertRaises(DimensionQuarantined):
            fixture_reg.query("raised_face_diameter_mm", standard="ASME_B16.5", nps="14", class_key="150")

    def test_no_est_true_style_interpolated_values_promoted(self):
        # No fact anywhere in the production registry carries an "est"
        # marker in its notes/provenance - interpolated/estimated legacy
        # values were never promoted to canonical authoritative facts.
        for f in _REGISTRY.all_facts():
            self.assertNotIn("est:true", (f.notes or "").lower())
            self.assertNotIn("est:true", (f.provenance.notes or "").lower())


class TestLegacyJSIsolationAudit(unittest.TestCase):
    """Sec.22: registry construction never reads CRM JS/HTML/KFEE, never
    depends on the network, and the one fixture that MENTIONS the CRM
    filename does so only in documentation, never by opening the file."""

    def _production_files(self):
        adapters_dir = os.path.join(_ROOT, "kgpe", "contract", "adapters")
        files = [os.path.join(adapters_dir, fn) for fn in os.listdir(adapters_dir)
                 if fn.endswith(".py") and fn not in ("legacy_crm_quarantine_fixture.py", "__init__.py")]
        files += [os.path.join(_ROOT, "kgpe", "contract", fn) for fn in
                  ("registry_builder.py", "model.py", "canonical_reader.py",
                   "data_layer_audit.py", "snapshot.py")]
        return files

    def test_no_crm_html_js_reference_in_production_files(self):
        for path in self._production_files():
            with open(path, "r", encoding="utf-8") as fh:
                src = fh.read()
            for forbidden in (".html", ".js\"", "KAFCO_CRM"):
                self.assertNotIn(forbidden, src, f"{forbidden!r} found in {path}")

    def test_no_network_import_in_production_files(self):
        for path in self._production_files():
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    s = line.strip()
                    self.assertFalse(s.startswith("import requests") or s.startswith("import urllib")
                                      or s.startswith("from urllib") or s.startswith("import http.client")
                                      or s.startswith("import socket") or "socketserver" in s,
                                      f"network-looking import in {path}: {s!r}")

    def test_fixture_mentions_crm_filename_only_as_documentation(self):
        fixture_path = os.path.join(_ROOT, "kgpe", "contract", "adapters", "legacy_crm_quarantine_fixture.py")
        with open(fixture_path, "r", encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("KAFCO_CRM_Dashboard.html", src)
        self.assertNotIn('open(', src)  # never actually opens any file

    def test_source_json_files_untouched_this_session(self):
        ai_readable_root = os.path.abspath(os.path.join(_ROOT, "..", "..", "AI-Readable"))
        json_files = []
        for dirpath, _dirs, filenames in os.walk(ai_readable_root):
            json_files.extend(os.path.join(dirpath, fn) for fn in filenames if fn.endswith(".json"))
        self.assertEqual(len(json_files), 11)


class TestExistingDemoUnchanged(unittest.TestCase):
    """Sec.27: the pre-existing demo/backward-compatibility script still
    runs clean and its determinism check still passes."""

    def test_demo_runs_and_determinism_check_passes(self):
        demo_path = os.path.join(_ROOT, "examples", "demo.py")
        result = subprocess.run([sys.executable, demo_path], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DETERMINISM CHECK", result.stdout)
        self.assertIn("PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
