# -*- coding: utf-8 -*-
"""
kgpe.geometry.products.buttweld_elbow
=========================================
Prompt 12 Sec.22-23 (original 90-deg LR reference) upgraded by Prompt 13
Sec.10-11 to a single parameterized builder covering every canonical
ASME B16.9 elbow subtype whose required dimensions are live-confirmed
available: elbow_90_lr, elbow_45_lr, elbow_90_3d, elbow_45_3d,
elbow_90_sr (all share the SAME geometry profile, `buttweld_elbow`, and
the SAME required-dimension pair - outside_diameter_mm + centre_to_end_mm
- confirmed live this prompt for all five subtypes at NPS4/NPS6, and
correctly QUARANTINED_ENGINEERING_DATA-blocked at NPS8/NPS12 for all
five, same as the reference 90-LR case). The subtype determines ONLY the
bend angle - `centre_to_end_mm` is always consumed directly as the bend
radius (the standard's own definition), never re-derived per subtype.

Backward compatibility (Prompt 13 Sec.34): the exact same request that
worked in Prompt 12 (elbow_90_lr, no wall context) produces the identical
external-envelope geometry via the identical code path (BEND_ANGLE_RAD
for elbow_90_lr matches Prompt 12's constant exactly; wall_thickness_value
defaults to None => solid/external mode, unchanged from Prompt 12).

Hollow upgrade (Sec.9): if an already-RESOLVED `wall_thickness_value`
(a `kgpe.geometry.construction_value.ConstructionValue`, produced
upstream by `kgpe.geometry.cross_family.ButtweldWallViaPipeScheduleRule`
- this builder NEVER resolves it itself, preserving the kernel's
never-resolves-a-request architecture) is supplied, a hollow elbow is
built instead (outer sweep, inner sweep/bore, two annular end caps).
Wall thickness is never fabricated - absent `wall_thickness_value`,
the external-envelope-only mode is used and honestly reported via
`topology_representation`.
"""
import math

from ..builders import build_arc_swept_solid, build_arc_swept_hollow_solid
from ..measurement import measure_radial_distance, measure_bend_radius, measure_axial_length
from ..product_api import ProductGeometryBuild, GeometryInputError
from ..ports import ConnectionPort, OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE, OPENING_DIAMETER_PROVENANCE_DERIVED
from ..result import TopologyRepresentation

GEOMETRY_TYPE = "buttweld_elbow"

# Sec.10: subtype -> bend angle (radians). centre_to_end_mm is always the
# bend radius directly - only the ANGLE varies by subtype, never inferred.
_SUBTYPE_BEND_ANGLE_RAD = {
    "elbow_90_lr": math.pi / 2.0,
    "elbow_45_lr": math.pi / 4.0,
    "elbow_90_3d": math.pi / 2.0,
    "elbow_45_3d": math.pi / 4.0,
    "elbow_90_sr": math.pi / 2.0,
}
# Retained for exact Prompt 12 compatibility/documentation.
BEND_ANGLE_RAD = _SUBTYPE_BEND_ANGLE_RAD["elbow_90_lr"]


def build(geometry_spec, generation_parameters, wall_thickness_value=None):
    subtype = (geometry_spec.engineering_object_identity or {}).get("subtype")
    bend_angle_rad = _SUBTYPE_BEND_ANGLE_RAD.get(subtype)
    if bend_angle_rad is None:
        raise GeometryInputError(
            f"buttweld_elbow geometry does not recognize subtype {subtype!r} - supported: "
            f"{sorted(_SUBTYPE_BEND_ANGLE_RAD)}")

    dims = geometry_spec.required_dimensions
    od_entry = dims.get("outside_diameter_mm")
    cte_entry = dims.get("centre_to_end_mm")
    if od_entry is None or cte_entry is None:
        raise GeometryInputError(
            f"buttweld_elbow geometry requires outside_diameter_mm and centre_to_end_mm - "
            f"got {sorted(dims.keys())}")

    od = float(od_entry["value"])
    bend_radius = float(cte_entry["value"])
    outer_radius = od / 2.0
    n, sw = generation_parameters.radial_segments, generation_parameters.sweep_segments

    trace = [f"buttweld_elbow[{subtype}]: OD={od}mm centre_to_end_mm={bend_radius}mm consumed directly "
             f"as bend radius (no construction rule required - both authoritative canonical dimensions)",
             f"buttweld_elbow[{subtype}]: swept through {math.degrees(bend_angle_rad)} degrees"]

    if wall_thickness_value is not None:
        wt = float(wall_thickness_value.value)
        inner_radius = outer_radius - wt
        if inner_radius <= 0:
            raise GeometryInputError(
                f"buttweld_elbow: derived inner_radius ({inner_radius}mm) is not positive given "
                f"OD={od}mm and wall_thickness={wt}mm.")
        mesh, features = build_arc_swept_hollow_solid(outer_radius, inner_radius, bend_radius,
                                                        bend_angle_rad, n, sw)
        topology = TopologyRepresentation.HOLLOW_SWEPT_SOLID
        trace.append(f"buttweld_elbow[{subtype}]: hollow mode - wall_thickness={wt}mm via rule "
                     f"{wall_thickness_value.rule_id} v{wall_thickness_value.rule_version} "
                     f"-> bore_radius={inner_radius}mm")
        construction_values = [wall_thickness_value]
        bore_feature_prefix = "swept_inner_profile_bore"
    else:
        mesh, features = build_arc_swept_solid(outer_radius, bend_radius, bend_angle_rad, n, sw)
        topology = TopologyRepresentation.SOLID_EXTERNAL_ENVELOPE
        trace.append(f"buttweld_elbow[{subtype}]: no wall context supplied - external-envelope-only mode "
                     f"(honestly reported, wall thickness never fabricated)")
        construction_values = []
        bore_feature_prefix = None

    swept = next(f for f in features if f["name"] == "swept_outer_profile")
    start_ring_indices = range(swept["vertex_range"][0], swept["vertex_range"][0] + n)
    end_ring_indices = range(swept["vertex_range"][1] - n + 1, swept["vertex_range"][1] + 1)

    measured_od = 2.0 * measure_radial_distance(mesh, start_ring_indices, axis_point=(0.0, 0.0))
    pivot = (bend_radius, 0.0, 0.0)
    # Sec.25 measurement note: the swept path's ring centre at each end is
    # not always a single dedicated mesh vertex (the hollow builder has no
    # centre vertex - only the solid builder's flat end caps do), so it is
    # computed here as the arithmetic mean of that ring's vertices - exact
    # (not approximate) for a `circle_ring()`-generated regular n-gon by
    # symmetry, since the ring is evenly spaced in angle around its centre.
    def _ring_centroid(indices):
        pts = [mesh.vertices[i] for i in indices]
        n_pts = len(pts)
        return (sum(p[0] for p in pts) / n_pts, sum(p[1] for p in pts) / n_pts, sum(p[2] for p in pts) / n_pts)

    start_center = _ring_centroid(start_ring_indices)
    end_center = _ring_centroid(end_ring_indices)
    measured_bend_radius = (
        math.sqrt(sum((a - b) ** 2 for a, b in zip(start_center, pivot))) +
        math.sqrt(sum((a - b) ** 2 for a, b in zip(end_center, pivot)))
    ) / 2.0

    measurements = {"outside_diameter_mm": measured_od, "centre_to_end_mm": measured_bend_radius}
    expected = {"outside_diameter_mm": od, "centre_to_end_mm": bend_radius}
    if wall_thickness_value is not None:
        bore_feature = next(f for f in features if f["name"] == bore_feature_prefix)
        bore_ring_indices = range(bore_feature["vertex_range"][0], bore_feature["vertex_range"][0] + n)
        measured_bore = 2.0 * measure_radial_distance(mesh, bore_ring_indices, axis_point=(0.0, 0.0))
        measurements["bore_diameter_mm"] = measured_bore
        expected["bore_diameter_mm"] = 2.0 * inner_radius

    size_identity = {k: (geometry_spec.engineering_object_identity or {}).get(k)
                      for k in ("size_system", "primary_size")}
    if wall_thickness_value is not None:
        opening_diameter_mm, opening_provenance = 2.0 * inner_radius, OPENING_DIAMETER_PROVENANCE_DERIVED
    else:
        opening_diameter_mm, opening_provenance = None, "NOT_MODELED"

    inlet_port = ConnectionPort(
        port_id="inlet", role="inlet", position=(0.0, 0.0, 0.0), direction=(0.0, 0.0, -1.0),
        size_identity=size_identity, opening_diameter_mm=opening_diameter_mm,
        opening_diameter_provenance=opening_provenance)
    outlet_direction = (math.sin(bend_angle_rad), 0.0, math.cos(bend_angle_rad))
    outlet_center = (bend_radius - bend_radius * math.cos(bend_angle_rad), 0.0,
                      bend_radius * math.sin(bend_angle_rad))
    outlet_port = ConnectionPort(
        port_id="outlet", role="outlet", position=outlet_center, direction=outlet_direction,
        size_identity=size_identity, opening_diameter_mm=opening_diameter_mm,
        opening_diameter_provenance=opening_provenance)

    return ProductGeometryBuild(
        geometry_type=f"buttweld_{subtype}", mesh=mesh, features=features,
        construction_values=construction_values, measurements=measurements, expected_dimensions=expected,
        trace=trace, ports=[inlet_port, outlet_port], topology_representation=topology,
    )
