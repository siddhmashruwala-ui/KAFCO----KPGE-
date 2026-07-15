# -*- coding: utf-8 -*-
"""
kgpe.geometry_spec.identity
=============================
Prompt 11 Sec.5: `EngineeringObjectIdentity` - an immutable structure
representing the fully resolved identity of ONE engineering object, built
from a RESOLVED (status == ResolutionStatus.RESOLVED)
`ResolvedEngineeringSpecification` (Prompt 10). Only applicable fields are
populated - this is never collapsed into one opaque display string; a
deterministic `display_label` is provided as a derived convenience only.
"""
from dataclasses import dataclass, asdict
from typing import Optional

from ..resolver.spec import ResolvedEngineeringSpecification, ResolutionStatus


class IdentityConstructionError(Exception):
    """Raised if `EngineeringObjectIdentity.from_resolved_spec()` is given
    a spec that is not RESOLVED - an identity can only be built from a
    successfully resolved engineering specification (Sec.5/13)."""
    pass


# Which EngineeringObjectIdentity field a given rating_system's rating_value
# belongs on - mirrors kgpe.resolver.engine's own rating-system constants,
# but this module never imports resolver.engine (that stays resolver-
# internal); it only depends on the plain string values already present on
# a resolved spec (Sec.12 - no hidden engineering lookup here either).
_RATING_SYSTEM_TO_IDENTITY_FIELD = {
    "ASME_CLASS": "pressure_class",
    "PN": "pn",
    "JIS_K": "jis_k",
    "SCHEDULE": "schedule",
    "WALL_DESIGNATION": "wall_designation",
}


@dataclass(frozen=True)
class EngineeringObjectIdentity:
    product_family: Optional[str] = None
    subtype: Optional[str] = None
    standard: Optional[str] = None
    size_system: Optional[str] = None
    primary_size: Optional[str] = None
    large_end_size: Optional[str] = None
    small_end_size: Optional[str] = None
    run_size: Optional[str] = None
    branch_size: Optional[str] = None
    pressure_class: Optional[str] = None
    schedule: Optional[str] = None
    pn: Optional[str] = None
    jis_k: Optional[str] = None
    wall_designation: Optional[str] = None
    manufacturer_profile: Optional[str] = None

    @classmethod
    def from_resolved_spec(cls, spec: ResolvedEngineeringSpecification):
        if spec.status != ResolutionStatus.RESOLVED:
            raise IdentityConstructionError(
                f"Cannot build EngineeringObjectIdentity from a specification with "
                f"status {spec.status!r} - identity construction requires a fully "
                f"RESOLVED ResolvedEngineeringSpecification (Sec.5/13).")
        sizes = spec.sizes or {}
        kwargs = dict(
            product_family=spec.product_family, subtype=spec.subtype, standard=spec.standard,
            size_system=spec.size_system, manufacturer_profile=spec.manufacturer_profile,
        )
        if spec.size_system:
            key = spec.size_system
            if key in sizes:
                kwargs["primary_size"] = sizes[key]
            large_key, small_key = f"large_end_{spec.size_system}", f"small_end_{spec.size_system}"
            if large_key in sizes:
                kwargs["large_end_size"] = sizes[large_key]
            if small_key in sizes:
                kwargs["small_end_size"] = sizes[small_key]
        if "run_nps" in sizes:
            kwargs["run_size"] = sizes["run_nps"]
        if "branch_nps" in sizes:
            kwargs["branch_size"] = sizes["branch_nps"]

        if spec.rating_system and spec.rating_value is not None:
            field_name = _RATING_SYSTEM_TO_IDENTITY_FIELD.get(spec.rating_system)
            if field_name:
                kwargs[field_name] = spec.rating_value

        return cls(**kwargs)

    def as_dict(self):
        """Only populated (non-None) fields - Sec.5 'only applicable fields
        should be populated'."""
        return {k: v for k, v in asdict(self).items() if v is not None}

    def to_dict(self):
        """Full dict including None fields, for stable/complete
        serialization of the GeometrySpecification this identity is
        embedded in (Sec.7 - stable, serializable)."""
        return asdict(self)

    @property
    def display_label(self):
        """Deterministic, human-readable convenience label - NEVER the
        identity itself (Sec.5), just a derived rendering of it."""
        parts = []
        if self.product_family:
            parts.append(self.product_family)
        if self.subtype:
            parts.append(self.subtype)
        if self.standard:
            parts.append(self.standard)
        size_bits = []
        if self.primary_size is not None:
            size_bits.append(str(self.primary_size))
        if self.large_end_size is not None and self.small_end_size is not None:
            size_bits.append(f"{self.large_end_size}x{self.small_end_size}")
        if self.run_size is not None and self.branch_size is not None:
            size_bits.append(f"run{self.run_size}xbranch{self.branch_size}")
        if size_bits:
            parts.append("/".join(size_bits))
        rating_bits = []
        for label, val in (("CLASS", self.pressure_class), ("SCH", self.schedule),
                            ("PN", self.pn), ("K", self.jis_k), ("WALL", self.wall_designation)):
            if val is not None:
                rating_bits.append(f"{label}{val}")
        if rating_bits:
            parts.append(",".join(rating_bits))
        if self.manufacturer_profile:
            parts.append(f"[{self.manufacturer_profile}]")
        return " ".join(str(p) for p in parts if p)
