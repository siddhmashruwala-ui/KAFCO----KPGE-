# -*- coding: utf-8 -*-
"""
kgpe.geometry.products.nipoflange  (rule v4 - catalog-fidelity audit)
=====================================================================
Generator for profile_id "flange_nipoflange". v4 rebuilds the contour to
match the KAFCO catalog section drawing's design intent (see
kgpe.geometry.transition_rules.NipoflangeNeckAllocationRule v4 docstring):
early continuous taper off a short 30deg conical hub, a LONG straight
outlet run (the Note-2 purchaser trim zone - all length variation lands
here), tool-relief undercut, olet crown collar, and a genuine B16.25-style
weld prep. When the order states a schedule, the bore is derived from
branch-pipe ID (provenance-carrying ConstructionValue) and the body is a
true hollow revolve; without a schedule the body stays solid and carries
an explicit "bore_not_modeled" feature (source Note 4 - purchaser to
specify; never fabricated).

AUTHORITATIVE INPUTS: nipoflange_flange_od_mm / nipoflange_flange_thickness_mm
(KAFCO catalog, VERIFIED_MANUFACTURER_SPECIFIC).
CONSTRUCTION INPUTS (ConstructionValues resolved by the pipeline):
overall_length_value (catalog default B - fixes the taper geometry),
neck_od_value, tip_od_value (reducing), bore_value (from schedule),
actual_overall_length_value (purchaser trim override of B, optional).
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


def _require_cv(value, name):
    if value is None:
        raise ConstructionRuleUnavailableError(
            f"{GEOMETRY_TYPE} geometry requires the ConstructionValue {name!r} (resolved by the "
            f"pipeline's nipoflange input-derivation step, or supplied via product_kwargs) - it was "
            f"not provided. Never fabricated here.")
    return float(value.value)


def _feature(name, ftype, v0, v1, f0, f1, params=None):
    return {"name": name, "type": ftype, "vertex_range": [v0, v1],
            "face_range": [f0, f1], "params": params or {}}


def build(geometry_spec, generation_parameters,
          overall_length_value=None, neck_od_value=None, tip_od_value=None,
          bore_value=None, actual_overall_length_value=None, flange_bore_value=None):
    dims = geometry_spec.required_dimensions
    required = ("nipoflange_flange_od_mm", "nipoflange_flange_thickness_mm")
    missing = [k for k in required if k not in dims]
    if missing:
        raise GeometryInputError(
            f"{GEOMETRY_TYPE} geometry requires {list(required)} - got {sorted(dims.keys())}")

    flange_od = float(dims["nipoflange_flange_od_mm"]["value"])
    flange_thk = float(dims["nipoflange_flange_thickness_mm"]["value"])
    b_default = _require_cv(overall_length_value, "overall_length_value")
    neck_od = _require_cv(neck_od_value, "neck_od_value")
    reducing = tip_od_value is not None
    outlet_od = float(tip_od_value.value) if reducing else neck_od
    bore_dia = float(bore_value.value) if bore_value is not None else None
    flange_bore_dia = float(flange_bore_value.value) if flange_bore_value is not None else None
    # Reducing nipoflange dual bore (2026-07-21, per Siddh): a flange whose
    # outlet NPS differs from its flange NPS bores through the flange body
    # and hub at the LARGER (flange-side) ID, only reducing to the smaller
    # (outlet-side) ID once past the Hub-to-Neck Transition - see the
    # per-z bore-radius interpolation below. Only active when genuinely
    # reducing and BOTH bores were actually derived; a size-on-size item
    # (or one missing flange_bore_value) keeps today's single-radius bore
    # unchanged.
    dual_bore = reducing and bore_dia is not None and flange_bore_dia is not None
    b_actual = (float(actual_overall_length_value.value)
                 if actual_overall_length_value is not None else b_default)
    n = generation_parameters.radial_segments

    if not (0.0 < neck_od < flange_od):
        raise GeometryInputError(
            f"neck OD ({neck_od!r}) must be positive and less than nipoflange_flange_od_mm ({flange_od!r}).")
    if reducing and not (0.0 < outlet_od < neck_od):
        raise GeometryInputError(
            f"reduced outlet OD ({outlet_od!r}) must be positive and less than the neck OD "
            f"({neck_od!r}) - a 'reducing' nipoflange whose outlet is not smaller is a contradiction.")
    if bore_dia is not None and not (0.0 < bore_dia < outlet_od):
        raise GeometryInputError(
            f"bore diameter ({bore_dia!r}) must be positive and less than the outlet OD ({outlet_od!r}).")
    if dual_bore and not (bore_dia < flange_bore_dia):
        raise GeometryInputError(
            f"flange-side bore ({flange_bore_dia!r}) must be larger than the outlet-side bore "
            f"({bore_dia!r}) - a reducing nipoflange's flange NPS is always larger than its outlet NPS.")

    rule = NipoflangeNeckAllocationRule()
    try:
        sec = rule.sections(b_default, flange_thk, flange_od, neck_od, outlet_od,
                             bore_diameter_mm=bore_dia)
        stub_len = rule.stub_length(sec, b_actual, outlet_od,
                                     extra_straight_mm=0.0 if reducing else sec["taper"])
    except ValueError as e:
        raise GeometryInputError(str(e))

    if dual_bore and not (0.0 < flange_bore_dia < sec["hub_base_r"] * 2.0):
        raise GeometryInputError(
            f"flange-side bore ({flange_bore_dia!r}) must be positive and less than the hub base OD "
            f"({sec['hub_base_r'] * 2.0!r}) so the bore wall stays solid at the narrowest flange-side "
            f"point.")

    d = flange_thk
    hub_base_r, neck_r, outlet_r = sec["hub_base_r"], sec["neck_r"], sec["outlet_r"]
    relief_r, crown_r, bevel_r = sec["undercut_relief_r"], sec["crown_r"], sec["bevel_target_r"]
    uc_len, crown_len, bevel_len = sec["undercut"], sec["crown"], sec["bevel"]
    taper_end_z = sec["taper_end_z"]
    uc_start = taper_end_z + stub_len
    crown_flat_start = uc_start + uc_len + 0.4 * crown_len
    crown_top = uc_start + uc_len + crown_len

    # ---- outer profile: minimal linear segments, one ring per point ----
    pts = [(flange_od / 2.0, 0.0),                       # P0
           (flange_od / 2.0, d),                          # P1 flange wall
           (hub_base_r, d),                               # P2 shoulder
           (neck_r, d + sec["hub"]),                      # P3 hub cone
           (outlet_r, taper_end_z),                       # P4 taper
           (outlet_r, uc_start),                          # P5 straight outlet stub
           (relief_r, uc_start + 0.25 * uc_len),          # P6 relief entry
           (relief_r, uc_start + 0.75 * uc_len),          # P7 relief floor
           (crown_r, crown_flat_start),                   # P8 crown flare
           (crown_r, crown_top),                          # P9 crown collar
           (bevel_r, b_actual)]                           # P10 weld bevel

    # Hub-to-Neck Transition (Hub Taper End): the exact z where the hub
    # cone ends and the reducing taper/straight neck begins - P3's z by
    # construction. For a reducing nipoflange this is also where the
    # internal bore begins its conical reduction from the flange-side ID
    # to the outlet-side ID (2026-07-21, per Siddh: "the reduction must
    # begin exactly at the point where the Hub Taper ends").
    hub_end_z = d + sec["hub"]

    u, v, _axis = straight_axis_frame()
    mesh = Mesh()
    outer_rings = []
    for r, z in pts:
        outer_rings.append(mesh.vertex_count())
        mesh.add_vertices(circle_ring((0.0, 0.0, z), u, v, r, n))
    band_ranges = []
    for k in range(len(pts) - 1):
        f0 = mesh.face_count()
        a, b = outer_rings[k], outer_rings[k + 1]
        for i in range(n):
            j = (i + 1) % n
            mesh.add_quad(a + i, a + j, b + j, b + i)
        band_ranges.append((f0, mesh.face_count()))

    inner_rings = []
    inner_zs = []
    hub_end_idx = None
    taper_end_idx = None
    if bore_dia is not None:
        bore_r = bore_dia / 2.0
        flange_bore_r = flange_bore_dia / 2.0 if dual_bore else None

        def _bore_radius_at(z):
            """Dual-bore rule (2026-07-21): constant flange_bore_r up to the
            Hub-to-Neck Transition, linear conical interpolation to bore_r
            by the reducing-taper end, constant bore_r thereafter. Reduces
            to the original constant bore_r everywhere when not dual_bore -
            zero behaviour change for standard (non-reducing) items."""
            if flange_bore_r is None:
                return bore_r
            if z <= hub_end_z + 1e-9:
                return flange_bore_r
            if z >= taper_end_z - 1e-9:
                return bore_r
            frac = (z - hub_end_z) / (taper_end_z - hub_end_z)
            return flange_bore_r + frac * (bore_r - flange_bore_r)

        # one inner ring per UNIQUE outer z (the outer profile repeats z at
        # the flange shoulder; duplicating the bore ring there would create
        # a zero-area band and fail structural validation). P3's z (=
        # hub_end_z) and P4's z (= taper_end_z) are already distinct entries
        # here, so the transition's start/end rings fall out naturally -
        # no extra rings are needed to carry the reduction.
        for _r, z in pts:
            if not inner_zs or abs(z - inner_zs[-1]) > 1e-9:
                inner_zs.append(z)
        for idx, z in enumerate(inner_zs):
            if dual_bore and hub_end_idx is None and abs(z - hub_end_z) < 1e-9:
                hub_end_idx = idx
            if dual_bore and abs(z - taper_end_z) < 1e-9:
                taper_end_idx = idx
            inner_rings.append(mesh.vertex_count())
            mesh.add_vertices(circle_ring((0.0, 0.0, z), u, v, _bore_radius_at(z), n))
        fb0 = mesh.face_count()
        for k in range(len(inner_rings) - 1):
            a, b = inner_rings[k], inner_rings[k + 1]
            for i in range(n):
                j = (i + 1) % n
                mesh.add_quad(a + j, a + i, b + i, b + j)  # reversed winding (inward-facing)
        fb1 = mesh.face_count()
        # bottom annulus (mating face) and top annulus (root face)
        fc0 = mesh.face_count()
        for i in range(n):
            j = (i + 1) % n
            mesh.add_quad(outer_rings[0] + i, outer_rings[0] + j, inner_rings[0] + j, inner_rings[0] + i)
        fc1 = mesh.face_count()
        for i in range(n):
            j = (i + 1) % n
            mesh.add_quad(outer_rings[-1] + j, outer_rings[-1] + i, inner_rings[-1] + i, inner_rings[-1] + j)
        fc2 = mesh.face_count()
        closure_info = ("annular", fb0, fb1, fc0, fc1, fc2)
    else:
        bottom_centre = mesh.add_vertex((0.0, 0.0, 0.0))
        fc0 = mesh.face_count()
        for i in range(n):
            j = (i + 1) % n
            mesh.add_triangle(outer_rings[0] + j, outer_rings[0] + i, bottom_centre)
        fc1 = mesh.face_count()
        top_centre = mesh.add_vertex((0.0, 0.0, b_actual))
        for i in range(n):
            j = (i + 1) % n
            mesh.add_triangle(outer_rings[-1] + i, outer_rings[-1] + j, top_centre)
        fc2 = mesh.face_count()
        closure_info = ("fan", None, None, fc0, fc1, fc2)

    # ---- features ----
    def band_feat(name, ftype, k0, k1, params):
        return _feature(name, ftype, outer_rings[k0], outer_rings[k1 + 1] + n - 1,
                         band_ranges[k0][0], band_ranges[k1][1], params)

    rp = {"rule_id": rule.rule_id, "rule_version": rule.rule_version}
    features = [
        band_feat("flange_outer_wall", "revolved_outer_profile", 0, 0,
                   {"radius_mm": flange_od / 2.0, "length_mm": d}),
        band_feat("flange_top_shoulder", "annular_shoulder", 1, 1,
                   {"outer_radius_mm": flange_od / 2.0, "inner_radius_mm": hub_base_r}),
        band_feat("hub_cone", "construction_cone", 2, 2,
                   dict(rp, base_od_mm=hub_base_r * 2, top_od_mm=neck_od,
                        half_angle_deg=rule.HUB_ANGLE_DEG, length_mm=sec["hub"])),
        band_feat("reducing_taper" if reducing else "neck_barrel",
                   "construction_taper" if reducing else "revolved_outer_profile", 3, 3,
                   dict(rp, from_od_mm=neck_od, to_od_mm=outlet_od,
                        length_mm=sec["taper"], taper_end_z_mm=taper_end_z)),
        band_feat("reduced_outlet_stub", "revolved_outer_profile", 4, 4,
                   dict(rp, radius_mm=outlet_r, length_mm=stub_len,
                        note="Purchaser trim zone per KAFCO source Note 2 - absorbs all overall-length variation.")),
        band_feat("undercut_relief", "construction_relief", 5, 6,
                   dict(rp, relief_od_mm=relief_r * 2, length_mm=uc_len)),
        band_feat("olet_crown", "construction_collar", 7, 8,
                   dict(rp, crown_od_mm=crown_r * 2, length_mm=crown_len)),
        band_feat("weld_prep_bevel", "construction_bevel", 9, 9,
                   dict(rp, bevel_angle_deg=rule.BEVEL_ANGLE_DEG,
                        root_face_mm=rule.ROOT_FACE_MM if bore_dia is not None else None,
                        end_radius_mm=bevel_r, length_mm=bevel_len)),
    ]
    if bore_dia is not None:
        _k, fb0, fb1, fc0, fc1, fc2 = closure_info
        if dual_bore and hub_end_idx is not None and taper_end_idx is not None and hub_end_idx < taper_end_idx:
            features.append(_feature("flange_bore_wall", "swept_inner_void",
                                       inner_rings[0], inner_rings[hub_end_idx] + n - 1,
                                       fb0, fb0 + hub_end_idx * n,
                                       {"radius_mm": flange_bore_dia / 2.0, "length_mm": hub_end_z,
                                        "source": f"{flange_bore_value.rule_id} v{flange_bore_value.rule_version}",
                                        "note": "Flange-side bore - constant through the flange body and "
                                                 "hub; ends at the Hub-to-Neck Transition."}))
            features.append(_feature("bore_transition_taper", "construction_bore_taper",
                                       inner_rings[hub_end_idx], inner_rings[taper_end_idx] + n - 1,
                                       fb0 + hub_end_idx * n, fb0 + taper_end_idx * n,
                                       {"from_radius_mm": flange_bore_dia / 2.0, "to_radius_mm": bore_dia / 2.0,
                                        "start_z_mm": hub_end_z, "end_z_mm": taper_end_z,
                                        "note": "Conical internal bore reduction from the flange-side ID "
                                                 "to the outlet-side ID, beginning exactly at the "
                                                 "Hub-to-Neck Transition (Hub Taper End) and completing at "
                                                 "the reducing-taper end."}))
            features.append(_feature("outlet_bore_wall", "swept_inner_void",
                                       inner_rings[taper_end_idx], inner_rings[-1] + n - 1,
                                       fb0 + taper_end_idx * n, fb1,
                                       {"radius_mm": bore_dia / 2.0, "length_mm": b_actual - taper_end_z,
                                        "source": f"{bore_value.rule_id} v{bore_value.rule_version}",
                                        "note": "Outlet-side bore - constant through the straight neck "
                                                 "and outlet."}))
        else:
            features.append(_feature("bore_wall", "swept_inner_void",
                                       inner_rings[0], inner_rings[-1] + n - 1, fb0, fb1,
                                       {"radius_mm": bore_dia / 2.0, "length_mm": b_actual,
                                        "source": f"{bore_value.rule_id} v{bore_value.rule_version}"}))
        features.append(_feature("mating_face_closure", "annular_end_cap",
                                   outer_rings[0], inner_rings[0] + n - 1, fc0, fc1, {"z_mm": 0.0}))
        features.append(_feature("weld_end_closure", "annular_end_cap",
                                   outer_rings[-1], inner_rings[-1] + n - 1, fc1, fc2,
                                   {"z_mm": b_actual, "outer_radius_mm": bevel_r,
                                    "note": "root face annulus - no cap wider than the root-face radius"}))
    else:
        _k, _a, _b, fc0, fc1, fc2 = closure_info
        features.append(_feature("bore_not_modeled", "bore_unavailable_metadata", 0, 0, 0, 0,
                                   {"note": "Bore (sch) is purchaser-specified per KAFCO source "
                                             "Note 4 and no schedule was supplied - not modeled, "
                                             "never fabricated."}))
        features.append(_feature("mating_face_closure", "flat_disc_closure",
                                   outer_rings[0], outer_rings[0] + n, fc0, fc1, {"z_mm": 0.0}))
        features.append(_feature("weld_end_closure", "flat_disc_closure",
                                   outer_rings[-1], outer_rings[-1] + n, fc1, fc2, {"z_mm": b_actual}))

    # ---- construction values ----
    from ..construction_value import ConstructionValue
    allocation_cv = ConstructionValue(
        name="nipoflange_neck_sections_mm", value=b_actual - d, unit="mm",
        rule_id=rule.rule_id, rule_version=rule.rule_version,
        derivation_trace=[
            "v4 catalog-faithful profile: fixed sections from DEFAULT B "
            f"({b_default}mm): hub={sec['hub']:.2f}, taper={sec['taper']:.2f} (ends z="
            f"{taper_end_z:.2f}), undercut={uc_len:.2f}, crown={crown_len:.2f}, "
            f"bevel={bevel_len:.2f}; straight outlet stub={stub_len:.2f} for actual B={b_actual}mm "
            "(purchaser trim zone, Note 2)."],
    )
    construction_values = [overall_length_value, neck_od_value, allocation_cv]
    if reducing:
        construction_values.append(tip_od_value)
    if bore_value is not None:
        construction_values.append(bore_value)
    if flange_bore_value is not None:
        construction_values.append(flange_bore_value)
    if actual_overall_length_value is not None:
        construction_values.append(actual_overall_length_value)

    # ---- measurements off the actual mesh ----
    def ring_radius(start):
        return 2.0 * measure_radial_distance(mesh, range(start, start + n), axis_point=(0.0, 0.0))

    measurements = {
        "nipoflange_flange_od_mm": ring_radius(outer_rings[0]),
        "nipoflange_flange_thickness_mm": abs(mesh.vertices[outer_rings[1]][2] - mesh.vertices[outer_rings[0]][2]),
        "nipoflange_overall_length_mm": max(vv[2] for vv in mesh.vertices) - min(vv[2] for vv in mesh.vertices),
        "neck_outside_diameter_mm": ring_radius(outer_rings[3]),
        "tip_outside_diameter_mm": ring_radius(outer_rings[4]),
        "crown_outside_diameter_mm": ring_radius(outer_rings[8]),
    }
    expected = {
        "nipoflange_flange_od_mm": flange_od,
        "nipoflange_flange_thickness_mm": d,
        "nipoflange_overall_length_mm": b_actual,
        "neck_outside_diameter_mm": neck_od,
        "tip_outside_diameter_mm": outlet_od,
        "crown_outside_diameter_mm": crown_r * 2.0,
    }
    if bore_dia is not None:
        # bore_diameter_mm reports the OUTLET/weld-end bore (matches the
        # "weld_end" port's opening_diameter_mm below); for a size-on-size
        # item every inner ring shares one radius so this is unchanged from
        # before. For a dual-bore item the flange-side ring at inner_rings[0]
        # is a DIFFERENT (larger) diameter - reported separately below.
        measurements["bore_diameter_mm"] = ring_radius(inner_rings[-1])
        expected["bore_diameter_mm"] = bore_dia
        if dual_bore:
            measurements["flange_bore_diameter_mm"] = ring_radius(inner_rings[0])
            expected["flange_bore_diameter_mm"] = flange_bore_dia

    identity = geometry_spec.engineering_object_identity or {}
    size_identity = {k: identity.get(k) for k in ("size_system", "primary_size")}
    ports = [
        ConnectionPort(port_id="flange_mating_face", role="flange_mating_face",
                        position=(0.0, 0.0, 0.0), direction=(0.0, 0.0, -1.0),
                        size_identity=size_identity,
                        opening_diameter_mm=(flange_bore_dia if dual_bore else bore_dia),
                        opening_diameter_provenance=(OPENING_DIAMETER_PROVENANCE_DERIVED
                                                      if bore_dia is not None else
                                                      OPENING_DIAMETER_PROVENANCE_NOT_MODELED)),
        ConnectionPort(port_id="weld_end", role="buttweld_end",
                        position=(0.0, 0.0, b_actual), direction=(0.0, 0.0, 1.0),
                        size_identity=size_identity,
                        opening_diameter_mm=bore_dia if bore_dia is not None else outlet_od,
                        opening_diameter_provenance=OPENING_DIAMETER_PROVENANCE_DERIVED),
    ]

    trace = [
        f"{GEOMETRY_TYPE} v4: flange OD={flange_od}mm THK={d}mm (KAFCO catalog), default B={b_default}mm"
        + (f", actual B={b_actual}mm ({actual_overall_length_value.rule_id})" if actual_overall_length_value else ""),
        f"{GEOMETRY_TYPE} v4: neck OD={neck_od}mm"
        + (f", reduced outlet OD={outlet_od}mm" if reducing else " (full/size-on-size)")
        + (f", bore ID={bore_dia}mm ({bore_value.rule_id} v{bore_value.rule_version})"
           if bore_dia is not None else " - bore not modeled (Note 4, no schedule supplied)"),
        f"{GEOMETRY_TYPE} v4: sections per {rule.rule_id} v{rule.rule_version}: "
        f"hub={sec['hub']:.2f}mm@{rule.HUB_ANGLE_DEG}deg, taper ends z={taper_end_z:.2f}mm "
        f"({rule.TAPER_END_FRACTION:.0%} of default envelope), stub={stub_len:.2f}mm (trim zone), "
        f"undercut={uc_len:.2f}mm, crown OD={crown_r*2:.2f}mm x {crown_len:.2f}mm, "
        f"bevel {rule.BEVEL_ANGLE_DEG}deg x {bevel_len:.2f}mm -> r={bevel_r:.2f}mm.",
    ]
    if dual_bore:
        trace.append(
            f"{GEOMETRY_TYPE} v4 (reducing nipoflange dual bore): flange-side bore ID={flange_bore_dia}mm "
            f"({flange_bore_value.rule_id} v{flange_bore_value.rule_version}) constant through the flange "
            f"and hub to z={hub_end_z:.2f}mm (Hub-to-Neck Transition), conical reduction to outlet-side "
            f"bore ID={bore_dia}mm complete by z={taper_end_z:.2f}mm (reducing-taper end), constant "
            f"thereafter through the straight neck and outlet.")

    topology = (TopologyRepresentation.HOLLOW_REVOLVED_COMPOSITE_CONSTRUCTION_ENVELOPE_NO_BOOLEAN_CUT
                 if bore_dia is not None else
                 TopologyRepresentation.SOLID_REVOLVED_COMPOSITE_CONSTRUCTION_ENVELOPE_NO_BOOLEAN_CUT)

    return ProductGeometryBuild(
        geometry_type=GEOMETRY_TYPE, mesh=mesh, features=features,
        construction_values=construction_values, measurements=measurements,
        expected_dimensions=expected, trace=trace, ports=ports,
        topology_representation=topology,
    )
