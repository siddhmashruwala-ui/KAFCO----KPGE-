# -*- coding: utf-8 -*-
"""
kgpe.geometry.mating_interface
===================================
Prompt 14 Sec.7: flange-specific mating-interface metadata - a flange has
more engineering identity at its mating face than a generic
`kgpe.geometry.ports.ConnectionPort` opening (bolt pattern, face type).
This is METADATA ONLY (Sec.7: "do not build assembly logic yet") for
future assembly alignment / bolt-pattern matching / dimension annotation
/ visualization - none of that is implemented here.

`face_type` is deliberately a tri-state string, never silently defaulted
to "RF": the canonical data layer this project actually ingests does not
carry a face-type IDENTITY field at all for any of ASME B16.5/JIS B2220/
EN 1092-1 (Sec.20/23 - confirmed live, see Prompt 14 report Sec.20/23) -
only a raised_face_diameter_mm DIMENSION exists (JIS only), which is a
different fact than a face-type classification. `FACE_TYPE_NOT_TRACKED`
is used for every flange this prompt generates.
"""
from dataclasses import dataclass, asdict
from typing import Tuple, Optional

FACE_TYPE_NOT_TRACKED = "NOT_TRACKED_BY_CANONICAL_DATA"
FACE_TYPE_RAISED_FACE = "RF"
FACE_TYPE_FLAT_FACE = "FF"

ALL_FACE_TYPES = frozenset({FACE_TYPE_NOT_TRACKED, FACE_TYPE_RAISED_FACE, FACE_TYPE_FLAT_FACE})


@dataclass(frozen=True)
class MatingInterface:
    mating_face_centre: Tuple[float, float, float]
    mating_face_normal: Tuple[float, float, float]
    outside_diameter_mm: float
    bolt_circle_diameter_mm: float
    bolt_hole_count: int
    bolt_hole_diameter_mm: float
    face_type: str = FACE_TYPE_NOT_TRACKED

    def to_dict(self):
        return asdict(self)
