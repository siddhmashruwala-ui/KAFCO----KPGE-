# -*- coding: utf-8 -*-
"""
kgpe.geometry_spec.coverage
===============================
Prompt 11 Sec.20-23: geometry profile coverage matrix, existing-geometry
compatibility mapping, and the construction-rule requirement register.

This module performs READ-ONLY inspection, exactly like Prompt 9's
kgpe.contract.data_layer_audit (which it reuses directly for the base
per-(family,subtype) rows) - it never modifies a source file, never
resolves a quarantined conflict, and never invents a construction rule.
"""
from ..contract import verification as V
from ..contract.data_layer_audit import coverage_vs_geometry_matrix
from .profile import PROFILE_REGISTRY, MFR_REQUIRED

PROFILE_READY = "PROFILE_READY"
PROFILE_BLOCKED_MISSING_AUTHORITATIVE_DIMENSIONS = "PROFILE_BLOCKED_MISSING_AUTHORITATIVE_DIMENSIONS"
PROFILE_BLOCKED_QUARANTINED_DIMENSION = "PROFILE_BLOCKED_QUARANTINED_DIMENSION"
PROFILE_BLOCKED_CONSTRUCTION_RULE_REQUIRED = "PROFILE_BLOCKED_CONSTRUCTION_RULE_REQUIRED"
PROFILE_NOT_YET_DEFINED = "PROFILE_NOT_YET_DEFINED"

ALL_PROFILE_COVERAGE_STATUSES = frozenset({
    PROFILE_READY, PROFILE_BLOCKED_MISSING_AUTHORITATIVE_DIMENSIONS, PROFILE_BLOCKED_QUARANTINED_DIMENSION,
    PROFILE_BLOCKED_CONSTRUCTION_RULE_REQUIRED, PROFILE_NOT_YET_DEFINED,
})


def _find_profile_for_row(product_family, subtype):
    subtype_key = None if subtype == "(generic)" else subtype
    for profile in PROFILE_REGISTRY:
        if profile.applies_to(product_family, subtype_key):
            return profile
    return None


def _profile_dimension_gaps(reader, profile, standard, subtype):
    """Checks the LIVE registry directly (never invented) for whether each
    required dimension has an authoritative (or, if permitted, manufacturer
    -specific) fact at this exact standard/subtype scope."""
    criteria = {"product_family": profile.product_family, "standard": standard}
    field = ("flange_type" if profile.product_family == "flange" else
             "fitting_type" if profile.product_family in ("buttweld_fitting", "socketweld_fitting", "olet") else None)
    if field and subtype and subtype != "(generic)":
        criteria[field] = subtype

    missing, quarantined = [], []
    for dim_name in sorted(profile.required_dimensions):
        facts = reader._matching_facts(dimension_name=dim_name, **criteria)
        statuses = {f.verification_status for f in facts}
        if V.VERIFIED_AUTHORITATIVE in statuses:
            continue
        if profile.manufacturer_specific != "NOT_APPLICABLE" and V.VERIFIED_MANUFACTURER_SPECIFIC in statuses:
            continue
        if statuses and statuses <= V.NEVER_AUTHORITATIVE_STATUSES:
            quarantined.append(dim_name)
        else:
            missing.append(dim_name)
    return missing, quarantined


def geometry_profile_coverage_matrix(reader):
    """Sec.20: one row per (product_family, subtype) actually present in
    the live registry (via Prompt 9's coverage_vs_geometry_matrix),
    extended with geometry-profile-specific columns."""
    rows = []
    for row in coverage_vs_geometry_matrix(reader.registry):
        fam, subtype = row["product_family"], row["subtype"]
        profile = _find_profile_for_row(fam, subtype)
        if profile is None:
            status, missing, quarantined = PROFILE_NOT_YET_DEFINED, [], []
        else:
            missing, quarantined = [], []
            for standard in row["standards"]:
                m, q = _profile_dimension_gaps(reader, profile, standard, subtype)
                missing = sorted(set(missing) | set(m))
                quarantined = sorted(set(quarantined) | set(q))
            if quarantined:
                status = PROFILE_BLOCKED_QUARANTINED_DIMENSION
            elif missing and (set(missing) & profile.construction_derivable_dimensions):
                status = PROFILE_BLOCKED_CONSTRUCTION_RULE_REQUIRED
            elif missing:
                status = PROFILE_BLOCKED_MISSING_AUTHORITATIVE_DIMENSIONS
            else:
                status = PROFILE_READY

        rows.append({
            "product_family": fam, "subtype": subtype, "standards": row["standards"],
            "canonical_data_available": row["data_available"],
            "legacy_geometry_available": row["legacy_geometry_available"],
            "geometry_profile_defined": profile is not None,
            "geometry_profile_id": profile.profile_id if profile else None,
            "manufacturer_context_required": bool(profile and profile.manufacturer_specific == MFR_REQUIRED),
            "missing_required_dimensions": missing,
            "quarantined_required_dimensions": quarantined,
            "geometry_readiness_status": status,
        })
    return rows


# ---------------------------------------------------------------------------
# Sec.22: existing-geometry compatibility mapping. Curated from direct
# inspection of kgpe/rules/*.py and kgpe/dimension_library.py during
# Prompt 11 (see kgpe/geometry_spec/profile.py's per-profile notes for the
# live-registry evidence) - documentation, not auto-derived, since it
# requires reading the LEGACY code's own request/field-naming choices,
# which are not mechanically introspectable the way canonical facts are.
# ---------------------------------------------------------------------------
EXISTING_GEOMETRY_COMPATIBILITY_MAPPING = [
    {
        "existing_geometry_path": "pipe (rules/pipe.py)",
        "geometry_profile_id": "pipe",
        "exact_mapping": "dl.get_pipe(standard,size,schedule) OD_mm/WallThickness_mm map 1:1 onto "
                          "outside_diameter_mm/wall_thickness_mm.",
        "missing_canonical_dimensions": [],
        "legacy_heuristic_inputs": ["BoreID_mm (OD-2*WT, computed in dimension_library.py, "
                                     "not a canonical fact)", "length_mm (commercial cut length, "
                                     "placeholder if not supplied - never a standard dimension)"],
        "backward_compatible_adapter_possible": True,
    },
    {
        "existing_geometry_path": "flange (rules/flange.py)",
        "geometry_profile_id": "flange_weld_neck",
        "exact_mapping": "dl.get_flange() OD_mm/BoltCircle_mm/BoltHoleDia_mm/NumBolts/BoltSize_in/"
                          "Thickness_WeldNeck_mm map onto outside_diameter_mm/bolt_circle_diameter_mm/"
                          "bolt_hole_diameter_mm/num_bolts/bolt_size_designation/"
                          "flange_thickness_weld_neck_mm.",
        "missing_canonical_dimensions": ["bore_diameter_mm (ASME_B16.5/EN_1092-1 only - legacy code "
                                          "falls back to a pipe_schedule cross-reference)",
                                          "hub_base_diameter_mm/length_through_hub_mm (no facts at all, "
                                          "any standard - hub/neck taper not modeled by legacy code either)"],
        "legacy_heuristic_inputs": ["bore via pipe_schedule cross-reference (_default_pipe_standard)"],
        "backward_compatible_adapter_possible": True,
    },
    {
        "existing_geometry_path": "buttweld elbow_90 (rules/buttweld.py._elbow90)",
        "geometry_profile_id": "buttweld_elbow",
        "exact_mapping": "dl.get_buttweld_elbow90() OD_mm/CtoE_mm map onto outside_diameter_mm/"
                          "centre_to_end_mm. NOTE: the legacy request literal fitting_type='elbow_90' "
                          "does not distinguish LR/SR/3D radius or 45/90deg angle at all - inspection of "
                          "dimension_library.get_buttweld_elbow90's ASME_B16.9 branch shows it always "
                          "reads Elbow90LR_CtoE_mm specifically, i.e. legacy 'elbow_90' == canonical "
                          "elbow_90_lr in practice, never elbow_45_lr/elbow_90_3d/elbow_90_sr.",
        "missing_canonical_dimensions": [],
        "legacy_heuristic_inputs": [],
        "backward_compatible_adapter_possible": True,
    },
    {
        "existing_geometry_path": "buttweld tee (rules/buttweld.py._tee)",
        "geometry_profile_id": "buttweld_tee_equal",
        "exact_mapping": "dl.get_buttweld_tee() OD_mm/RunCtoE_mm/OutletCtoE_mm map onto "
                          "outside_diameter_mm/tee_run_centre_to_end_mm/tee_branch_centre_to_end_mm.",
        "missing_canonical_dimensions": [],
        "legacy_heuristic_inputs": [],
        "backward_compatible_adapter_possible": True,
    },
    {
        "existing_geometry_path": "buttweld cap (rules/buttweld.py._cap)",
        "geometry_profile_id": "buttweld_cap",
        "exact_mapping": "dl.get_buttweld_cap() OD_mm/Length_mm map onto outside_diameter_mm/"
                          "cap_length_standard_wall_mm ONLY.",
        "missing_canonical_dimensions": [],
        "legacy_heuristic_inputs": ["cap_length_heavy_wall_mm/cap_wall_thickness_threshold_mm exist "
                                     "canonically but are never read by legacy code - dl.get_buttweld_cap "
                                     "always returns Length_H_mm (standard-wall) unconditionally, never "
                                     "comparing the mating pipe's actual wall thickness against the "
                                     "published threshold to decide between H and H1."],
        "backward_compatible_adapter_possible": True,
    },
    {
        "existing_geometry_path": "olet (rules/olet.py)",
        "geometry_profile_id": "olet_body / olet_outlet_height",
        "exact_mapping": "None - rules/olet.py unconditionally returns GEOMETRY_DEFINITION_INCOMPLETE; "
                          "no dimension_library.get_olet() function exists at all.",
        "missing_canonical_dimensions": [],
        "legacy_heuristic_inputs": [],
        "backward_compatible_adapter_possible": False,
    },
]


# ---------------------------------------------------------------------------
# Sec.23: construction-rule requirement register. Every entry traces to a
# concrete, live-confirmed finding (see profile.py's per-profile notes) -
# none are invented. Prompt 12 will begin resolving these; this prompt
# only registers them.
# ---------------------------------------------------------------------------
CONSTRUCTION_RULE_REQUIREMENT_REGISTER = [
    {
        "product_family": "flange", "subtype": "weld_neck", "standards": ["ASME_B16.5", "EN_1092-1"],
        "missing_geometric_concept": "Flange bore diameter (ASME_B16.5/EN_1092-1 publish no per-class "
                                      "bore at all).",
        "authoritative_dimensions_available": ["outside_diameter_mm", "flange_thickness_weld_neck_mm",
                                                "bolt_circle_diameter_mm", "bolt_hole_diameter_mm"],
        "legacy_behaviour": "rules/flange.py falls back to a pipe_schedule cross-reference "
                             "(dl.get_pipe via _default_pipe_standard) when bore isn't tabulated.",
        "future_rule_required": "A formalized cross-family construction rule: bore = mating pipe's "
                                 "BoreID at the same NPS/DN + an explicit pipe schedule/wall-thickness "
                                 "input, promoted from legacy heuristic to an approved Phase-3+ rule.",
        "blocks_geometry_generation_now": False,
        "resolved_in": "Prompt 14 Sec.14-16/18 (profile.py v1->v2 removed bore_diameter_mm from "
                        "PROFILE_FLANGE_WELD_NECK's required_dimensions; ASME_B16.5's bore is now "
                        "resolved externally via kgpe.geometry.cross_family."
                        "FlangeBoreViaPipeScheduleRule and threaded through GeometryKernel.generate()'s "
                        "product_kwargs, exactly like Prompt 13's wall-context pattern. EN_1092-1's bore "
                        "remains genuinely unavailable - no DN-based cross-family rule exists yet; "
                        "EN_1092-1 flanges generate as SOLID_EXTERNAL_ENVELOPE with no bore modeled, "
                        "which is why this entry is retained (historical + partially-resolved record) "
                        "rather than deleted.",
    },
    {
        "product_family": "flange", "subtype": "weld_neck", "standards": ["ASME_B16.5", "JIS_B2220", "EN_1092-1"],
        "missing_geometric_concept": "Hub/neck taper geometry (hub base diameter, length through hub).",
        "authoritative_dimensions_available": [],
        "legacy_behaviour": "rules/flange.py models a flat-plate body only - explicitly does not "
                             "attempt hub/neck taper, by its own documented v1 scope.",
        "future_rule_required": "New source data would be required first (no facts exist at all); "
                                 "this is a DATA gap, not solvable by a construction rule alone.",
        "blocks_geometry_generation_now": False,
    },
    {
        "product_family": "buttweld_fitting", "subtype": "reducer_concentric/reducer_eccentric",
        "standards": ["ASME_B16.9"],
        "missing_geometric_concept": "Per-end (large/small) outside diameter for a reducer.",
        "authoritative_dimensions_available": ["end_to_end_mm (via large_end_nps/small_end_nps)"],
        "legacy_behaviour": "No existing legacy geometry rule for reducers exists at all "
                             "(buttweld.py only branches on elbow_90/tee/cap).",
        "future_rule_required": "A resolver/compiler-level mapping rule: resolve outside_diameter_mm "
                                 "TWICE, once with nps=large_end_size and once with nps=small_end_size "
                                 "(the plain 'nps' shared cross-subtype identity), since large_end_nps/"
                                 "small_end_nps do not scope outside_diameter_mm at all.",
        "blocks_geometry_generation_now": False,
        "resolved_in": "Prompt 13 Sec.20: kgpe.geometry.reducer_rules.ReducerPerEndOutsideDiameterRule "
                        "performs exactly this two-call per-end resolution at the geometry-kernel layer; "
                        "kgpe/geometry_spec/profile.py's PROFILE_BUTTWELD_REDUCER was bumped v1->v2 "
                        "(outside_diameter_mm moved from required to construction_derivable) since "
                        "requiring it made GEOMETRY_READY structurally unreachable.",
    },
    {
        "product_family": "socketweld_fitting", "subtype": "elbow_90_sw/elbow_45_sw/tee_sw/cross_sw",
        "standards": ["ASME_B16.11"],
        "missing_geometric_concept": "Body outside diameter (mating-pipe OD, a cross-family "
                                      "dependency - already documented as a curated source gap in "
                                      "Prompt 9's data_layer_audit._CURATED_SOURCE_GAPS).",
        "authoritative_dimensions_available": ["centre_to_end_mm", "fitting_body_wall_thickness_mm",
                                                "socket_bore_diameter_min_mm", "socket_bore_depth_min_mm"],
        "legacy_behaviour": "No existing legacy geometry rule for socketweld fittings exists at all "
                             "(generator.py has no 'socketweld_fitting' _DISPATCH entry).",
        "future_rule_required": "Cross-family dimension resolution: outside_diameter_mm from "
                                 "product_family='pipe' standard='ASME_B36.10M'/'ASME_B36.19M' at the "
                                 "same NPS, given an explicit mating-pipe schedule - not implemented by "
                                 "kgpe.resolver.engine today (single-family queries only).",
        "blocks_geometry_generation_now": True,
    },
    {
        "product_family": "buttweld_fitting", "subtype": "cap", "standards": ["ASME_B16.9"],
        "missing_geometric_concept": "Selecting between standard-wall (H) and heavy-wall (H1) cap "
                                      "length based on the actual mating pipe's wall thickness vs. the "
                                      "published cap_wall_thickness_threshold_mm.",
        "authoritative_dimensions_available": ["cap_length_standard_wall_mm", "cap_length_heavy_wall_mm",
                                                "cap_wall_thickness_threshold_mm"],
        "legacy_behaviour": "rules/buttweld.py._cap() always uses Length_H_mm (standard-wall) "
                             "unconditionally - never compares against the threshold.",
        "future_rule_required": "A construction rule taking an explicit mating-pipe wall thickness "
                                 "and selecting H vs H1 accordingly - both dimensions are already "
                                 "authoritative and available; only the SELECTION policy is missing.",
        "blocks_geometry_generation_now": False,
    },
]
