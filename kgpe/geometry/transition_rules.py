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
    envelope E = B - D, mirroring (and now owning, as the single
    engineering authority) the split the CRM's reference-photo-validated
    heuristic already used:

      REDUCING (integral reduced weldolet outlet at the tip):
        28% hub fillet / 12% straight full-size barrel / 22% reducing
        transition / 28% reduced outlet (weldolet) body / 10% weld bevel.
      NON-REDUCING (full, size-on-size):
        30% hub fillet / 60% straight barrel / 10% weld bevel.

    Radial construction defaults (same provenance - deterministic shop-
    practice proportions, never claimed as published dimensions):
      hub fillet base OD  = min(0.58 x flange OD, 2.2 x neck OD)
      weldolet base OD    = min(1.5 x tip OD, 0.92 x neck OD)  (reducing only)
      weld-prep tip OD    = 0.62 x end OD (the honest flat-closure edge,
                            same policy as CapProfileConstructionRule)."""
    rule_id = "nipoflange_neck_envelope_allocation"
    rule_version = "1"
    is_exact_engineering_envelope = False
    description = ("Deterministic allocation of the Nipoflange neck envelope (overall length minus "
                   "flange thickness) across hub fillet / barrel / reducing transition / weldolet "
                   "outlet / weld bevel - a construction default for a contour no standard or "
                   "manufacturer table publishes, never a source-published dimension.")

    REDUCING_SPLIT = {"hub_fillet": 0.28, "barrel": 0.12, "transition": 0.22,
                       "outlet_body": 0.28, "weld_bevel": 0.10}
    STRAIGHT_SPLIT = {"hub_fillet": 0.30, "barrel": 0.60, "weld_bevel": 0.10}
    HUB_BASE_FLANGE_OD_FACTOR = 0.58
    HUB_BASE_NECK_OD_FACTOR = 2.2
    OLET_BASE_TIP_OD_FACTOR = 1.5
    OLET_BASE_NECK_OD_FACTOR = 0.92
    WELD_PREP_TIP_FACTOR = 0.62

    def allocate(self, overall_length_mm, flange_thickness_mm, reducing):
        """Returns {section_name: length_mm} for the neck above the flange
        top face. Raises ValueError when the envelope is non-positive -
        fail-closed, never a fabricated minimum."""
        envelope = overall_length_mm - flange_thickness_mm
        if envelope <= 0.0:
            raise ValueError(
                f"Nipoflange neck envelope must be positive: overall_length_mm={overall_length_mm!r} "
                f"- flange_thickness_mm={flange_thickness_mm!r} = {envelope!r}")
        split = self.REDUCING_SPLIT if reducing else self.STRAIGHT_SPLIT
        return {name: envelope * fraction for name, fraction in split.items()}

    def hub_base_od(self, flange_od_mm, neck_od_mm):
        return min(self.HUB_BASE_FLANGE_OD_FACTOR * flange_od_mm,
                   self.HUB_BASE_NECK_OD_FACTOR * neck_od_mm)

    def outlet_base_od(self, tip_od_mm, neck_od_mm):
        return min(self.OLET_BASE_TIP_OD_FACTOR * tip_od_mm,
                   self.OLET_BASE_NECK_OD_FACTOR * neck_od_mm)


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
