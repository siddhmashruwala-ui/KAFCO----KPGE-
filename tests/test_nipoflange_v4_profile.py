# -*- coding: utf-8 -*-
"""
tests.test_nipoflange_v4_profile
====================================
R1-R7 of the v4 spec, implemented as mesh-envelope assertions computed off
the ACTUAL generated vertices (r_out(z)/r_in(z)) plus payload features /
measurements / provenance. Test identity: 2" cl150 KAFCO reducing to 1",
Sch160. Catalog: A=152, B=150, D=19; neck 60.3, outlet 33.4, bore 20.7.
"""
import math
import unittest

from kgpe.contract.canonical_reader import build_canonical_reader
from kgpe.contract.snapshot import registry_fingerprint
from kgpe.resolver import EngineeringResolver, EngineeringRequest
from kgpe.geometry.pipeline import run_pipeline
from kgpe.geometry.transition_rules import NipoflangeNeckAllocationRule
from kgpe.geometry.cross_family import FlangeBoreViaPipeScheduleRule

A, B, D = 152.0, 150.0, 19.0
NECK, OUTLET, BORE = 60.3, 33.4, 20.7
RULE = NipoflangeNeckAllocationRule()


def _req(pressure_class="150"):
    return EngineeringRequest(
        product_family="flange", subtype="nipoflange", standard="KAFCO_NIPOFLANGE",
        size_system="nps", primary_size="2", pressure_class=pressure_class,
        manufacturer_profile="KAFCO", allow_manufacturer_specific=True)


def _envelope(mesh):
    """z -> (r_out, r_in) from raw vertices; r_in None when single radius."""
    by_z = {}
    for x, y, z in mesh["vertices"]:
        r = math.hypot(x, y)
        key = round(z, 6)
        lo, hi = by_z.get(key, (r, r))
        by_z[key] = (min(lo, r), max(hi, r))
    zs = sorted(by_z)
    return zs, {z: by_z[z][1] for z in zs}, {z: by_z[z][0] for z in zs}


def _linfit_residual(pairs):
    """max |r - fit(z)| for a least-squares line r(z)."""
    n = len(pairs)
    sz = sum(p[0] for p in pairs); sr = sum(p[1] for p in pairs)
    szz = sum(p[0] * p[0] for p in pairs); szr = sum(p[0] * p[1] for p in pairs)
    denom = n * szz - sz * sz
    if abs(denom) < 1e-12:
        m, c = 0.0, sr / n
    else:
        m = (n * szr - sz * sr) / denom
        c = (sr - m * sz) / n
    return m, max(abs(r - (m * z + c)) for z, r in pairs)


class NipoflangeV4ProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reader, _ = build_canonical_reader()
        cls.resolver = EngineeringResolver(reader, registry_fingerprint(reader.registry))
        cls.sec = RULE.sections(B, D, A, NECK, OUTLET, bore_diameter_mm=BORE)
        cls.res = run_pipeline(_req(), resolver=cls.resolver,
                                product_kwargs={"reduced_tip_size": "1", "bore_schedule": "Sch160"})
        gr = cls.res.geometry_result
        assert gr is not None and gr.generation_status == "GEOMETRY_GENERATED", (
            f"pipeline did not generate: {cls.res.failed_stage} / "
            f"{gr.generation_status if gr else None} / {gr.warnings if gr else None}")
        cls.gr = gr
        cls.gp = gr.geometry_payload
        cls.zs, cls.r_out, cls.r_in_all = _envelope(cls.gp["mesh"])
        cls.feats = {f["name"]: f for f in cls.gp["features"]}

    def _log(self, name, measured, threshold):
        print(f"  CHECK {name}: measured={measured} threshold={threshold}")

    # ---------------- R1 hub ----------------
    def test_R1_hub(self):
        # the flange shoulder shares the hub-base z-plane, so the naive
        # per-z max radius at z=D is the flange OD - extract the hub band's
        # own mesh vertices via its feature vertex_range instead (still
        # computed off geometry_payload.mesh, ring by ring).
        hub = self.feats["hub_cone"]
        v0, v1 = hub["vertex_range"]
        verts = self.gp["mesh"]["vertices"][v0:v1 + 1]
        pts_all = [(round(vv[2], 6), math.hypot(vv[0], vv[1])) for vv in verts]
        by_z = {}
        for z, r in pts_all:
            by_z[z] = max(by_z.get(z, 0.0), r)
        pts = sorted(by_z.items())
        radii = [r for _z, r in pts]
        self._log("R1.monotonic", radii, "non-increasing")
        self.assertTrue(all(radii[i] >= radii[i + 1] - 1e-9 for i in range(len(radii) - 1)))
        slope, resid = _linfit_residual(pts)
        self._log("R1.residual_mm", round(resid, 4), "<=0.3")
        self.assertLessEqual(resid, 0.3)
        angle = math.degrees(math.atan(abs(slope)))
        self._log("R1.half_angle_deg", round(angle, 3), "30.0 +/-0.5")
        self.assertAlmostEqual(angle, RULE.HUB_ANGLE_DEG, delta=0.5)
        base_r = pts[0][1]
        self._log("R1.hub_base_radius", round(base_r, 3), f"{self.sec['hub_base_r']:.3f} +/-0.2")
        self.assertAlmostEqual(base_r, self.sec["hub_base_r"], delta=0.2)

    # ---------------- R2 taper ----------------
    def test_R2_taper(self):
        t0, t1 = D + self.sec["hub"], self.sec["taper_end_z"]
        pts = [(z, self.r_out[z]) for z in self.zs if t0 - 1e-6 <= z <= t1 + 1e-6]
        _m, resid = _linfit_residual(pts)
        self._log("R2.residual_mm", round(resid, 4), "<=0.3")
        self.assertLessEqual(resid, 0.3)
        expected_end = D + 0.45 * (B - D)
        self._log("R2.taper_end_z", round(t1, 3), f"{expected_end:.3f} +/-{0.01*(B-D):.2f}")
        self.assertAlmostEqual(t1, expected_end, delta=0.01 * (B - D))
        r_end = min(r for z, r in pts)
        self._log("R2.r_at_taper_end", round(r_end, 3), "16.7 +/-0.2")
        self.assertAlmostEqual(r_end, OUTLET / 2.0, delta=0.2)

    # ---------------- R3 straight run ----------------
    def test_R3_straight_run(self):
        stub = self.feats["reduced_outlet_stub"]
        t1 = self.sec["taper_end_z"]
        uc_start = t1 + stub["params"]["length_mm"]
        pts = [(z, self.r_out[z]) for z in self.zs if t1 - 1e-6 <= z <= uc_start + 1e-6]
        for z, r in pts:
            self.assertAlmostEqual(r, 16.7, delta=0.1,
                                    msg=f"stub r_out at z={z} is {r}")
        self._log("R3.r_out_over_interval", sorted({round(r, 3) for _z, r in pts}), "16.7 +/-0.1")
        length = uc_start - t1
        self._log("R3.interval_length_mm", round(length, 3), f">={0.30*(B-D):.2f}")
        self.assertGreaterEqual(length, 0.30 * (B - D))
        self._log("R3.feature_length_mm", round(stub["params"]["length_mm"], 3),
                   f"{length:.3f} +/-0.2")
        self.assertAlmostEqual(stub["params"]["length_mm"], length, delta=0.2)

    # ---------------- R4 crown + undercut ----------------
    def test_R4_crown_and_undercut(self):
        stub_len = self.feats["reduced_outlet_stub"]["params"]["length_mm"]
        uc_start = self.sec["taper_end_z"] + stub_len
        uc_end = uc_start + self.sec["undercut"]
        crown_end = uc_end + self.sec["crown"]
        crown_rs = [self.r_out[z] for z in self.zs if uc_end - 1e-6 <= z <= crown_end + 1e-6]
        crown_max = max(crown_rs)
        self._log("R4.crown_max_r", round(crown_max, 3), f"{1.15*16.7:.3f} +/-0.25 and >= 18.2")
        self.assertAlmostEqual(crown_max, 1.15 * 16.7, delta=0.25)
        self.assertGreaterEqual(crown_max, 16.7 + 1.5)
        uc_rs = [self.r_out[z] for z in self.zs if uc_start - 1e-6 <= z <= uc_end + 1e-6]
        uc_min = min(uc_rs)
        limit = 16.7 - (0.06 * OUTLET) / 2.0 + 0.1
        self._log("R4.undercut_min_r", round(uc_min, 3), f"<={limit:.3f}")
        self.assertLessEqual(uc_min, limit)
        z_stub_c = self.sec["taper_end_z"] + stub_len / 2.0
        z_crown_c = (uc_end + crown_end) / 2.0
        self._log("R4.crown_above_stub", (round(z_crown_c, 2), round(z_stub_c, 2)), "crown > stub")
        self.assertGreater(z_crown_c, z_stub_c)

    # ---------------- R5 bore + weld prep ----------------
    def test_R5_bore_and_weld_prep(self):
        # 2026-07-21 dual-bore correction: this identity is a REDUCING
        # nipoflange (2" flange x 1" outlet), so the bore is only constant
        # at 10.35mm from the reducing-taper end onward (the outlet-side
        # region) - checked here. The flange-side/transition region (which
        # carries the LARGER 2" flange bore) is covered separately by
        # test_R8_reducing_dual_bore, so it is deliberately excluded from
        # this range (was previously asserted constant end-to-end, which
        # was the bug this correction fixes).
        t1 = self.sec["taper_end_z"]
        inner = [(z, self.r_in_all[z]) for z in self.zs
                  if t1 - 1e-6 <= z <= 0.95 * B and self.r_in_all[z] < self.r_out[z] - 1e-6]
        self.assertTrue(inner, "no inner (bore) rings found in [taper_end_z, 0.95B]")
        for z, r in inner:
            self.assertAlmostEqual(r, 10.35, delta=0.1, msg=f"r_in at z={z} is {r}")
        self._log("R5.r_in_values", sorted({round(r, 3) for _z, r in inner}), "10.35 +/-0.1")
        r_top = self.r_out[max(self.zs)]
        self._log("R5.root_face_radius", round(r_top, 3), "11.95 +/-0.2")
        self.assertAlmostEqual(r_top, 10.35 + 1.6, delta=0.2)
        bevel = self.feats["weld_prep_bevel"]
        crown_r = self.sec["crown_r"]
        angle = math.degrees(math.atan((crown_r - r_top) / bevel["params"]["length_mm"]))
        self._log("R5.bevel_angle_deg", round(angle, 3), "37.5 +/-0.5")
        self.assertAlmostEqual(angle, 37.5, delta=0.5)
        self.assertLessEqual(r_top, 10.35 + 1.6 + 0.2, "flat cap wider than root face")
        # control: no schedule -> solid + bore_not_modeled with Note-4 text
        res2 = run_pipeline(_req(pressure_class="300"), resolver=self.resolver,
                             product_kwargs={"reduced_tip_size": "1"})
        gr2 = res2.geometry_result
        self.assertEqual(gr2.generation_status, "GEOMETRY_GENERATED")
        _zs, _r_out2, r_in2 = _envelope(gr2.geometry_payload["mesh"])
        # bore presence = rings well below the outlet radius (the flange
        # shoulder plane legitimately has two radii; a bore ring would sit
        # near 10.35mm, far under 0.4*outlet = 13.4mm)
        has_bore_rings = any(r_in2[z] < 0.4 * OUTLET for z in _zs if 0.1 * B < z < 0.9 * B)
        self._log("R5.control_solid", has_bore_rings, "False (no bore rings)")
        self.assertFalse(has_bore_rings)
        f2 = {f["name"]: f for f in gr2.geometry_payload["features"]}
        self.assertIn("bore_not_modeled", f2)
        self.assertIn("Note 4", f2["bore_not_modeled"]["params"]["note"])

    # ---------------- R6 trim validity ----------------
    def test_R6_trim(self):
        base = self.feats
        res120 = run_pipeline(_req(), resolver=self.resolver,
                               product_kwargs={"reduced_tip_size": "1", "bore_schedule": "Sch160",
                                                "overall_length_override": 120})
        gr120 = res120.geometry_result
        self._log("R6.B120_status", gr120.generation_status, "GEOMETRY_GENERATED")
        self.assertEqual(gr120.generation_status, "GEOMETRY_GENERATED")
        f120 = {f["name"]: f for f in gr120.geometry_payload["features"]}
        for name in ("hub_cone", "reducing_taper", "undercut_relief", "olet_crown", "weld_prep_bevel"):
            l150 = base[name]["params"]["length_mm"]
            l120 = f120[name]["params"]["length_mm"]
            self._log(f"R6.fixed.{name}", round(l120, 3), f"{l150:.3f} +/-0.1")
            self.assertAlmostEqual(l120, l150, delta=0.1)
        d_stub = (base["reduced_outlet_stub"]["params"]["length_mm"]
                   - f120["reduced_outlet_stub"]["params"]["length_mm"])
        self._log("R6.stub_delta_mm", round(d_stub, 3), "30.0 +/-0.1")
        self.assertAlmostEqual(d_stub, 30.0, delta=0.1)
        min_b = RULE.min_valid_overall_length(self.sec, OUTLET)
        res_bad = run_pipeline(_req(), resolver=self.resolver,
                                product_kwargs={"reduced_tip_size": "1", "bore_schedule": "Sch160",
                                                 "overall_length_override": min_b - 1.0})
        status = res_bad.geometry_result.generation_status
        self._log("R6.below_min_status", status, "NOT GEOMETRY_GENERATED")
        self.assertNotEqual(status, "GEOMETRY_GENERATED")

    # ---------------- R7 provenance ----------------
    def test_R7_provenance(self):
        crv = self.gr.construction_rule_versions
        self._log("R7.allocation_version", crv.get("nipoflange_neck_envelope_allocation"), "4")
        self.assertEqual(crv.get("nipoflange_neck_envelope_allocation"), "4")
        # the bore ConstructionValue carries the id of the rule that DERIVED
        # it: FlangeBoreViaPipeScheduleRule delegates the final ID = OD-2*WT
        # computation to PipeBoreConstructionRule, whose id is what lands in
        # construction_rule_versions.
        self._log("R7.bore_rule", "pipe_bore_from_od_wall_thickness" in crv, "True")
        self.assertIn("pipe_bore_from_od_wall_thickness", crv)
        bore = self.gp["measurements"]["bore_diameter_mm"]
        self._log("R7.bore_measured", round(bore, 3), "20.7 +/-0.1")
        self.assertAlmostEqual(bore, 20.7, delta=0.1)
        self.assertTrue(self.gr.dimensional_validation_summary["passed"])
        self.assertTrue(self.gr.geometry_validation_summary["passed"])
        res_b = run_pipeline(_req(), resolver=self.resolver,
                              product_kwargs={"reduced_tip_size": "1", "bore_schedule": "Sch160"})
        self._log("R7.determinism", res_b.geometry_result.geometry_fingerprint == self.gr.geometry_fingerprint, "True")
        self.assertEqual(res_b.geometry_result.geometry_fingerprint, self.gr.geometry_fingerprint)

    # ---------------- R8 reducing nipoflange dual bore (2026-07-21) ----------------
    def test_R8_reducing_dual_bore(self):
        """A 2"x1" reducing nipoflange must NOT have a single constant bore
        end-to-end: the flange body + hub bore at the 2" flange ID, a
        conical transition begins exactly at the Hub-to-Neck Transition
        (hub taper end, z = D + hub length) and completes by the
        reducing-taper end, and the outlet bores at the 1" ID thereafter.
        Expected flange-side bore is derived independently via the SAME
        cross-family rule the production pipeline uses (not a hardcoded
        literal), so this is a wiring/correctness check, not a coincidence
        check."""
        expected_flange_bore = FlangeBoreViaPipeScheduleRule().resolve(
            self.resolver, target_standard="KAFCO_NIPOFLANGE", target_size_system="nps",
            target_size="2", pipe_standard="ASME_B36.10M", pipe_schedule="Sch160")
        self.assertTrue(expected_flange_bore.is_applied())
        flange_bore_r = expected_flange_bore.value.value / 2.0
        self._log("R8.expected_flange_bore_dia", round(flange_bore_r * 2, 3), "derived via FlangeBoreViaPipeScheduleRule")
        self.assertGreater(flange_bore_r, BORE / 2.0, "flange-side (2\") bore must be larger than outlet (1\") bore")

        hub_end_z = D + self.sec["hub"]
        taper_end_z = self.sec["taper_end_z"]

        flange_side = [(z, self.r_in_all[z]) for z in self.zs
                        if z <= hub_end_z + 1e-6 and self.r_in_all[z] < self.r_out[z] - 1e-6]
        self.assertTrue(flange_side, "no inner rings found in the flange/hub region")
        for z, r in flange_side:
            self.assertAlmostEqual(r, flange_bore_r, delta=0.1, msg=f"flange-side r_in at z={z} is {r}")
        self._log("R8.flange_side_r_in", sorted({round(r, 3) for _z, r in flange_side}),
                   f"{flange_bore_r:.3f} +/-0.1")

        transition = sorted((z, self.r_in_all[z]) for z in self.zs
                              if hub_end_z - 1e-6 < z < taper_end_z + 1e-6
                              and self.r_in_all[z] < self.r_out[z] - 1e-6)
        radii = [r for _z, r in transition]
        self._log("R8.transition_monotonic_decreasing", radii, "non-increasing, bounded by the two bores")
        self.assertTrue(all(radii[i] >= radii[i + 1] - 1e-6 for i in range(len(radii) - 1)))
        for r in radii:
            self.assertLessEqual(r, flange_bore_r + 1e-6)
            self.assertGreaterEqual(r, BORE / 2.0 - 1e-6)

        outlet_side = [(z, self.r_in_all[z]) for z in self.zs
                        if z >= taper_end_z - 1e-6 and self.r_in_all[z] < self.r_out[z] - 1e-6]
        self.assertTrue(outlet_side, "no inner rings found in the outlet region")
        for z, r in outlet_side:
            self.assertAlmostEqual(r, BORE / 2.0, delta=0.1, msg=f"outlet-side r_in at z={z} is {r}")

        meas = self.gp["measurements"]
        self._log("R8.measurements", {"bore_diameter_mm": meas.get("bore_diameter_mm"),
                                        "flange_bore_diameter_mm": meas.get("flange_bore_diameter_mm")},
                   f"{{'bore_diameter_mm': {BORE:.1f}, 'flange_bore_diameter_mm': {flange_bore_r*2:.1f}}}")
        self.assertAlmostEqual(meas["bore_diameter_mm"], BORE, delta=0.2)
        self.assertIn("flange_bore_diameter_mm", meas)
        self.assertAlmostEqual(meas["flange_bore_diameter_mm"], flange_bore_r * 2.0, delta=0.2)

        feats = self.feats
        self.assertIn("flange_bore_wall", feats)
        self.assertIn("bore_transition_taper", feats)
        self.assertIn("outlet_bore_wall", feats)
        self.assertNotIn("bore_wall", feats, "single-region bore_wall feature should not appear for a dual-bore item")

    # ---------------- R9 size-on-size regression (no behaviour change) ----------------
    def test_R9_size_on_size_unchanged(self):
        """A non-reducing (size-on-size) nipoflange must keep today's single
        constant bore end-to-end and the original single "bore_wall"
        feature - zero behaviour change from the dual-bore correction."""
        res = run_pipeline(_req(), resolver=self.resolver, product_kwargs={"bore_schedule": "Sch160"})
        gr = res.geometry_result
        self.assertEqual(gr.generation_status, "GEOMETRY_GENERATED")
        gp = gr.geometry_payload
        zs, r_out, r_in = _envelope(gp["mesh"])
        inner = [(z, r_in[z]) for z in zs if r_in[z] < r_out[z] - 1e-6]
        self.assertTrue(inner)
        radii = {round(r, 3) for _z, r in inner}
        self._log("R9.r_in_values", sorted(radii), "single constant value")
        self.assertEqual(len(radii), 1, "size-on-size bore must be a single constant radius")
        feats = {f["name"]: f for f in gp["features"]}
        self.assertIn("bore_wall", feats)
        self.assertNotIn("flange_bore_wall", feats)
        self.assertNotIn("bore_transition_taper", feats)
        self.assertNotIn("flange_bore_diameter_mm", gp["measurements"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
