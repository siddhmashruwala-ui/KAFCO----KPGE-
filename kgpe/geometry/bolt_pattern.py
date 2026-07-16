# -*- coding: utf-8 -*-
"""
kgpe.geometry.bolt_pattern
==============================
Prompt 14 Sec.10-11: a reusable, deterministic, serializable `BoltPattern`
model - shared by ASME B16.5, JIS B2220, and EN 1092-1 flange geometry
(the bolt-pattern MATH is standard-agnostic; only the authoritative
bolt-circle diameter/hole diameter/count values differ per standard,
which this module never looks up itself - it only consumes
already-resolved numeric inputs).

Angular-zero convention (Sec.11, documented once here - never redefined
elsewhere): hole index 0 is centred on the local +X axis (angle 0), holes
are placed at equal `360/N` degree spacing, increasing counter-clockwise
when viewed from +Z looking toward the origin (the same right-handed
rotation direction `kgpe.geometry.primitives.circle_ring` already uses for
every other product's ring vertices - Sec.5's "deterministic angular-zero
reference / rotation direction" requirement is satisfied by reusing the
kernel's one existing rotation convention rather than inventing a second
one).
"""
import math
from dataclasses import dataclass, field, asdict
from typing import Tuple

from .policy import NEAR_ZERO_MM, LINEAR_TOLERANCE_MM


class BoltPatternError(Exception):
    """Raised for a genuinely malformed bolt pattern (non-positive count/
    diameter, non-finite geometry) - a programmer/input defect, never an
    expected engineering outcome."""
    pass


@dataclass(frozen=True)
class BoltPattern:
    bolt_circle_diameter_mm: float
    bolt_hole_diameter_mm: float
    count: int
    centre: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    axis: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    angular_zero_deg: float = 0.0
    hole_centres: Tuple[Tuple[float, float, float], ...] = field(default_factory=tuple)

    def to_dict(self):
        d = asdict(self)
        d["hole_centres"] = [list(c) for c in self.hole_centres]
        return d


def build_bolt_pattern(bolt_circle_diameter_mm, bolt_hole_diameter_mm, count,
                        centre=(0.0, 0.0, 0.0), angular_zero_deg=0.0):
    """Sec.10-11: deterministic construction. Only supports bolt patterns
    on the flange's own +Z axis (Sec.5's 'bolt pattern centred on the
    Z-axis') - `axis` is always (0,0,1) for every flange this prompt
    generates; a future non-axial use would need a new constructor, not a
    silent generalization here."""
    if not isinstance(count, int) or count <= 0:
        raise BoltPatternError(f"bolt hole count must be a positive integer, got {count!r}")
    if bolt_hole_diameter_mm is None or bolt_hole_diameter_mm <= NEAR_ZERO_MM:
        raise BoltPatternError(f"bolt_hole_diameter_mm must be positive, got {bolt_hole_diameter_mm!r}")
    if bolt_circle_diameter_mm is None or bolt_circle_diameter_mm <= NEAR_ZERO_MM:
        raise BoltPatternError(f"bolt_circle_diameter_mm must be positive, got {bolt_circle_diameter_mm!r}")

    radius = bolt_circle_diameter_mm / 2.0
    cx, cy, cz = centre
    zero_rad = math.radians(angular_zero_deg)
    centres = []
    for i in range(count):
        angle = zero_rad + i * (2.0 * math.pi / count)
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)
        centres.append((x, y, cz))

    return BoltPattern(
        bolt_circle_diameter_mm=float(bolt_circle_diameter_mm),
        bolt_hole_diameter_mm=float(bolt_hole_diameter_mm),
        count=count, centre=(cx, cy, cz), axis=(0.0, 0.0, 1.0),
        angular_zero_deg=angular_zero_deg, hole_centres=tuple(centres),
    )


def validate_bolt_pattern(pattern: BoltPattern):
    """Sec.11/29: verify every hole centre lies on the required bolt-
    circle radius within tolerance, angular spacing is exactly 360/N,
    hole count matches len(hole_centres), no duplicate hole centres,
    every coordinate is finite. Raises BoltPatternError on a genuine
    defect (a product builder should never emit an invalid pattern)."""
    n = pattern.count
    if len(pattern.hole_centres) != n:
        raise BoltPatternError(
            f"bolt pattern declares count={n} but has {len(pattern.hole_centres)} hole centres.")

    expected_radius = pattern.bolt_circle_diameter_mm / 2.0
    cx, cy, cz = pattern.centre
    seen = []
    angles = []
    for idx, (x, y, z) in enumerate(pattern.hole_centres):
        for v in (x, y, z):
            if not math.isfinite(v):
                raise BoltPatternError(f"hole {idx} has non-finite coordinate: {(x, y, z)!r}")
        r = math.hypot(x - cx, y - cy)
        if abs(r - expected_radius) > LINEAR_TOLERANCE_MM:
            raise BoltPatternError(
                f"hole {idx} radius {r!r} does not match bolt-circle radius {expected_radius!r} "
                f"within tolerance {LINEAR_TOLERANCE_MM!r}.")
        for other in seen:
            if abs(x - other[0]) <= LINEAR_TOLERANCE_MM and abs(y - other[1]) <= LINEAR_TOLERANCE_MM:
                raise BoltPatternError(f"hole {idx} duplicates an existing hole centre at {(x, y)!r}.")
        seen.append((x, y))
        angles.append(math.atan2(y - cy, x - cx))

    if n > 1:
        expected_spacing = 2.0 * math.pi / n
        zero_rad = math.radians(pattern.angular_zero_deg)
        for idx, angle in enumerate(angles):
            expected_angle = zero_rad + idx * expected_spacing
            diff = (angle - expected_angle) % (2.0 * math.pi)
            if diff > math.pi:
                diff -= 2.0 * math.pi
            if abs(diff) > 1e-6:
                raise BoltPatternError(
                    f"hole {idx} angle does not match the deterministic {360.0 / n:.6f} degree spacing "
                    f"(angular-zero={pattern.angular_zero_deg} deg).")
    return True
