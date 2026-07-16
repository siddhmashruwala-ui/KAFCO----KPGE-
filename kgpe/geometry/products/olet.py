# -*- coding: utf-8 -*-
"""
kgpe.geometry.products.olet
===============================
Prompt 15 Sec.6/9/13: MSS SP-97 branch-outlet fittings - weldolet,
sockolet, threadolet (`PROFILE_OLET_BODY` - the ONLY olet subtypes with
any canonical geometry-relevant data; elbolet/latrolet/sweepolet/
nippolet have ZERO canonical coverage, confirmed live, and remain
UNSUPPORTED_BY_CANONICAL_DATA - never fabricated).

Every required dimension (olet_height_mm, olet_face_to_face_mm,
olet_base_outside_diameter_mm, olet_bore_diameter_mm) exists ONLY as
VERIFIED_MANUFACTURER_SPECIFIC (Bonney Forge) - there is no MSS-SP-97-
standard-text-authoritative alternative at all (Prompt 9's documented
GAP_MANUFACTURER_SPECIFIC_ONLY finding). `PROFILE_OLET_BODY.
manufacturer_specific == MFR_REQUIRED` means `kgpe.geometry_spec.compiler`
already fails closed with `MANUFACTURER_CONTEXT_REQUIRED` (Prompt 10) if
the caller's EngineeringRequest carries no `manufacturer_profile` - this
builder is never reached without one; it never defaults to Bonney Forge
silently.

Representation: MSS SP-97 does not publish a continuous reinforcement-
body contour - this builder uses
`kgpe.geometry.construction_rules.OletReinforcementEnvelopeConstructionRule`
to build a straight-sided frustum envelope (base OD at the run interface,
tapering to the branch bore diameter, over the published height) via
`kgpe.geometry.builders.build_frustum_solid` - explicitly construction-
derived, never claimed as an MSS-published contour.
`olet_face_to_face_mm` is exposed as authoritative METADATA ONLY (not
consumed by this prompt's simplified frustum construction - its precise
geometric role along the run-pipe axis is not modeled, since no run pipe
is modeled at all, Sec.44 no-assemblies discipline). Sockolet's
ADDITIONAL `olet_socket_diameter_mm` is likewise exposed as metadata
only - see `kgpe.geometry.outlet_geometry`'s module docstring for why it
is never used as the frustum's small-end radius.
"""
from ..builders import build_frustum_solid
from ..measurement import measure_radial_distance, measure_axial_length
from ..product_api import ProductGeometryBuild, GeometryInputError, ConstructionRuleUnavailableError
from ..ports import ConnectionPort, OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE
from ..result import TopologyRepresentation
from ..construction_rules import OletReinforcementEnvelopeConstructionRule, ConstructionRuleStatus
from ..outlet_geometry import build_outlet_geometry, validate_outlet_geometry, OutletGeometryError

GEOMETRY_TYPE = "olet_body"

_REQUIRED = ("olet_height_mm", "olet_face_to_face_mm", "olet_base_outside_diameter_mm",
             "olet_bore_diameter_mm")


def build(geometry_spec, generation_parameters):
    dims = geometry_spec.required_dimensions
    opt = geometry_spec.optional_dimensions
    missing = [k for k in _REQUIRED if k not in dims]
    if missing:
        raise GeometryInputError(
            f"olet_body geometry requires {list(_REQUIRED)} - got {sorted(dims.keys())}")

    height = float(dims["olet_height_mm"]["value"])
    face_to_face = float(dims["olet_face_to_face_mm"]["value"])
    base_od = float(dims["olet_base_outside_diameter_mm"]["value"])
    bore = float(dims["olet_bore_diameter_mm"]["value"])
    socket_dia_entry = opt.get("olet_socket_diameter_mm")
    socket_dia = float(socket_dia_entry["value"]) if socket_dia_entry is not None else None

    if not (0.0 < height):
        raise GeometryInputError(f"olet_height_mm must be positive, got {height!r}")
    if not (0.0 < base_od):
        raise GeometryInputError(f"olet_base_outside_diameter_mm must be positive, got {base_od!r}")
    if not (0.0 < bore < base_od):
        raise GeometryInputError(
            f"olet_bore_diameter_mm ({bore!r}) must be positive and less than "
            f"olet_base_outside_diameter_mm ({base_od!r}).")

    rule = OletReinforcementEnvelopeConstructionRule()
    outcome = rule.apply(base_od_value=base_od, branch_opening_value=bore, height_value=height)
    if outcome.status != ConstructionRuleStatus.RULE_APPLIED:
        raise ConstructionRuleUnavailableError(
            f"OletReinforcementEnvelopeConstructionRule could not be applied: {outcome.detail}")

    n = generation_parameters.radial_segments
    mesh, features = build_frustum_solid(base_od / 2.0, bore / 2.0, height, n)

    large_wall = next(f for f in features if f["name"] == "conical_transition")
    large_ring0 = range(large_wall["vertex_range"][0], large_wall["vertex_range"][0] + n)
    small_ring0 = range(large_wall["vertex_range"][0] + n, large_wall["vertex_range"][0] + 2 * n)
    measured_base_od = 2.0 * measure_radial_distance(mesh, large_ring0, axis_point=(0.0, 0.0))
    measured_bore = 2.0 * measure_radial_distance(mesh, small_ring0, axis_point=(0.0, 0.0))
    measured_height = measure_axial_length(mesh)

    try:
        og = build_outlet_geometry(base_od, bore, height)
        validate_outlet_geometry(og)
    except OutletGeometryError as e:
        raise GeometryInputError(f"outlet geometry invalid: {e}")

    identity = geometry_spec.engineering_object_identity or {}
    subtype = identity.get("subtype")
    manufacturer = identity.get("manufacturer_profile")
    size_identity = {"size_system": identity.get("size_system"), "branch_size": identity.get("branch_size"),
                      "run_size": identity.get("run_size")}

    run_connection = ConnectionPort(
        port_id="run_connection", role="run_connection", position=(0.0, 0.0, 0.0),
        direction=(0.0, 0.0, -1.0), size_identity=size_identity, opening_diameter_mm=base_od,
        opening_diameter_provenance=OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE)
    branch_connection = ConnectionPort(
        port_id="branch_connection", role="branch_connection", position=(0.0, 0.0, height),
        direction=(0.0, 0.0, 1.0), size_identity=size_identity, opening_diameter_mm=bore,
        opening_diameter_provenance=OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE)

    outlet_feature = {"name": "outlet_geometry", "type": "outlet_metadata_bundle",
                       "vertex_range": [0, 0], "face_range": [0, 0], "params": og.to_dict()}
    face_to_face_feature = {"name": "face_to_face", "type": "authoritative_metadata_only",
                             "vertex_range": [0, 0], "face_range": [0, 0],
                             "params": {"olet_face_to_face_mm": face_to_face, "status": "AUTHORITATIVE",
                                        "detail": "Published dimension not consumed by this prompt's "
                                                  "simplified frustum-envelope construction - exposed "
                                                  "as metadata only (no run-pipe assembly is modeled)."}}
    features = list(features) + [outlet_feature, face_to_face_feature]
    if socket_dia is not None:
        features.append({
            "name": "branch_socket_diameter", "type": "authoritative_metadata_only",
            "vertex_range": [0, 0], "face_range": [0, 0],
            "params": {"olet_socket_diameter_mm": socket_dia, "status": "AUTHORITATIVE",
                       "detail": "Sockolet-only additional dimension (E_socketDia_mm) - the actual "
                                 "branch pipe socket size, distinct from olet_bore_diameter_mm (the "
                                 "internal flow bore) and not following a simple ordering relationship "
                                 "with base OD - never used as the frustum's small-end radius, exposed "
                                 "as metadata only."}})

    trace = [
        f"olet_body ({subtype}, manufacturer_profile={manufacturer!r}): base_OD={base_od}mm "
        f"bore={bore}mm height={height}mm - all consumed directly from resolved manufacturer-"
        f"specific dimensions.",
        f"olet_body: reinforcement body via {rule.rule_id} v{rule.rule_version} - {outcome.detail} "
        f"(construction-derived frustum envelope, NOT an MSS SP-97-published contour).",
        "olet_body: olet_face_to_face_mm exposed as metadata only (no run-pipe assembly modeled).",
    ]
    measurements = {"olet_base_outside_diameter_mm": measured_base_od, "olet_bore_diameter_mm": measured_bore,
                     "olet_height_mm": measured_height}
    expected = {"olet_base_outside_diameter_mm": base_od, "olet_bore_diameter_mm": bore,
                "olet_height_mm": height}

    return ProductGeometryBuild(
        geometry_type=GEOMETRY_TYPE, mesh=mesh, features=features, construction_values=[outcome.value],
        measurements=measurements, expected_dimensions=expected, trace=trace,
        ports=[run_connection, branch_connection],
        topology_representation=TopologyRepresentation.CONSTRUCTION_DERIVED_ENVELOPE_WITH_INTERFACE_METADATA_NO_BOOLEAN_CUT,
    )
