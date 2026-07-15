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
