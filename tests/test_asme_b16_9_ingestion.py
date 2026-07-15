# -*- coding: utf-8 -*-
"""
Automated tests for the ASME B16.9 buttweld-fitting ingestion pipeline
(Prompt 7) - multi-size product identity (reducers), fitting-type
vocabulary, and the real cross-section OD conflict discovered during this
prompt (NPS8 / NPS12).

Run with:
    cd "Dimensions and Standards/Engine/KGPE"
    python -m unittest discover -s tests -p "test_*.py" -v

Uses only the Python standard library `unittest`.
"""
import sys
import os
import unittest
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from kgpe import dimension_library as dl
from kgpe.generator import generate_geometry
from kgpe.contract import vocabulary as VOC
from kgpe.contract.applicability import Applicability
from kgpe.contract.units import Quantity, LENGTH_MM
from kgpe.contract.normalization import normalize_nps, nps_sort_key
from kgpe.contract.model import (
    FactRegistry, EngineeringFact, EngineeringFactProvenance,
    CombinationNotFound, DimensionQuarantined, ConflictingDuplicateFact, SourceValidationError,
)
from kgpe.contract import verification as V
from kgpe.contract.adapters import asme_b16_9_buttweld as adapter

STD = "ASME_B16.9"


class TestSuccessfulIngestion(unittest.TestCase):
    def test_ingestion_succeeds_without_raising(self):
        registry, facts = adapter.ingest_asme_b16_9_buttweld()
        self.assertGreater(len(facts), 0)

    def test_deterministic_record_count_across_two_fresh_ingestions(self):
        _, facts1 = adapter.ingest_asme_b16_9_buttweld()
        _, facts2 = adapter.ingest_asme_b16_9_buttweld()
        self.assertEqual(len(facts1), len(facts2))

    def test_deterministic_ingestion_order(self):
        _, facts1 = adapter.ingest_asme_b16_9_buttweld()
        _, facts2 = adapter.ingest_asme_b16_9_buttweld()
        self.assertEqual([f.identity_key() for f in facts1], [f.identity_key() for f in facts2])


class TestFittingTypeVocabulary(unittest.TestCase):
    def test_five_distinct_elbow_subtypes_present(self):
        _, facts = adapter.ingest_asme_b16_9_buttweld()
        elbow_types = {f.applicability.fitting_type for f in facts
                       if f.applicability.fitting_type and "elbow" in f.applicability.fitting_type}
        self.assertEqual(elbow_types, {
            VOC.FITTING_TYPE_ELBOW_90_LR, VOC.FITTING_TYPE_ELBOW_45_LR,
            VOC.FITTING_TYPE_ELBOW_90_3D, VOC.FITTING_TYPE_ELBOW_45_3D, VOC.FITTING_TYPE_ELBOW_90_SR,
        })

    def test_concentric_and_eccentric_reducers_both_present_and_distinct(self):
        _, facts = adapter.ingest_asme_b16_9_buttweld()
        reducer_types = {f.applicability.fitting_type for f in facts
                          if f.applicability.fitting_type in
                          (VOC.FITTING_TYPE_REDUCER_CONCENTRIC, VOC.FITTING_TYPE_REDUCER_ECCENTRIC)}
        self.assertEqual(reducer_types, {VOC.FITTING_TYPE_REDUCER_CONCENTRIC, VOC.FITTING_TYPE_REDUCER_ECCENTRIC})

    def test_only_equal_tee_present_no_fabricated_reducing_tee(self):
        _, facts = adapter.ingest_asme_b16_9_buttweld()
        tee_types = {f.applicability.fitting_type for f in facts if f.dimension_name in
                     (VOC.DIM_TEE_RUN_CENTRE_TO_END, VOC.DIM_TEE_BRANCH_CENTRE_TO_END)}
        self.assertEqual(tee_types, {VOC.FITTING_TYPE_TEE_EQUAL})


class TestMultiSizeReducerIdentity(unittest.TestCase):
    def setUp(self):
        self.registry, _ = adapter.ingest_asme_b16_9_buttweld()

    def test_reducer_queryable_by_large_and_small_end_role(self):
        res = self.registry.query(VOC.DIM_END_TO_END, standard=STD,
                                   fitting_type=VOC.FITTING_TYPE_REDUCER_CONCENTRIC,
                                   large_end_nps="6", small_end_nps="4")
        self.assertEqual(len(res), 1)

    def test_concentric_and_eccentric_share_value_but_distinct_identity(self):
        conc = self.registry.query(VOC.DIM_END_TO_END, standard=STD,
                                    fitting_type=VOC.FITTING_TYPE_REDUCER_CONCENTRIC,
                                    large_end_nps="6", small_end_nps="4")[0]
        ecc = self.registry.query(VOC.DIM_END_TO_END, standard=STD,
                                   fitting_type=VOC.FITTING_TYPE_REDUCER_ECCENTRIC,
                                   large_end_nps="6", small_end_nps="4")[0]
        self.assertEqual(conc.value.value, ecc.value.value)  # source: identical tabulated value
        self.assertNotEqual(conc.identity_key(), ecc.identity_key())  # but distinct engineering identity

    def test_reversed_reducer_pair_is_rejected_at_validation(self):
        errs = adapter._validate_reducer_row(0, {
            "NPS_Large-Small": "4 - 6", "OD_Large_D_mm": 114.3, "OD_Small_D1_mm": 168.3, "Length_H_mm": 100.0,
        })
        self.assertTrue(any("strictly greater" in e for e in errs))

    def test_equal_pair_is_rejected_at_validation(self):
        errs = adapter._validate_reducer_row(0, {
            "NPS_Large-Small": "6 - 6", "OD_Large_D_mm": 168.3, "OD_Small_D1_mm": 168.3, "Length_H_mm": 100.0,
        })
        self.assertTrue(any("strictly greater" in e for e in errs))

    def test_reducer_pair_parses_fractional_nps_correctly(self):
        large, small = adapter._parse_reducer_pair("3/4 - 1/2")
        self.assertEqual(large, "3/4")
        self.assertEqual(small, "1/2")


class TestSameValueDifferentSubtypeNonConflict(unittest.TestCase):
    """Proves that legitimately-distinct facts sharing the same numeric
    value never trigger a false ConflictingDuplicateFact - e.g. the
    reducer Length_H value, which this source states applies identically
    to both concentric and eccentric reducers."""

    def test_ingestion_of_reducers_does_not_raise_despite_shared_values(self):
        registry, facts = adapter.ingest_asme_b16_9_buttweld()  # would already have raised if mishandled
        reducer_facts = [f for f in facts if f.applicability.fitting_type in
                          (VOC.FITTING_TYPE_REDUCER_CONCENTRIC, VOC.FITTING_TYPE_REDUCER_ECCENTRIC)]
        self.assertGreater(len(reducer_facts), 0)


class TestRealODCrossSectionConflictDiscovery(unittest.TestCase):
    """The key finding of Prompt 7: this source's OD_mm is NOT consistent
    across all sections for NPS8 and NPS12. Structural cross-section
    identity sharing (no fitting_type on the OD applicability) surfaced
    this live, rather than a hand-built fixture. Both values must be
    retained (QUARANTINED_CONFLICT), never silently picked/averaged/
    dropped, and the source JSON itself must never be edited to "fix" it."""

    def test_conflicts_detected_for_exactly_nps8_and_nps12(self):
        data, _ = adapter._load_source()
        observations = adapter._collect_od_observations(data)
        conflicts = adapter._find_od_conflicts(observations)
        self.assertEqual(set(conflicts.keys()), {"8", "12"})

    def test_nps12_conflict_values_are_323_8_and_323_9(self):
        data, _ = adapter._load_source()
        conflicts = adapter._find_od_conflicts(adapter._collect_od_observations(data))
        self.assertEqual(set(conflicts["12"].keys()), {323.8, 323.9})

    def test_nps8_conflict_values_are_219_1_and_219_0(self):
        data, _ = adapter._load_source()
        conflicts = adapter._find_od_conflicts(adapter._collect_od_observations(data))
        self.assertEqual(set(conflicts["8"].keys()), {219.1, 219.0})

    def test_conflicted_nps_od_is_quarantined_not_authoritative(self):
        registry, _ = adapter.ingest_asme_b16_9_buttweld()
        with self.assertRaises(DimensionQuarantined):
            registry.query(VOC.DIM_OUTSIDE_DIAMETER, standard=STD, nps="8")
        with self.assertRaises(DimensionQuarantined):
            registry.query(VOC.DIM_OUTSIDE_DIAMETER, standard=STD, nps="12")

    def test_both_disagreeing_values_are_retained_and_inspectable(self):
        registry, _ = adapter.ingest_asme_b16_9_buttweld()
        quarantined = registry.get_quarantined(dimension_name=VOC.DIM_OUTSIDE_DIAMETER)
        nps12_values = {f.value.value for f in quarantined if f.applicability.nps == "12"}
        self.assertEqual(nps12_values, {323.8, 323.9})

    def test_unaffected_nps_remains_verified_authoritative(self):
        registry, _ = adapter.ingest_asme_b16_9_buttweld()
        r = registry.query(VOC.DIM_OUTSIDE_DIAMETER, standard=STD, nps="6")
        self.assertEqual(r[0].value.value, 168.3)
        self.assertEqual(r[0].verification_status, V.VERIFIED_AUTHORITATIVE)


class TestSourceValidation(unittest.TestCase):
    def test_missing_top_level_key_rejected(self):
        with self.assertRaises(SourceValidationError):
            adapter._validate_top_level({"standard": "x"})

    def test_negative_od_rejected(self):
        errs = adapter._validate_single_size_row("t", 0, {"NPS": "6", "OD_mm": -1.0}, [])
        self.assertTrue(any("OD_mm" in e for e in errs))

    def test_null_optional_column_is_valid(self):
        errs = adapter._validate_single_size_row("t", 0, {"NPS": "6", "OD_mm": 168.3, "X": None}, ["X"])
        self.assertEqual(errs, [])

    def test_required_column_null_is_rejected(self):
        errs = adapter._validate_single_size_row("t", 0, {"NPS": "6", "OD_mm": 168.3, "X": None}, ["X"],
                                                   required_value_cols=["X"])
        self.assertTrue(any("required and must not be null" in e for e in errs))

    def test_cap_h1_threshold_must_be_paired(self):
        errs = adapter._validate_cap_row(0, {
            "NPS": "6", "OD_mm": 168.3, "Length_H_mm": 100.0, "Length_H1_mm": 120.0, "WT_threshold_mm": None,
        })
        self.assertTrue(any("present together or null together" in e for e in errs))

    def test_duplicate_nps_rejected(self):
        rows = [{"NPS": "6", "OD_mm": 168.3}, {"NPS": "6", "OD_mm": 168.3}]
        errs = adapter._check_duplicate_nps("t", rows)
        self.assertTrue(errs)

    def test_duplicate_reducer_pair_rejected(self):
        rows = [{"NPS_Large-Small": "6 - 4"}, {"NPS_Large-Small": "6 - 4"}]
        errs = adapter._check_duplicate_reducer_pairs(rows)
        self.assertTrue(errs)


class TestMissingCombinationSemantics(unittest.TestCase):
    def test_unavailable_elbow_sr_at_out_of_range_nps_fails_closed(self):
        registry, _ = adapter.ingest_asme_b16_9_buttweld()
        # elbows_90_SR only covers NPS 1-24 in this source; NPS48 has no SR row at all.
        with self.assertRaises(CombinationNotFound):
            registry.query(VOC.DIM_CENTRE_TO_END, standard=STD,
                            fitting_type=VOC.FITTING_TYPE_ELBOW_90_SR, nps="48")

    def test_cap_h1_threshold_unavailable_at_large_nps(self):
        registry, _ = adapter.ingest_asme_b16_9_buttweld()
        with self.assertRaises(CombinationNotFound):
            registry.query(VOC.DIM_CAP_LENGTH_HEAVY_WALL, standard=STD, fitting_type=VOC.FITTING_TYPE_CAP, nps="48")


class TestProvenancePresence(unittest.TestCase):
    def test_every_fact_has_source_file_and_original_field(self):
        _, facts = adapter.ingest_asme_b16_9_buttweld()
        for f in facts:
            self.assertIsNotNone(f.provenance.source_file)
            self.assertIsNotNone(f.provenance.original_field)
            self.assertEqual(f.provenance.standard_designation, STD)


class TestDuplicateAndConflictHandling(unittest.TestCase):
    def test_re_ingesting_into_same_registry_is_exact_duplicate_noop(self):
        registry = FactRegistry()
        adapter.ingest_asme_b16_9_buttweld(registry)
        count1 = len(registry.all_facts())
        adapter.ingest_asme_b16_9_buttweld(registry)
        count2 = len(registry.all_facts())
        self.assertEqual(count1, count2)

    def test_manually_constructed_conflicting_duplicate_still_rejected(self):
        registry = FactRegistry()
        applicability = Applicability(product_family=VOC.PRODUCT_FAMILY_BUTTWELD_FITTING, standard=STD, nps="99")
        fact_a = EngineeringFact(
            dimension_name=VOC.DIM_OUTSIDE_DIAMETER, value=Quantity(100.0, LENGTH_MM),
            applicability=applicability, verification_status=V.VERIFIED_AUTHORITATIVE,
            provenance=EngineeringFactProvenance(source_name="A"),
        )
        fact_b = EngineeringFact(
            dimension_name=VOC.DIM_OUTSIDE_DIAMETER, value=Quantity(200.0, LENGTH_MM),
            applicability=applicability, verification_status=V.VERIFIED_AUTHORITATIVE,
            provenance=EngineeringFactProvenance(source_name="B"),
        )
        registry.add_checked(fact_a)
        with self.assertRaises(ConflictingDuplicateFact):
            registry.add_checked(fact_b)


class TestExhaustiveComparisonAgainstDimensionLibrary(unittest.TestCase):
    """Broken down by fitting subtype (Prompt 7 Sec.17): elbow 90LR, tee,
    cap have existing dimension_library.py lookups to cross-check exactly;
    elbow 45LR/90-3D/45-3D/90SR and reducers have NO existing lookup at
    all (new canonical-only coverage), which is reported, not hidden."""

    @classmethod
    def setUpClass(cls):
        cls.registry, cls.facts = adapter.ingest_asme_b16_9_buttweld()
        cls.data, _ = adapter._load_source()

    def test_elbow_90_lr_exact_match(self):
        checked = mismatches = 0
        for row in self.data["elbows_90_45_LR_3D"]["rows"]:
            nps = row["NPS"]
            try:
                dims, _src = dl.get_buttweld_elbow90(STD, nps)
            except dl.DimNotFound:
                continue
            checked += 1
            canon_nps = normalize_nps(nps)
            res = self.registry.query(VOC.DIM_CENTRE_TO_END, standard=STD,
                                       fitting_type=VOC.FITTING_TYPE_ELBOW_90_LR, nps=canon_nps)
            if res[0].value.value != dims["CtoE_mm"]:
                mismatches += 1
        print(f"\n[Prompt 7 cross-check] elbow_90_lr: checked={checked} mismatches={mismatches}")
        self.assertEqual(mismatches, 0)
        self.assertGreater(checked, 0)

    def test_tee_exact_match(self):
        checked = mismatches = 0
        for row in self.data["tees_straight_equal"]["rows"]:
            nps = row["NPS"]
            try:
                dims, _src = dl.get_buttweld_tee(STD, nps)
            except dl.DimNotFound:
                continue
            checked += 1
            canon_nps = normalize_nps(nps)
            run_res = self.registry.query(VOC.DIM_TEE_RUN_CENTRE_TO_END, standard=STD,
                                           fitting_type=VOC.FITTING_TYPE_TEE_EQUAL, nps=canon_nps)
            outlet_res = self.registry.query(VOC.DIM_TEE_BRANCH_CENTRE_TO_END, standard=STD,
                                              fitting_type=VOC.FITTING_TYPE_TEE_EQUAL, nps=canon_nps)
            if run_res[0].value.value != dims["RunCtoE_mm"] or outlet_res[0].value.value != dims["OutletCtoE_mm"]:
                mismatches += 1
        print(f"[Prompt 7 cross-check] tee: checked={checked} mismatches={mismatches}")
        self.assertEqual(mismatches, 0)
        self.assertGreater(checked, 0)

    def test_cap_exact_match(self):
        checked = mismatches = 0
        for row in self.data["caps"]["rows"]:
            nps = row["NPS"]
            try:
                dims, _src = dl.get_buttweld_cap(STD, nps)
            except dl.DimNotFound:
                continue
            checked += 1
            canon_nps = normalize_nps(nps)
            res = self.registry.query(VOC.DIM_CAP_LENGTH_STANDARD_WALL, standard=STD,
                                       fitting_type=VOC.FITTING_TYPE_CAP, nps=canon_nps)
            if res[0].value.value != dims["Length_mm"]:
                mismatches += 1
        print(f"[Prompt 7 cross-check] cap: checked={checked} mismatches={mismatches}")
        self.assertEqual(mismatches, 0)
        self.assertGreater(checked, 0)

    def test_subtypes_with_no_existing_lookup_are_new_canonical_only_coverage(self):
        # elbow_45_lr / 90_3d / 45_3d / 90_sr and both reducer types have no
        # dimension_library.py equivalent at all - confirm they're present
        # in the canonical registry (new coverage), not silently dropped.
        for ft in (VOC.FITTING_TYPE_ELBOW_45_LR, VOC.FITTING_TYPE_ELBOW_90_3D,
                   VOC.FITTING_TYPE_ELBOW_45_3D, VOC.FITTING_TYPE_ELBOW_90_SR):
            count = sum(1 for f in self.facts if f.applicability.fitting_type == ft
                        and f.dimension_name == VOC.DIM_CENTRE_TO_END)
            self.assertGreater(count, 0, f"expected new-coverage facts for {ft}")
        reducer_count = sum(1 for f in self.facts if f.applicability.fitting_type in
                            (VOC.FITTING_TYPE_REDUCER_CONCENTRIC, VOC.FITTING_TYPE_REDUCER_ECCENTRIC))
        self.assertGreater(reducer_count, 0)

    def test_reducer_fact_count_matches_source_row_count_times_two(self):
        n_rows = len(self.data["reducers_concentric_eccentric"]["rows"])
        reducer_length_facts = [f for f in self.facts if f.dimension_name == VOC.DIM_END_TO_END]
        self.assertEqual(len(reducer_length_facts), n_rows * 2)  # concentric + eccentric per row


class TestRegistryScale(unittest.TestCase):
    def test_registry_scale_remains_trivial(self):
        registry, facts = adapter.ingest_asme_b16_9_buttweld()
        bucket_sizes = {dim: len(bucket) for dim, bucket in registry._by_dimension.items()}
        largest = max(bucket_sizes.values())
        print(f"\n[Prompt 7 registry scale] total_facts={len(facts)} largest_dimension_bucket={largest} "
              f"buckets={bucket_sizes}")
        self.assertGreater(len(facts), 0)
        self.assertLess(largest, 1000)


class TestBackwardCompatibility(unittest.TestCase):
    def test_existing_elbow_90_generation_path_unaffected(self):
        req = {"product_type": "buttweld_fitting", "fitting_type": "elbow_90", "standard": "ASME_B16.9", "size": "6"}
        result = generate_geometry(req)
        self.assertEqual(result["status"], "OK")

    def test_existing_tee_generation_path_unaffected(self):
        req = {"product_type": "buttweld_fitting", "fitting_type": "tee", "standard": "ASME_B16.9", "size": "6"}
        result = generate_geometry(req)
        self.assertEqual(result["status"], "OK")

    def test_existing_cap_generation_path_unaffected(self):
        req = {"product_type": "buttweld_fitting", "fitting_type": "cap", "standard": "ASME_B16.9", "size": "6"}
        result = generate_geometry(req)
        self.assertEqual(result["status"], "OK")

    def test_existing_dimension_library_lookups_unaffected(self):
        dims, _src = dl.get_buttweld_elbow90("ASME_B16.9", "6")
        self.assertEqual(dims["CtoE_mm"], dims["CtoE_mm"])  # smoke check: call succeeds, no exception


if __name__ == "__main__":
    unittest.main(verbosity=2)
