# -*- coding: utf-8 -*-
"""
kgpe.geometry.products.socketweld_cap
==========================================
Prompt 15 Sec.3/13: ASME B16.11 socket-weld cap. Required dimensions
(cap_body_diameter_mm, cap_socket_length_mm, socket_bore_depth_min_mm) are
all VERIFIED_AUTHORITATIVE (Prompt 15 Sec.2 live inspection) -
cap_body_diameter_mm (source: CapDia_R_mm) is the cap's OWN body OD, a
genuinely different, self-contained dimension from the mating-pipe-OD gap
that affects elbow/tee/cross/coupling/half-coupling - NO cross-family
rule is needed here.

Confirmed live: ASME B16.11's cap table publishes NO socket bore diameter
column at all (only SocketBoreDepth_B_max/min, SocketLength_Q, CapDia_R) -
a genuine source gap. The socket's diameter/bore/opening are therefore
UNAVAILABLE in the resulting `SocketGeometry` metadata (see
kgpe.geometry.socket_geometry.build_socket_geometry's None-safe handling)
- never fabricated from the overall body diameter.

Representation: reuses `kgpe.geometry.builders.build_cap_solid` (Prompt
13's buttweld-cap primitive) - open end at z=0 (socket opening, where the
mating pipe inserts), closed flat disc at z=cap_socket_length_mm.
"""
from ..builders import build_cap_solid
from ..measurement import measure_radial_distance, measure_axial_length
from ..product_api import ProductGeometryBuild, GeometryInputError
from ..ports import ConnectionPort, OPENING_DIAMETER_PROVENANCE_NOT_MODELED
from ..result import TopologyRepresentation
from ..socket_geometry import build_socket_geometry, validate_socket_geometry, SocketGeometryError

GEOMETRY_TYPE = "socketweld_cap"

_REQUIRED = ("cap_body_diameter_mm", "cap_socket_length_mm", "socket_bore_depth_min_mm")


def _opt_float(opt, name):
    entry = opt.get(name)
    return float(entry["value"]) if entry is not None else None


def build(geometry_spec, generation_parameters):
    dims = geometry_spec.required_dimensions
    opt = geometry_spec.optional_dimensions
    missing = [k for k in _REQUIRED if k not in dims]
    if missing:
        raise GeometryInputError(
            f"socketweld_cap geometry requires {list(_REQUIRED)} - got {sorted(dims.keys())}")

    body_od = float(dims["cap_body_diameter_mm"]["value"])
    length = float(dims["cap_socket_length_mm"]["value"])
    depth_min = float(dims["socket_bore_depth_min_mm"]["value"])
    depth_max = _opt_float(opt, "socket_bore_depth_max_mm")

    if not (0.0 < body_od):
        raise GeometryInputError(f"cap_body_diameter_mm must be positive, got {body_od!r}")
    if not (0.0 < length):
        raise GeometryInputError(f"cap_socket_length_mm must be positive, got {length!r}")

    n = generation_parameters.radial_segments
    mesh, features = build_cap_solid(body_od / 2.0, length, n)

    body_wall = next(f for f in features if f["name"] == "cap_body_wall")
    ring0 = range(body_wall["vertex_range"][0], body_wall["vertex_range"][0] + n)
    measured_od = 2.0 * measure_radial_distance(mesh, ring0, axis_point=(0.0, 0.0))
    measured_length = measure_axial_length(mesh)

    try:
        sg = build_socket_geometry("socket_opening", None, None, depth_min, depth_max,
                                    wall_thickness_min=None, wall_thickness_max=None,
                                    body_wall_thickness=None)
        validate_socket_geometry(sg)
    except SocketGeometryError as e:
        raise GeometryInputError(f"socket geometry invalid for cap: {e}")

    features = list(features) + [{
        "name": "socket_geometry", "type": "socket_metadata_bundle",
        "vertex_range": [0, 0], "face_range": [0, 0], "params": {"socket_opening": sg.to_dict()},
    }]

    identity = geometry_spec.engineering_object_identity or {}
    size_identity = {k: identity.get(k) for k in ("size_system", "primary_size")}
    port = ConnectionPort(
        port_id="socket_opening", role="socket_opening", position=(0.0, 0.0, 0.0),
        direction=(0.0, 0.0, -1.0), size_identity=size_identity, opening_diameter_mm=None,
        opening_diameter_provenance=OPENING_DIAMETER_PROVENANCE_NOT_MODELED)

    trace = [
        f"socketweld_cap: body_OD={body_od}mm (cap_body_diameter_mm, authoritative, no cross-family "
        f"rule needed) socket_length={length}mm (cap_socket_length_mm) - socket bore diameter is "
        f"UNAVAILABLE (no such column exists in the ASME B16.11 cap source table).",
    ]
    measurements = {"outside_diameter_mm": measured_od, "cap_socket_length_mm": measured_length}
    expected = {"outside_diameter_mm": body_od, "cap_socket_length_mm": length}

    return ProductGeometryBuild(
        geometry_type=GEOMETRY_TYPE, mesh=mesh, features=features, construction_values=[],
        measurements=measurements, expected_dimensions=expected, trace=trace, ports=[port],
        topology_representation=TopologyRepresentation.SOLID_EXTERNAL_ENVELOPE_WITH_SOCKET_METADATA_NO_BOOLEAN_CUT,
    )
