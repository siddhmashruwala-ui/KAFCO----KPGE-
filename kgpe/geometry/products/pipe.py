# -*- coding: utf-8 -*-
"""
kgpe.geometry.products.pipe
===============================
Prompt 12 Sec.18/21: Reference Product A. Consumes a GEOMETRY_READY pipe
`GeometrySpecification` (required dims: outside_diameter_mm,
wall_thickness_mm), derives bore via the approved
`PipeBoreConstructionRule` (never invented, never written back to the
canonical registry), builds a hollow cylindrical solid via the shared
primitive/mesh layer, and reports measurements for dimensional validation.
"""
from ..construction_rules import PipeBoreConstructionRule
from ..builders import build_hollow_cylinder
from ..measurement import measure_radial_distance, measure_axial_length
from ..product_api import ProductGeometryBuild, GeometryInputError, ConstructionRuleUnavailableError

GEOMETRY_TYPE = "pipe_segment"


def build(geometry_spec, generation_parameters):
    dims = geometry_spec.required_dimensions
    od_entry = dims.get("outside_diameter_mm")
    wt_entry = dims.get("wall_thickness_mm")
    if od_entry is None or wt_entry is None:
        raise GeometryInputError(
            f"pipe geometry requires outside_diameter_mm and wall_thickness_mm - "
            f"got {sorted(dims.keys())}")

    bore_rule = PipeBoreConstructionRule()
    outcome = bore_rule.apply(
        od_value=od_entry["value"], od_unit=od_entry["unit"],
        od_source_ref={"name": "outside_diameter_mm", "source_file": od_entry.get("source_file")},
        wt_value=wt_entry["value"], wt_unit=wt_entry["unit"],
        wt_source_ref={"name": "wall_thickness_mm", "source_file": wt_entry.get("source_file")},
    )
    if not outcome.is_applied():
        raise ConstructionRuleUnavailableError(f"pipe bore construction rule could not be applied: {outcome.detail}")
    bore_cv = outcome.value

    od = float(od_entry["value"])
    wt = float(wt_entry["value"])
    length = generation_parameters.pipe_segment_length_mm

    mesh, features = build_hollow_cylinder(
        outer_radius=od / 2.0, inner_radius=bore_cv.value / 2.0, length=length,
        radial_segments=generation_parameters.radial_segments)

    outer_feature = next(f for f in features if f["name"] == "outer_cylindrical_wall")
    inner_feature = next(f for f in features if f["name"] == "inner_cylindrical_wall_bore")
    outer_indices = range(outer_feature["vertex_range"][0], outer_feature["vertex_range"][1] + 1)
    inner_indices = range(inner_feature["vertex_range"][0], inner_feature["vertex_range"][1] + 1)

    measured_od = 2.0 * measure_radial_distance(mesh, outer_indices)
    measured_bore = 2.0 * measure_radial_distance(mesh, inner_indices)
    measured_length = measure_axial_length(mesh, axis="z")

    measurements = {
        "outside_diameter_mm": measured_od,
        "bore_diameter_mm": measured_bore,
        "wall_thickness_mm": (measured_od - measured_bore) / 2.0,
        "length_mm": measured_length,
    }
    expected = {
        "outside_diameter_mm": od,
        "bore_diameter_mm": bore_cv.value,
        "wall_thickness_mm": wt,
        "length_mm": length,
    }
    trace = [
        f"pipe: OD={od}mm WT={wt}mm -> bore={bore_cv.value}mm "
        f"(rule={bore_cv.rule_id} v{bore_cv.rule_version})",
        f"pipe: segment length={length}mm (GEOMETRY_DISPLAY_PARAMETER_NOT_AUTHORITATIVE)",
    ]
    return ProductGeometryBuild(
        geometry_type=GEOMETRY_TYPE, mesh=mesh, features=features, construction_values=[bore_cv],
        measurements=measurements, expected_dimensions=expected, trace=trace,
    )
