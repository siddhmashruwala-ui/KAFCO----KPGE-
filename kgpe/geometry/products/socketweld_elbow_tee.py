# -*- coding: utf-8 -*-
"""
kgpe.geometry.products.socketweld_elbow_tee
================================================
Prompt 15 Sec.3/13: ASME B16.11 socket-weld 90deg elbow, 45deg elbow, tee,
and cross. Required dimensions (centre_to_end_mm, fitting_body_wall_
thickness_mm, socket_bore_diameter_min_mm, socket_bore_depth_min_mm) are
all VERIFIED_AUTHORITATIVE (Prompt 15 Sec.2 live inspection).

Body outside diameter is NOT published by ASME B16.11 at all (confirmed
live - zero facts anywhere under product_family='socketweld_fitting') - it
is resolved EXTERNALLY via kgpe.geometry.cross_family.
SocketweldBodyOutsideDiameterViaPipeRule and passed in as `body_od_value`
(a resolved ConstructionValue) through GeometryKernel.generate()'s
product_kwargs, exactly like Prompt 13/14's wall-context/bore patterns.
If not supplied, this builder raises ConstructionRuleUnavailableError -
Sec.18 requires a structured blocked outcome, never a fabricated OD.

Representation: the mesh models ONLY the external body envelope - two
overlapping arms (elbow), three (tee), or four (cross) solid cylindrical
arms joined at the origin, honestly non-manifold at the intersection
(mirrors buttweld_elbow/tee's own multi-feature pattern, Prompt 13
Sec.29). Socket cavities (depth/diameter/wall/shoulder/stop/transition/
opening) are represented as `kgpe.geometry.socket_geometry.SocketGeometry`
feature metadata at each port - NEVER boolean-cut into the mesh (Sec.13,
mirrors Prompt 14's bolt-hole-metadata precedent exactly).

Coordinate convention: elbow bend plane = X-Z plane (matches Prompt 13's
buttweld-elbow convention); tee/cross branches extend along +-Y from the
run centreline, exactly like buttweld_tee_equal.
"""
import math

from ..builders import build_two_arm_multi_feature, build_tee_multi_feature, build_cross_multi_feature
from ..measurement import measure_radial_distance
from ..product_api import ProductGeometryBuild, GeometryInputError, ConstructionRuleUnavailableError
from ..ports import ConnectionPort, OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE
from ..result import TopologyRepresentation
from ..construction_value import ConstructionValue
from ..socket_geometry import build_socket_geometry, validate_socket_geometry, SocketGeometryError

GEOMETRY_TYPE = "socketweld_elbow_tee"

_ANGLE_BY_SUBTYPE = {"elbow_90_sw": math.pi / 2.0, "elbow_45_sw": math.pi / 4.0}

_REQUIRED = ("centre_to_end_mm", "fitting_body_wall_thickness_mm",
             "socket_bore_diameter_min_mm", "socket_bore_depth_min_mm")


def _opt_float(opt, name):
    entry = opt.get(name)
    return float(entry["value"]) if entry is not None else None


def build(geometry_spec, generation_parameters, body_od_value=None):
    if body_od_value is None:
        raise ConstructionRuleUnavailableError(
            "socketweld_elbow_tee geometry requires an externally-resolved body_od_value "
            "(kgpe.geometry.cross_family.SocketweldBodyOutsideDiameterViaPipeRule) - ASME B16.11 "
            "does not publish a fitting-body OD of its own; never fabricated.")

    dims = geometry_spec.required_dimensions
    opt = geometry_spec.optional_dimensions
    missing = [k for k in _REQUIRED if k not in dims]
    if missing:
        raise GeometryInputError(
            f"socketweld_elbow_tee geometry requires {list(_REQUIRED)} - got {sorted(dims.keys())}")

    cte = float(dims["centre_to_end_mm"]["value"])
    body_wall = float(dims["fitting_body_wall_thickness_mm"]["value"])
    bore_min = float(dims["socket_bore_diameter_min_mm"]["value"])
    depth_min = float(dims["socket_bore_depth_min_mm"]["value"])
    bore_max = _opt_float(opt, "socket_bore_diameter_max_mm")
    depth_max = _opt_float(opt, "socket_bore_depth_max_mm")
    wall_min = _opt_float(opt, "socket_wall_thickness_min_mm")
    wall_max = _opt_float(opt, "socket_wall_thickness_max_mm")

    if not (0.0 < cte):
        raise GeometryInputError(f"centre_to_end_mm must be positive, got {cte!r}")
    if not (0.0 < bore_min):
        raise GeometryInputError(f"socket_bore_diameter_min_mm must be positive, got {bore_min!r}")

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

    trace = [f"socketweld_elbow_tee: subtype={subtype!r} body_OD={body_od}mm (via "
             f"{body_od_value.rule_id} v{body_od_value.rule_version}, cross-family pipe reference) - "
             f"socket cavities represented as feature metadata only, never boolean-cut."]

    def _make_socket(port_id):
        try:
            sg = build_socket_geometry(port_id, bore_min, bore_max, depth_min, depth_max,
                                        wall_min, wall_max, body_wall)
            validate_socket_geometry(sg)
        except SocketGeometryError as e:
            raise GeometryInputError(f"socket geometry invalid for port {port_id!r}: {e}")
        return sg

    if subtype in _ANGLE_BY_SUBTYPE:
        angle = _ANGLE_BY_SUBTYPE[subtype]
        mesh, features = build_two_arm_multi_feature(radius, cte, cte, angle, n)
        arm_a_wall = next(f for f in features if f["name"] == "arm_a_outer_wall")
        arm_a_ring0 = range(arm_a_wall["vertex_range"][0], arm_a_wall["vertex_range"][0] + n)
        measured_od = 2.0 * measure_radial_distance(mesh, arm_a_ring0, axis_point=(0.0, 0.0))
        arm_a_end = next(f for f in features if f["name"] == "arm_a_end_cap")
        arm_b_end = next(f for f in features if f["name"] == "arm_b_end_cap")
        port_a_pos = tuple(mesh.vertices[arm_a_end["vertex_range"][0]])
        port_b_pos = tuple(mesh.vertices[arm_b_end["vertex_range"][0]])
        port_b_dir = (math.sin(angle), 0.0, math.cos(angle))
        ports = [
            ConnectionPort(port_id="inlet_socket", role="inlet_socket", position=port_a_pos,
                            direction=(0.0, 0.0, 1.0), size_identity=size_identity, opening_diameter_mm=bore_min,
                            opening_diameter_provenance=OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE),
            ConnectionPort(port_id="outlet_socket", role="outlet_socket", position=port_b_pos,
                            direction=port_b_dir, size_identity=size_identity, opening_diameter_mm=bore_min,
                            opening_diameter_provenance=OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE),
        ]
        socket_port_ids = ("inlet_socket", "outlet_socket")
        measurements = {"outside_diameter_mm": measured_od, "centre_to_end_mm": cte}

    elif subtype == "tee_sw":
        mesh, features = build_tee_multi_feature(radius, cte, radius, cte, n)
        run_wall = next(f for f in features if f["name"] == "run_outer_wall")
        run_ring0 = range(run_wall["vertex_range"][0], run_wall["vertex_range"][0] + n)
        measured_od = 2.0 * measure_radial_distance(mesh, run_ring0, axis_point=(0.0, 0.0))
        ports = [
            ConnectionPort(port_id="run_inlet_socket", role="run_inlet_socket", position=(0.0, 0.0, -cte),
                            direction=(0.0, 0.0, -1.0), size_identity=size_identity, opening_diameter_mm=bore_min,
                            opening_diameter_provenance=OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE),
            ConnectionPort(port_id="run_outlet_socket", role="run_outlet_socket", position=(0.0, 0.0, cte),
                            direction=(0.0, 0.0, 1.0), size_identity=size_identity, opening_diameter_mm=bore_min,
                            opening_diameter_provenance=OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE),
            ConnectionPort(port_id="branch_socket", role="branch_socket", position=(0.0, cte, 0.0),
                            direction=(0.0, 1.0, 0.0), size_identity=size_identity, opening_diameter_mm=bore_min,
                            opening_diameter_provenance=OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE),
        ]
        socket_port_ids = ("run_inlet_socket", "run_outlet_socket", "branch_socket")
        measurements = {"outside_diameter_mm": measured_od, "centre_to_end_mm": cte}

    elif subtype == "cross_sw":
        mesh, features = build_cross_multi_feature(radius, cte, cte, cte, n)
        run_wall = next(f for f in features if f["name"] == "run_outer_wall")
        run_ring0 = range(run_wall["vertex_range"][0], run_wall["vertex_range"][0] + n)
        measured_od = 2.0 * measure_radial_distance(mesh, run_ring0, axis_point=(0.0, 0.0))
        ports = [
            ConnectionPort(port_id="run_inlet_socket", role="run_inlet_socket", position=(0.0, 0.0, -cte),
                            direction=(0.0, 0.0, -1.0), size_identity=size_identity, opening_diameter_mm=bore_min,
                            opening_diameter_provenance=OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE),
            ConnectionPort(port_id="run_outlet_socket", role="run_outlet_socket", position=(0.0, 0.0, cte),
                            direction=(0.0, 0.0, 1.0), size_identity=size_identity, opening_diameter_mm=bore_min,
                            opening_diameter_provenance=OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE),
            ConnectionPort(port_id="branch_a_socket", role="branch_socket", position=(0.0, cte, 0.0),
                            direction=(0.0, 1.0, 0.0), size_identity=size_identity, opening_diameter_mm=bore_min,
                            opening_diameter_provenance=OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE),
            ConnectionPort(port_id="branch_b_socket", role="branch_socket", position=(0.0, -cte, 0.0),
                            direction=(0.0, -1.0, 0.0), size_identity=size_identity, opening_diameter_mm=bore_min,
                            opening_diameter_provenance=OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE),
        ]
        socket_port_ids = ("run_inlet_socket", "run_outlet_socket", "branch_a_socket", "branch_b_socket")
        measurements = {"outside_diameter_mm": measured_od, "centre_to_end_mm": cte}

    else:
        raise GeometryInputError(f"socketweld_elbow_tee builder does not recognize subtype {subtype!r}")

    socket_metadata = {pid: _make_socket(pid).to_dict() for pid in socket_port_ids}
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
    expected = {"outside_diameter_mm": body_od, "centre_to_end_mm": cte}

    return ProductGeometryBuild(
        geometry_type=GEOMETRY_TYPE, mesh=mesh, features=features, construction_values=[od_marker],
        measurements=measurements, expected_dimensions=expected, trace=trace, ports=ports,
        topology_representation=TopologyRepresentation.MULTI_FEATURE_MESH_WITH_SOCKET_METADATA_NO_BOOLEAN_CUT,
    )
