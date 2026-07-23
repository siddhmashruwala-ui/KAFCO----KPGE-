# -*- coding: utf-8 -*-
"""
Automated tests for Prompt 8 - completing migration of all remaining
structured engineering datasets (ASME B16.11, MSS SP-97, JIS x3, EN x3)
and the complete canonical registry build.

Run with:
    cd "Dimensions and Standards/Engine/KGPE"
    python -m unittest discover -s tests -p "test_*.py" -v

Uses only the Python standard library `unittest`.
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from kgpe import dimension_library as dl
from kgpe.generator import generate_geometry
from kgpe.contract import vocabulary as VOC
from kgpe.contract import verification as V
from kgpe.contract.model import CombinationNotFound, DimensionQuarantined
from kgpe.contract.normalization import (
    normalize_dn, dn_sort_key, normalize_jis_size, jis_size_sort_key,
    normalize_wall_designation, normalize_pressure_class,
)
from kgpe.contract.vocabulary import RATING_SYSTEM_JIS_K
from kgpe.contract.adapters import asme_b16_11_socketweld as b1611
from kgpe.contract.adapters import mss_sp97_olets as mss
from kgpe.contract.adapters import jis_b2220_flanges as jis_fl
from kgpe.contract.adapters import jis_pipes as jis_pipe
from kgpe.contract.adapters import jis_buttweld as jis_bw
from kgpe.contract.adapters import en_1092_flanges as en_fl
from kgpe.contract.adapters import en_pipes as en_pipe
from kgpe.contract.adapters import en_buttweld as en_bw
from kgpe.contract.registry_builder import build_canonical_registry, registry_statistics, _ADAPTERS


# ---------------------------------------------------------------------------
# 1. Inventory
# ---------------------------------------------------------------------------
class TestInventoryComplete(unittest.TestCase):
    def test_all_eleven_datasets_have_an_adapter_in_the_builder(self):
        # 11 Prompt 5-8 datasets + KAFCO_Nipoflange (added post-Prompt-9,
        # 2026-07-20 - a genuine 12th approved dataset with no
        # dimension_library.py live-lookup counterpart; see
        # kgpe/contract/data_layer_audit.py's _DATASET_TABLE dl_key=None
        # exception for the same fact).
        self.assertEqual(len(_ADAPTERS), 12)

    def test_every_ai_readable_file_maps_to_exactly_one_registered_standard_id(self):
        # 3 flange + 3 pipe + 3 buttweld + 1 socketweld + 1 olet = 11 files total,
        # matching the actual AI-Readable inventory (Prompt 8 Sec.2).
        all_ids = set(dl.FLANGE_FILES) | set(dl.PIPE_FILES) | set(dl.BUTTWELD_FILES) \
            | set(dl.SOCKETWELD_FILES) | set(dl.OLET_FILES)
        self.assertEqual(len(all_ids), 11)


# ---------------------------------------------------------------------------
# 2. Normalization
# ---------------------------------------------------------------------------
class TestNewNormalization(unittest.TestCase):
    def test_dn_variants_normalize_consistently(self):
        self.assertEqual(normalize_dn("50"), "DN50")
        self.assertEqual(normalize_dn(50), "DN50")
        self.assertEqual(normalize_dn("DN50"), "DN50")
        self.assertEqual(normalize_dn("DN 50"), "DN50")

    def test_dn_sort_key_is_exact_int(self):
        self.assertEqual(dn_sort_key("DN50"), 50)
        self.assertLess(dn_sort_key("DN50"), dn_sort_key("DN100"))

    def test_jis_size_variants_normalize_consistently(self):
        self.assertEqual(normalize_jis_size("50"), "50A")
        self.assertEqual(normalize_jis_size(50), "50A")
        self.assertEqual(normalize_jis_size("50A"), "50A")
        self.assertEqual(normalize_jis_size("50 A"), "50A")

    def test_jis_size_sort_key_is_exact_int(self):
        self.assertEqual(jis_size_sort_key("50A"), 50)

    def test_wall_designation_normalizes_and_is_en_prefixed(self):
        self.assertEqual(normalize_wall_designation("Series3"), "EN_SERIES3")
        self.assertEqual(normalize_wall_designation("SERIES 5"), "EN_SERIES5")
        self.assertTrue(normalize_wall_designation("Series1").startswith("EN_"))

    def test_dn_and_jis_size_and_nps_never_collide_by_construction(self):
        # Same numeric value, three different size systems - must remain
        # textually distinct so no accidental cross-system query is possible.
        self.assertNotEqual(normalize_dn(50), normalize_jis_size(50))
        from kgpe.contract.normalization import normalize_nps
        self.assertNotEqual(normalize_dn(50), normalize_nps(50))
        self.assertNotEqual(normalize_jis_size(50), normalize_nps(50))

    def test_k_rating_normalization_reused_from_prompt4(self):
        # Not a new function - proves the existing normalize_pressure_class
        # JIS_K branch (declared in Prompt 4) is what JIS flange ingestion
        # actually uses, not a duplicate implementation.
        self.assertEqual(normalize_pressure_class("5K", RATING_SYSTEM_JIS_K), "5K")
        self.assertEqual(normalize_pressure_class("10K", RATING_SYSTEM_JIS_K), "10K")


# ---------------------------------------------------------------------------
# 3. ASME B16.11 socketweld
# ---------------------------------------------------------------------------
class TestAsmeB1611Socketweld(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry, cls.facts = b1611.ingest_asme_b16_11_socketweld()

    def test_ingestion_succeeds(self):
        self.assertGreater(len(self.facts), 0)

    def test_five_socket_dimension_pairs_present_for_elbow(self):
        r = self.registry.query(VOC.DIM_SOCKET_BORE_DEPTH_MAX, standard="ASME_B16.11",
                                fitting_type=VOC.FITTING_TYPE_ELBOW_90_SW, class_key="3000", nps="1")
        self.assertEqual(r[0].value.value, 34.05)

    def test_tee_and_cross_share_value_but_distinct_identity(self):
        tee = self.registry.query(VOC.DIM_CENTRE_TO_END, standard="ASME_B16.11",
                                  fitting_type=VOC.FITTING_TYPE_TEE_SW, class_key="3000", nps="1/2")[0]
        cross = self.registry.query(VOC.DIM_CENTRE_TO_END, standard="ASME_B16.11",
                                    fitting_type=VOC.FITTING_TYPE_CROSS_SW, class_key="3000", nps="1/2")[0]
        self.assertEqual(tee.value.value, cross.value.value)
        self.assertNotEqual(tee.identity_key(), cross.identity_key())

    def test_unavailable_combination_fails_closed(self):
        # Class 9000 does not exist in this source at all.
        with self.assertRaises(CombinationNotFound):
            self.registry.query(VOC.DIM_CENTRE_TO_END, standard="ASME_B16.11",
                                fitting_type=VOC.FITTING_TYPE_ELBOW_90_SW, class_key="9000", nps="1")

    def test_class_6000_narrower_nps_range_fails_closed_above_nps2(self):
        with self.assertRaises(CombinationNotFound):
            self.registry.query(VOC.DIM_CENTRE_TO_END, standard="ASME_B16.11",
                                fitting_type=VOC.FITTING_TYPE_ELBOW_90_SW, class_key="6000", nps="3")

    def test_deterministic(self):
        _, facts2 = b1611.ingest_asme_b16_11_socketweld()
        self.assertEqual(len(facts2), len(self.facts))
        self.assertEqual([f.identity_key() for f in facts2], [f.identity_key() for f in self.facts])


# ---------------------------------------------------------------------------
# 4. MSS SP-97
# ---------------------------------------------------------------------------
class TestMssSp97Olets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry, cls.facts = mss.ingest_mss_sp97_olets()

    def test_ingestion_succeeds(self):
        self.assertGreater(len(self.facts), 0)

    def test_run_and_branch_roles_are_not_interchangeable(self):
        # Official height table: run_nps populated, branch_nps never set.
        official = [f for f in self.facts if f.dimension_name == VOC.DIM_BRANCH_OUTLET_HEIGHT]
        self.assertTrue(all(f.applicability.run_nps is not None for f in official))
        self.assertTrue(all(f.applicability.branch_nps is None for f in official))
        # Sockolet/threadolet body dims: branch_nps populated, run_nps never set.
        sockolets = [f for f in self.facts if f.applicability.fitting_type == VOC.FITTING_TYPE_SOCKOLET]
        self.assertTrue(all(f.applicability.branch_nps is not None for f in sockolets))
        self.assertTrue(all(f.applicability.run_nps is None for f in sockolets))

    def test_official_height_table_is_verified_authoritative(self):
        r = self.registry.query(VOC.DIM_BRANCH_OUTLET_HEIGHT, standard="MSS_SP97",
                                fitting_type=VOC.FITTING_TYPE_WELDOLET_FULL, run_nps="2", schedule="STD")
        self.assertEqual(r[0].verification_status, V.VERIFIED_AUTHORITATIVE)

    def test_manufacturer_body_dims_are_manufacturer_specific_not_authoritative(self):
        weldolet_facts = [f for f in self.facts if f.applicability.fitting_type == VOC.FITTING_TYPE_WELDOLET]
        self.assertTrue(all(f.verification_status == V.VERIFIED_MANUFACTURER_SPECIFIC for f in weldolet_facts))
        self.assertTrue(all(f.applicability.manufacturer_profile == "Bonney Forge" for f in weldolet_facts))
        with self.assertRaises(DimensionQuarantined):
            self.registry.query(VOC.DIM_OLET_HEIGHT, standard="MSS_SP97",
                                fitting_type=VOC.FITTING_TYPE_WELDOLET, branch_nps="4")

    def test_no_heuristic_crm_geometry_ingested(self):
        # This adapter never opens a CRM HTML/JS file - a static-analysis
        # check that it only ever reads via load_json_source() against
        # dl.OLET_FILES (the mention of "nipoflange" in the module's own
        # docstring is documentation explaining what is deliberately NOT
        # ingested, not a data source reference, so that word itself is
        # not the right thing to forbid here).
        import inspect
        source = inspect.getsource(mss)
        self.assertNotIn(".html", source.lower())
        self.assertNotIn(".js\"", source.lower())
        self.assertIn("load_json_source", source)
        self.assertIn("dl.OLET_FILES", source)

    def test_deterministic(self):
        _, facts2 = mss.ingest_mss_sp97_olets()
        self.assertEqual(len(facts2), len(self.facts))


# ---------------------------------------------------------------------------
# 5. JIS datasets
# ---------------------------------------------------------------------------
class TestJisFlange(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry, cls.facts = jis_fl.ingest_jis_b2220_flanges()

    def test_representative_lookup(self):
        r = self.registry.query(VOC.DIM_OUTSIDE_DIAMETER, standard="JIS_B2220", class_key="10K", jis_size="50A")
        self.assertEqual(r[0].value.value, 155)

    def test_k_rating_identity_preserved(self):
        r5k = self.registry.query(VOC.DIM_OUTSIDE_DIAMETER, standard="JIS_B2220", class_key="5K", jis_size="50A")
        r10k = self.registry.query(VOC.DIM_OUTSIDE_DIAMETER, standard="JIS_B2220", class_key="10K", jis_size="50A")
        self.assertNotEqual(r5k[0].value.value, r10k[0].value.value)


class TestJisPipe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry, cls.facts = jis_pipe.ingest_jis_pipes()

    def test_representative_lookup_sgp(self):
        r = self.registry.query(VOC.DIM_WALL_THICKNESS, standard=jis_pipe.JIS_G3452, jis_size="50A")
        self.assertEqual(r[0].value.value, 3.8)

    def test_representative_lookup_stpg_schedule(self):
        r = self.registry.query(VOC.DIM_WALL_THICKNESS, standard=jis_pipe.JIS_G3454, jis_size="50A", schedule="SCH40")
        self.assertEqual(r[0].value.value, 3.9)

    def test_cross_standard_same_value_distinct_identity(self):
        stpg = self.registry.query(VOC.DIM_WALL_THICKNESS, standard=jis_pipe.JIS_G3454, jis_size="50A", schedule="SCH40")[0]
        sus = self.registry.query(VOC.DIM_WALL_THICKNESS, standard=jis_pipe.JIS_G3459, jis_size="50A", schedule="SCH40")[0]
        self.assertEqual(stpg.value.value, sus.value.value)
        self.assertNotEqual(stpg.identity_key(), sus.identity_key())


class TestJisButtweld(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry, cls.facts = jis_bw.ingest_jis_buttweld()

    def test_representative_lookup(self):
        r = self.registry.query(VOC.DIM_CENTRE_TO_END, standard="JIS_B2311_2312",
                                fitting_type=VOC.FITTING_TYPE_ELBOW_90_LR_JIS, jis_size="100A")
        self.assertEqual(r[0].value.value, 152.4)

    def test_reducer_sample_is_partial_not_extrapolated(self):
        # Only the 7 sampled pairs exist - any other pair must fail closed.
        with self.assertRaises(CombinationNotFound):
            self.registry.query(VOC.DIM_END_TO_END, standard="JIS_B2311_2312",
                                fitting_type=VOC.FITTING_TYPE_REDUCER_CONCENTRIC_JIS,
                                large_end_jis_size="65A", small_end_jis_size="50A")


# ---------------------------------------------------------------------------
# 6. EN datasets
# ---------------------------------------------------------------------------
class TestEnFlange(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry, cls.facts = en_fl.ingest_en_1092_flanges()

    def test_representative_lookup(self):
        r = self.registry.query(VOC.DIM_OUTSIDE_DIAMETER, standard="EN_1092-1", class_key="PN16", dn="DN50")
        self.assertEqual(r[0].value.value, 165)

    def test_pn_identity_preserved_not_forced_to_asme_class(self):
        r_pn16 = self.registry.query(VOC.DIM_OUTSIDE_DIAMETER, standard="EN_1092-1", class_key="PN16", dn="DN50")
        r_pn40 = self.registry.query(VOC.DIM_OUTSIDE_DIAMETER, standard="EN_1092-1", class_key="PN40", dn="DN50")
        self.assertEqual(r_pn16[0].value.value, r_pn40[0].value.value)  # coincidentally equal at this size
        self.assertNotEqual(r_pn16[0].identity_key(), r_pn40[0].identity_key())


class TestEnPipe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry, cls.facts = en_pipe.ingest_en_pipes()

    def test_representative_lookup(self):
        r = self.registry.query(VOC.DIM_WALL_THICKNESS, standard="EN_10216_10217", dn="DN150", schedule="EN_SERIES3")
        self.assertEqual(r[0].value.value, 4.5)

    def test_sch_equivalent_columns_not_ingested(self):
        # Sch40_equiv/Sch80_equiv are explicitly excluded (Prompt 8 Sec.16/17) -
        # no fact should exist under an ASME-style "SCH.." schedule for this standard.
        with self.assertRaises(CombinationNotFound):
            self.registry.query(VOC.DIM_WALL_THICKNESS, standard="EN_10216_10217", dn="DN150", schedule="SCH40")

    def test_dn_not_forced_into_nps(self):
        facts_dn = [f for f in self.facts if f.applicability.dn is not None]
        facts_nps = [f for f in self.facts if f.applicability.nps is not None]
        self.assertGreater(len(facts_dn), 0)
        self.assertEqual(len(facts_nps), 0)


class TestEnButtweld(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry, cls.facts = en_bw.ingest_en_buttweld()

    def test_representative_lookup(self):
        r = self.registry.query(VOC.DIM_CENTRE_TO_END, standard="EN_10253",
                                fitting_type=VOC.FITTING_TYPE_ELBOW_90_EN, dn="DN100")
        self.assertEqual(r[0].value.value, 152.5)

    def test_derived_45deg_column_not_ingested(self):
        with self.assertRaises(CombinationNotFound):
            self.registry.query(VOC.DIM_CENTRE_TO_END, standard="EN_10253",
                                fitting_type="elbow_45_en", dn="DN100")

    def test_reducer_not_duplicated_as_eccentric(self):
        with self.assertRaises(CombinationNotFound):
            self.registry.query(VOC.DIM_END_TO_END, standard="EN_10253", fitting_type="reducer_eccentric_en",
                                large_end_dn="DN100", small_end_dn="DN80")

    def test_newly_discovered_od_wt_conflicts_are_quarantined(self):
        conflicts = self.registry.get_quarantined()
        conflicted_dns = {f.applicability.dn for f in conflicts}
        self.assertEqual(conflicted_dns, {"DN450", "DN600", "DN200", "DN500"})
        for f in conflicts:
            self.assertEqual(f.verification_status, V.QUARANTINED_CONFLICT)
        with self.assertRaises(DimensionQuarantined):
            self.registry.query(VOC.DIM_OUTSIDE_DIAMETER, standard="EN_10253", dn="DN450")

    def test_unaffected_dn_remains_authoritative(self):
        r = self.registry.query(VOC.DIM_OUTSIDE_DIAMETER, standard="EN_10253", dn="DN100")
        self.assertEqual(r[0].value.value, 114.3)
        self.assertEqual(r[0].verification_status, V.VERIFIED_AUTHORITATIVE)

    def test_deterministic_and_idempotent(self):
        _, facts2 = en_bw.ingest_en_buttweld()
        self.assertEqual(len(facts2), len(self.facts))
        from kgpe.contract.model import FactRegistry
        registry = FactRegistry()
        en_bw.ingest_en_buttweld(registry)
        c1 = len(registry.all_facts())
        en_bw.ingest_en_buttweld(registry)
        self.assertEqual(c1, len(registry.all_facts()))


# ---------------------------------------------------------------------------
# 7. Complete canonical registry build
# ---------------------------------------------------------------------------
class TestCompleteRegistryBuild(unittest.TestCase):
    def test_build_succeeds_and_is_deterministic(self):
        registry1, counts1 = build_canonical_registry()
        registry2, counts2 = build_canonical_registry()
        self.assertEqual(counts1, counts2)
        self.assertEqual(len(registry1.all_facts()), len(registry2.all_facts()))
        self.assertEqual([f.identity_key() for f in registry1.all_facts()],
                         [f.identity_key() for f in registry2.all_facts()])

    def test_all_eleven_adapters_contribute(self):
        registry, counts = build_canonical_registry()
        # 11 Prompt 5-8 adapters + KAFCO_Nipoflange (post-Prompt-9) = 12.
        self.assertEqual(len(counts), 12)
        for name, count in counts:
            self.assertGreater(count, 0, f"{name} contributed zero facts")

    def test_known_quarantines_remain_present_and_inaccessible_via_query(self):
        registry, _ = build_canonical_registry()
        q = registry.get_quarantined()
        self.assertGreaterEqual(len(q), 16)
        with self.assertRaises(DimensionQuarantined):
            registry.query(VOC.DIM_OUTSIDE_DIAMETER, standard="ASME_B16.9", nps="12")
        with self.assertRaises(DimensionQuarantined):
            registry.query(VOC.DIM_OUTSIDE_DIAMETER, standard="EN_10253", dn="DN600")

    def test_registry_statistics_computed_not_hand_estimated(self):
        registry, _ = build_canonical_registry()
        stats = registry_statistics(registry)
        self.assertEqual(stats["total_facts"], len(registry.all_facts()))
        self.assertEqual(
            stats["authoritative_facts"] + stats["quarantined_facts"] + stats["manufacturer_specific_facts"],
            stats["total_facts"])

    def test_no_network_dependency(self):
        # Static-analysis-style check: none of the new adapter modules
        # import a networking library. Checks actual import statements,
        # not bare substrings - "socket" legitimately appears throughout
        # the ASME B16.11/MSS text as an engineering term (socket-weld,
        # socket bore, etc), so a substring check would false-positive.
        import inspect
        for mod in (b1611, mss, jis_fl, jis_pipe, jis_bw, en_fl, en_pipe, en_bw):
            source = inspect.getsource(mod)
            import_lines = [line.strip() for line in source.splitlines()
                            if line.strip().startswith("import ") or line.strip().startswith("from ")]
            for line in import_lines:
                for forbidden in ("requests", "urllib", "http.client", "import socket", "socketserver"):
                    self.assertNotIn(forbidden, line, f"{mod.__name__} has a networking import: {line!r}")


# ---------------------------------------------------------------------------
# 8. Backward compatibility / regression
# ---------------------------------------------------------------------------
class TestBackwardCompatibility(unittest.TestCase):
    def test_existing_flange_generation_unaffected(self):
        req = {"product_type": "flange", "standard": "ASME_B16.5", "size": "2", "class_key": "150", "pipe_schedule": "Sch40"}
        result = generate_geometry(req)
        self.assertEqual(result["status"], "OK")

    def test_existing_jis_flange_live_lookup_unaffected(self):
        dims, _src = dl.get_flange("JIS_B2220", 50, "10K")
        self.assertEqual(dims["OD_mm"], 155)

    def test_existing_en_flange_live_lookup_unaffected(self):
        dims, _src = dl.get_flange("EN_1092-1", 50, "PN16")
        self.assertEqual(dims["OD_mm"], 165)


if __name__ == "__main__":
    unittest.main(verbosity=2)
