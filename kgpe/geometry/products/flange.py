# -*- coding: utf-8 -*-
"""
kgpe.geometry.products.flange
=================================
Prompt 14: ASME B16.5 / JIS B2220 / EN 1092-1 weld-neck flange (the ONLY
flange_type this project's canonical data populates for any of the three
standards - confirmed live in Sec.3/Sec.6 of the Prompt 14 report; blind/
slip-on/threaded/socket-weld/lap-joint remain UNSUPPORTED_BY_CANONICAL_DATA
this prompt, not fabricated).

Required dimensions (outside_diameter_mm, flange_thickness_weld_neck_mm,
bolt_circle_diameter_mm, bolt_hole_diameter_mm, num_bolts,
bolt_size_designation) are VERIFIED_AUTHORITATIVE for all three standards.
bore_diameter_mm is VERIFIED_AUTHORITATIVE (optional, direct) for
JIS_B2220 only; for ASME_B16.5 it may instead arrive as an already-
RESOLVED `ConstructionValue` (`bore_value`, produced upstream by
`kgpe.geometry.cross_family.FlangeBoreViaPipeScheduleRule` - this builder
never resolves it itself); for EN_1092-1 no bore is available at all
(SOLID_EXTERNAL_ENVELOPE - never fabricated). raised_face_diameter_mm is
optional/JIS-only, and is exposed only as a PARTIAL feature (diameter
known, height has zero production facts for any standard - never
fabricated, Sec.19). Hub geometry has zero facts for any standard and is
never attempted (Sec.21-22).
"""
from ..builders import build_hollow_cylinder, build_solid_cylinder
from ..measurement import measure_radial_distance, measure_axial_length
from ..product_api import ProductGeometryBuild, GeometryInputError
from ..ports import ConnectionPort, OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE, \
    OPENING_DIAMETER_PROVENANCE_DERIVED, OPENING_DIAMETER_PROVENANCE_NOT_MODELED
from ..result import TopologyRepresentation
from ..bolt_pattern import build_bolt_pattern, validate_bolt_pattern, BoltPatternError
from ..mating_interface import MatingInterface, FACE_TYPE_NOT_TRACKED

GEOMETRY_TYPE = "flange_weld_neck"

_REQUIRED_NUMERIC = ("outside_diameter_mm", "flange_thickness_weld_neck_mm",
                     "bolt_circle_diameter_mm", "bolt_hole_diameter_mm")


def build(geometry_spec, generation_parameters, bore_value=None):
    dims = geometry_spec.required_dimensions
    opt = geometry_spec.optional_dimensions
    missing = [k for k in _REQUIRED_NUMERIC if k not in dims]
    if missing or "num_bolts" not in dims:
        raise GeometryInputError(
            f"flange_weld_neck geometry requires {list(_REQUIRED_NUMERIC)} and num_bolts - "
            f"got {sorted(dims.keys())}")

    od = float(dims["outside_diameter_mm"]["value"])
    thickness = float(dims["flange_thickness_weld_neck_mm"]["value"])
    bolt_circle = float(dims["bolt_circle_diameter_mm"]["value"])
    bolt_hole_dia = float(dims["bolt_hole_diameter_mm"]["value"])
    num_bolts = int(dims["num_bolts"]["value"])
    n = generation_parameters.radial_segments

    if not (0.0 < thickness):
        raise GeometryInputError(f"flange_thickness_weld_neck_mm must be positive, got {thickness!r}")
    if not (0.0 < bolt_circle < od):
        raise GeometryInputError(
            f"bolt_circle_diameter_mm ({bolt_circle!r}) must be positive and less than "
            f"outside_diameter_mm ({od!r}).")
    if bolt_circle / 2.0 + bolt_hole_dia / 2.0 > od / 2.0:
        raise GeometryInputError(
            f"bolt holes (circle radius {bolt_circle / 2.0!r} + hole radius {bolt_hole_dia / 2.0!r}) "
            f"would extend beyond the flange OD envelope ({od / 2.0!r}).")

    # --- Prompt 14 Sec.14-16: bore policy - direct authoritative (JIS),
    # then cross-family construction value (ASME, resolved externally by
    # the caller via FlangeBoreViaPipeScheduleRule), else unavailable
    # (EN_1092-1 today) - never fabricated, never NPS/pipe-OD substituted.
    bore_entry = opt.get("bore_diameter_mm")
    construction_values = []
    bore_mm = None
    bore_provenance = OPENING_DIAMETER_PROVENANCE_NOT_MODELED
    if bore_entry is not None:
        bore_mm = float(bore_entry["value"])
        bore_provenance = OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE
        bore_source = "direct canonical bore_diameter_mm fact"
    elif bore_value is not None:
        bore_mm = float(bore_value.value)
        bore_provenance = OPENING_DIAMETER_PROVENANCE_DERIVED
        bore_source = f"cross-family construction value ({bore_value.rule_id} v{bore_value.rule_version})"
        construction_values.append(bore_value)
    else:
        bore_source = "unavailable - no direct fact and no cross-family construction value supplied"

    if bore_mm is not None and not (0.0 < bore_mm < od):
        raise GeometryInputError(
            f"bore_diameter_mm ({bore_mm!r}) must be positive and less than outside_diameter_mm ({od!r}).")

    if bore_mm is not None:
        mesh, features = build_hollow_cylinder(od / 2.0, bore_mm / 2.0, thickness, n)
        topology = TopologyRepresentation.HOLLOW_ANNULAR_BODY_WITH_BOLT_HOLE_METADATA_NO_BOOLEAN_CUT
    else:
        mesh, features = build_solid_cylinder(od / 2.0, thickness, n)
        topology = TopologyRepresentation.SOLID_EXTERNAL_ENVELOPE_WITH_BOLT_HOLE_METADATA_NO_BOOLEAN_CUT

    # --- Bolt pattern (Sec.10-11): centred on the flange axis at the
    # mating face (z=0), deterministic angular-zero=0 (+X axis).
    try:
        pattern = build_bolt_pattern(bolt_circle, bolt_hole_dia, num_bolts, centre=(0.0, 0.0, 0.0))
        validate_bolt_pattern(pattern)
    except BoltPatternError as e:
        raise GeometryInputError(f"bolt pattern construction/validation failed: {e}")

    # --- Measurements (Sec.28): only dimensions actually represented in
    # the generated mesh are measured off it - bolt-hole/bore-when-absent
    # are validated structurally above, not via mesh measurement.
    if bore_mm is not None:
        outer_wall = next(f for f in features if f["name"] == "outer_cylindrical_wall")
        inner_wall = next(f for f in features if f["name"] == "inner_cylindrical_wall_bore")
        outer_ring0 = range(outer_wall["vertex_range"][0], outer_wall["vertex_range"][0] + n)
        inner_ring0 = range(inner_wall["vertex_range"][0], inner_wall["vertex_range"][0] + n)
        measured_od = 2.0 * measure_radial_distance(mesh, outer_ring0, axis_point=(0.0, 0.0))
        measured_bore = 2.0 * measure_radial_distance(mesh, inner_ring0, axis_point=(0.0, 0.0))
        measurements = {"outside_diameter_mm": measured_od, "bore_diameter_mm": measured_bore,
                         "flange_thickness_weld_neck_mm": measure_axial_length(mesh)}
        expected = {"outside_diameter_mm": od, "bore_diameter_mm": bore_mm,
                    "flange_thickness_weld_neck_mm": thickness}
    else:
        outer_wall = next(f for f in features if f["name"] == "outer_wall")
        outer_ring0 = range(outer_wall["vertex_range"][0], outer_wall["vertex_range"][0] + n)
        measured_od = 2.0 * measure_radial_distance(mesh, outer_ring0, axis_point=(0.0, 0.0))
        measurements = {"outside_diameter_mm": measured_od,
                         "flange_thickness_weld_neck_mm": measure_axial_length(mesh)}
        expected = {"outside_diameter_mm": od, "flange_thickness_weld_neck_mm": thickness}

    # --- Raised face (Sec.18-19): diameter-only PARTIAL feature metadata -
    # raised_face_height_mm has ZERO production facts for any standard, so
    # no raised-face geometry is ever generated, even when diameter IS
    # known (JIS_B2220 only) - never fabricate the missing height.
    rf_entry = opt.get("raised_face_diameter_mm")
    if rf_entry is not None:
        rf_diameter = float(rf_entry["value"])
        if rf_diameter > od:
            raise GeometryInputError(
                f"raised_face_diameter_mm ({rf_diameter!r}) must not exceed outside_diameter_mm ({od!r}).")
        rf_status = "PARTIAL_DIAMETER_KNOWN_HEIGHT_UNAVAILABLE"
        rf_params = {"raised_face_diameter_mm": rf_diameter, "raised_face_height_mm": None,
                     "status": rf_status}
    else:
        rf_diameter = None
        rf_status = "UNAVAILABLE_NO_AUTHORITATIVE_DIMENSIONS"
        rf_params = {"raised_face_diameter_mm": None, "raised_face_height_mm": None, "status": rf_status}
    raised_face_feature = {"name": "raised_face", "type": "raised_face_partial_metadata",
                            "vertex_range": [0, 0], "face_range": [0, 0], "params": rf_params}

    # --- Hub (Sec.21-22): zero facts for any standard, any subtype - never
    # attempted, always reported unavailable.
    hub_feature = {"name": "hub", "type": "hub_unavailable_metadata", "vertex_range": [0, 0],
                   "face_range": [0, 0],
                   "params": {"status": "UNAVAILABLE_NO_AUTHORITATIVE_DIMENSIONS_ANY_STANDARD"}}

    face_type = FACE_TYPE_NOT_TRACKED
    mating = MatingInterface(
        mating_face_centre=(0.0, 0.0, 0.0), mating_face_normal=(0.0, 0.0, -1.0),
        outside_diameter_mm=od, bolt_circle_diameter_mm=bolt_circle, bolt_hole_count=num_bolts,
        bolt_hole_diameter_mm=bolt_hole_dia, face_type=face_type,
    )
    mating_feature = {"name": "mating_interface", "type": "mating_interface_metadata",
                       "vertex_range": [0, 0], "face_range": [0, 0], "params": mating.to_dict()}
    bolt_pattern_feature = {"name": "bolt_pattern", "type": "bolt_hole_metadata",
                             "vertex_range": [0, 0], "face_range": [0, 0], "params": pattern.to_dict()}

    all_features = list(features) + [bolt_pattern_feature, raised_face_feature, hub_feature, mating_feature]

    identity = geometry_spec.engineering_object_identity or {}
    size_identity = {k: identity.get(k) for k in ("size_system", "primary_size")}
    standard = identity.get("standard")

    port = ConnectionPort(
        port_id="primary_connection", role="primary_connection", position=(0.0, 0.0, 0.0),
        direction=(0.0, 0.0, -1.0), size_identity=size_identity,
        opening_diameter_mm=bore_mm, opening_diameter_provenance=bore_provenance,
    )

    trace = [
        f"flange_weld_neck ({standard}): OD={od}mm thickness={thickness}mm bolt_circle={bolt_circle}mm "
        f"bolt_hole_dia={bolt_hole_dia}mm num_bolts={num_bolts} - all consumed directly from resolved "
        f"canonical dimensions (no construction rule needed for the body/bolt pattern).",
        f"flange_weld_neck ({standard}): bore policy -> {bore_source}"
        + (f" -> bore_diameter_mm={bore_mm}mm" if bore_mm is not None else " -> SOLID_EXTERNAL_ENVELOPE, no bore modeled"),
        f"flange_weld_neck ({standard}): raised_face -> {rf_status}",
        f"flange_weld_neck ({standard}): hub -> UNAVAILABLE_NO_AUTHORITATIVE_DIMENSIONS_ANY_STANDARD",
        f"flange_weld_neck ({standard}): face_type -> {face_type}",
    ]

    return ProductGeometryBuild(
        geometry_type=GEOMETRY_TYPE, mesh=mesh, features=all_features, construction_values=construction_values,
        measurements=measurements, expected_dimensions=expected, trace=trace, ports=[port],
        topology_representation=topology,
    )
