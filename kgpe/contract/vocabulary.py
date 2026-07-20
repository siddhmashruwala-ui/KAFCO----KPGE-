# -*- coding: utf-8 -*-
"""
kgpe.contract.vocabulary
========================
Canonical vocabulary for the KGPE engineering-data contract (Phase 2 /
Prompt 4). This module defines NAMES ONLY - no values, no lookups, no
geometry. It exists so every later KGPE module (and, eventually, migrated
datasets) refers to the same engineering concepts by the same string,
instead of each file inventing its own field name - Prompts 1-3 found this
already happening between the Python Dimension Library and the JS CRM
system (e.g. "RF_BORE" in JS actually meaning raised-face diameter, not a
bore).

Nothing here is authoritative engineering DATA. This is naming only.

Per Prompt 4 scope: these are the canonical names KGPE will use going
forward. They do NOT retroactively rename existing fields in
dimension_library.py or the AI-Readable JSON files - that is an explicit
non-goal of this prompt (no mass migration). A compatibility map at the
bottom of this file documents how today's field names relate to these
canonical names, for future migration work.
"""

# ---------------------------------------------------------------------------
# 1. Product identity
# ---------------------------------------------------------------------------
# NOTE: these values are DELIBERATELY identical to the strings already used
# by kgpe/generator.py's _DISPATCH and each rules/*.py's PRODUCT_TYPE
# constant (confirmed by direct file inspection in this prompt) - reusing
# them here is a compatibility decision, not an oversight.
PRODUCT_FAMILY_FLANGE = "flange"
PRODUCT_FAMILY_PIPE = "pipe"
PRODUCT_FAMILY_BUTTWELD_FITTING = "buttweld_fitting"
PRODUCT_FAMILY_SOCKETWELD_FITTING = "socketweld_fitting"
PRODUCT_FAMILY_OLET = "olet"

PRODUCT_FAMILIES = frozenset({
    PRODUCT_FAMILY_FLANGE, PRODUCT_FAMILY_PIPE, PRODUCT_FAMILY_BUTTWELD_FITTING,
    PRODUCT_FAMILY_SOCKETWELD_FITTING, PRODUCT_FAMILY_OLET,
})

# product_type / subtype / connection_type / flange_type are free-form
# strings scoped within a product_family (e.g. product_family=flange,
# flange_type="weld_neck"|"other" per the Prompt 3 T/TJ split). Not
# enumerated exhaustively here.

# fitting_type: canonical ASME B16.9 buttweld fitting-type identifiers
# (Prompt 7), established from the ACTUAL source file's product sections,
# not assumed in advance. Deliberately five distinct elbow identities
# (angle x radius-type are both engineering-significant - a 45deg elbow is
# not "a 90deg elbow rotated" and a 3D-radius elbow is not the same
# fitting as a long-radius elbow at the same angle), one tee identity (the
# source contains ONLY equal tees - no reducing-tee table exists in this
# project's data, so no "tee_reducing" identifier is defined until such
# data actually exists), and two reducer identities (concentric/eccentric
# share identical tabulated OD/length values per the source's own note,
# but remain distinct engineering identities - Prompt 7 Sec.9).
FITTING_TYPE_ELBOW_90_LR = "elbow_90_lr"     # 90deg, long radius (1.5x NPS)
FITTING_TYPE_ELBOW_45_LR = "elbow_45_lr"     # 45deg, long radius
FITTING_TYPE_ELBOW_90_3D = "elbow_90_3d"     # 90deg, 3D radius (3x NPS)
FITTING_TYPE_ELBOW_45_3D = "elbow_45_3d"     # 45deg, 3D radius
FITTING_TYPE_ELBOW_90_SR = "elbow_90_sr"     # 90deg, short radius (1.0x NPS) - no 45SR in this source
FITTING_TYPE_TEE_EQUAL = "tee_equal"         # only tee subtype in this source (no reducing tee data present)
FITTING_TYPE_REDUCER_CONCENTRIC = "reducer_concentric"
FITTING_TYPE_REDUCER_ECCENTRIC = "reducer_eccentric"
FITTING_TYPE_CAP = "cap"

BUTTWELD_FITTING_TYPES = frozenset({
    FITTING_TYPE_ELBOW_90_LR, FITTING_TYPE_ELBOW_45_LR, FITTING_TYPE_ELBOW_90_3D,
    FITTING_TYPE_ELBOW_45_3D, FITTING_TYPE_ELBOW_90_SR, FITTING_TYPE_TEE_EQUAL,
    FITTING_TYPE_REDUCER_CONCENTRIC, FITTING_TYPE_REDUCER_ECCENTRIC, FITTING_TYPE_CAP,
})

# ---------------------------------------------------------------------------
# Prompt 8 additions - socketweld (ASME B16.11), branch-outlet (MSS SP-97),
# JIS (B2311/2312) and EN/DIN (EN 10253 family) buttweld-fitting types.
# Each is its own identifier - none of these are collapsed into the ASME
# B16.9 fitting-type constants above even where the engineering concept is
# similar (e.g. elbow_90_lr vs elbow_90_lr_jis), because the underlying
# standard, tolerance basis, and (for JIS) OD series are all genuinely
# different (Prompt 8 Sec.4/10/14 - cross-standard equality is not
# duplicate identity).
# ---------------------------------------------------------------------------
FITTING_TYPE_ELBOW_90_SW = "elbow_90_sw"           # ASME B16.11 socket-weld 90deg elbow
FITTING_TYPE_ELBOW_45_SW = "elbow_45_sw"           # ASME B16.11 socket-weld 45deg elbow
FITTING_TYPE_TEE_SW = "tee_sw"                     # ASME B16.11 socket-weld tee
FITTING_TYPE_CROSS_SW = "cross_sw"                 # ASME B16.11 socket-weld cross (source: identical body-socket dims to tee)
FITTING_TYPE_COUPLING_SW = "coupling_sw"           # ASME B16.11 full coupling
FITTING_TYPE_HALF_COUPLING_SW = "half_coupling_sw"  # ASME B16.11 half coupling
FITTING_TYPE_CAP_SW = "cap_sw"                     # ASME B16.11 socket-weld cap

SOCKETWELD_FITTING_TYPES = frozenset({
    FITTING_TYPE_ELBOW_90_SW, FITTING_TYPE_ELBOW_45_SW, FITTING_TYPE_TEE_SW,
    FITTING_TYPE_CROSS_SW, FITTING_TYPE_COUPLING_SW, FITTING_TYPE_HALF_COUPLING_SW,
    FITTING_TYPE_CAP_SW,
})

FITTING_TYPE_WELDOLET_REDUCING = "weldolet_reducing"  # MSS SP-97 official branch-outlet-height table, reducing config
FITTING_TYPE_WELDOLET_FULL = "weldolet_full"          # MSS SP-97 official branch-outlet-height table, full/size-on-size config
FITTING_TYPE_WELDOLET = "weldolet"                    # MSS SP-97 (Bonney Forge) manufacturer body dims, size-on-size
FITTING_TYPE_SOCKOLET = "sockolet"                    # MSS SP-97 (Bonney Forge) manufacturer body dims
FITTING_TYPE_THREADOLET = "threadolet"                # MSS SP-97 (Bonney Forge) manufacturer body dims
# Nipoflange: a forged branch-outlet fitting (same structural family as
# weldolet/sockolet/threadolet) that terminates in an integral raised-face
# flange rather than a weld bevel/socket/thread end. Kept under
# PRODUCT_FAMILY_OLET (not a new top-level product family) because it is
# engineering-equivalent to the other branch-outlet fitting types, only
# the terminal end differs - exactly what fitting_type already exists to
# distinguish. Data source: KAFCO's own Nipoflange catalog (manufacturer-
# specific, not an MSS/ASME standard table) - see
# adapters/kafco_nipoflange.py.
FITTING_TYPE_NIPOFLANGE = "nipoflange"

OLET_FITTING_TYPES = frozenset({
    FITTING_TYPE_WELDOLET_REDUCING, FITTING_TYPE_WELDOLET_FULL,
    FITTING_TYPE_WELDOLET, FITTING_TYPE_SOCKOLET, FITTING_TYPE_THREADOLET,
    FITTING_TYPE_NIPOFLANGE,
})

FITTING_TYPE_ELBOW_90_LR_JIS = "elbow_90_lr_jis"
FITTING_TYPE_ELBOW_45_JIS = "elbow_45_jis"          # source does not split LR/SR for 45deg - one JIS 45deg identity
FITTING_TYPE_TEE_EQUAL_JIS = "tee_equal_jis"
FITTING_TYPE_CAP_JIS = "cap_jis"
FITTING_TYPE_REDUCER_CONCENTRIC_JIS = "reducer_concentric_jis"  # source: concentric only, representative sample

JIS_BUTTWELD_FITTING_TYPES = frozenset({
    FITTING_TYPE_ELBOW_90_LR_JIS, FITTING_TYPE_ELBOW_45_JIS, FITTING_TYPE_TEE_EQUAL_JIS,
    FITTING_TYPE_CAP_JIS, FITTING_TYPE_REDUCER_CONCENTRIC_JIS,
})

FITTING_TYPE_ELBOW_90_EN = "elbow_90_en"
FITTING_TYPE_RETURN_180_EN = "return_180_en"        # source: 180deg return, CtoC not CtoE - distinct fitting, not "elbow x2"
FITTING_TYPE_TEE_EQUAL_EN = "tee_equal_en"
FITTING_TYPE_CAP_EN = "cap_en"
FITTING_TYPE_REDUCER_CONCENTRIC_EN = "reducer_concentric_en"  # source: concentric only, no eccentric table present

EN_BUTTWELD_FITTING_TYPES = frozenset({
    FITTING_TYPE_ELBOW_90_EN, FITTING_TYPE_RETURN_180_EN, FITTING_TYPE_TEE_EQUAL_EN,
    FITTING_TYPE_CAP_EN, FITTING_TYPE_REDUCER_CONCENTRIC_EN,
})

# ---------------------------------------------------------------------------
# 2. Governing specification
# ---------------------------------------------------------------------------
STANDARD_FAMILY_ASME = "ASME"
STANDARD_FAMILY_JIS = "JIS"
STANDARD_FAMILY_EN = "EN"   # covers DIN/EN jointly, per existing DIMLIB naming
STANDARD_FAMILY_MSS = "MSS"

STANDARD_FAMILIES = frozenset({
    STANDARD_FAMILY_ASME, STANDARD_FAMILY_JIS, STANDARD_FAMILY_EN, STANDARD_FAMILY_MSS,
})


def known_dimensional_standards():
    """Returns the set of `standard` identifiers dimension_library.py
    actually supports right now (e.g. "ASME_B16.5", "JIS_B2220"), read
    directly from its own FLANGE_FILES/PIPE_FILES/BUTTWELD_FILES/
    SOCKETWELD_FILES/OLET_FILES registries rather than re-typed by hand -
    so this can never silently drift out of sync the way the JS/Python
    field-name duplication did (Prompt 2 finding). Local import avoids a
    hard import-order dependency at module load time."""
    from .. import dimension_library as _dl
    ids = set()
    for registry in (_dl.FLANGE_FILES, _dl.PIPE_FILES, _dl.BUTTWELD_FILES,
                      _dl.SOCKETWELD_FILES, _dl.OLET_FILES):
        ids.update(registry.keys())
    return frozenset(ids)


# material_standard is intentionally NOT enumerated here - Prompts 1-3
# noted MATGRADES/MATPROPS in the JS CRM as out of scope; material
# standards are a separate future concern, not part of this geometry
# data contract.
#
# standard_edition is free-form (e.g. "2020") and always Optional/None
# when unconfirmed - see EngineeringFactProvenance in model.py. No
# canonical list here: fabricating one would violate "do not invent
# standard editions" (Prompt 4 Sec. 7).

# ---------------------------------------------------------------------------
# 3. Size identity
# ---------------------------------------------------------------------------
SIZE_SYSTEM_NPS = "NPS"                           # ASME nominal pipe size, e.g. "2", "1-1/2"
SIZE_SYSTEM_DN = "DN"                             # EN/ISO nominal diameter, e.g. 50
SIZE_SYSTEM_JIS_A = "JIS_A"                       # JIS nominal size "A" designation, e.g. 50A
SIZE_SYSTEM_REDUCING_PAIR = "REDUCING_PAIR"       # e.g. large NPS6 x small NPS4
SIZE_SYSTEM_RUN_BRANCH_PAIR = "RUN_BRANCH_PAIR"   # e.g. run NPS6 x branch NPS2

SIZE_SYSTEMS = frozenset({
    SIZE_SYSTEM_NPS, SIZE_SYSTEM_DN, SIZE_SYSTEM_JIS_A,
    SIZE_SYSTEM_REDUCING_PAIR, SIZE_SYSTEM_RUN_BRANCH_PAIR,
})

# ---------------------------------------------------------------------------
# 4. Rating identity
# ---------------------------------------------------------------------------
RATING_SYSTEM_ASME_CLASS = "ASME_CLASS"                # e.g. "150", "300", "600"
RATING_SYSTEM_PN = "PN"                                # e.g. "PN16"
RATING_SYSTEM_JIS_K = "JIS_K"                          # e.g. "10K"
RATING_SYSTEM_SCHEDULE = "SCHEDULE"                    # e.g. "Sch40", "Sch80"
RATING_SYSTEM_WALL_DESIGNATION = "WALL_DESIGNATION"    # e.g. EN "Series3"

RATING_SYSTEMS = frozenset({
    RATING_SYSTEM_ASME_CLASS, RATING_SYSTEM_PN, RATING_SYSTEM_JIS_K,
    RATING_SYSTEM_SCHEDULE, RATING_SYSTEM_WALL_DESIGNATION,
})

# ---------------------------------------------------------------------------
# 5. Dimension identity (canonical names)
# ---------------------------------------------------------------------------
# Length dimensions end in _mm so a bare name is self-describing and can
# never be silently mixed with an inches-based figure (see units.py).
DIM_OUTSIDE_DIAMETER = "outside_diameter_mm"
DIM_BORE_DIAMETER = "bore_diameter_mm"
DIM_RAISED_FACE_DIAMETER = "raised_face_diameter_mm"
DIM_RAISED_FACE_HEIGHT = "raised_face_height_mm"
# Prompt 3 finding: ASME B16.5 publishes TWO different minimum flange
# thickness figures depending on flange type. These MUST remain two
# distinct canonical names, never merged into one "flange thickness":
DIM_FLANGE_THICKNESS_WELD_NECK = "flange_thickness_weld_neck_mm"
DIM_FLANGE_THICKNESS_OTHER_TYPES = "flange_thickness_other_types_mm"
# Prompt 41 addition: Blind flange minimum thickness is a THIRD distinct
# ASME B16.5 figure - neither the weld-neck "T" nor the shared "other
# types" TJ (slip-on/threaded/socket-weld/lap-joint) - never merged into
# either existing name.
DIM_FLANGE_THICKNESS_BLIND = "flange_thickness_blind_mm"
DIM_BOLT_CIRCLE_DIAMETER = "bolt_circle_diameter_mm"
DIM_BOLT_HOLE_DIAMETER = "bolt_hole_diameter_mm"
DIM_HUB_BASE_DIAMETER = "hub_base_diameter_mm"
DIM_LENGTH_THROUGH_HUB = "length_through_hub_mm"
DIM_CENTRE_TO_END = "centre_to_end_mm"
DIM_END_TO_END = "end_to_end_mm"
DIM_WALL_THICKNESS = "wall_thickness_mm"

# Non-length dimension identities - no unit suffix, and units.py's
# "count"/"designation" pseudo-units must be used for these, never a
# length unit:
DIM_NUM_BOLTS = "num_bolts"
DIM_BOLT_SIZE_DESIGNATION = "bolt_size_designation"

# Mass dimension (e.g. manufacturer-specific cap weight, Prompt 3's CAP_WT
# finding) - kept separate from the _mm length names above:
DIM_MASS = "mass_kg"

# Prompt 7 additions - ASME B16.9 buttweld fittings. DIM_CENTRE_TO_END
# (already existed) is REUSED as-is for every elbow subtype (LR/SR/3D,
# 90/45deg) - the dimension's MEANING doesn't change between subtypes,
# only its value and applicability (fitting_type), so no new elbow-
# specific dimension names were added (Prompt 7 Sec.11: "do not add
# duplicate synonyms"). DIM_END_TO_END (already existed) is reused as-is
# for a reducer's overall face-to-face length, per the source's own note
# ("Length_H is overall face-to-face length, not a per-end dimension").
#
# Tees, however, genuinely have TWO DIFFERENT SIMULTANEOUS measurements
# on the same fitting (run-direction vs branch/outlet-direction centre-
# to-end) that diverge at larger NPS in the real source (confirmed: NPS42
# Run=762mm vs Outlet=711mm) - these need two distinct canonical names,
# not fitting_type-based disambiguation, since both values exist on the
# very same row/fitting at once:
DIM_TEE_RUN_CENTRE_TO_END = "tee_run_centre_to_end_mm"
DIM_TEE_BRANCH_CENTRE_TO_END = "tee_branch_centre_to_end_mm"

# Caps: the source has TWO distinct standard-tabulated lengths (Length_H,
# Length_H1) selected by which side of a wall-thickness threshold the
# actual pipe being capped falls on - genuinely different engineering
# facts, not the same "cap length" repeated, so DIM_END_TO_END/generic
# length is deliberately NOT reused here:
DIM_CAP_LENGTH_STANDARD_WALL = "cap_length_standard_wall_mm"   # source: Length_H_mm (applies below the WT threshold)
DIM_CAP_LENGTH_HEAVY_WALL = "cap_length_heavy_wall_mm"         # source: Length_H1_mm (applies at/above the WT threshold)
DIM_CAP_WALL_THICKNESS_THRESHOLD = "cap_wall_thickness_threshold_mm"  # source: WT_threshold_mm

# ---------------------------------------------------------------------------
# Prompt 8 additions - ASME B16.11 socket-weld dimensions. Socket bore
# depth/diameter and socket wall thickness are each published as a
# max/min PAIR in the source (not a single nominal value) - preserved as
# two distinct canonical facts, never averaged or collapsed to one number.
# DIM_CENTRE_TO_END and DIM_END_TO_END (already existed) are reused as-is
# for the elbow "centre to bottom of socket" and coupling/half-coupling
# laying-length dimensions respectively - the physical role (centre of
# fitting to its terminal reference plane) is the same concept as their
# ASME B16.9 buttweld usage, only the terminal reference itself differs
# (socket bottom vs weld bevel), which is exactly what `fitting_type`
# already exists to distinguish.
# ---------------------------------------------------------------------------
DIM_SOCKET_BORE_DEPTH_MAX = "socket_bore_depth_max_mm"    # source: SocketBoreDepth_B_max_mm
DIM_SOCKET_BORE_DEPTH_MIN = "socket_bore_depth_min_mm"    # source: SocketBoreDepth_B_min_mm
DIM_SOCKET_WALL_MIN_AT_BOTTOM = "socket_wall_min_at_bottom_mm"  # source: J_mm
DIM_SOCKET_BORE_DIAMETER_MAX = "socket_bore_diameter_max_mm"    # source: SocketBoreDia_D_max_mm
DIM_SOCKET_BORE_DIAMETER_MIN = "socket_bore_diameter_min_mm"    # source: SocketBoreDia_D_min_mm
DIM_SOCKET_WALL_THICKNESS_MAX = "socket_wall_thickness_max_mm"  # source: SocketWT_C_max_mm
DIM_SOCKET_WALL_THICKNESS_MIN = "socket_wall_thickness_min_mm"  # source: SocketWT_C_min_mm
DIM_FITTING_BODY_WALL_THICKNESS = "fitting_body_wall_thickness_mm"  # source: BodyWT_G_mm (elbow/tee/cross only)
DIM_CAP_SOCKET_LENGTH = "cap_socket_length_mm"      # source: SocketLength_Q_mm (socket-weld cap only)
DIM_CAP_BODY_DIAMETER = "cap_body_diameter_mm"      # source: CapDia_R_mm (socket-weld cap body OD, NOT pipe OD)

# Prompt 8 additions - MSS SP-97 branch-outlet fittings.
DIM_BRANCH_OUTLET_HEIGHT = "branch_outlet_height_mm"   # source: official MSS SP-97 Table-A1-style height, by run NPS+schedule+config
DIM_OLET_HEIGHT = "olet_height_mm"                     # source: A_height_mm (manufacturer body dims)
DIM_OLET_FACE_TO_FACE = "olet_face_to_face_mm"         # source: B_faceToFace_mm
DIM_OLET_BASE_OUTSIDE_DIAMETER = "olet_base_outside_diameter_mm"  # source: C_baseOD_mm
DIM_OLET_BORE_DIAMETER = "olet_bore_diameter_mm"       # source: D_bore_mm
DIM_OLET_SOCKET_DIAMETER = "olet_socket_diameter_mm"   # source: E_socketDia_mm (sockolet only)

# Nipoflange-specific dimensions (KAFCO manufacturer catalog - see
# adapters/kafco_nipoflange.py). Deliberately NOT reusing
# DIM_OUTSIDE_DIAMETER/DIM_FLANGE_THICKNESS_OTHER_TYPES even though the
# source states "flange dimensions to ANSI B16.5": that claim was not
# independently cross-checked cell-by-cell against the ASME B16.5 table
# ingested elsewhere in this project, so silently aliasing to the ASME
# canonical names would assert a cross-standard equality this adapter
# never verified (same discipline as Prompt 7/8's cross-standard-equality
# rule). Weight reuses the existing generic DIM_MASS - no new name needed.
DIM_NIPOFLANGE_FLANGE_OD = "nipoflange_flange_od_mm"                # source: FlangeOD_A_mm
DIM_NIPOFLANGE_OVERALL_LENGTH = "nipoflange_overall_length_mm"      # source: OverallLength_B_mm - CONSTRUCTION_PARAMETER, purchaser-modifiable per source Note 2
DIM_NIPOFLANGE_FLANGE_THICKNESS = "nipoflange_flange_thickness_mm"  # source: FlangeThk_D_mm (includes RF thickness per source Note 3)

# Prompt 8 additions - EN/DIN buttweld-specific dimensions not already
# covered by a reused ASME name.
DIM_RETURN_180_CENTRE_TO_CENTRE = "return_180_centre_to_centre_mm"  # source: Return180_CtoC_mm
DIM_BEND_RADIUS = "bend_radius_mm"                                  # source: BendRadius_K_mm

DIMENSION_NAMES = frozenset({
    DIM_OUTSIDE_DIAMETER, DIM_BORE_DIAMETER, DIM_RAISED_FACE_DIAMETER,
    DIM_RAISED_FACE_HEIGHT, DIM_FLANGE_THICKNESS_WELD_NECK,
    DIM_FLANGE_THICKNESS_OTHER_TYPES, DIM_FLANGE_THICKNESS_BLIND, DIM_BOLT_CIRCLE_DIAMETER,
    DIM_BOLT_HOLE_DIAMETER, DIM_HUB_BASE_DIAMETER, DIM_LENGTH_THROUGH_HUB,
    DIM_CENTRE_TO_END, DIM_END_TO_END, DIM_WALL_THICKNESS,
    DIM_NUM_BOLTS, DIM_BOLT_SIZE_DESIGNATION, DIM_MASS,
    DIM_TEE_RUN_CENTRE_TO_END, DIM_TEE_BRANCH_CENTRE_TO_END,
    DIM_CAP_LENGTH_STANDARD_WALL, DIM_CAP_LENGTH_HEAVY_WALL, DIM_CAP_WALL_THICKNESS_THRESHOLD,
    DIM_SOCKET_BORE_DEPTH_MAX, DIM_SOCKET_BORE_DEPTH_MIN, DIM_SOCKET_WALL_MIN_AT_BOTTOM,
    DIM_SOCKET_BORE_DIAMETER_MAX, DIM_SOCKET_BORE_DIAMETER_MIN,
    DIM_SOCKET_WALL_THICKNESS_MAX, DIM_SOCKET_WALL_THICKNESS_MIN,
    DIM_FITTING_BODY_WALL_THICKNESS, DIM_CAP_SOCKET_LENGTH, DIM_CAP_BODY_DIAMETER,
    DIM_BRANCH_OUTLET_HEIGHT, DIM_OLET_HEIGHT, DIM_OLET_FACE_TO_FACE,
    DIM_OLET_BASE_OUTSIDE_DIAMETER, DIM_OLET_BORE_DIAMETER, DIM_OLET_SOCKET_DIAMETER,
    DIM_RETURN_180_CENTRE_TO_CENTRE, DIM_BEND_RADIUS,
    DIM_NIPOFLANGE_FLANGE_OD, DIM_NIPOFLANGE_OVERALL_LENGTH, DIM_NIPOFLANGE_FLANGE_THICKNESS,
})

NON_LENGTH_DIMENSION_NAMES = frozenset({DIM_NUM_BOLTS, DIM_BOLT_SIZE_DESIGNATION})

# ---------------------------------------------------------------------------
# 6. Compatibility map: canonical name -> known existing legacy field(s)
# ---------------------------------------------------------------------------
# Documentation only - used by tests/docs to show the relationship, and by
# future migration prompts. NOT executed as an automatic renaming/ingest
# path in this prompt. Populated only from fields actually confirmed in
# Prompts 1-3; left as None rather than guessed where not confirmed.
LEGACY_FIELD_MAP = {
    DIM_OUTSIDE_DIAMETER: {
        "python_dimension_library": "OD_mm",
        "js_crm": "FLG[cls][nps][0] (inches, requires *25.4)",
    },
    DIM_FLANGE_THICKNESS_WELD_NECK: {
        "python_dimension_library": "Thickness_WeldNeck_mm",
        "js_crm": None,  # JS does not carry this distinct figure (Prompt 3 Sec.3)
    },
    DIM_FLANGE_THICKNESS_OTHER_TYPES: {
        "python_dimension_library": "Thickness_SlipOn_mm / Thickness_LapJoint_mm / "
                                     "Thickness_Threaded_mm / Thickness_SocketWeld_mm "
                                     "(Prompt 41 - four applicability-scoped columns, one shared "
                                     "canonical dimension name, per the pre-existing Prompt 3 design)",
        "js_crm": "FLG[cls][nps][1] (inches, requires *25.4) - verified = Texas Flange 'TJ' column",
    },
    DIM_FLANGE_THICKNESS_BLIND: {
        "python_dimension_library": "Thickness_Blind_mm (Prompt 41)",
        "js_crm": None,
    },
    DIM_BOLT_CIRCLE_DIAMETER: {"python_dimension_library": "BoltCircle_mm", "js_crm": "FLG[cls][nps][2]*25.4"},
    DIM_BOLT_HOLE_DIAMETER: {"python_dimension_library": "BoltHoleDia_mm", "js_crm": "BOLT_HOLE[cls][nps]*25.4"},
    DIM_HUB_BASE_DIAMETER: {
        "python_dimension_library": "HubBaseDiameter_mm (Prompt 42) - shared by weld_neck and "
                                     "long_weld_neck (identical per ASME B16.5's own LWN rule; "
                                     "flange_type=None, matching the OD/bolt-circle sharing pattern)",
        "js_crm": "HUB_DIM[cls][nps][0]*25.4 - CRM's legacy table; values match to <0.01in on every "
                  "spot-checked NPS/class (independent 3rd confirmation of X, no conflict for X)",
    },
    DIM_LENGTH_THROUGH_HUB: {
        "python_dimension_library": "LengthThroughHub_WeldNeck_mm (flange_type=weld_neck) / "
                                     "LengthThroughHub_LongWeldNeck_mm (flange_type=long_weld_neck, "
                                     "fixed 229/305mm override, Prompt 42) - see "
                                     "_ingest_hub_dimensions.py for the disclosed Y-convention "
                                     "conflict with the CRM's own HUB_DIM table (RF-height-inclusion "
                                     "difference, ~1.5mm, resolved in favor of the flat-plane "
                                     "convention used by two independently cross-verified sources)",
        "js_crm": "HUB_DIM[cls][nps][1]*25.4 - CRM's legacy table; ~1.5mm higher than the value "
                  "ingested here for the same NPS/class - see conflict disclosure above",
    },
    DIM_RAISED_FACE_DIAMETER: {"python_dimension_library": "RaisedFace_mm (JIS/EN only)", "js_crm": "RF_BORE[cls][nps]"},
    DIM_RAISED_FACE_HEIGHT: {"python_dimension_library": None, "js_crm": "rfHeightMM(cls) - derived rule, not tabulated"},
    DIM_WALL_THICKNESS: {"python_dimension_library": "WallThickness_mm", "js_crm": "PIPE_WT[sch][nps]"},
    DIM_CENTRE_TO_END: {"python_dimension_library": "CtoE_mm / RunCtoE_mm / OutletCtoE_mm", "js_crm": None},
    DIM_END_TO_END: {"python_dimension_library": "Length_mm (caps)", "js_crm": "CAP_LEN[nps] / REDUCER_LEN[nps]"},
    DIM_BOLT_SIZE_DESIGNATION: {"python_dimension_library": "BoltSize_in / BoltSize", "js_crm": None},
    DIM_MASS: {"python_dimension_library": None, "js_crm": "CAP_WT[sch][nps] (Hackney Ladish manufacturer data)"},
}
