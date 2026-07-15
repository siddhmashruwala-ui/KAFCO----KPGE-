# -*- coding: utf-8 -*-
"""
Automated tests for the ASME B36.10M/19M pipe ingestion pipeline (Prompt 6).

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
from kgpe.contract.normalization import (
    normalize_nps, nps_sort_key, normalize_schedule, normalize_asme_pipe_standard,
    ASME_B36_10M, ASME_B36_19M,
)
from kgpe.contract.model import (
    FactRegistry, EngineeringFact, EngineeringFactProvenance,
    CombinationNotFound, ConflictingDuplicateFact, SourceValidationError,
)
from kgpe.contract import verification as V
from kgpe.contract.adapters import asme_b36_pipes as adapter
from kgpe.contract.adapters import asme_b16_5_flanges as flange_adapter


class TestScheduleNormalization(unittest.TestCase):
    def test_variant_forms_normalize_consistently(self):
        self.assertEqual(normalize_schedule("40"), "SCH40")
        self.assertEqual(normalize_schedule("Sch40"), "SCH40")
        self.assertEqual(normalize_schedule("SCH 40"), "SCH40")
        self.assertEqual(normalize_schedule("SCH-40"), "SCH40")
        self.assertEqual(normalize_schedule("40S"), "SCH40S")
        self.assertEqual(normalize_schedule("Sch40S"), "SCH40S")

    def test_40_and_40s_never_collapse(self):
        self.assertNotEqual(normalize_schedule("40"), normalize_schedule("40S"))

    def test_80_and_80s_never_collapse(self):
        self.assertNotEqual(normalize_schedule("80"), normalize_schedule("80S"))

    def test_std_xs_xxs_are_not_aliased_to_numeric_schedules(self):
        self.assertEqual(normalize_schedule("SchSTD"), "STD")
        self.assertEqual(normalize_schedule("SchXS"), "XS")
        self.assertEqual(normalize_schedule("SchXXS"), "XXS")
        self.assertNotIn(normalize_schedule("STD"), (normalize_schedule("40"), normalize_schedule("80")))
        self.assertNotIn(normalize_schedule("XS"), (normalize_schedule("40"), normalize_schedule("80")))

    def test_standard_identity_normalization(self):
        self.assertEqual(normalize_asme_pipe_standard("ASME_B36.10M"), ASME_B36_10M)
        self.assertEqual(normalize_asme_pipe_standard("ASME B36.10M"), ASME_B36_10M)
        self.assertEqual(normalize_asme_pipe_standard("B36.10M"), ASME_B36_10M)
        self.assertEqual(normalize_asme_pipe_standard("ASME_B36.19M"), ASME_B36_19M)
        self.assertEqual(normalize_asme_pipe_standard("B36.19"), ASME_B36_19M)
        self.assertNotEqual(ASME_B36_10M, ASME_B36_19M)


class TestSuccessfulIngestion(unittest.TestCase):
    def test_ingestion_succeeds(self):
        registry, facts = adapter.ingest_asme_pipes()
        self.assertGreater(len(facts), 0)
        self.assertEqual(len(facts), len(registry.all_facts()))

    def test_record_count_matches_source_non_null_cells(self):
        data, _ = adapter._load_source()
        expected_od = len(data["B36_10M_wall_thickness_mm"]) + len(data["B36_19M_wall_thickness_mm"])
        cols_10m = [c for c in data["columns_B36_10M"] if c not in ("NPS", "OD_mm")]
        cols_19m = [c for c in data["columns_B36_19M"] if c not in ("NPS", "OD_mm")]
        expected_wt = sum(1 for row in data["B36_10M_wall_thickness_mm"] for c in cols_10m if row.get(c) is not None)
        expected_wt += sum(1 for row in data["B36_19M_wall_thickness_mm"] for c in cols_19m if row.get(c) is not None)

        _, facts = adapter.ingest_asme_pipes()
        od_facts = [f for f in facts if f.dimension_name == VOC.DIM_OUTSIDE_DIAMETER]
        wt_facts = [f for f in facts if f.dimension_name == VOC.DIM_WALL_THICKNESS]
        print(f"\n[Prompt 6] source OD rows(both tables)={expected_od} source non-null WT cells={expected_wt} "
              f"ingested OD facts={len(od_facts)} ingested WT facts={len(wt_facts)} total={len(facts)}")
        self.assertEqual(len(od_facts), expected_od)
        self.assertEqual(len(wt_facts), expected_wt)


class TestDeterministicIngestion(unittest.TestCase):
    def test_deterministic_record_count_across_two_fresh_ingestions(self):
        _, facts1 = adapter.ingest_asme_pipes()
        _, facts2 = adapter.ingest_asme_pipes()
        self.assertEqual(len(facts1), len(facts2))

    def test_deterministic_ingestion_order(self):
        _, facts1 = adapter.ingest_asme_pipes()
        _, facts2 = adapter.ingest_asme_pipes()
        self.assertEqual([f.identity_key() for f in facts1], [f.identity_key() for f in facts2])


class TestNoInterpolationOfMissingCells(unittest.TestCase):
    def test_a_known_null_cell_produces_no_fact(self):
        # Source: B36.10M NPS22 Sch40 is explicitly null.
        registry, _ = adapter.ingest_asme_pipes()
        with self.assertRaises(CombinationNotFound):
            registry.query(VOC.DIM_WALL_THICKNESS, standard=ASME_B36_10M, nps="22", schedule="SCH40")


class TestStandardIdentityPreservation(unittest.TestCase):
    def test_overlapping_nps_has_two_distinct_od_facts_by_standard(self):
        registry, _ = adapter.ingest_asme_pipes()
        r_10m = registry.query(VOC.DIM_OUTSIDE_DIAMETER, standard=ASME_B36_10M, nps="6")
        r_19m = registry.query(VOC.DIM_OUTSIDE_DIAMETER, standard=ASME_B36_19M, nps="6")
        self.assertEqual(len(r_10m), 1)
        self.assertEqual(len(r_19m), 1)
        self.assertEqual(r_10m[0].value.value, r_19m[0].value.value)  # same physical OD
        self.assertNotEqual(r_10m[0].identity_key(), r_19m[0].identity_key())  # distinct identity

    def test_standard_not_collapsed_into_ambiguous_generic_identity(self):
        registry, facts = adapter.ingest_asme_pipes()
        standards_seen = {f.applicability.standard for f in facts}
        self.assertEqual(standards_seen, {ASME_B36_10M, ASME_B36_19M})


class TestScheduleIdentityVsDimensionalEquality(unittest.TestCase):
    """Proves Sch40/Sch40S and Sch80/Sch80S are NOT globally aliased, using
    real source values: they coincide at small NPS but diverge at NPS12/NPS10."""

    def setUp(self):
        self.registry, _ = adapter.ingest_asme_pipes()

    def _wt(self, standard, nps, schedule):
        return self.registry.query(VOC.DIM_WALL_THICKNESS, standard=standard, nps=nps, schedule=schedule)[0].value.value

    def test_sch40_and_sch40s_coincide_at_small_nps(self):
        self.assertEqual(self._wt(ASME_B36_10M, "6", "SCH40"), self._wt(ASME_B36_19M, "6", "SCH40S"))

    def test_sch40_and_sch40s_diverge_at_nps12(self):
        sch40 = self._wt(ASME_B36_10M, "12", "SCH40")
        sch40s = self._wt(ASME_B36_19M, "12", "SCH40S")
        self.assertEqual(sch40, 10.31)
        self.assertEqual(sch40s, 9.53)
        self.assertNotEqual(sch40, sch40s)

    def test_sch80_and_sch80s_diverge_at_nps10(self):
        sch80 = self._wt(ASME_B36_10M, "10", "SCH80")
        sch80s = self._wt(ASME_B36_19M, "10", "SCH80S")
        self.assertEqual(sch80, 15.09)
        self.assertEqual(sch80s, 12.7)
        self.assertNotEqual(sch80, sch80s)

    def test_std_is_not_aliased_to_sch40(self):
        std = self._wt(ASME_B36_10M, "12", "STD")
        sch40 = self._wt(ASME_B36_10M, "12", "SCH40")
        self.assertEqual(std, 9.53)
        self.assertEqual(sch40, 10.31)
        self.assertNotEqual(std, sch40)


class TestProvenancePresence(unittest.TestCase):
    def test_every_fact_has_source_file_and_original_field(self):
        _, facts = adapter.ingest_asme_pipes()
        for f in facts:
            self.assertIsNotNone(f.provenance.source_file)
            self.assertIsNotNone(f.provenance.original_field)
            self.assertIn(f.provenance.standard_designation, (ASME_B36_10M, ASME_B36_19M))


class TestDuplicateAndConflictHandling(unittest.TestCase):
    def test_re_ingesting_into_same_registry_is_exact_duplicate_noop(self):
        registry = FactRegistry()
        adapter.ingest_asme_pipes(registry)
        count1 = len(registry.all_facts())
        adapter.ingest_asme_pipes(registry)
        count2 = len(registry.all_facts())
        self.assertEqual(count1, count2)

    def test_conflicting_duplicate_is_rejected(self):
        registry = FactRegistry()
        applicability = Applicability(product_family="pipe", standard=ASME_B36_10M, nps="6", schedule="SCH40")
        fact_a = EngineeringFact(
            dimension_name=VOC.DIM_WALL_THICKNESS, value=Quantity(7.11, LENGTH_MM),
            applicability=applicability, verification_status=V.VERIFIED_AUTHORITATIVE,
            provenance=EngineeringFactProvenance(source_name="A"),
        )
        fact_b = EngineeringFact(
            dimension_name=VOC.DIM_WALL_THICKNESS, value=Quantity(999.0, LENGTH_MM),
            applicability=applicability, verification_status=V.VERIFIED_AUTHORITATIVE,
            provenance=EngineeringFactProvenance(source_name="B"),
        )
        registry.add_checked(fact_a)
        with self.assertRaises(ConflictingDuplicateFact):
            registry.add_checked(fact_b)

    def test_same_value_different_standard_is_not_a_conflict(self):
        # This is the cross-standard-overlap case: same NPS+dimension+value,
        # but different `standard` -> different identity -> no exception at all.
        registry, _ = adapter.ingest_asme_pipes()  # would have raised already if this were mishandled
        self.assertGreater(len(registry.all_facts()), 0)


class TestMalformedSourceRejection(unittest.TestCase):
    def test_missing_required_field_rejected(self):
        errs = adapter._validate_row("t", 0, {"NPS": "6"}, ["Sch40"])
        self.assertTrue(errs)

    def test_negative_od_rejected(self):
        errs = adapter._validate_row("t", 0, {"NPS": "6", "OD_mm": -1.0, "Sch40": 7.11}, ["Sch40"])
        self.assertTrue(any("OD_mm" in e for e in errs))

    def test_physically_impossible_wall_thickness_rejected(self):
        # WT >= OD/2 is impossible (zero or negative bore).
        errs = adapter._validate_row("t", 0, {"NPS": "6", "OD_mm": 100.0, "Sch40": 60.0}, ["Sch40"])
        self.assertTrue(any("physically impossible" in e for e in errs))

    def test_null_cell_is_valid_not_an_error(self):
        errs = adapter._validate_row("t", 0, {"NPS": "6", "OD_mm": 168.3, "Sch40": None}, ["Sch40"])
        self.assertEqual(errs, [])

    def test_duplicate_nps_rejected(self):
        rows = [{"NPS": "6", "OD_mm": 168.3}, {"NPS": "6", "OD_mm": 168.3}]
        errs = adapter._check_duplicate_nps("t", rows)
        self.assertTrue(errs)

    def test_missing_top_level_key_rejected(self):
        with self.assertRaises(SourceValidationError):
            adapter._validate_top_level({"standards": {ASME_B36_10M: "x", ASME_B36_19M: "y"}})


class TestAuthoritativeLookupProof(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry, _ = adapter.ingest_asme_pipes()

    def test_small_nps_od(self):
        r = self.registry.query(VOC.DIM_OUTSIDE_DIAMETER, standard=ASME_B36_10M, nps="1/2")
        self.assertEqual(r[0].value.value, 21.3)

    def test_mid_range_nps_od(self):
        r = self.registry.query(VOC.DIM_OUTSIDE_DIAMETER, standard=ASME_B36_10M, nps="6")
        self.assertEqual(r[0].value.value, 168.3)

    def test_large_nps_od_10m_only(self):
        r = self.registry.query(VOC.DIM_OUTSIDE_DIAMETER, standard=ASME_B36_10M, nps="36")
        self.assertEqual(r[0].value.value, 914.4)
        with self.assertRaises(CombinationNotFound):
            self.registry.query(VOC.DIM_OUTSIDE_DIAMETER, standard=ASME_B36_19M, nps="36")

    def test_common_schedule_wall_thickness(self):
        r = self.registry.query(VOC.DIM_WALL_THICKNESS, standard=ASME_B36_10M, nps="6", schedule="SCH40")
        self.assertEqual(r[0].value.value, 7.11)

    def test_s_suffix_schedule_wall_thickness(self):
        r = self.registry.query(VOC.DIM_WALL_THICKNESS, standard=ASME_B36_19M, nps="6", schedule="SCH40S")
        self.assertEqual(r[0].value.value, 7.11)

    def test_heavy_wall_schedule(self):
        r = self.registry.query(VOC.DIM_WALL_THICKNESS, standard=ASME_B36_10M, nps="6", schedule="SCH160")
        self.assertEqual(r[0].value.value, 18.26)

    def test_unavailable_combination_fails_closed(self):
        with self.assertRaises(CombinationNotFound):
            self.registry.query(VOC.DIM_WALL_THICKNESS, standard=ASME_B36_10M, nps="22", schedule="SCH40")

    def test_same_value_different_standard_both_reachable(self):
        r10 = self.registry.query(VOC.DIM_OUTSIDE_DIAMETER, standard=ASME_B36_10M, nps="6")
        r19 = self.registry.query(VOC.DIM_OUTSIDE_DIAMETER, standard=ASME_B36_19M, nps="6")
        self.assertEqual(r10[0].value.value, r19[0].value.value)
        self.assertNotEqual(r10[0].identity_key(), r19[0].identity_key())


class TestExhaustiveComparisonAgainstDimensionLibrary(unittest.TestCase):
    def test_od_and_wall_thickness_cross_check(self):
        _, facts = adapter.ingest_asme_pipes()

        od_total = od_exact = od_round = 0
        od_mismatches = []
        wt_total = wt_exact = wt_round = 0
        wt_mismatches = []
        wt_not_comparable = 0
        wt_not_comparable_reasons = defaultdict(int)

        for f in facts:
            nps = f.applicability.nps
            if f.dimension_name == VOC.DIM_OUTSIDE_DIAMETER:
                # SchSTD is defined (non-null) for every B36.10M row in this
                # source, so it reliably resolves OD via the live lookup
                # regardless of which standard this canonical fact is tagged with.
                try:
                    live_dims, _src = dl.get_pipe("ASME_B36", nps, "SchSTD")
                except dl.DimNotFound:
                    continue
                od_total += 1
                live_od = live_dims["OD_mm"]
                if live_od == f.value.value:
                    od_exact += 1
                elif abs(live_od - f.value.value) < 1e-6:
                    od_round += 1
                else:
                    od_mismatches.append((nps, f.applicability.standard, f.value.value, live_od))

            elif f.dimension_name == VOC.DIM_WALL_THICKNESS:
                original_field = f.provenance.original_field
                try:
                    live_dims, _src = dl.get_pipe("ASME_B36", nps, original_field)
                except dl.DimNotFound:
                    wt_not_comparable += 1
                    if original_field.endswith("S"):
                        wt_not_comparable_reasons[
                            "S-suffix schedule: live dimension_library.get_pipe() concatenates B36.10M "
                            "before B36.19M and always matches the first row for this NPS (the B36.10M "
                            "row, which has no S-suffix columns) - a pre-existing live-lookup limitation, "
                            "not touched in this prompt."] += 1
                    else:
                        wt_not_comparable_reasons["other DimNotFound"] += 1
                    continue
                wt_total += 1
                live_wt = live_dims["WallThickness_mm"]
                if live_wt == f.value.value:
                    wt_exact += 1
                elif abs(live_wt - f.value.value) < 1e-6:
                    wt_round += 1
                else:
                    wt_mismatches.append((nps, f.applicability.standard, original_field, f.value.value, live_wt))

        print(f"\n[Prompt 6 cross-check] OD: total_comparable={od_total} exact={od_exact} "
              f"rounding_equivalent={od_round} mismatches={len(od_mismatches)}")
        print(f"[Prompt 6 cross-check] WT: total_comparable={wt_total} exact={wt_exact} "
              f"rounding_equivalent={wt_round} mismatches={len(wt_mismatches)} not_comparable={wt_not_comparable}")
        for reason, count in wt_not_comparable_reasons.items():
            print(f"[Prompt 6 cross-check] WT not_comparable reason ({count}): {reason}")

        self.assertEqual(od_mismatches, [], f"Unexplained OD mismatches: {od_mismatches}")
        self.assertEqual(wt_mismatches, [], f"Unexplained WT mismatches: {wt_mismatches}")
        self.assertGreater(od_total, 0)
        self.assertGreater(wt_total, 0)
        # Every non-comparable WT fact must be an S-suffix schedule (the
        # known, explained live-lookup limitation) - anything else would be
        # an unexplained gap and must fail the test.
        self.assertEqual(
            wt_not_comparable,
            wt_not_comparable_reasons.get(
                "S-suffix schedule: live dimension_library.get_pipe() concatenates B36.10M "
                "before B36.19M and always matches the first row for this NPS (the B36.10M "
                "row, which has no S-suffix columns) - a pre-existing live-lookup limitation, "
                "not touched in this prompt.", 0),
        )


class TestRegistryScale(unittest.TestCase):
    def test_combined_flange_and_pipe_registry_scale(self):
        registry = FactRegistry()
        flange_adapter.ingest_asme_b16_5_flanges(registry)
        adapter.ingest_asme_pipes(registry)
        total = len(registry.all_facts())
        bucket_sizes = {dim: len(bucket) for dim, bucket in registry._by_dimension.items()}
        largest = max(bucket_sizes.values())
        print(f"\n[Prompt 6 registry scale] combined_total_facts={total} "
              f"largest_dimension_bucket={largest} buckets={bucket_sizes}")
        self.assertGreater(total, 0)
        self.assertLess(largest, 1000)  # sanity bound proving linear scan remains trivial


class TestBackwardCompatibility(unittest.TestCase):
    def test_existing_pipe_generation_path_unaffected(self):
        req = {"product_type": "pipe", "standard": "ASME_B36", "size": "6", "schedule": "Sch40"}
        result = generate_geometry(req)
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["geometry"]["outside_dia_mm"], 168.3)
        self.assertEqual(result["geometry"]["wall_thickness_mm"], 7.11)

    def test_existing_dimension_library_pipe_lookup_unaffected(self):
        dims, _src = dl.get_pipe("ASME_B36", "6", "Sch40")
        self.assertEqual(dims["OD_mm"], 168.3)
        self.assertEqual(dims["WallThickness_mm"], 7.11)


if __name__ == "__main__":
    unittest.main(verbosity=2)
