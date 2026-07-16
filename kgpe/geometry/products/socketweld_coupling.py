# -*- coding: utf-8 -*-
"""
kgpe.geometry.products.socketweld_coupling
===============================================
Prompt 15 Sec.3/13: ASME B16.11 socket-weld full coupling and half
coupling. Required dimensions (end_to_end_mm, socket_bore_diameter_min_mm,
socket_bore_depth_min_mm) are VERIFIED_AUTHORITATIVE (Prompt 15 Sec.2 live
inspection) - each subtype has its OWN end_to_end_mm (laying length,
source columns E/F respectively), never averaged or substituted between
the two.

Body outside diameter is NOT published by ASME B16.11 (same curated gap
as the elbow/tee/cross family) - resolved EXTERNALLY via
kgpe.geometry.cross_family.SocketweldBodyOutsideDiameterViaPipeRule and
passed in as `body_od_value` through product_kwargs; raises
ConstructionRuleUnavailableError if not supplied.

Representation: a single solid cylindrical body envelope
(kgpe.geometry.builders.build_solid_cylinder), length=end_to_end_mm,
spanning z in [0, end_to_end_mm]. Coupling exposes TWO socket ports (both
ends open); half coupling exposes ONE real socket port ("pipe_side") plus
a documented "closed_side" port with NO opening
(opening_diameter_provenance=NOT_MODELED) - mirroring Prompt 14's blind-
flange precedent of never fabricating an opening that does not exist.
Socket cavity geometry is feature metadata only, never boolean-cut.
"""
from ..builders import build_solid_cylinder
from ..measurement import measure_radial_distance, measure_axial_length
from ..product_api import ProductGeometryBuild, GeometryInputError, ConstructionRuleUnavailableError
from ..ports import ConnectionPort, OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE, OPENING_DIAMETER_PROVENANCE_NOT_MODELED
from ..result import TopologyRepresentation
from ..construction_value import ConstructionValue
from ..socket_geometry import build_socket_geometry, validate_socket_geometry, SocketGeometryError

GEOMETRY_TYPE = "socketweld_coupling"

_REQUIRED = ("end_to_end_mm", "socket_bore_diameter_min_mm", "socket_bore_depth_min_mm")


def _opt_float(opt, name):
    entry = opt.get(name)
    return float(entry["value"]) if entry is not None else None


def build(geometry_spec, generation_parameters, body_od_value=None):
    if body_od_value is None:
        raise ConstructionRuleUnavailableError(
            "socketweld_coupling geometry requires an externally-resolved body_od_value "
            "(kgpe.geometry.cross_family.SocketweldBodyOutsideDiameterViaPipeRule) - ASME B16.11 "
            "does not publish a fitting-body OD of its own; never fabricated.")

    dims = geometry_spec.required_dimensions
    opt = geometry_spec.optional_dimensions
    missing = [k for k in _REQUIRED if k not in dims]
    if missing:
        raise GeometryInputError(
            f"socketweld_coupling geometry requires {list(_REQUIRED)} - got {sorted(dims.keys())}")

    length = float(dims["end_to_end_mm"]["value"])
    bore_min = float(dims["socket_bore_diameter_min_mm"]["value"])
    depth_min = float(dims["socket_bore_depth_min_mm"]["value"])
    bore_max = _opt_float(opt, "socket_bore_diameter_max_mm")
    depth_max = _opt_float(opt, "socket_bore_depth_max_mm")
    wall_min = _opt_float(opt, "socket_wall_thickness_min_mm")
    wall_max = _opt_float(opt, "socket_wall_thickness_max_mm")

    if not (0.0 < length):
        raise GeometryInputError(f"end_to_end_mm must be positive, got {length!r}")

    body_od = float(body_od_value.value)
    if bore_min >= body_od:
        raise GeometryInputError(
            f"socket_bore_diameter_min_mm ({bore_min!r}) must be less than the derived body OD "
            f"({body_od!r}).")
    radius = body_od / 2.0
    n = generation_parameters.radial_segments

    identity = geometry_spec.engineering_object_identity or {}
    subtype = identity.get("subtype")
    size_identity = {k: identity.get(k) for k in ("size_system", "primary_size")}
    is_half = subtype == "half_coupling_sw"

    mesh, features = build_solid_cylinder(radius, length, n)
    outer_wall = next(f for f in features if f["name"] == "outer_wall")
    outer_ring0 = range(outer_wall["vertex_range"][0], outer_wall["vertex_range"][0] + n)
    measured_od = 2.0 * measure_radial_distance(mesh, outer_ring0, axis_point=(0.0, 0.0))
    measured_length = measure_axial_length(mesh)

    def _make_socket(port_id):
        try:
            sg = build_socket_geometry(port_id, bore_min, bore_max, depth_min, depth_max,
                                        wall_min, wall_max, body_wall_thickness=None)
            validate_socket_geometry(sg)
        except SocketGeometryError as e:
            raise GeometryInputError(f"socket geometry invalid for port {port_id!r}: {e}")
        return sg

    if is_half:
        pipe_side = ConnectionPort(
            port_id="pipe_side", role="pipe_side_socket", position=(0.0, 0.0, 0.0),
            direction=(0.0, 0.0, -1.0), size_identity=size_identity, opening_diameter_mm=bore_min,
            opening_diameter_provenance=OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE)
        closed_side = ConnectionPort(
            port_id="closed_side", role="closed_side", position=(0.0, 0.0, length),
            direction=(0.0, 0.0, 1.0), size_identity=size_identity, opening_diameter_mm=None,
            opening_diameter_provenance=OPENING_DIAMETER_PROVENANCE_NOT_MODELED)
        ports = [pipe_side, closed_side]
        socket_metadata = {"pipe_side": _make_socket("pipe_side").to_dict()}
        trace_note = "half_coupling_sw: ONE real socket (pipe_side) + one documented closed_side port " \
                     "with NO opening (never fabricated) - mirrors the Prompt 14 blind-flange precedent."
    else:
        end_a = ConnectionPort(
            port_id="socket_a", role="socket", position=(0.0, 0.0, 0.0),
            direction=(0.0, 0.0, -1.0), size_identity=size_identity, opening_diameter_mm=bore_min,
            opening_diameter_provenance=OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE)
        end_b = ConnectionPort(
            port_id="socket_b", role="socket", position=(0.0, 0.0, length),
            direction=(0.0, 0.0, 1.0), size_identity=size_identity, opening_diameter_mm=bore_min,
            opening_diameter_provenance=OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE)
        ports = [end_a, end_b]
        socket_metadata = {"socket_a": _make_socket("socket_a").to_dict(),
                            "socket_b": _make_socket("socket_b").to_dict()}
        trace_note = "coupling_sw: two open socket ports (both ends)."

    features = list(features) + [{
        "name": "socket_geometry", "type": "socket_metadata_bundle",
        "vertex_range": [0, 0], "face_range": [0, 0], "params": socket_metadata,
    }]

    od_marker = ConstructionValue(
        name="body_outside_diameter_mm", value=body_od, unit="mm",
        rule_id=body_od_value.rule_id, rule_version=body_od_value.rule_version,
        input_dimension_refs=body_od_value.input_dimension_refs,
        derivation_trace=body_od_value.derivation_trace,
    )
    trace = [
        f"socketweld_coupling: subtype={subtype!r} body_OD={body_od}mm (via "
        f"{body_od_value.rule_id} v{body_od_value.rule_version}, cross-family pipe reference) - "
        f"socket cavities represented as feature metadata only, never boolean-cut.",
        trace_note,
    ]
    measurements = {"outside_diameter_mm": measured_od, "end_to_end_mm": measured_length}
    expected = {"outside_diameter_mm": body_od, "end_to_end_mm": length}

    return ProductGeometryBuild(
        geometry_type=GEOMETRY_TYPE, mesh=mesh, features=features, construction_values=[od_marker],
        measurements=measurements, expected_dimensions=expected, trace=trace, ports=ports,
        topology_representation=TopologyRepresentation.SOLID_EXTERNAL_ENVELOPE_WITH_SOCKET_METADATA_NO_BOOLEAN_CUT,
    )
