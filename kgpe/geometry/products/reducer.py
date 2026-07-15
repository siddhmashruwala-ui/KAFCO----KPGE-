# -*- coding: utf-8 -*-
"""
kgpe.geometry.products.reducer
==================================
Prompt 13 Sec.20-26: ASME B16.9 concentric/eccentric reducer. Only
`end_to_end_mm` is in the compiled `GeometrySpecification.
required_dimensions` (Sec.20 fix - profile.py v1->v2); the large-end and
small-end outside diameters are supplied as two already-RESOLVED
`ConstructionValue`s (`large_od_value`/`small_od_value`), produced
upstream by `kgpe.geometry.reducer_rules.ReducerPerEndOutsideDiameterRule`
- this builder never resolves them itself (kernel/product layer never
touches the resolver, mirroring the wall-context pattern). Each end's
role, source fact, and quarantine status are therefore preserved
independently (Sec.20) - large and small ends are never swapped, never
represented with one shared OD.
"""
from ..builders import build_frustum_solid
from ..measurement import measure_radial_distance, measure_axial_length
from ..product_api import ProductGeometryBuild, GeometryInputError
from ..ports import ConnectionPort, OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE
from ..result import TopologyRepresentation
from ..construction_value import ConstructionValue
from ..transition_rules import ConcentricReducerTransitionRule, EccentricReducerOffsetRule

GEOMETRY_TYPE_CONCENTRIC = "buttweld_reducer_concentric"
GEOMETRY_TYPE_ECCENTRIC = "buttweld_reducer_eccentric"


def build(geometry_spec, generation_parameters, large_od_value=None, small_od_value=None,
          eccentric=None, orientation=None):
    if large_od_value is None or small_od_value is None:
        raise GeometryInputError(
            "buttweld_reducer geometry requires both large_od_value and small_od_value - "
            "these must be pre-resolved via ReducerPerEndOutsideDiameterRule before calling "
            "the kernel (the kernel/product layer never resolves engineering requests itself).")

    subtype = (geometry_spec.engineering_object_identity or {}).get("subtype")
    if eccentric is None:
        eccentric = (subtype == "reducer_eccentric")

    dims = geometry_spec.required_dimensions
    length_entry = dims.get("end_to_end_mm")
    if length_entry is None:
        raise GeometryInputError(f"buttweld_reducer geometry requires end_to_end_mm - got {sorted(dims.keys())}")

    large_od = float(large_od_value.value)
    small_od = float(small_od_value.value)
    length = float(length_entry["value"])
    n = generation_parameters.radial_segments
    large_radius, small_radius = large_od / 2.0, small_od / 2.0

    transition_rule = ConcentricReducerTransitionRule()
    construction_values = [large_od_value, small_od_value]
    trace = [
        f"buttweld_reducer: large_end_OD={large_od}mm (role=large_end, rule={large_od_value.rule_id} "
        f"v{large_od_value.rule_version})",
        f"buttweld_reducer: small_end_OD={small_od}mm (role=small_end, rule={small_od_value.rule_id} "
        f"v{small_od_value.rule_version})",
        f"buttweld_reducer: end_to_end_mm={length}mm consumed directly (no construction rule needed)",
    ]

    if eccentric:
        offset_rule = EccentricReducerOffsetRule()
        offset_magnitude, resolved_orientation = offset_rule.offset(large_radius, small_radius, orientation)
        small_end_offset = (0.0, offset_magnitude)
        offset_marker = ConstructionValue(
            name="eccentric_offset_mm", value=offset_magnitude, unit="mm",
            rule_id=offset_rule.rule_id, rule_version=offset_rule.rule_version,
            derivation_trace=[f"offset = large_radius({large_radius}) - small_radius({small_radius}) = "
                               f"{offset_magnitude}mm, orientation={resolved_orientation}"],
        )
        construction_values.append(offset_marker)
        trace.append(f"buttweld_reducer: eccentric offset={offset_magnitude}mm orientation={resolved_orientation} "
                     f"via {offset_rule.rule_id} v{offset_rule.rule_version}")
        geometry_type = GEOMETRY_TYPE_ECCENTRIC
    else:
        small_end_offset = (0.0, 0.0)
        trace.append(f"buttweld_reducer: concentric - axis remains coincident, transition="
                     f"{transition_rule.rule_id} v{transition_rule.rule_version}")
        geometry_type = GEOMETRY_TYPE_CONCENTRIC

    mesh, features = build_frustum_solid(large_radius, small_radius, length, n, small_end_offset)
    transition_marker = ConstructionValue(
        name="topology_rule_applied", value=1.0, unit="rule", rule_id=transition_rule.rule_id,
        rule_version=transition_rule.rule_version,
        derivation_trace=["linear radius interpolation between large and small end rings"],
    )
    construction_values.append(transition_marker)

    transition = next(f for f in features if f["name"] == "conical_transition")
    large_ring = range(transition["vertex_range"][0], transition["vertex_range"][0] + n)
    small_ring = range(transition["vertex_range"][0] + n, transition["vertex_range"][0] + 2 * n)
    measured_large_od = 2.0 * measure_radial_distance(mesh, large_ring, axis_point=(0.0, 0.0))
    measured_small_od = 2.0 * measure_radial_distance(mesh, small_ring, axis_point=small_end_offset)
    measured_length = measure_axial_length(mesh, axis="z")

    measurements = {
        "large_end_outside_diameter_mm": measured_large_od,
        "small_end_outside_diameter_mm": measured_small_od,
        "length_mm": measured_length,
    }
    expected = {
        "large_end_outside_diameter_mm": large_od, "small_end_outside_diameter_mm": small_od,
        "length_mm": length,
    }
    if eccentric:
        measurements["eccentric_offset_mm"] = abs(small_end_offset[1])
        expected["eccentric_offset_mm"] = abs(offset_magnitude)

    size_identity_large = {"size_system": (geometry_spec.engineering_object_identity or {}).get("size_system"),
                            "size": (geometry_spec.engineering_object_identity or {}).get("large_end_size")}
    size_identity_small = {"size_system": (geometry_spec.engineering_object_identity or {}).get("size_system"),
                            "size": (geometry_spec.engineering_object_identity or {}).get("small_end_size")}
    large_port = ConnectionPort(port_id="large_end", role="large_end", position=(0.0, 0.0, 0.0),
                                 direction=(0.0, 0.0, -1.0), size_identity=size_identity_large,
                                 opening_diameter_mm=large_od,
                                 opening_diameter_provenance=OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE)
    small_port = ConnectionPort(port_id="small_end", role="small_end",
                                 position=(small_end_offset[0], small_end_offset[1], length),
                                 direction=(0.0, 0.0, 1.0), size_identity=size_identity_small,
                                 opening_diameter_mm=small_od,
                                 opening_diameter_provenance=OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE)

    return ProductGeometryBuild(
        geometry_type=geometry_type, mesh=mesh, features=features, construction_values=construction_values,
        measurements=measurements, expected_dimensions=expected, trace=trace, ports=[large_port, small_port],
        topology_representation=TopologyRepresentation.SOLID_EXTERNAL_ENVELOPE,
    )
