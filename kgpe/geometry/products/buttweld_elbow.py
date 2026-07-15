# -*- coding: utf-8 -*-
"""
kgpe.geometry.products.buttweld_elbow
=========================================
Prompt 12 Sec.22-23: Reference Product B - ASME B16.9 90 degree long-
radius elbow (`buttweld_elbow` geometry profile, Prompt 11). Selected
because its required dimensions (outside_diameter_mm, centre_to_end_mm)
are already authoritative with no cross-family/construction-rule gap
(unlike the reducer/socketweld/flange-bore cases Prompt 11 registered as
blocked), and because it directly exercises the arc-sweep/revolution
primitives future elbow/tee/reducer product modules will reuse.

Geometric mapping (no construction rule needed - both dimensions are
consumed directly, not derived): a 90 degree long-radius elbow's
`centre_to_end_mm` IS its bend radius (the standard's own definition -
the distance from the fitting's theoretical centreline intersection to
its face equals the radius of the swept arc for a 90 degree bend).
No bore is modeled - wall_thickness/bore is not part of this profile's
required (or, absent an explicit request, included optional) dimension
set; documented honestly rather than fabricated.
"""
import math

from ..builders import build_arc_swept_solid
from ..measurement import measure_radial_distance, measure_bend_radius
from ..product_api import ProductGeometryBuild, GeometryInputError

GEOMETRY_TYPE = "buttweld_elbow_90_lr"
BEND_ANGLE_RAD = math.pi / 2.0


def build(geometry_spec, generation_parameters):
    dims = geometry_spec.required_dimensions
    od_entry = dims.get("outside_diameter_mm")
    cte_entry = dims.get("centre_to_end_mm")
    if od_entry is None or cte_entry is None:
        raise GeometryInputError(
            f"buttweld_elbow geometry requires outside_diameter_mm and centre_to_end_mm - "
            f"got {sorted(dims.keys())}")

    od = float(od_entry["value"])
    bend_radius = float(cte_entry["value"])

    mesh, features = build_arc_swept_solid(
        outer_radius=od / 2.0, bend_radius=bend_radius, total_angle_rad=BEND_ANGLE_RAD,
        radial_segments=generation_parameters.radial_segments,
        sweep_segments=generation_parameters.sweep_segments,
    )

    swept = next(f for f in features if f["name"] == "swept_outer_profile")
    start_ring_indices = range(swept["vertex_range"][0], swept["vertex_range"][0] + generation_parameters.radial_segments)
    start_cap = next(f for f in features if f["name"] == "end_cap_start")
    end_cap = next(f for f in features if f["name"] == "end_cap_end")

    measured_od = 2.0 * measure_radial_distance(mesh, start_ring_indices, axis_point=(0.0, 0.0))
    pivot = (bend_radius, 0.0, 0.0)
    measured_bend_radius = measure_bend_radius(
        mesh, [start_cap["vertex_range"][0], end_cap["vertex_range"][0]], pivot=pivot)

    measurements = {"outside_diameter_mm": measured_od, "centre_to_end_mm": measured_bend_radius}
    expected = {"outside_diameter_mm": od, "centre_to_end_mm": bend_radius}
    trace = [
        f"buttweld_elbow: OD={od}mm centre_to_end_mm={bend_radius}mm consumed directly as bend radius "
        f"(no construction rule required - both are authoritative canonical dimensions)",
        f"buttweld_elbow: swept through {math.degrees(BEND_ANGLE_RAD)} degrees",
    ]
    return ProductGeometryBuild(
        geometry_type=GEOMETRY_TYPE, mesh=mesh, features=features, construction_values=[],
        measurements=measurements, expected_dimensions=expected, trace=trace,
    )
