# -*- coding: utf-8 -*-
"""
kgpe.geometry.products.nipoflange
=====================================
2026-07-21 (CRM production audit - "KGPE as single geometry authority"):
the first real geometry generator for profile_id "flange_nipoflange"
(kgpe.geometry_spec.profile.PROFILE_FLANGE_NIPOFLANGE, which until now
was dimension-level only - the kernel returned
UNSUPPORTED_GEOMETRY_PROFILE and the CRM hologram silently fell back to
its own JS heuristic; that fallback gap is exactly what this module
closes).

WHAT IS BUILT: a KAFCO Nipoflange - an ASME-B16.5-style flange with an
integral nipple rising from its centre; when a reduced tip size is
requested, the neck necks down and terminates in an integral reduced
WELDOLET-style outlet body with a weld-prep bevel (confirmed against the
real WELSURE product photo, 2026-07-20 - NOT a branch-saddle fitting).

AUTHORITATIVE INPUTS (canonical, resolved upstream - never invented):
  - nipoflange_flange_od_mm / nipoflange_flange_thickness_mm: required
    dims from the KAFCO catalog adapter (VERIFIED_MANUFACTURER_SPECIFIC).
CONSTRUCTION INPUTS (ConstructionValues, resolved by the pipeline's
nipoflange input-derivation step or supplied via product_kwargs - each
carries its own rule provenance):
  - overall_length_value: KAFCO catalog Overall Length B (a
    CONSTRUCTION_PARAMETER - purchaser-modifiable per source Note 2).
  - neck_od_value: main-barrel OD = branch-size pipe OD (cross-family,
    kgpe.geometry.cross_family.NipoflangeNeckODViaBranchPipeODRule).
  - tip_od_value (optional): reduced weld-end OD, same cross-family rule
    on the requested reduced size. Present => REDUCING nipoflange.

Everything the sources do NOT publish (the continuous neck contour) is
allocated by the versioned, deterministic
kgpe.geometry.transition_rules.NipoflangeNeckAllocationRule - explicitly
construction geometry, never claimed authoritative. No bore is modeled
(purchaser-specified per source Note 4 - never fabricated):
SOLID_REVOLVED_COMPOSITE_CONSTRUCTION_ENVELOPE_NO_BOOLEAN_CUT.
"""
import math

from ..mesh import Mesh
from ..primitives import circle_ring, straight_axis_frame
from ..measurement import measure_radial_distance
from ..product_api import ProductGeometryBuild, GeometryInputError, ConstructionRuleUnavailableError
from ..ports import ConnectionPort, OPENING_DIAMETER_PROVENANCE_DERIVED, \
    OPENING_DIAMETER_PROVENANCE_NOT_MODELED
from ..result import TopologyRepresentation
from ..transition_rules import NipoflangeNeckAllocationRule

GEOMETRY_TYPE = "flange_nipoflange"

# Deterministic profile sampling densities (construction constants, same
# spirit as GenerationParameters.radial_segments - not engineering data).
_FILLET_SEGMENTS = 14
_TRANSITION_SEGMENTS = 10
_FILLET_EASE_EXPONENT = 2.2
_TRANSITION_EASE_EXPONENT = 2.0


def _require_cv(value, name):
    if value is None:
        raise ConstructionRuleUnavailableError(
            f"{GEOMETRY_TYPE} geometry requires the ConstructionValue {name!r} (resolved by the "
            f"pipeline's nipoflange input-derivation step, or supplied via product_kwargs) - it was "
            f"not provided. Never fabricated here.")
    return float(value.value)


def _revolve_profile(profile_points, n):
    """Revolves a deterministic (radius, z) polyline 360 degrees about +Z.
    Consecutive duplicate points are rejected by construction (the caller
    builds a strictly advancing profile). Closed with flat discs at both
    ends (centre-fan triangulation). Returns (mesh, ring_start_indices)."""
    u, v, _axis = straight_axis_frame()
    mesh = Mesh()
    ring_starts = []
    for radius, z in profile_points:
        ring_starts.append(mesh.vertex_count())
        mesh.add_vertices(circle_ring((0.0, 0.0, z), u, v, radius, n))
    band_face_ranges = []
    for k in range(len(profile_points) - 1):
        f0 = mesh.face_count()
        a, b = ring_starts[k], ring_starts[k + 1]
        for i in range(n):
            j = (i + 1) % n
            mesh.add_quad(a + i, a + j, b + j, b + i)
        band_face_ranges.append((f0, mesh.face_count()))
    # bottom closure (z of first point, normal -Z)
    bottom_centre = mesh.add_vertex((0.0, 0.0, profile_points[0][1]))
    fb0 = mesh.face_count()
    for i in range(n):
        j = (i + 1) % n
        mesh.add_triangle(ring_starts[0] + j, ring_starts[0] + i, bottom_centre)
    fb1 = mesh.face_count()
    # top closure (z of last point, normal +Z)
    top_centre = mesh.add_vertex((0.0, 0.0, profile_points[-1][1]))
    ft0 = mesh.face_count()
    last = ring_starts[-1]
    for i in range(n):
        j = (i + 1) % n
        mesh.add_triangle(last + i, last + j, top_centre)
    ft1 = mesh.face_count()
    closures = {"bottom": (bottom_centre, fb0, fb1), "top": (top_centre, ft0, ft1)}
    return mesh, ring_starts, band_face_ranges, closures


def _ease(t, exponent):
    return 1.0 - math.pow(1.0 - t, exponent)


def build(geometry_spec, generation_parameters,
          overall_length_value=None, neck_od_value=None, tip_od_value=None):
    dims = geometry_spec.required_dimensions
    required = ("nipoflange_flange_od_mm", "nipoflange_flange_thickness_mm")
    missing = [k for k in required if k not in dims]
    if missing:
        raise GeometryInputError(
            f"{GEOMETRY_TYPE} geometry requires {list(required)} - got {sorted(dims.keys())}")

    flange_od = float(dims["nipoflange_flange_od_mm"]["value"])
    flange_thk = float(dims["nipoflange_flange_thickness_mm"]["value"])
    overall_length = _require_cv(overall_length_value, "overall_length_value")
    neck_od = _require_cv(neck_od_value, "neck_od_value")
    reducing = tip_od_value is not None
    tip_od = float(tip_od_value.value) if reducing else neck_od
    n = generation_parameters.radial_segments

    if not (0.0 < flange_thk < overall_length):
        raise GeometryInputError(
            f"nipoflange_flange_thickness_mm ({flange_thk!r}) must be positive and less than the "
            f"overall length ({overall_length!r}).")
    if not (0.0 < neck_od < flange_od):
        raise GeometryInputError(
            f"neck OD ({neck_od!r}) must be positive and less than nipoflange_flange_od_mm ({flange_od!r}).")
    if reducing and not (0.0 < tip_od < neck_od):
        raise GeometryInputError(
            f"reduced tip OD ({tip_od!r}) must be positive and less than the neck OD ({neck_od!r}) - "
            f"a 'reducing' nipoflange whose tip is not smaller than its barrel is a contradiction.")

    rule = NipoflangeNeckAllocationRule()
    try:
        sections = rule.allocate(overall_length, flange_thk, reducing)
    except ValueError as e:
        raise GeometryInputError(str(e))
    hub_base_od = rule.hub_base_od(flange_od, neck_od)
    bevel_tip_od = rule.WELD_PREP_TIP_FACTOR * tip_od

    # ---- profile construction (radius, z), z=0 at the flange mating face ----
    profile = [(flange_od / 2.0, 0.0), (flange_od / 2.0, flange_thk),
               (hub_base_od / 2.0, flange_thk)]
    z = flange_thk
    fillet_l = sections["hub_fillet"]
    for i in range(1, _FILLET_SEGMENTS + 1):
        t = i / float(_FILLET_SEGMENTS)
        r = hub_base_od / 2.0 + (neck_od / 2.0 - hub_base_od / 2.0) * _ease(t, _FILLET_EASE_EXPONENT)
        profile.append((max(r, 0.1), z + fillet_l * t))
    z += fillet_l
    z += sections["barrel"]
    profile.append((neck_od / 2.0, z))
    outlet_base_od = None
    if reducing:
        outlet_base_od = rule.outlet_base_od(tip_od, neck_od)
        trans_l = sections["transition"]
        for i in range(1, _TRANSITION_SEGMENTS + 1):
            t = i / float(_TRANSITION_SEGMENTS)
            r = neck_od / 2.0 + (outlet_base_od / 2.0 - neck_od / 2.0) * _ease(t, _TRANSITION_EASE_EXPONENT)
            profile.append((max(r, 0.1), z + trans_l * t))
        z += trans_l
        # weldolet outlet body: linear frustum from the reinforced base down
        # to the tip OD (the same honest linear-taper policy as
        # ConcentricReducerTransitionRule - no published contour exists).
        z += sections["outlet_body"]
        profile.append((tip_od / 2.0, z))
    z += sections["weld_bevel"]
    profile.append((bevel_tip_od / 2.0, z))

    mesh, ring_starts, band_ranges, closures = _revolve_profile(profile, n)

    # ---- features (deterministic ranges off the revolve bands) ----
    def band_feature(name, ftype, first_band, last_band, params):
        f0 = band_ranges[first_band][0]
        f1 = band_ranges[last_band][1]
        v0 = ring_starts[first_band]
        v1 = ring_starts[last_band + 1] + n - 1
        return {"name": name, "type": ftype, "vertex_range": [v0, v1],
                "face_range": [f0, f1], "params": params}

    features = [band_feature("flange_outer_wall", "revolved_outer_profile", 0, 0,
                              {"radius_mm": flange_od / 2.0, "length_mm": flange_thk}),
                band_feature("flange_top_shoulder", "annular_shoulder", 1, 1,
                              {"outer_radius_mm": flange_od / 2.0, "inner_radius_mm": hub_base_od / 2.0}),
                band_feature("hub_fillet", "construction_fillet", 2, 1 + _FILLET_SEGMENTS,
                              {"base_od_mm": hub_base_od, "neck_od_mm": neck_od,
                               "length_mm": sections["hub_fillet"], "rule_id": rule.rule_id}),
                band_feature("main_barrel", "revolved_outer_profile",
                              2 + _FILLET_SEGMENTS, 2 + _FILLET_SEGMENTS,
                              {"radius_mm": neck_od / 2.0, "length_mm": sections["barrel"]})]
    next_band = 3 + _FILLET_SEGMENTS
    if reducing:
        features.append(band_feature("reducing_transition", "construction_transition",
                                      next_band, next_band + _TRANSITION_SEGMENTS - 1,
                                      {"from_od_mm": neck_od, "to_od_mm": outlet_base_od,
                                       "length_mm": sections["transition"], "rule_id": rule.rule_id}))
        next_band += _TRANSITION_SEGMENTS
        features.append(band_feature("weldolet_outlet_body", "construction_frustum",
                                      next_band, next_band,
                                      {"base_od_mm": outlet_base_od, "tip_od_mm": tip_od,
                                       "length_mm": sections["outlet_body"], "rule_id": rule.rule_id}))
        next_band += 1
    features.append(band_feature("weld_prep_bevel", "construction_bevel", next_band, next_band,
                                  {"end_od_mm": tip_od, "bevel_tip_od_mm": bevel_tip_od,
                                   "length_mm": sections["weld_bevel"], "rule_id": rule.rule_id}))
    bc, fb0, fb1 = closures["bottom"]
    features.append({"name": "mating_face_closure", "type": "flat_disc_closure",
                      "vertex_range": [ring_starts[0], bc], "face_range": [fb0, fb1],
                      "params": {"z_mm": 0.0,
                                  "note": "No bore modeled - purchaser-specified per KAFCO source Note 4, never fabricated."}})
    tc, ft0, ft1 = closures["top"]
    features.append({"name": "weld_end_closure", "type": "flat_disc_closure",
                      "vertex_range": [ring_starts[-1], tc], "face_range": [ft0, ft1],
                      "params": {"z_mm": overall_length}})

    # ---- construction values (provenance-carrying inputs + this rule) ----
    from ..construction_value import ConstructionValue
    allocation_cv = ConstructionValue(
        name="nipoflange_neck_envelope_mm", value=overall_length - flange_thk, unit="mm",
        rule_id=rule.rule_id, rule_version=rule.rule_version,
        derivation_trace=[
            "Neck envelope = overall length B - flange thickness D; allocated across "
            + ", ".join(f"{k} {v:.2f}mm" for k, v in sections.items())
            + f" per {rule.rule_id} v{rule.rule_version} (construction geometry, not source-published)."],
    )
    construction_values = [overall_length_value, neck_od_value, allocation_cv]
    if reducing:
        construction_values.append(tip_od_value)

    # ---- measurements off the actual mesh ----
    ring0 = range(ring_starts[0], ring_starts[0] + n)
    measured_od = 2.0 * measure_radial_distance(mesh, ring0, axis_point=(0.0, 0.0))
    measured_thk = abs(mesh.vertices[ring_starts[1]][2] - mesh.vertices[ring_starts[0]][2])
    measured_overall = max(vtx[2] for vtx in mesh.vertices) - min(vtx[2] for vtx in mesh.vertices)
    neck_ring = range(ring_starts[2 + _FILLET_SEGMENTS], ring_starts[2 + _FILLET_SEGMENTS] + n)
    measured_neck_od = 2.0 * measure_radial_distance(mesh, neck_ring, axis_point=(0.0, 0.0))
    measurements = {"nipoflange_flange_od_mm": measured_od,
                     "nipoflange_flange_thickness_mm": measured_thk,
                     "nipoflange_overall_length_mm": measured_overall,
                     "neck_outside_diameter_mm": measured_neck_od}
    expected = {"nipoflange_flange_od_mm": flange_od,
                "nipoflange_flange_thickness_mm": flange_thk,
                "nipoflange_overall_length_mm": overall_length,
                "neck_outside_diameter_mm": neck_od}
    if reducing:
        tip_band_index = 4 + _FILLET_SEGMENTS + _TRANSITION_SEGMENTS
        tip_ring = range(ring_starts[tip_band_index], ring_starts[tip_band_index] + n)
        measured_tip_od = 2.0 * measure_radial_distance(mesh, tip_ring, axis_point=(0.0, 0.0))
        measurements["tip_outside_diameter_mm"] = measured_tip_od
        expected["tip_outside_diameter_mm"] = tip_od

    identity = geometry_spec.engineering_object_identity or {}
    size_identity = {k: identity.get(k) for k in ("size_system", "primary_size")}
    ports = [
        ConnectionPort(port_id="flange_mating_face", role="flange_mating_face",
                        position=(0.0, 0.0, 0.0), direction=(0.0, 0.0, -1.0),
                        size_identity=size_identity, opening_diameter_mm=None,
                        opening_diameter_provenance=OPENING_DIAMETER_PROVENANCE_NOT_MODELED),
        ConnectionPort(port_id="weld_end", role="buttweld_end",
                        position=(0.0, 0.0, overall_length), direction=(0.0, 0.0, 1.0),
                        size_identity=size_identity, opening_diameter_mm=tip_od,
                        opening_diameter_provenance=OPENING_DIAMETER_PROVENANCE_DERIVED),
    ]

    trace = [
        f"{GEOMETRY_TYPE}: flange OD={flange_od}mm THK={flange_thk}mm (KAFCO catalog, "
        f"VERIFIED_MANUFACTURER_SPECIFIC), overall length B={overall_length}mm "
        f"({overall_length_value.rule_id} v{overall_length_value.rule_version} - purchaser-modifiable "
        f"catalog reference, source Note 2).",
        f"{GEOMETRY_TYPE}: neck OD={neck_od}mm ({neck_od_value.rule_id} v{neck_od_value.rule_version})"
        + (f", reduced tip OD={tip_od}mm ({tip_od_value.rule_id} v{tip_od_value.rule_version}) - "
           f"REDUCING configuration with integral weldolet outlet body (base OD={outlet_base_od:.2f}mm)"
           if reducing else " - full/size-on-size configuration (no reduction requested)."),
        f"{GEOMETRY_TYPE}: neck envelope allocation via {rule.rule_id} v{rule.rule_version}: "
        + ", ".join(f"{k}={v:.2f}mm" for k, v in sections.items()) + " (construction geometry, "
        f"not source-published).",
        f"{GEOMETRY_TYPE}: no bore modeled (purchaser-specified per source Note 4) - solid revolved "
        f"envelope, flat disc closures.",
    ]

    return ProductGeometryBuild(
        geometry_type=GEOMETRY_TYPE, mesh=mesh, features=features,
        construction_values=construction_values, measurements=measurements,
        expected_dimensions=expected, trace=trace, ports=ports,
        topology_representation=TopologyRepresentation.SOLID_REVOLVED_COMPOSITE_CONSTRUCTION_ENVELOPE_NO_BOOLEAN_CUT,
    )
