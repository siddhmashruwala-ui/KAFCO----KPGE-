# -*- coding: utf-8 -*-
"""
tests.test_nipoflange_geometry
==================================
2026-07-21 (CRM production audit): regression coverage for the nipoflange
product generator and the pipeline-level construction-input derivation -
the two pieces that closed the "UNSUPPORTED_GEOMETRY_PROFILE -> CRM
heuristic fallback" gap. Also locks in the subtype-dispatch guarantee the
CRM hologram now relies on: every flange subtype profile generates its
OWN geometry (distinct fingerprints), never a shared/generic body.
"""
import unittest

from kgpe.contract.canonical_reader import build_canonical_reader
from kgpe.contract.snapshot import registry_fingerprint
from kgpe.resolver import EngineeringResolver, EngineeringRequest
from kgpe.geometry.pipeline import run_pipeline


def _nipo_request(size="2", pressure_class="150"):
    return EngineeringRequest(
        product_family="flange", subtype="nipoflange", standard="KAFCO_NIPOFLANGE",
        size_system="nps", primary_size=size, pressure_class=pressure_class,
        manufacturer_profile="KAFCO", allow_manufacturer_specific=True)


class NipoflangeGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reader, _issues = build_canonical_reader()
        cls.resolver = EngineeringResolver(reader, registry_fingerprint(reader.registry))

    def test_reducing_nipoflange_generates_with_weldolet_outlet(self):
        res = run_pipeline(_nipo_request(), resolver=self.resolver,
                            product_kwargs={"reduced_tip_size": "1"})
        self.assertIsNone(res.failed_stage)
        gr = res.geometry_result
        self.assertEqual(gr.generation_status, "GEOMETRY_GENERATED")
        self.assertEqual(gr.geometry_type, "flange_nipoflange")
        gp = gr.geometry_payload
        meas = gp["measurements"]
        # KAFCO catalog class150 NPS2 row: A=152, D=19, B=150.
        self.assertAlmostEqual(meas["nipoflange_flange_od_mm"], 152.0, places=1)
        self.assertAlmostEqual(meas["nipoflange_flange_thickness_mm"], 19.0, places=1)
        self.assertAlmostEqual(meas["nipoflange_overall_length_mm"], 150.0, places=1)
        # neck = 2" pipe OD, tip = 1" pipe OD - and the tip is genuinely smaller.
        self.assertAlmostEqual(meas["neck_outside_diameter_mm"], 60.3, places=1)
        self.assertAlmostEqual(meas["tip_outside_diameter_mm"], 33.4, places=1)
        self.assertLess(meas["tip_outside_diameter_mm"], meas["neck_outside_diameter_mm"])
        # the compound assembly's sections are named features (v4 names).
        names = [f["name"] for f in gp["features"]]
        for expected in ("flange_outer_wall", "hub_cone", "reducing_taper",
                          "reduced_outlet_stub", "undercut_relief", "olet_crown",
                          "weld_prep_bevel"):
            self.assertIn(expected, names)
        self.assertTrue(gr.dimensional_validation_summary["passed"])
        self.assertTrue(gr.geometry_validation_summary["passed"])

    def test_straight_nipoflange_generates_without_reduction_features(self):
        res = run_pipeline(_nipo_request(pressure_class="300"), resolver=self.resolver)
        gr = res.geometry_result
        self.assertEqual(gr.generation_status, "GEOMETRY_GENERATED")
        names = [f["name"] for f in gr.geometry_payload["features"]]
        self.assertNotIn("reducing_taper", names)
        self.assertIn("neck_barrel", names)
        self.assertIn("weld_prep_bevel", names)
        self.assertIn("bore_not_modeled", names)

    def test_reducing_is_deterministic(self):
        kwargs = {"reduced_tip_size": "1"}
        fp1 = run_pipeline(_nipo_request(), resolver=self.resolver,
                            product_kwargs=dict(kwargs)).geometry_result.geometry_fingerprint
        fp2 = run_pipeline(_nipo_request(), resolver=self.resolver,
                            product_kwargs=dict(kwargs)).geometry_result.geometry_fingerprint
        self.assertEqual(fp1, fp2)

    def test_reversed_reduction_fails_closed(self):
        # "reduced" tip equal to the branch size is a contradiction - the
        # builder must refuse, never render something invented.
        res = run_pipeline(_nipo_request(), resolver=self.resolver,
                            product_kwargs={"reduced_tip_size": "2"})
        gr = res.geometry_result
        self.assertNotEqual(gr.generation_status, "GEOMETRY_GENERATED")

    def test_flange_subtypes_generate_distinct_geometry(self):
        # The CRM hologram renders geometry_payload.mesh directly - so each
        # subtype must remain its OWN geometry, never a shared generic body.
        fps = {}
        for sub in ("weld_neck", "slip_on", "blind", "socket_weld", "threaded", "lap_joint"):
            req = EngineeringRequest(product_family="flange", subtype=sub, standard="ASME_B16.5",
                                      size_system="nps", primary_size="2", pressure_class="150")
            res = run_pipeline(req, resolver=self.resolver)
            gr = res.geometry_result
            self.assertEqual(gr.generation_status, "GEOMETRY_GENERATED",
                              f"{sub} no longer generates: {res.failed_stage}")
            self.assertEqual(gr.geometry_type, f"flange_{sub}")
            fps[sub] = gr.geometry_fingerprint
        # weld_neck (hub) vs slip_on (flat) vs blind (solid) must all differ.
        self.assertNotEqual(fps["weld_neck"], fps["slip_on"])
        self.assertNotEqual(fps["slip_on"], fps["blind"])
        self.assertNotEqual(fps["weld_neck"], fps["blind"])


if __name__ == "__main__":
    unittest.main()
