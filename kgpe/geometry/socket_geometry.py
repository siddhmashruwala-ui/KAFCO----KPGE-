# -*- coding: utf-8 -*-
"""
kgpe.geometry.socket_geometry
=================================
Prompt 15 Sec.5/8/11: a reusable `SocketGeometry` model representing one
socket-weld cavity feature (depth/diameter/bore/shoulder/stop/transition/
opening), each carrying an EXPLICIT provenance status - AUTHORITATIVE /
CONSTRUCTION_DERIVED / DEPENDENCY_DERIVED / UNAVAILABLE. This is metadata
ONLY - never boolean-cut into a product builder's mesh, mirroring Prompt
14's bolt-hole-as-metadata precedent exactly.
"""
from dataclasses import dataclass, asdict
from typing import Optional

SOCKET_STATUS_AUTHORITATIVE = "AUTHORITATIVE"
SOCKET_STATUS_CONSTRUCTION_DERIVED = "CONSTRUCTION_DERIVED"
SOCKET_STATUS_DEPENDENCY_DERIVED = "DEPENDENCY_DERIVED"
SOCKET_STATUS_UNAVAILABLE = "UNAVAILABLE"

ALL_SOCKET_FEATURE_STATUSES = frozenset({
    SOCKET_STATUS_AUTHORITATIVE, SOCKET_STATUS_CONSTRUCTION_DERIVED,
    SOCKET_STATUS_DEPENDENCY_DERIVED, SOCKET_STATUS_UNAVAILABLE,
})


class SocketGeometryError(Exception):
    """Raised for a genuinely malformed socket geometry (non-positive
    depth/diameter, min>max) - a programmer/input defect, never an
    expected engineering outcome."""
    pass


@dataclass(frozen=True)
class SocketFeatureValue:
    name: str
    status: str
    value_mm: Optional[float] = None
    max_value_mm: Optional[float] = None
    min_value_mm: Optional[float] = None
    detail: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class SocketGeometry:
    port_id: str
    depth: SocketFeatureValue
    diameter: SocketFeatureValue
    bore: SocketFeatureValue
    wall_thickness: SocketFeatureValue
    shoulder: SocketFeatureValue
    stop: SocketFeatureValue
    transition: SocketFeatureValue
    opening: SocketFeatureValue

    def to_dict(self):
        return {
            "port_id": self.port_id, "depth": self.depth.to_dict(), "diameter": self.diameter.to_dict(),
            "bore": self.bore.to_dict(), "wall_thickness": self.wall_thickness.to_dict(),
            "shoulder": self.shoulder.to_dict(), "stop": self.stop.to_dict(),
            "transition": self.transition.to_dict(), "opening": self.opening.to_dict(),
        }


def build_socket_geometry(port_id, bore_diameter_min, bore_diameter_max, bore_depth_min, bore_depth_max,
                           wall_thickness_min=None, wall_thickness_max=None, body_wall_thickness=None):
    """Sec.5/8: assembles a `SocketGeometry` from already-resolved
    authoritative dimension values (the caller/product builder has
    already obtained these from a GEOMETRY_READY GeometrySpecification -
    this function performs no resolution itself).

    `bore_diameter_min` may be `None` (socket-weld CAPS: confirmed live,
    ASME B16.11's cap table publishes socket_bore_depth_min/max_mm and
    cap_body_diameter_mm/cap_socket_length_mm, but NO socket bore
    diameter column at all - a genuine source gap, not an omission by
    this adapter) - `diameter`/`bore`/`opening` are then UNAVAILABLE
    rather than fabricated from the cap's overall body diameter.

    `shoulder` and `stop` are ALWAYS UNAVAILABLE: ASME B16.11's own
    min-wall-at-bottom field (canonical name socket_wall_min_at_bottom_mm,
    source column J_mm) has ZERO ingested facts anywhere in the canonical
    registry (confirmed live, Prompt 15 Sec.2 coverage inspection - the
    adapter validates the column but never converts it to an
    EngineeringFact) - never fabricated. Likewise there is no published
    pipe-insertion assembly-gap dimension (the commonly-cited ~1/16in
    gap is a fabrication practice, not a tabulated canonical fact).

    `transition` is CONSTRUCTION_DERIVED (an approximate outer-envelope
    radius at the socket = socket bore radius + fitting_body_wall_
    thickness_mm) only when BOTH an authoritative bore diameter AND
    body_wall_thickness are supplied (elbow/tee/cross only - couplings/
    half-couplings/caps have no fitting_body_wall_thickness_mm fact) -
    otherwise UNAVAILABLE."""
    if bore_diameter_min is not None:
        diameter = SocketFeatureValue(
            "socket_diameter", SOCKET_STATUS_AUTHORITATIVE, value_mm=bore_diameter_min,
            max_value_mm=bore_diameter_max, min_value_mm=bore_diameter_min,
            detail="socket_bore_diameter_min/max_mm (ASME B16.11) - min used as the generation value "
                   "(the tighter/worst-case bore).")
        bore = SocketFeatureValue(
            "socket_bore", SOCKET_STATUS_AUTHORITATIVE, value_mm=bore_diameter_min,
            detail="Same authoritative cavity as 'diameter', exposed separately per Sec.5's requested "
                   "socket-geometry vocabulary (socket diameter vs. bore are named separately).")
        opening = SocketFeatureValue(
            "opening", SOCKET_STATUS_AUTHORITATIVE, value_mm=bore_diameter_min,
            detail="The socket mouth - same diameter as 'diameter'; positioned at the port location "
                   "by the calling product builder.")
    else:
        diameter = SocketFeatureValue(
            "socket_diameter", SOCKET_STATUS_UNAVAILABLE,
            detail="No socket_bore_diameter_min/max_mm fact exists for this subtype (confirmed live: "
                   "ASME B16.11's cap table publishes no socket bore diameter column at all) - never "
                   "fabricated from the body's overall diameter.")
        bore = SocketFeatureValue(
            "socket_bore", SOCKET_STATUS_UNAVAILABLE,
            detail="Same gap as 'diameter' - no authoritative fact available.")
        opening = SocketFeatureValue(
            "opening", SOCKET_STATUS_UNAVAILABLE,
            detail="Same gap as 'diameter' - no authoritative fact available.")
    depth = SocketFeatureValue(
        "socket_depth", SOCKET_STATUS_AUTHORITATIVE, value_mm=bore_depth_min,
        max_value_mm=bore_depth_max, min_value_mm=bore_depth_min,
        detail="socket_bore_depth_min/max_mm (ASME B16.11) - min used as the generation value.")
    if wall_thickness_min is not None:
        wall = SocketFeatureValue(
            "socket_wall_thickness", SOCKET_STATUS_AUTHORITATIVE, value_mm=wall_thickness_min,
            max_value_mm=wall_thickness_max, min_value_mm=wall_thickness_min,
            detail="socket_wall_thickness_min/max_mm (ASME B16.11).")
    else:
        wall = SocketFeatureValue(
            "socket_wall_thickness", SOCKET_STATUS_UNAVAILABLE,
            detail="socket_wall_thickness_min_mm was not requested/resolved for this generation call.")
    shoulder = SocketFeatureValue(
        "shoulder", SOCKET_STATUS_UNAVAILABLE,
        detail="ASME B16.11's own min-wall-at-bottom field (socket_wall_min_at_bottom_mm, source "
               "column J_mm) has ZERO ingested facts anywhere in the canonical registry - confirmed "
               "live - never fabricated.")
    stop = SocketFeatureValue(
        "stop", SOCKET_STATUS_UNAVAILABLE,
        detail="No published pipe-insertion assembly-gap/stop-clearance dimension exists in the "
               "canonical registry - never invented.")
    if body_wall_thickness is not None and bore_diameter_min is not None:
        transition = SocketFeatureValue(
            "transition", SOCKET_STATUS_CONSTRUCTION_DERIVED,
            value_mm=(bore_diameter_min / 2.0 + body_wall_thickness),
            detail="Construction-derived outer-envelope radius at the socket "
                   "(socket_bore_radius + fitting_body_wall_thickness_mm) - an approximate transition "
                   "envelope, NOT an ASME-published contour.")
    else:
        transition = SocketFeatureValue(
            "transition", SOCKET_STATUS_UNAVAILABLE,
            detail="fitting_body_wall_thickness_mm is not available for this subtype (elbow/tee/cross-"
                   "only field) - no transition envelope constructed.")
    return SocketGeometry(port_id=port_id, depth=depth, diameter=diameter, bore=bore, wall_thickness=wall,
                           shoulder=shoulder, stop=stop, transition=transition, opening=opening)


def validate_socket_geometry(sg: SocketGeometry):
    """Sec.11: positive depth/diameter, min<=max where both present. Never
    silently clips an invalid value - raises `SocketGeometryError`."""
    if sg.diameter.value_mm is not None and sg.diameter.value_mm <= 0:
        raise SocketGeometryError(f"Socket {sg.port_id!r} diameter must be positive: {sg.diameter.value_mm!r}")
    if sg.depth.value_mm is not None and sg.depth.value_mm <= 0:
        raise SocketGeometryError(f"Socket {sg.port_id!r} depth must be positive: {sg.depth.value_mm!r}")
    for feat in (sg.diameter, sg.depth, sg.wall_thickness):
        if feat.min_value_mm is not None and feat.max_value_mm is not None:
            if feat.min_value_mm > feat.max_value_mm:
                raise SocketGeometryError(
                    f"Socket {sg.port_id!r} {feat.name} min ({feat.min_value_mm!r}) > "
                    f"max ({feat.max_value_mm!r}).")
    return True
