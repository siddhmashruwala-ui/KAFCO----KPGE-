# -*- coding: utf-8 -*-
"""
kgpe.geometry.products.cap
==============================
Prompt 13 Sec.16-19: ASME B16.9 cap. `outside_diameter_mm` +
`cap_length_standard_wall_mm` are required (confirmed live: ready at
NPS4/NPS6, quarantine-blocked at NPS8/NPS12); `cap_length_heavy_wall_mm`/
`cap_wall_thickness_threshold_mm` are optional (only present when the
caller explicitly requested them, per Prompt 11's "optional only when
included" rule). `CapLengthSelectionRule` (Sec.17) decides between
standard-wall (H) and heavy-wall (H1) length; `CapProfileConstructionRule`
(Sec.18) defines the flat-disc closure. Actual mating-pipe wall thickness,
if supplied, comes from an already-RESOLVED
`kgpe.geometry.construction_value.ConstructionValue`
(`actual_wall_thickness_value`) produced upstream by
`ButtweldWallViaPipeScheduleRule` - this builder never resolves it itself.
"""
from ..builders import build_cap_solid
from ..construction_rules import CapLengthSelectionRule, ConstructionRuleStatus
from ..measurement import measure_radial_distance
from ..product_api import ProductGeometryBuild, GeometryInputError, ConstructionRuleUnavailableError
from ..ports import ConnectionPort, OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE
from ..result import TopologyRepresentation
from ..construction_value import ConstructionValue
from ..transition_rules import CapProfileConstructionRule

GEOMETRY_TYPE = "buttweld_cap"


def build(geometry_spec, generation_parameters, actual_wall_thickness_value=None):
    dims = geometry_spec.required_dimensions
    opt = geometry_spec.optional_dimensions
    od_entry = dims.get("outside_diameter_mm")
    std_len_entry = dims.get("cap_length_standard_wall_mm")
    if od_entry is None or std_len_entry is None:
        raise GeometryInputError(
            f"buttweld_cap geometry requires outside_diameter_mm and cap_length_standard_wall_mm - "
            f"got {sorted(dims.keys())}")

    heavy_entry = opt.get("cap_length_heavy_wall_mm")
    threshold_entry = opt.get("cap_wall_thickness_threshold_mm")
    actual_wall_mm = float(actual_wall_thickness_value.value) if actual_wall_thickness_value is not None else None

    selection_rule = CapLengthSelectionRule()
    outcome = selection_rule.apply(
        standard_length_value=std_len_entry["value"], standard_length_unit=std_len_entry["unit"],
        actual_wall_thickness_mm=actual_wall_mm, heavy_wall_length_entry=heavy_entry,
        wall_threshold_entry=threshold_entry,
    )
    if outcome.status not in (ConstructionRuleStatus.RULE_APPLIED, ConstructionRuleStatus.RULE_NOT_APPLICABLE):
        raise ConstructionRuleUnavailableError(f"cap length selection could not be applied: {outcome.detail}")
    length_cv = outcome.value

    od = float(od_entry["value"])
    radius = od / 2.0
    length = float(length_cv.value)
    n = generation_parameters.radial_segments

    profile_rule = CapProfileConstructionRule()
    mesh, features = build_cap_solid(radius, length, n)
    profile_marker = ConstructionValue(
        name="topology_rule_applied", value=1.0, unit="rule", rule_id=profile_rule.rule_id,
        rule_version=profile_rule.rule_version, derivation_trace=[profile_rule.description],
    )

    body_wall = next(f for f in features if f["name"] == "cap_body_wall")
    open_end = next(f for f in features if f["name"] == "open_end")
    open_ring = range(open_end["vertex_range"][0], open_end["vertex_range"][0] + n)
    measured_od = 2.0 * measure_radial_distance(mesh, open_ring, axis_point=(0.0, 0.0))
    closed_disc = next(f for f in features if f["name"] == "closed_end_disc")
    measured_length = mesh.vertices[closed_disc["vertex_range"][0]][2]

    measurements = {"outside_diameter_mm": measured_od, "selected_cap_length_mm": measured_length}
    expected = {"outside_diameter_mm": od, "selected_cap_length_mm": length}
    trace = [f"buttweld_cap: OD={od}mm selected_length={length}mm via {length_cv.rule_id} "
             f"v{length_cv.rule_version} ({outcome.detail})",
             f"buttweld_cap: profile closure = {profile_rule.rule_id} v{profile_rule.rule_version} - "
             f"{profile_rule.description}"]

    size_identity = {k: (geometry_spec.engineering_object_identity or {}).get(k)
                      for k in ("size_system", "primary_size")}
    open_port = ConnectionPort(port_id="open_end", role="open_end", position=(0.0, 0.0, 0.0),
                                direction=(0.0, 0.0, -1.0), size_identity=size_identity,
                                opening_diameter_mm=od, opening_diameter_provenance=OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE)

    return ProductGeometryBuild(
        geometry_type=GEOMETRY_TYPE, mesh=mesh, features=features, construction_values=[length_cv, profile_marker],
        measurements=measurements, expected_dimensions=expected, trace=trace, ports=[open_port],
        topology_representation=TopologyRepresentation.SOLID_EXTERNAL_ENVELOPE,
    )
