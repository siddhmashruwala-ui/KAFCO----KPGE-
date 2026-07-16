# -*- coding: utf-8 -*-
"""
kgpe.geometry.outlet_geometry
=================================
Prompt 15 Sec.6/9/12: a reusable `OutletGeometry` model representing an
MSS SP-97 branch-outlet fitting's (weldolet/sockolet/threadolet) key
regions - run interface, branch interface, outlet axis, outlet opening,
reinforcement body, blend region - each carrying an explicit provenance
status. `branch_interface`/`outlet_opening` always use
`olet_bore_diameter_mm` (D_bore) uniformly across weldolet/sockolet/
threadolet - the one field common to all three subtypes and the one that
scales consistently with base OD (confirmed live: base_OD > bore for
every row inspected). Sockolet's ADDITIONAL `olet_socket_diameter_mm`
(E_socketDia) is deliberately NOT folded into this model - its values do
not follow a simple ordering relationship with base OD/bore (confirmed
live: e.g. NPS2 sockolet has base_OD=65.08mm, bore=52.5mm, but
socket_diameter=23.81mm - a genuinely different, smaller port dimension,
not a scaled-down bore) - it is exposed as a separate, sockolet-specific
metadata feature by `kgpe.geometry.products.olet`, never forced into this
generic model's ordering assumptions.
"""
from dataclasses import dataclass, asdict
from typing import Optional, Tuple

OUTLET_STATUS_AUTHORITATIVE = "AUTHORITATIVE"
OUTLET_STATUS_CONSTRUCTION_DERIVED = "CONSTRUCTION_DERIVED"
OUTLET_STATUS_DEPENDENCY_DERIVED = "DEPENDENCY_DERIVED"
OUTLET_STATUS_UNAVAILABLE = "UNAVAILABLE"

ALL_OUTLET_FEATURE_STATUSES = frozenset({
    OUTLET_STATUS_AUTHORITATIVE, OUTLET_STATUS_CONSTRUCTION_DERIVED,
    OUTLET_STATUS_DEPENDENCY_DERIVED, OUTLET_STATUS_UNAVAILABLE,
})


class OutletGeometryError(Exception):
    """Raised for a genuinely malformed outlet geometry (non-positive
    dimension, branch interface exceeding run interface) - a programmer/
    input defect, never an expected engineering outcome."""
    pass


@dataclass(frozen=True)
class OutletFeatureValue:
    name: str
    status: str
    value_mm: Optional[float] = None
    detail: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class OutletGeometry:
    run_interface: OutletFeatureValue
    branch_interface: OutletFeatureValue
    outlet_opening: OutletFeatureValue
    reinforcement_body: OutletFeatureValue
    blend_region: OutletFeatureValue
    outlet_axis: Tuple[float, float, float] = (0.0, 0.0, 1.0)

    def to_dict(self):
        return {
            "run_interface": self.run_interface.to_dict(), "branch_interface": self.branch_interface.to_dict(),
            "outlet_opening": self.outlet_opening.to_dict(),
            "reinforcement_body": self.reinforcement_body.to_dict(),
            "blend_region": self.blend_region.to_dict(), "outlet_axis": list(self.outlet_axis),
        }


def build_outlet_geometry(base_outside_diameter_mm, bore_diameter_mm, height_mm):
    """Sec.6/9: assembles an `OutletGeometry` from already-resolved
    authoritative manufacturer-specific dimension values (Bonney Forge,
    via `PROFILE_OLET_BODY`). `blend_region` is ALWAYS UNAVAILABLE - no
    fillet/blend-radius dimension is published for this family in the
    canonical registry, never fabricated. `reinforcement_body` is always
    CONSTRUCTION_DERIVED - see `OletReinforcementEnvelopeConstructionRule`
    in `kgpe.geometry.construction_rules`."""
    run_interface = OutletFeatureValue(
        "run_interface", OUTLET_STATUS_AUTHORITATIVE, value_mm=base_outside_diameter_mm,
        detail="olet_base_outside_diameter_mm (Bonney Forge manufacturer-specific) - the footprint/"
               "weld-prep interface where this outlet attaches to the run pipe (not itself a flow "
               "opening - no assembly/piping connectivity is modeled).")
    branch_interface = OutletFeatureValue(
        "branch_interface", OUTLET_STATUS_AUTHORITATIVE, value_mm=bore_diameter_mm,
        detail="olet_bore_diameter_mm (Bonney Forge manufacturer-specific) - the branch-side flow "
               "opening, the one dimension common to weldolet/sockolet/threadolet alike.")
    outlet_opening = OutletFeatureValue(
        "outlet_opening", OUTLET_STATUS_AUTHORITATIVE, value_mm=bore_diameter_mm,
        detail="Same authoritative value as branch_interface; positioned at the branch port location "
               "by the calling product builder.")
    reinforcement_body = OutletFeatureValue(
        "reinforcement_body", OUTLET_STATUS_CONSTRUCTION_DERIVED, value_mm=height_mm,
        detail="Construction-derived frustum envelope (base_OD at the run interface tapering to the "
               "branch opening diameter over olet_height_mm) - NOT an MSS SP-97-published continuous "
               "reinforcement contour. See OletReinforcementEnvelopeConstructionRule.")
    blend_region = OutletFeatureValue(
        "blend_region", OUTLET_STATUS_UNAVAILABLE,
        detail="No fillet/blend-radius dimension is published for this family in the canonical "
               "registry - never fabricated.")
    return OutletGeometry(run_interface=run_interface, branch_interface=branch_interface,
                           outlet_opening=outlet_opening, reinforcement_body=reinforcement_body,
                           blend_region=blend_region, outlet_axis=(0.0, 0.0, 1.0))


def validate_outlet_geometry(og: OutletGeometry):
    """Sec.12: positive run/branch interface dimensions; branch interface
    must not exceed run interface (the reinforcement envelope tapers
    inward from the run footprint, never outward) - confirmed true for
    every weldolet/sockolet/threadolet row inspected live."""
    if og.run_interface.value_mm is not None and og.run_interface.value_mm <= 0:
        raise OutletGeometryError(f"run_interface must be positive: {og.run_interface.value_mm!r}")
    if og.branch_interface.value_mm is not None and og.branch_interface.value_mm <= 0:
        raise OutletGeometryError(f"branch_interface must be positive: {og.branch_interface.value_mm!r}")
    if (og.run_interface.value_mm is not None and og.branch_interface.value_mm is not None
            and og.branch_interface.value_mm > og.run_interface.value_mm):
        raise OutletGeometryError(
            f"branch_interface ({og.branch_interface.value_mm!r}) must not exceed run_interface "
            f"({og.run_interface.value_mm!r}) - the reinforcement envelope tapers inward, never outward.")
    return True
