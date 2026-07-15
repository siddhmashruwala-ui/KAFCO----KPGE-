# -*- coding: utf-8 -*-
"""
Automated tests for the ASME B16.5 production ingestion pipeline (Prompt 5).

Run with:
    cd "Dimensions and Standards/Engine/KGPE"
    python -m unittest discover -s tests -p "test_*.py" -v

Uses only the Python standard library `unittest` (no pytest installed,
none installed for this prompt either).
"""
import sys
import os
import unittest
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from kgpe import dimension_library as dl
from kgpe.generator import generate_geometry
from kgpe.contract import vocabulary as VOC
from kgpe.contract import verification as V
from kgpe.contract.applicability import Applicability
from kgpe.contract.units import Quantity, LENGTH_MM
from kgpe.contract.normalization import normalize_nps, nps_sort_key, normalize_pressure_class
from kgpe.contract.model import (
    FactRegistry, EngineeringFact, EngineeringFactProvenance,
    DimensionQuarantined, CombinationNotFound, ConflictingDuplicateFact, SourceValidationError,
)
from kgpe.contract.adapters import asme_b16_5_flanges as adapter
from kgpe.contract.adapters.legacy_crm_quarantine_fixture import load_legacy_crm_quarantine_fixture


class TestNpsNormalization(unittest.TestCase):
    def test_variant_forms_normalize_to_the_same_canonical_string(self):
        self.assertEqual(normalize_nps("1-1/2"), "1-1/2")
        self.assertEqual(normalize_nps("1 1/2"), "1-1/2")
        self.assertEqual(normalize_nps("3/4"), "3/4")
        self.assertEqual(normalize_nps("2"), "2")
        self.assertEqual(normalize_nps(" 24 "), "24")

    def test_sort_key_is_exact_rational_and_orders_correctly(self):
        ordered = ["1/2", "3/4", "1", "1-1/4", "1-1/2", "2", "2-1/2", "3", "3-1/2", "4"]
        keys = [nps_sort_key(normalize_nps(n)) for n in ordered]
        self.assertEqual(keys, sorted(keys))

    def test_unrecognized_format_rejected(self):
        with self.assertRaises(ValueError):
            normalize_nps("two inches")


class TestPressureClassNormalization(unittest.TestCase):
    def test_variant_forms_normalize_to_the_same_canonical_string(self):
        self.assertEqual(normalize_pressure_class("150"), "150")
        self.assertEqual(normalize_pressure_class(150), "150")
        self.assertEqual(normalize_pressure_class("Class 150"), "150")
        self.assertEqual(normalize_pressure_class("CL150"), "150")
        self.assertEqual(normalize_pressure_class("0150"), "150")

    def test_unrecognized_format_rejected(self):
        with self.assertRaises(ValueError):
            normalize_pressure_class("XYZ")


class TestSuccessfulIngestion(unittest.TestCase):
    def test_ingestion_succeeds_with_facts(self):
        registry, facts = adapter.ingest_asme_b16_5_flanges()
        self.assertGreater(len(facts), 0)
        self.assertEqual(len(facts), len(registry.all_facts()))

    def test_record_count_is_six_per_source_row(self):
        data, _ = adapter._load_source()
        total_rows = sum(len(rows) for rows in data["classes"].values())
        _, facts = adapter.ingest_asme_b16_5_flanges()
        self.assertEqual(len(facts), total_rows * 6)


class TestDeterministicIngestion(unittest.TestCase):
    def test_deterministic_record_count_across_two_fresh_ingestions(self):
        _, facts1 = adapter.ingest_asme_b16_5_flanges()
        _, facts2 = adapter.ingest_asme_b16_5_flanges()
        self.assertEqual(len(facts1), len(facts2))

    def test_deterministic_ingestion_order(self):
        _, facts1 = adapter.ingest_asme_b16_5_flanges()
        _, facts2 = adapter.ingest_asme_b16_5_flanges()
        keys1 = [f.identity_key() for f in facts1]
        keys2 = [f.identity_key() for f in facts2]
        self.assertEqual(keys1, keys2)


class TestWeldNeckApplicability(unittest.TestCase):
    def test_weld_neck_thickness_has_flange_type_weld_neck(self):
        _, facts = adapter.ingest_asme_b16_5_flanges()
        thickness_facts = [f for f in facts if f.dimension_name == VOC.DIM_FLANGE_THICKNESS_WELD_NECK]
        self.assertTrue(thickness_facts)
        self.assertTrue(all(f.applicability.flange_type == "weld_neck" for f in thickness_facts))

    def test_shared_dimensions_have_no_false_flange_type_specificity(self):
        _, facts = adapter.ingest_asme_b16_5_flanges()
        shared_dims = (VOC.DIM_OUTSIDE_DIAMETER, VOC.DIM_BOLT_CIRCLE_DIAMETER,
                       VOC.DIM_BOLT_HOLE_DIAMETER, VOC.DIM_NUM_BOLTS, VOC.DIM_BOLT_SIZE_DESIGNATION)
        shared_facts = [f for f in facts if f.dimension_name in shared_dims]
        self.assertTrue(shared_facts)
        self.assertTrue(all(f.applicability.flange_type is None for f in shared_facts))


class TestProvenancePresence(unittest.TestCase):
    def test_every_fact_has_source_file_and_original_field(self):
        _, facts = adapter.ingest_asme_b16_5_flanges()
        for f in facts:
            self.assertIsNotNone(f.provenance.source_file)
            self.assertIsNotNone(f.provenance.original_field)
            self.assertEqual(f.provenance.standard_designation, "ASME B16.5")

    def test_standard_edition_read_from_source_header_not_fabricated(self):
        _, facts = adapter.ingest_asme_b16_5_flanges()
        editions = {f.provenance.standard_edition for f in facts}
        # The source file's own "standard" header literally contains
        # "ASME B16.5-2022" - this is read directly, not invented.
        self.assertEqual(editions, {"2022"})


class TestDuplicateAndConflictHandling(unittest.TestCase):
    def test_re_ingesting_into_the_same_registry_is_an_exact_duplicate_noop(self):
        registry = FactRegistry()
        adapter.ingest_asme_b16_5_flanges(registry)
        count_after_first = len(registry.all_facts())
        adapter.ingest_asme_b16_5_flanges(registry)
        count_after_second = len(registry.all_facts())
        self.assertEqual(count_after_first, count_after_second)

    def test_conflicting_duplicate_is_rejected_not_overwritten(self):
        registry = FactRegistry()
        applicability = Applicability(product_family="flange", standard="ASME_B16.5", class_key="150", nps="2")
        fact_a = EngineeringFact(
            dimension_name=VOC.DIM_OUTSIDE_DIAMETER, value=Quantity(152.4, LENGTH_MM),
            applicability=applicability, verification_status=V.VERIFIED_AUTHORITATIVE,
            provenance=EngineeringFactProvenance(source_name="A"),
        )
        fact_b_conflicting = EngineeringFact(
            dimension_name=VOC.DIM_OUTSIDE_DIAMETER, value=Quantity(999.9, LENGTH_MM),
            applicability=applicability, verification_status=V.VERIFIED_AUTHORITATIVE,
            provenance=EngineeringFactProvenance(source_name="B"),
        )
        registry.add_checked(fact_a)
        with self.assertRaises(ConflictingDuplicateFact):
            registry.add_checked(fact_b_conflicting)
        # The original value must still be the one in the registry - never silently overwritten.
        results = registry.query(VOC.DIM_OUTSIDE_DIAMETER, standard="ASME_B16.5", class_key="150", nps="2")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].value.value, 152.4)


class TestMalformedSourceRejection(unittest.TestCase):
    def test_missing_required_row_field_is_rejected(self):
        bad_row = {"NPS": "2", "OD_mm": 152.4}  # missing several required fields
        errors = adapter._validate_row("150", 0, bad_row)
        self.assertTrue(errors)

    def test_non_positive_dimension_is_rejected(self):
        bad_row = {"NPS": "2", "OD_mm": -1.0, "Thickness_WeldNeck_mm": 17.53,
                   "BoltCircle_mm": 120.65, "BoltHoleDia_mm": 19.05, "NumBolts": 4, "BoltSize_in": "5/8"}
        errors = adapter._validate_row("150", 0, bad_row)
        self.assertTrue(any("OD_mm" in e for e in errors))

    def test_non_string_nps_is_rejected(self):
        bad_row = {"NPS": 2.0, "OD_mm": 152.4, "Thickness_WeldNeck_mm": 17.53,
                   "BoltCircle_mm": 120.65, "BoltHoleDia_mm": 19.05, "NumBolts": 4, "BoltSize_in": "5/8"}
        errors = adapter._validate_row("150", 0, bad_row)
        self.assertTrue(any("NPS" in e for e in errors))

    def test_missing_top_level_key_is_rejected(self):
        with self.assertRaises(SourceValidationError):
            adapter._validate_top_level({"standard": "x"})  # missing 'classes', 'columns'


class TestAuthoritativeLookupProof(unittest.TestCase):
    """Values below are copied directly from the source JSON as read in
    this prompt - not recomputed - so this proves the ingested canonical
    facts match the real file, not just each other."""

    @classmethod
    def setUpClass(cls):
        cls.registry, _ = adapter.ingest_asme_b16_5_flanges()

    def _q(self, dim, **filters):
        return self.registry.query(dim, standard="ASME_B16.5", **filters)[0].value.value

    def test_small_nps_class_150(self):
        self.assertEqual(self._q(VOC.DIM_OUTSIDE_DIAMETER, class_key="150", nps="1/2"), 88.9)
        self.assertEqual(self._q(VOC.DIM_FLANGE_THICKNESS_WELD_NECK, class_key="150", nps="1/2", flange_type="weld_neck"), 9.65)
        self.assertEqual(self._q(VOC.DIM_BOLT_CIRCLE_DIAMETER, class_key="150", nps="1/2"), 60.45)
        self.assertEqual(self._q(VOC.DIM_BOLT_HOLE_DIAMETER, class_key="150", nps="1/2"), 15.88)
        self.assertEqual(self._q(VOC.DIM_NUM_BOLTS, class_key="150", nps="1/2"), 4)

    def test_mid_range_nps_class_300(self):
        self.assertEqual(self._q(VOC.DIM_OUTSIDE_DIAMETER, class_key="300", nps="6"), 317.5)
        self.assertEqual(self._q(VOC.DIM_FLANGE_THICKNESS_WELD_NECK, class_key="300", nps="6", flange_type="weld_neck"), 35.05)
        self.assertEqual(self._q(VOC.DIM_BOLT_CIRCLE_DIAMETER, class_key="300", nps="6"), 269.75)
        self.assertEqual(self._q(VOC.DIM_BOLT_HOLE_DIAMETER, class_key="300", nps="6"), 22.22)
        self.assertEqual(self._q(VOC.DIM_NUM_BOLTS, class_key="300", nps="6"), 12)

    def test_higher_pressure_class_1500(self):
        self.assertEqual(self._q(VOC.DIM_OUTSIDE_DIAMETER, class_key="1500", nps="6"), 393.7)
        self.assertEqual(self._q(VOC.DIM_FLANGE_THICKNESS_WELD_NECK, class_key="1500", nps="6", flange_type="weld_neck"), 82.55)
        self.assertEqual(self._q(VOC.DIM_BOLT_CIRCLE_DIAMETER, class_key="1500", nps="6"), 317.5)
        self.assertEqual(self._q(VOC.DIM_BOLT_HOLE_DIAMETER, class_key="1500", nps="6"), 38.1)
        self.assertEqual(self._q(VOC.DIM_NUM_BOLTS, class_key="1500", nps="6"), 12)


class TestProductionQuarantineProof(unittest.TestCase):
    def setUp(self):
        self.registry, _ = adapter.ingest_asme_b16_5_flanges()
        load_legacy_crm_quarantine_fixture(self.registry)

    def test_quarantined_rf_conflict_blocked_from_authoritative_query(self):
        with self.assertRaises(DimensionQuarantined):
            self.registry.query(VOC.DIM_RAISED_FACE_DIAMETER, standard="ASME_B16.5", class_key="150", nps="14")

    def test_quarantined_records_visible_via_explicit_inspector(self):
        quarantined = self.registry.get_quarantined()
        codes = {(q.dimension_name, q.applicability.nps, q.applicability.class_key) for q in quarantined}
        self.assertIn((VOC.DIM_RAISED_FACE_DIAMETER, "14", "150"), codes)
        self.assertIn((VOC.DIM_LENGTH_THROUGH_HUB, "2", "300"), codes)
        self.assertEqual(len(quarantined), 3)

    def test_real_authoritative_facts_still_reachable_alongside_quarantine(self):
        # Proves quarantined fixture data doesn't contaminate real lookups.
        results = self.registry.query(VOC.DIM_OUTSIDE_DIAMETER, standard="ASME_B16.5", class_key="150", nps="2")
        self.assertEqual(results[0].value.value, 152.4)


class TestExhaustiveComparisonAgainstDimensionLibrary(unittest.TestCase):
    def test_full_cross_check_zero_unexplained_mismatches(self):
        _, facts = adapter.ingest_asme_b16_5_flanges()
        by_combo = defaultdict(dict)
        for f in facts:
            key = (f.applicability.class_key, f.applicability.nps)
            by_combo[key][f.dimension_name] = f

        field_map = {
            VOC.DIM_OUTSIDE_DIAMETER: "OD_mm",
            VOC.DIM_FLANGE_THICKNESS_WELD_NECK: "Thickness_mm",
            VOC.DIM_BOLT_CIRCLE_DIAMETER: "BoltCircle_mm",
            VOC.DIM_BOLT_HOLE_DIAMETER: "BoltHoleDia_mm",
            VOC.DIM_NUM_BOLTS: "NumBolts",
            VOC.DIM_BOLT_SIZE_DESIGNATION: "BoltSize",
        }

        total_comparable = 0
        exact_matches = 0
        rounding_matches = 0
        mismatches = []
        not_comparable = 0

        for (class_key, nps), dims in by_combo.items():
            try:
                live_dims, _src = dl.get_flange("ASME_B16.5", nps, class_key)
            except dl.DimNotFound:
                not_comparable += len(dims)
                continue
            for dim_name, live_key in field_map.items():
                fact = dims.get(dim_name)
                live_value = live_dims.get(live_key)
                if fact is None or live_value is None:
                    not_comparable += 1
                    continue
                total_comparable += 1
                canonical_value = fact.value.value
                if canonical_value == live_value:
                    exact_matches += 1
                elif isinstance(canonical_value, (int, float)) and isinstance(live_value, (int, float)) \
                        and abs(canonical_value - live_value) < 1e-6:
                    rounding_matches += 1
                else:
                    mismatches.append((class_key, nps, dim_name, canonical_value, live_value))

        print(f"\n[Prompt 5 cross-check] combinations={len(by_combo)} total_comparable={total_comparable} "
              f"exact={exact_matches} rounding_equivalent={rounding_matches} "
              f"mismatches={len(mismatches)} not_comparable={not_comparable}")
        self.assertEqual(mismatches, [], f"Unexplained mismatches: {mismatches}")
        self.assertGreater(total_comparable, 0)
        self.assertEqual(exact_matches + rounding_matches, total_comparable)


class TestBackwardCompatibility(unittest.TestCase):
    def test_existing_flange_generation_path_unaffected(self):
        req = {"product_type": "flange", "standard": "ASME_B16.5", "size": "2",
               "class_key": "150", "pipe_schedule": "Sch40"}
        result = generate_geometry(req)
        self.assertEqual(result["status"], "OK")

    def test_existing_dimension_library_lookup_unaffected(self):
        dims, source = dl.get_flange("ASME_B16.5", "2", "150")
        self.assertEqual(dims["OD_mm"], 152.4)
        self.assertEqual(source["standard"], "ASME B16.5 Class 150")


if __name__ == "__main__":
    unittest.main(verbosity=2)
