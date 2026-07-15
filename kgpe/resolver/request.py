# -*- coding: utf-8 -*-
"""
kgpe.resolver.request
=========================
Sec.5-6: `EngineeringRequest` - the external-facing request model.

Deliberately a SEPARATE, flat dataclass from `kgpe.contract.model.
EngineeringFact`. An EngineeringFact represents one canonical, already-
verified engineering fact; an EngineeringRequest represents "what
engineering object is being asked for" - raw, unnormalized, possibly
incomplete or wrong, before any canonical validation has happened. These
are different concepts and must never be conflated (Sec.5).

Every field is Optional and RAW (as given by the caller) - normalization
happens in `kgpe.resolver.engine`, not here. This module only defines the
shape and provides serialization; it performs no canonical validation and
imports nothing from `kgpe.contract` beyond what's needed for type hints.
"""
from dataclasses import dataclass, field, asdict
from typing import Optional, List


@dataclass
class EngineeringRequest:
    # --- identity criteria (Sec.4) ---
    product_family: Optional[str] = None      # raw, e.g. "flange", "Flange", "buttweld"
    subtype: Optional[str] = None             # raw subtype/alias, e.g. "WN", "elbow_90", "sockolet"
    standard: Optional[str] = None            # raw standard alias, e.g. "ASME B16.5", "ASME_B16.5"

    # --- size criteria (Sec.4/13/15) ---
    size_system: Optional[str] = None         # explicit override: "nps" | "dn" | "jis_size"
    primary_size: Optional[object] = None     # single-size products (flange/pipe/most fittings)
    large_end_size: Optional[object] = None   # reducer large end
    small_end_size: Optional[object] = None   # reducer small end
    run_size: Optional[object] = None         # branch-outlet run size (NPS)
    branch_size: Optional[object] = None      # branch-outlet branch/outlet size (NPS)

    # --- rating/wall criteria (Sec.4/14) - kept as SEPARATE explicit
    # fields on purpose, so the caller must say which rating SYSTEM a
    # bare number belongs to; the resolver never has to guess between
    # them (Sec.14: "do not allow a generic number... to be interpreted
    # without context when multiple rating systems are possible").
    pressure_class: Optional[object] = None   # ASME class, e.g. "150"
    schedule: Optional[str] = None            # ASME/JIS pipe schedule, e.g. "Sch40", "STD"
    pn: Optional[object] = None               # EN PN, e.g. "PN16"
    jis_k: Optional[object] = None            # JIS K rating, e.g. "10K"
    wall_designation: Optional[str] = None    # EN wall designation, e.g. "Series3"

    # --- manufacturer context (Sec.23) ---
    manufacturer_profile: Optional[str] = None
    allow_manufacturer_specific: bool = False

    # --- requested dimensions (Sec.17) ---
    # None/empty means "tell me what authoritative dimensions are
    # available for this identity" (Sec.17.B); a non-empty list means
    # "resolve exactly these named canonical dimensions" (Sec.17.A).
    dimensions: Optional[List[str]] = field(default_factory=list)

    def to_dict(self):
        return {k: v for k, v in asdict(self).items()}

    @classmethod
    def from_dict(cls, d):
        known = {f for f in cls.__dataclass_fields__}
        unknown = set(d) - known
        if unknown:
            raise ValueError(f"Unknown EngineeringRequest field(s): {sorted(unknown)}")
        return cls(**d)
