# -*- coding: utf-8 -*-
"""
kgpe.geometry.products.flange
=================================
Prompt 14: ASME B16.5 / JIS B2220 / EN 1092-1 weld-neck flange geometry.

Prompt 41 addition: this module now also serves five additional ASME
B16.5 flange subtypes - slip_on, threaded, socket_weld, lap_joint, blind
- ingested in Prompt 41 (kgpe.contract.adapters.asme_b16_5_flanges'
_OPTIONAL_TYPE_THICKNESS_SPECS; full sourcing/cross-verification record
in _ingest_new_flange_types.py's module docstring). ONE module still
builds all six subtypes (never six near-duplicate files) - the specific
subtype is derived deterministically from
`geometry_spec.geometry_profile_id` (never guessed, never defaulted; see
_SUBTYPE_BY_PROFILE_ID below), exactly mirroring how
kgpe.geometry.kernel.GeometryKernel.generate() already uses that same
field to dispatch to this module in the first place - each of the six
geometry_profile_id values (kgpe.geometry_spec.profile.py) maps 1:1 to
exactly one subtype, so there is no ambiguity.

Required dimensions (outside_diameter_mm, the subtype's own thickness
dimension, bolt_circle_diameter_mm, bolt_hole_diameter_mm, num_bolts,
bolt_size_designation) are VERIFIED_AUTHORITATIVE for weld_neck across
all three standards; for the five Prompt 41 subtypes, ASME_B16.5 is
currently the only standard with any canonical facts at all. bore_
diameter_mm is VERIFIED_AUTHORITATIVE (optional, direct) for JIS_B2220
weld_neck only; for ASME_B16.5 it may instead arrive as an already-
RESOLVED `ConstructionValue` (`bore_value`, produced upstream by
kgpe.geometry.cross_family.FlangeBoreViaPipeScheduleRule - this builder
never resolves it itself); for EN_1092-1 no bore is available at all
(SOLID_EXTERNAL_ENVELOPE - never fabricated). blind flanges NEVER attempt
bore resolution at all, regardless of what is passed in - they have no
through-bore by physical definition (Sec. profile.py PROFILE_FLANGE_
BLIND) - always SOLID_EXTERNAL_ENVELOPE. raised_face_diameter_mm is
optional/JIS-only, and is exposed only as a PARTIAL feature (diameter
known, height has zero production facts for any standard - never
fabricated, Sec.19). Hub geometry has zero facts for any standard/subtype
and is never attempted (Sec.21-22).
"""
from ..builders import build_hollow_cylinder, build_solid_cylinder
from ..measurement import measure_radial_distance, measure_axial_length
from ..product_api import ProductGeometryBuild, GeometryInputError
from ..ports import ConnectionPort, OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE, \
    OPENING_DIAMETER_PROVENANCE_DERIVED, OPENING_DIAMETER_PROVENANCE_NOT_MODELED
from ..result import TopologyRepresentation
from ..bolt_pattern import build_bolt_pattern, validate_bolt_pattern, BoltPatternError
from ..mating_interface import MatingInterface, FACE_TYPE_NOT_TRACKED

# Prompt 41: geometry_profile_id -> subtype, the single deterministic
# source of truth this module uses to know which flange it is building -
# kept in exact 1:1 correspondence with kgpe.geometry_spec.profile.py's
# PROFILE_REGISTRY entries (profile_id <-> subtypes frozenset of one).
_SUBTYPE_BY_PROFILE_ID = {
    "flange_weld_neck": "weld_neck",
    "flange_slip_on": "slip_on",
    "flange_threaded": "threaded",
    "flange_socket_weld": "socket_weld",
    "flange_lap_joint": "lap_joint",
    "flange_blind": "blind",
}

# Prompt 41: subtype -> which canonical thickness dimension name this
# subtype's minimum thickness is filed under (Sec.3/Sec.41 T/TJ/C split -
# kgpe.contract.vocabulary.DIM_FLANGE_THICKNESS_WELD_NECK / _OTHER_TYPES /
# _BLIND - three distinct canonical names, never merged).
_THICKNESS_DIM_BY_SUBTYPE = {
    "weld_neck": "flange_thickness_weld_neck_mm",
    "slip_on": "flange_thickness_other_types_mm",
    "threaded": "flange_thickness_other_types_mm",
    "socket_weld": "flange_thickness_other_types_mm",
    "lap_joint": "flange_thickness_other_types_mm",
    "blind": "flange_thickness_blind_mm",
}

# Prompt 41: blind flanges close off the pipe end entirely - no
# through-bore by physical definition. This builder must never attempt
# bore resolution for this subtype, regardless of what dims/bore_value
# happen to be supplied (defense in depth alongside profile.py's
# PROFILE_FLANGE_BLIND already omitting bore_diameter_mm from its
# optional/construction-derivable sets).
_NO_BORE_SUBTYPES = frozenset({"blind"})

_REQUIRED_NUMERIC_BASE = ("outside_diameter_mm", "bolt_circle_diameter_mm", "bolt_hole_diameter_mm")


def build(geometry_spec, generation_parameters, bore_value=None):
    profile_id = geometry_spec.geometry_profile_id
    subtype = _SUBTYPE_BY_PROFILE_ID.get(profile_id)
    if subtype is None:
        raise GeometryInputError(
            f"kgpe.geometry.products.flange cannot build geometry_profile_id={profile_id!r} - "
            f"not one of {sorted(_SUBTYPE_BY_PROFILE_ID)}.")
    thickness_dim = _THICKNESS_DIM_BY_SUBTYPE[subtype]
    geometry_type = f"flange_{subtype}"

    dims = geometry_spec.required_dimensions
    opt = geometry_spec.optional_dimensions
    required_numeric = _REQUIRED_NUMERIC_BASE + (thickness_dim,)
    missing = [k for k in required_numeric if k not in dims]
    if missing or "num_bolts" not in dims:
        raise GeometryInputError(
            f"{geometry_type} geometry requires {list(required_numeric)} and num_bolts - "
            f"got {sorted(dims.keys())}")

    od = float(dims["outside_diameter_mm"]["value"])
    thickness = float(dims[thickness_dim]["value"])
    bolt_circle = float(dims["bolt_circle_diameter_mm"]["value"])
    bolt_hole_dia = float(dims["bolt_hole_diameter_mm"]["value"])
    num_bolts = int(dims["num_bolts"]["value"])
    n = generation_parameters.radial_segments

    if not (0.0 < thickness):
        raise GeometryInputError(f"{thickness_dim} must be positive, got {thickness!r}")
    if not (0.0 < bolt_circle < od):
        raise GeometryInputError(
            f"bolt_circle_diameter_mm ({bolt_circle!r}) must be positive and less than "
            f"outside_diameter_mm ({od!r}).")
    if bolt_circle / 2.0 + bolt_hole_dia / 2.0 > od / 2.0:
        raise GeometryInputError(
            f"bolt holes (circle radius {bolt_circle / 2.0!r} + hole radius {bolt_hole_dia / 2.0!r}) "
            f"would extend beyond the flange OD envelope ({od / 2.0!r}).")

    # --- Prompt 14 Sec.14-16 / Prompt 41: bore policy - direct
    # authoritative (JIS), then cross-family construction value (ASME,
    # resolved externally by the caller via FlangeBoreViaPipeScheduleRule),
    # else unavailable (EN_1092-1 today) - never fabricated, never
    # NPS/pipe-OD substituted. blind (Prompt 41) is hard-forced to
    # UNAVAILABLE regardless of what was supplied - no through-bore by
    # physical definition.
    bore_entry = None if subtype in _NO_BORE_SUBTYPES else opt.get("bore_diameter_mm")
    effective_bore_value = None if subtype in _NO_BORE_SUBTYPES else bore_value
    construction_values = []
    bore_mm = None
    bore_provenance = OPENING_DIAMETER_PROVENANCE_NOT_MODELED
    if subtype in _NO_BORE_SUBTYPES:
        bore_source = "unavailable - blind flange, no through-bore by physical definition"
    elif bore_entry is not None:
        bore_mm = float(bore_entry["value"])
        bore_provenance = OPENING_DIAMETER_PROVENANCE_AUTHORITATIVE
        bore_source = "direct canonical bore_diameter_mm fact"
    elif effective_bore_value is not None:
        bore_mm = float(effective_bore_value.value)
        bore_provenance = OPENING_DIAMETER_PROVENANCE_DERIVED
        bore_source = f"cross-family construction value ({effective_bore_value.rule_id} v{effective_bore_value.rule_version})"
        construction_values.append(effective_bore_value)
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
                         thickness_dim: measure_axial_length(mesh)}
        expected = {"outside_diameter_mm": od, "bore_diameter_mm": bore_mm,
                    thickness_dim: thickness}
    else:
        outer_wall = next(f for f in features if f["name"] == "outer_wall")
        outer_ring0 = range(outer_wall["vertex_range"][0], outer_wall["vertex_range"][0] + n)
        measured_od = 2.0 * measure_radial_distance(mesh, outer_ring0, axis_point=(0.0, 0.0))
        measurements = {"outside_diameter_mm": measured_od,
                         thickness_dim: measure_axial_length(mesh)}
        expected = {"outside_diameter_mm": od, thickness_dim: thickness}

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

    # --- Hub (Sec.21-22): zero facts for any standard/subtype - never
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
        f"{geometry_type} ({standard}): OD={od}mm thickness={thickness}mm ({thickness_dim}) "
        f"bolt_circle={bolt_circle}mm bolt_hole_dia={bolt_hole_dia}mm num_bolts={num_bolts} - all "
        f"consumed directly from resolved canonical dimensions (no construction rule needed for "
        f"the body/bolt pattern).",
        f"{geometry_type} ({standard}): bore policy -> {bore_source}"
        + (f" -> bore_diameter_mm={bore_mm}mm" if bore_mm is not None else " -> SOLID_EXTERNAL_ENVELOPE, no bore modeled"),
        f"{geometry_type} ({standard}): raised_face -> {rf_status}",
        f"{geometry_type} ({standard}): hub -> UNAVAILABLE_NO_AUTHORITATIVE_DIMENSIONS_ANY_STANDARD",
        f"{geometry_type} ({standard}): face_type -> {face_type}",
    ]

    return ProductGeometryBuild(
        geometry_type=geometry_type, mesh=mesh, features=all_features, construction_values=construction_values,
        measurements=measurements, expected_dimensions=expected, trace=trace, ports=[port],
        topology_representation=topology,
    )
