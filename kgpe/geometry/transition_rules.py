# -*- coding: utf-8 -*-
"""
kgpe.geometry.transition_rules
==================================
Prompt 13 Sec.13-14 (tee), Sec.18 (cap), Sec.23 (concentric reducer),
Sec.25 (eccentric reducer): versioned, deterministic CONSTRUCTION
geometry rules for continuous surfaces the canonical data does not itself
define a contour for. Every rule here is explicitly labeled as
construction geometry, never claimed as a source-published contour,
per the repeated instruction across Sec.13/18/23 not to hide this
distinction.
"""
import math
from dataclasses import dataclass


class TeeBranchBlendingRule:
    """Sec.14: formalizes the tee run/branch intersection policy. No
    ASME B16.9 fact publishes a blend/fillet radius for the run-branch
    intersection - so this rule defines NO constructed fillet/blend
    surface at all: the run and branch are represented as two independent
    swept cylindrical features whose volumes geometrically overlap where
    the branch axis crosses the run body. This is a deterministic
    visualization/construction representation, not exact engineering
    envelope geometry - explicitly NOT claimed as watertight/manifold at
    the intersection (see kgpe.geometry.result topology_representation)."""
    rule_id = "tee_branch_raw_intersection_no_blend"
    rule_version = "1"
    is_exact_engineering_envelope = False
    description = ("Run and branch are independent overlapping cylindrical features; no "
                   "ASME-published or construction-derived blend/fillet radius is applied or fabricated.")


class CapProfileConstructionRule:
    """Sec.18: ASME B16.9 publishes cap OD + length (H/H1) but no dome-
    curvature dimension - the actual standard cap has a rounded/dished
    head. This rule defines a deterministic flat-disc closure at the
    selected length as the kernel's construction default: it preserves
    the authoritative OD and selected length EXACTLY, and does not claim
    the closing profile's curvature is standard-authoritative."""
    rule_id = "cap_flat_disc_closure"
    rule_version = "1"
    is_exact_engineering_envelope = False
    description = ("Cap body is a cylindrical shell of the selected (OD, length); the outer "
                   "end is closed with a flat disc, not the standard's true rounded/dished "
                   "head profile - no curvature dimension exists in canonical data to derive one.")


class ConcentricReducerTransitionRule:
    """Sec.23: ASME B16.9 defines each end's OD and the overall
    end_to_end_mm length but not the continuous transition contour. This
    rule defines a deterministic LINEAR (conical) transition between the
    large and small end radii - the simplest, most defensible construction
    default given no source-published contour exists. Preserves both
    authoritative end ODs and the authoritative length exactly."""
    rule_id = "linear_conical_transition"
    rule_version = "1"
    is_exact_engineering_envelope = False

    def radius_at(self, large_radius, small_radius, length, z):
        """Linear interpolation of radius along the axial coordinate z in
        [0, length], z=0 at the large end."""
        t = 0.0 if length <= 0 else max(0.0, min(1.0, z / length))
        return large_radius + (small_radius - large_radius) * t


class NipoflangeNeckAllocationRule:
    """2026-07-21 (CRM production audit): versioned construction rule for
    the KAFCO Nipoflange's neck geometry - the continuous flange-to-weld-
    end contour that NO source tabulates. The KAFCO catalog publishes only
    Flange OD (A), Overall Length (B - purchaser-modifiable per source
    Note 2) and Flange THK (D); the customer explicitly left the height of
    the OD transition to KAFCO (recorded per Siddh, 2026-07-20). This rule
    therefore fixes a deterministic allocation of the available neck
    envelope E = B - D (this rule, not the CRM heuristic, is the single
    engineering authority for it - the heuristic now mirrors THESE
    numbers, not the other way around):

    VERSION 4 (2026-07-21, catalog-fidelity audit). v1-v3 allocated the
    neck as percentage splits of the ACTUAL envelope; the catalog section
    drawing encodes a different design intent entirely:
      - the reduction is an EARLY continuous taper starting right off a
        short conical hub and ending ~45% of (B-D) up the neck;
      - the rest of the length is a STRAIGHT run at the reduced/outlet OD
        - the purchaser TRIM ZONE that makes source Note 2 ("Dimension B
        can be modified") geometrically valid;
      - the outlet ends in the olet CROWN (a collar slightly WIDER than
        the stub, tool-relief undercut beneath it) and a genuine
        B16.25-style weld prep (37.5deg bevel to bore ID + root face),
        never a decorative flat cap.
    CRITICAL v4 SEMANTICS: hub/taper/undercut/crown/bevel lengths are
    computed from the CATALOG DEFAULT B of the identity's class/NB row
    and stay FIXED in absolute mm; the straight outlet run =
    B_actual - (fixed sections) absorbs ALL length variation.

      profile (z up from mating face): flange (D) -> shoulder -> hub cone
      (HUB_ANGLE_DEG) -> linear taper neck OD -> outlet OD, ending at
      D + TAPER_END_FRACTION*(B_default - D) -> straight outlet stub ->
      undercut relief -> crown collar -> weld bevel (with bore: bevel
      lands at ID/2 + ROOT_FACE_MM at z = B_actual).

    All constants below are DECLARED, versioned construction defaults -
    never claimed as source-published dimensions.

    DOCUMENTED CLAMP (per the v4 spec's own infeasibility clause):
    MIN_STUB was specified as 1.0 x outlet OD, but on the 2" rows that
    makes the required 20%-trim capability (B=150 -> 120) infeasible
    (120mm leaves a 15.9mm stub < 33.4mm). Clamped deterministically to
    MIN_STUB_FACTOR = 0.45 x outlet OD, recorded here and covered by an
    explicit fail-closed test at min_valid_overall_length() - 1."""
    rule_id = "nipoflange_neck_envelope_allocation"
    rule_version = "4"
    is_exact_engineering_envelope = False
    description = ("Catalog-faithful Nipoflange contour: early continuous taper, straight "
                   "trimmable outlet run, olet crown + undercut, B16.25-style weld prep - a "
                   "construction default for a contour no standard or manufacturer table "
                   "publishes, never a source-published dimension.")

    HUB_ANGLE_DEG = 30.0                # hub cone half-angle (wall vs axis)
    HUB_BASE_FLANGE_OD_FACTOR = 0.45    # hub base OD = min(0.45*A, 1.3*neck OD)
    HUB_BASE_NECK_OD_FACTOR = 1.3
    TAPER_END_FRACTION = 0.45           # taper ends at D + 0.45*(B_default - D)
    CROWN_OD_FACTOR = 1.15              # crown OD = 1.15 * outlet OD
    CROWN_LENGTH_FACTOR = 0.35          # crown length = 0.35 * outlet OD
    UNDERCUT_DEPTH_FACTOR = 0.06        # diametral relief = 0.06 * outlet OD
    UNDERCUT_LENGTH_FACTOR = 0.15       # relief length = 0.15 * outlet OD
    BEVEL_ANGLE_DEG = 37.5              # B16.25-style weld-prep bevel angle
    ROOT_FACE_MM = 1.6                  # weld-prep root face
    MIN_STUB_FACTOR = 0.45              # see DOCUMENTED CLAMP above (spec said 1.0)

    def hub_base_od(self, flange_od_mm, neck_od_mm):
        return min(self.HUB_BASE_FLANGE_OD_FACTOR * flange_od_mm,
                   self.HUB_BASE_NECK_OD_FACTOR * neck_od_mm)

    def crown_od(self, outlet_od_mm):
        return self.CROWN_OD_FACTOR * outlet_od_mm

    def root_face_radius(self, bore_diameter_mm):
        return bore_diameter_mm / 2.0 + self.ROOT_FACE_MM

    def sections(self, default_overall_length_mm, flange_thickness_mm,
                  flange_od_mm, neck_od_mm, outlet_od_mm, bore_diameter_mm=None):
        """Fixed absolute section lengths (mm) computed from the CATALOG
        DEFAULT B - independent of any purchaser-trimmed actual B. Returns
        a dict of lengths plus derived radii. Fail-closed on impossible
        geometry (never fabricates a minimum)."""
        import math as _m
        d = flange_thickness_mm
        b_def = default_overall_length_mm
        if not (0.0 < d < b_def):
            raise ValueError(f"flange thickness {d!r} must be positive and less than default B {b_def!r}")
        hub_base_r = self.hub_base_od(flange_od_mm, neck_od_mm) / 2.0
        neck_r = neck_od_mm / 2.0
        outlet_r = outlet_od_mm / 2.0
        if not (outlet_r <= neck_r < hub_base_r):
            # equality outlet==neck is the FULL (size-on-size) variant: the
            # "taper" band degenerates into the straight neck barrel.
            raise ValueError(
                f"nipoflange radii must satisfy hub_base > neck >= outlet - got "
                f"{hub_base_r!r}, {neck_r!r}, {outlet_r!r}")
        hub_len = (hub_base_r - neck_r) / _m.tan(_m.radians(self.HUB_ANGLE_DEG))
        taper_end_z = d + self.TAPER_END_FRACTION * (b_def - d)
        taper_len = taper_end_z - (d + hub_len)
        if taper_len <= 0.0:
            raise ValueError(
                f"taper length non-positive ({taper_len!r}) - hub too long for TAPER_END_FRACTION")
        undercut_len = self.UNDERCUT_LENGTH_FACTOR * outlet_od_mm
        undercut_relief_r = outlet_r - (self.UNDERCUT_DEPTH_FACTOR * outlet_od_mm) / 2.0
        crown_len = self.CROWN_LENGTH_FACTOR * outlet_od_mm
        crown_r = self.crown_od(outlet_od_mm) / 2.0
        bevel_target_r = (self.root_face_radius(bore_diameter_mm)
                           if bore_diameter_mm is not None else outlet_r * 0.62)
        bevel_len = (crown_r - bevel_target_r) / _m.tan(_m.radians(self.BEVEL_ANGLE_DEG))
        if bevel_len <= 0.0:
            raise ValueError(f"bevel length non-positive ({bevel_len!r}) - crown below bevel target radius")
        return {"hub": hub_len, "taper": taper_len, "taper_end_z": taper_end_z,
                "undercut": undercut_len, "crown": crown_len, "bevel": bevel_len,
                "hub_base_r": hub_base_r, "neck_r": neck_r, "outlet_r": outlet_r,
                "undercut_relief_r": undercut_relief_r, "crown_r": crown_r,
                "bevel_target_r": bevel_target_r}

    def min_valid_overall_length(self, sections, outlet_od_mm):
        """Smallest legal actual B: taper end + fixed top sections + minimum
        trimmable stub (MIN_STUB_FACTOR x outlet OD - see DOCUMENTED CLAMP)."""
        return (sections["taper_end_z"] + sections["undercut"] + sections["crown"]
                + sections["bevel"] + self.MIN_STUB_FACTOR * outlet_od_mm)

    def stub_length(self, sections, actual_overall_length_mm, outlet_od_mm, extra_straight_mm=0.0):
        """Straight outlet run for the ACTUAL B - the purchaser trim zone.
        Fail-closed below min_valid_overall_length(). extra_straight_mm:
        for the FULL (size-on-size) variant the 'taper' band is itself a
        straight neck-OD run contiguous with the stub, so it counts toward
        the minimum trimmable straight length."""
        stub = (actual_overall_length_mm - sections["taper_end_z"]
                - sections["undercut"] - sections["crown"] - sections["bevel"])
        if stub + extra_straight_mm + 1e-9 < self.MIN_STUB_FACTOR * outlet_od_mm:
            raise ValueError(
                f"overall length {actual_overall_length_mm!r}mm leaves a {stub:.2f}mm outlet stub - "
                f"below the minimum {self.MIN_STUB_FACTOR * outlet_od_mm:.2f}mm "
                f"(min valid B = {self.min_valid_overall_length(sections, outlet_od_mm):.2f}mm).")
        return stub


class EccentricReducerOffsetRule:
    """Sec.24-25: defines the eccentric reducer's centreline-offset
    construction. Kernel default orientation is FLAT_ON_BOTTOM (documented
    default - "one canonical kernel default", Sec.24): the bottom
    generatrix (tangent line) of both ends lies in one continuous plane,
    so the small-end centreline is offset from the large-end centreline
    by exactly (large_radius - small_radius) in the direction away from
    the flat side. This offset is derived purely from the two
    authoritative end diameters - never stored in the canonical registry,
    always recomputed and tagged as a construction-derived value."""
    rule_id = "eccentric_offset_flat_side_tangent"
    rule_version = "1"
    ORIENTATION_FLAT_ON_BOTTOM = "FLAT_ON_BOTTOM"
    ORIENTATION_FLAT_ON_TOP = "FLAT_ON_TOP"
    DEFAULT_ORIENTATION = ORIENTATION_FLAT_ON_BOTTOM

    def offset(self, large_radius, small_radius, orientation=None):
        orientation = orientation or self.DEFAULT_ORIENTATION
        magnitude = large_radius - small_radius
        if orientation == self.ORIENTATION_FLAT_ON_BOTTOM:
            sign = 1.0   # small-end centreline shifts toward +Y (up), flat side is -Y (bottom)
        elif orientation == self.ORIENTATION_FLAT_ON_TOP:
            sign = -1.0  # flat side is +Y (top), centreline shifts toward -Y (down)
        else:
            raise ValueError(f"Unknown eccentric orientation {orientation!r} - must be "
                              f"{self.ORIENTATION_FLAT_ON_BOTTOM!r} or {self.ORIENTATION_FLAT_ON_TOP!r}.")
        return sign * magnitude, orientation
