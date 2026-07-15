# -*- coding: utf-8 -*-
"""
kgpe.geometry.policy
========================
Prompt 12 Sec.7-9: the ONE place that defines KGPE's global geometry
coordinate convention, unit convention, and numerical policy. Every other
kernel module imports these constants rather than scattering literal
tolerances/axis choices through unrelated code.

Coordinate system convention (Sec.7):
  - Right-handed coordinate system.
  - Primary product axis: +Z. Straight/extruded products (pipe) extend
    along +Z from the origin. Swept products (elbow) enter the bend at
    the origin travelling along +Z and leave along whichever axis the
    sweep angle rotates onto (e.g. +X for a 90 degree bend in the XZ
    plane - see kgpe.geometry.primitives.arc_sweep_ring_centers).
  - Origin convention: the origin is the centreline point of the START
    face of the product (never the bounding-box corner, never a
    manufacturing datum).
  - X/Y span the cross-sectional plane at the start face; Z is the
    axial/travel direction.

Unit convention (Sec.8):
  - ALL internal kernel length values are millimetres (mm) - matching
    kgpe.contract.units.CANONICAL_LENGTH_UNIT, so no conversion is ever
    needed between the canonical engineering layer and the kernel.
  - Non-length engineering values (counts, designations) are never
    treated as lengths and never enter geometric calculations.
  - Angles used internally are radians (Python's `math` module native
    unit); degrees are only used at documentation/API boundaries.
"""
import math

LENGTH_UNIT = "mm"
ANGLE_UNIT_INTERNAL = "rad"

# ---------------------------------------------------------------------------
# Sec.9: centralized numerical policy. Never redefine a tolerance locally
# in another module - import it from here.
# ---------------------------------------------------------------------------
LINEAR_TOLERANCE_MM = 1e-6          # dimensional-comparison tolerance
NEAR_ZERO_MM = 1e-9                 # below this magnitude, a length is "zero"
ANGULAR_TOLERANCE_RAD = 1e-9        # angular comparison tolerance
DEGENERATE_AREA_THRESHOLD_MM2 = 1e-9  # triangle area below this is degenerate
FINGERPRINT_ROUNDING_DECIMALS = 6   # coordinate rounding before hashing

COORDINATE_CONVENTION = {
    "handedness": "right_handed",
    "primary_product_axis": "+Z",
    "origin": "start_face_centreline",
    "cross_section_plane": "XY_at_start_face",
}


def is_effectively_zero(value_mm):
    return abs(value_mm) < NEAR_ZERO_MM


def within_tolerance(a_mm, b_mm, tolerance_mm=LINEAR_TOLERANCE_MM):
    return abs(a_mm - b_mm) <= tolerance_mm


def round_for_fingerprint(value):
    return round(float(value), FINGERPRINT_ROUNDING_DECIMALS)


def degrees_to_radians(deg):
    return math.radians(deg)
