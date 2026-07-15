# -*- coding: utf-8 -*-
"""
kgpe.geometry.wall_context
=============================
Prompt 13 Sec.7-8: explicit, additive wall-thickness context for hollow
buttweld geometry (elbow/tee/cap). ASME B16.9 does not publish
wall_thickness_mm for these fittings at all (confirmed live - only
EN_10253 elbow facts carry it) - the mating pipe's schedule/wall
designation is the only source. This model exists SEPARATELY from
`kgpe.resolver.EngineeringRequest` and `kgpe.geometry_spec.
GeometrySpecification` (both frozen, Prompt 10/11) - it is the smallest
additive downstream extension, threaded only through
`kgpe.geometry.kernel.GeometryKernel.generate()` and product `build()`
functions, never hacked into an unrelated frozen field.

`WallContext` must be supplied EXPLICITLY by the caller (never inferred
from nominal size, never defaulted to Sch40, never guessing the thinnest/
most common wall) - absence of a `WallContext` means "generate the
external-envelope-only geometry", never a silent hollow-with-guessed-wall
result (Sec.7).
"""
from dataclasses import dataclass
from typing import Optional


class WallContextError(Exception):
    """Raised when a supplied WallContext is ambiguous or incomplete -
    fails closed rather than guessing (Sec.7)."""
    pass


@dataclass(frozen=True)
class WallContext:
    pipe_standard: str
    pipe_schedule: Optional[str] = None
    pipe_wall_designation: Optional[str] = None

    def __post_init__(self):
        if not self.pipe_standard:
            raise WallContextError("WallContext.pipe_standard is required and must be explicit.")
        if not self.pipe_schedule and not self.pipe_wall_designation:
            raise WallContextError(
                "WallContext requires an explicit pipe_schedule OR pipe_wall_designation - "
                "never defaulted, never inferred from nominal size alone.")
        if self.pipe_schedule and self.pipe_wall_designation:
            raise WallContextError(
                "WallContext must specify exactly ONE of pipe_schedule/pipe_wall_designation, "
                "never both - the caller must state which rating system applies (mirrors "
                "kgpe.resolver's own separate-rating-field discipline).")
