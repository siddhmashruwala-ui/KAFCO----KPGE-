# -*- coding: utf-8 -*-
"""
kgpe.geometry.products.tee
==============================
Prompt 13 Sec.12-15: ASME B16.9 equal tee. Required dimensions
(outside_diameter_mm, tee_run_centre_to_end_mm, tee_branch_centre_to_end_mm)
are all VERIFIED_AUTHORITATIVE and confirmed live this prompt (ready at
NPS4/NPS6, QUARANTINED_ENGINEERING_DATA-blocked at NPS8/NPS12 - same
shared-OD quarantine as pipe/elbow/cap). Run and branch centre-to-end are
NOT assumed equal - each is read independently from its own canonical
field (they happen to be numerically equal for THIS "equal tee" family,
but the geometry uses each dimension by name, never one substituted for
the other).

Representation (Sec.13, `TeeBranchBlendingRule`): a deterministic
multi-feature mesh - independent run/branch cylindrical bodies that
geometrically overlap where the branch meets the run. No fillet/blend
surface is fabricated; `topology_representation` honestly declares this
as non-manifold at the intersection (Sec.29).
"""
from ..builders import build_tee_multi_feature
from ..measurement import measure_radial_distance, measure_axial_length
from ..product_api import ProductGeometryBuild, GeometryInputError
from ..ports import ConnectionPort, OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE
from ..result import TopologyRepresentation
from ..construction_value import ConstructionValue
from ..transition_rules import TeeBranchBlendingRule

GEOMETRY_TYPE = "buttweld_tee_equal"


def build(geometry_spec, generation_parameters):
    dims = geometry_spec.required_dimensions
    od_entry = dims.get("outside_diameter_mm")
    run_cte_entry = dims.get("tee_run_centre_to_end_mm")
    branch_cte_entry = dims.get("tee_branch_centre_to_end_mm")
    if od_entry is None or run_cte_entry is None or branch_cte_entry is None:
        raise GeometryInputError(
            f"buttweld_tee_equal geometry requires outside_diameter_mm, tee_run_centre_to_end_mm, "
            f"and tee_branch_centre_to_end_mm - got {sorted(dims.keys())}")

    od = float(od_entry["value"])
    run_cte = float(run_cte_entry["value"])
    branch_cte = float(branch_cte_entry["value"])
    radius = od / 2.0
    n = generation_parameters.radial_segments

    rule = TeeBranchBlendingRule()
    mesh, features = build_tee_multi_feature(radius, run_cte, radius, branch_cte, n)

    blend_marker = ConstructionValue(
        name="topology_rule_applied", value=1.0, unit="rule", rule_id=rule.rule_id, rule_version=rule.rule_version,
        derivation_trace=[rule.description],
    )

    run_wall = next(f for f in features if f["name"] == "run_outer_wall")
    branch_wall = next(f for f in features if f["name"] == "branch_outer_wall")
    run_ring0 = range(run_wall["vertex_range"][0], run_wall["vertex_range"][0] + n)
    branch_ring0 = range(branch_wall["vertex_range"][0], branch_wall["vertex_range"][0] + n)

    measured_od_run = 2.0 * measure_radial_distance(mesh, run_ring0, axis_point=(0.0, 0.0))
    run_end_cap = next(f for f in features if f["name"] == "run_end_cap")
    run_tip_z = mesh.vertices[run_end_cap["vertex_range"][0]][2]  # run tip at (0,0,+run_cte)
    measured_run_cte = run_tip_z
    branch_end_cap = next(f for f in features if f["name"] == "branch_end_cap")
    branch_tip = mesh.vertices[branch_end_cap["vertex_range"][0]]
    measured_branch_cte = branch_tip[1]  # branch extends along +Y from y=0

    measurements = {
        "outside_diameter_mm": measured_od_run,
        "tee_run_centre_to_end_mm": measured_run_cte,
        "tee_branch_centre_to_end_mm": measured_branch_cte,
    }
    expected = {
        "outside_diameter_mm": od, "tee_run_centre_to_end_mm": run_cte, "tee_branch_centre_to_end_mm": branch_cte,
    }
    trace = [
        f"buttweld_tee_equal: OD={od}mm run_cte={run_cte}mm branch_cte={branch_cte}mm consumed directly "
        f"(no construction rule needed for either dimension)",
        f"buttweld_tee_equal: branch blending policy = {rule.rule_id} v{rule.rule_version} - {rule.description}",
    ]

    size_identity = {k: (geometry_spec.engineering_object_identity or {}).get(k)
                      for k in ("size_system", "primary_size")}
    run_inlet = ConnectionPort(port_id="run_inlet", role="run_inlet", position=(0.0, 0.0, -run_cte),
                                direction=(0.0, 0.0, -1.0), size_identity=size_identity,
                                opening_diameter_mm=od, opening_diameter_provenance=OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE)
    run_outlet = ConnectionPort(port_id="run_outlet", role="run_outlet", position=(0.0, 0.0, run_cte),
                                 direction=(0.0, 0.0, 1.0), size_identity=size_identity,
                                 opening_diameter_mm=od, opening_diameter_provenance=OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE)
    branch_port = ConnectionPort(port_id="branch", role="branch", position=(0.0, branch_cte, 0.0),
                                  direction=(0.0, 1.0, 0.0), size_identity=size_identity,
                                  opening_diameter_mm=od, opening_diameter_provenance=OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE)

    return ProductGeometryBuild(
        geometry_type=GEOMETRY_TYPE, mesh=mesh, features=features, construction_values=[blend_marker],
        measurements=measurements, expected_dimensions=expected, trace=trace,
        ports=[run_inlet, run_outlet, branch_port],
        topology_representation=TopologyRepresentation.DETERMINISTIC_MULTI_FEATURE_MESH_NON_MANIFOLD_AT_INTERSECTION,
    )
