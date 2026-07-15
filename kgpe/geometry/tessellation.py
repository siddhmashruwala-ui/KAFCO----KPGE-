# -*- coding: utf-8 -*-
"""
kgpe.geometry.tessellation
==============================
Prompt 12 Sec.20: deterministic tessellation policy. The same
`GeometrySpecification` plus the same `GenerationParameters` must always
produce identical mesh topology - no platform-dependent randomness ever
affects segment counts, seam placement, or face orientation (seam
placement/orientation are guaranteed by `kgpe.geometry.primitives.
circle_ring`/`arc_sweep_frames` always starting at the same deterministic
basis vector, never a random angle).
"""
MIN_RADIAL_SEGMENTS = 8
MIN_SWEEP_SEGMENTS = 2
DEFAULT_RADIAL_SEGMENTS = 32
DEFAULT_SWEEP_SEGMENTS = 16


def validate_tessellation(radial_segments, sweep_segments):
    if not isinstance(radial_segments, int) or radial_segments < MIN_RADIAL_SEGMENTS:
        raise ValueError(f"radial_segments must be an int >= {MIN_RADIAL_SEGMENTS}, got {radial_segments!r}")
    if not isinstance(sweep_segments, int) or sweep_segments < MIN_SWEEP_SEGMENTS:
        raise ValueError(f"sweep_segments must be an int >= {MIN_SWEEP_SEGMENTS}, got {sweep_segments!r}")
