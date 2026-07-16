# -*- coding: utf-8 -*-
"""
kgpe.geometry_spec.profile
==============================
Prompt 11 Sec.9-12: `GeometryProfile` - declares, per product family/
subtype-group, which canonical dimensions are required/optional to build
engineering geometry, and whether manufacturer-specific data is permitted
or required.

Every profile below was built from LIVE inspection of the canonical
registry (via CanonicalReader.available_dimensions()/discover(), a fresh
build_canonical_reader()) and of the existing kgpe/rules/*.py and
kgpe/dimension_library.py implementations, carried out during Prompt 11
authoring - not invented. See CANONICAL_DATA_CONTRACT.md's Prompt 11
section for the raw findings each profile is based on, and
kgpe/geometry_spec/coverage.py's construction-rule register for the
individual gaps found.

Profiles NEVER read source JSON, import adapters, call
dimension_library.py, choose standards, or normalize raw input (Sec.12) -
they are pure declarative data plus a small `applies_to()` matcher.
"""
from dataclasses import dataclass, field
from typing import Optional, FrozenSet

from ..contract import vocabulary as VOC

PROFILE_SCHEMA_VERSION = "geometry-profile-schema-2026.07.15"

MFR_NOT_APPLICABLE = "NOT_APPLICABLE"
MFR_OPTIONAL = "OPTIONAL"
MFR_REQUIRED = "REQUIRED"


@dataclass(frozen=True)
class GeometryProfile:
    profile_id: str
    version: str
    product_family: str
    # None = applies regardless of subtype (e.g. pipe); a frozenset means
    # "applies to any of these canonical subtype/fitting_type identities".
    subtypes: Optional[FrozenSet[str]]
    required_dimensions: FrozenSet[str]
    optional_dimensions: FrozenSet[str] = field(default_factory=frozenset)
    # Sec.11: dimensions that are required in principle but for which no
    # authoritative canonical fact exists for at least one covered
    # standard - documented here as a candidate for a FUTURE approved
    # construction rule, never silently treated as resolved today.
    construction_derivable_dimensions: FrozenSet[str] = field(default_factory=frozenset)
    manufacturer_specific: str = MFR_NOT_APPLICABLE
    notes: str = ""

    def applies_to(self, product_family, subtype):
        if product_family != self.product_family:
            return False
        if self.subtypes is None:
            return True
        return subtype in self.subtypes

    def to_dict(self):
        return {
            "profile_id": self.profile_id, "version": self.version,
            "product_family": self.product_family,
            "subtypes": sorted(self.subtypes) if self.subtypes is not None else None,
            "required_dimensions": sorted(self.required_dimensions),
            "optional_dimensions": sorted(self.optional_dimensions),
            "construction_derivable_dimensions": sorted(self.construction_derivable_dimensions),
            "manufacturer_specific": self.manufacturer_specific,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Pipe. Confirmed live: reader.available_dimensions(product_family="pipe")
# across ALL 6 pipe standards -> exactly {outside_diameter_mm,
# wall_thickness_mm}. bore_diameter_mm has ZERO facts anywhere for pipe -
# dimension_library.py's legacy get_pipe() derives it as OD-2*WallThickness,
# a legacy heuristic, not an approved canonical construction rule.
# ---------------------------------------------------------------------------
PROFILE_PIPE = GeometryProfile(
    profile_id="pipe", version="1",
    product_family=VOC.PRODUCT_FAMILY_PIPE, subtypes=None,
    required_dimensions=frozenset({VOC.DIM_OUTSIDE_DIAMETER, VOC.DIM_WALL_THICKNESS}),
    construction_derivable_dimensions=frozenset({VOC.DIM_BORE_DIAMETER}),
    notes="bore_diameter_mm has no canonical fact at all for any pipe standard; "
          "dimension_library.get_pipe() derives it as OD-2*WallThickness, a legacy "
          "heuristic (Sec.11), not an approved Phase-3 construction rule.",
)

# ---------------------------------------------------------------------------
# Flange (weld_neck - the only flange_type this project's canonical data
# populates). Confirmed live: bore_diameter_mm and raised_face_diameter_mm
# are VERIFIED_AUTHORITATIVE for JIS_B2220 only (80 facts each) - ASME_B16.5
# and EN_1092-1 publish neither. hub_base_diameter_mm/length_through_hub_mm
# have ZERO facts for any flange standard at all.
#
# Prompt 14 Sec.14-16 fix (v1->v2): bore_diameter_mm was originally listed
# in BOTH required_dimensions and construction_derivable_dimensions - this
# made GEOMETRY_READY structurally unreachable for ASME_B16.5/EN_1092-1
# (bore never resolves directly there; see kgpe.geometry.compiler's
# required-dimension gate, which does not consult
# construction_derivable_dimensions at all) - a genuine blocking defect of
# exactly the same shape Prompt 13 Sec.20 fixed for the buttweld reducer's
# outside_diameter_mm. Fixed the same way: bore_diameter_mm removed from
# required_dimensions, added to optional_dimensions (so JIS_B2220's direct
# authoritative bore is still captured when present) and retained in
# construction_derivable_dimensions (so ASME_B16.5's cross-family
# pipe-schedule derivation - kgpe.geometry.cross_family.
# FlangeBoreViaPipeScheduleRule, resolved externally and threaded through
# GeometryKernel.generate()'s product_kwargs, exactly like Prompt 13's
# wall-context/reducer-OD pattern - still applies at the kernel layer).
# EN_1092-1's bore remains genuinely UNAVAILABLE this prompt (no DN-based
# cross-family rule has been built/approved yet - Prompt 14 Sec.44 scope
# discipline) - flanges for EN_1092-1 generate as SOLID_EXTERNAL_ENVELOPE
# (no bore modeled), never fabricated.
# ---------------------------------------------------------------------------
PROFILE_FLANGE_WELD_NECK = GeometryProfile(
    profile_id="flange_weld_neck", version="2",
    product_family=VOC.PRODUCT_FAMILY_FLANGE, subtypes=frozenset({"weld_neck"}),
    required_dimensions=frozenset({
        VOC.DIM_OUTSIDE_DIAMETER, VOC.DIM_FLANGE_THICKNESS_WELD_NECK,
        VOC.DIM_BOLT_CIRCLE_DIAMETER, VOC.DIM_BOLT_HOLE_DIAMETER,
        VOC.DIM_NUM_BOLTS, VOC.DIM_BOLT_SIZE_DESIGNATION,
    }),
    optional_dimensions=frozenset({VOC.DIM_RAISED_FACE_DIAMETER, VOC.DIM_BORE_DIAMETER}),
    construction_derivable_dimensions=frozenset(
        {VOC.DIM_BORE_DIAMETER, VOC.DIM_HUB_BASE_DIAMETER, VOC.DIM_LENGTH_THROUGH_HUB}),
    notes="v2 (Prompt 14): bore_diameter_mm no longer required at profile-compilation stage - "
          "resolved directly (JIS_B2220, now optional) or via cross-family construction rule "
          "at the geometry-kernel layer (ASME_B16.5, kgpe.geometry.cross_family."
          "FlangeBoreViaPipeScheduleRule) or left unmodeled (EN_1092-1, SOLID_EXTERNAL_ENVELOPE). "
          "raised_face_diameter_mm is JIS_B2220-only, hence optional not required - and even where "
          "present, raised-face HEIGHT has zero production facts for any standard, so no raised-"
          "face geometry is generated this prompt (diameter-only partial feature, Prompt 14 "
          "Sec.19). hub_base_diameter_mm/length_through_hub_mm have NO facts at all for any "
          "flange standard - hub/neck taper is not modeled, matching rules/flange.py's own "
          "documented v1 scope limitation.",
)


# ---------------------------------------------------------------------------
# Buttweld elbows (any radius/angle variant, ASME/EN/JIS). Confirmed live:
# outside_diameter_mm is a SHARED cross-subtype canonical identity at
# ASME_B16.9/EN_10253 (fitting_type=None on the underlying facts - resolved
# via kgpe.resolver.engine's own relaxed-criteria fallback); centre_to_end_mm
# is subtype-scoped and resolves per elbow variant.
# ---------------------------------------------------------------------------
_ELBOW_SUBTYPES = frozenset({
    VOC.FITTING_TYPE_ELBOW_90_LR, VOC.FITTING_TYPE_ELBOW_45_LR, VOC.FITTING_TYPE_ELBOW_90_3D,
    VOC.FITTING_TYPE_ELBOW_45_3D, VOC.FITTING_TYPE_ELBOW_90_SR,
    VOC.FITTING_TYPE_ELBOW_90_EN, VOC.FITTING_TYPE_ELBOW_90_LR_JIS, VOC.FITTING_TYPE_ELBOW_45_JIS,
})
PROFILE_BUTTWELD_ELBOW = GeometryProfile(
    profile_id="buttweld_elbow", version="1",
    product_family=VOC.PRODUCT_FAMILY_BUTTWELD_FITTING, subtypes=_ELBOW_SUBTYPES,
    required_dimensions=frozenset({VOC.DIM_OUTSIDE_DIAMETER, VOC.DIM_CENTRE_TO_END}),
    optional_dimensions=frozenset({VOC.DIM_WALL_THICKNESS}),
    notes="outside_diameter_mm is confirmed live as a shared cross-subtype identity at "
          "ASME_B16.9 (fitting_type=None) - resolvable only via the resolver's relaxed-"
          "criteria fallback, not a direct subtype-scoped query. wall_thickness_mm is only "
          "published alongside EN_10253 elbow facts and is optional, matching "
          "rules/buttweld.py's own dims.get('WallThickness_mm') (defaults to None).",
)

PROFILE_BUTTWELD_TEE_EQUAL = GeometryProfile(
    profile_id="buttweld_tee_equal", version="1",
    product_family=VOC.PRODUCT_FAMILY_BUTTWELD_FITTING,
    subtypes=frozenset({VOC.FITTING_TYPE_TEE_EQUAL, "tee_equal_en", "tee_equal_jis"}),
    required_dimensions=frozenset({
        VOC.DIM_OUTSIDE_DIAMETER, VOC.DIM_TEE_RUN_CENTRE_TO_END, VOC.DIM_TEE_BRANCH_CENTRE_TO_END,
    }),
    notes="Confirmed live for ASME_B16.9 tee_equal: outside_diameter_mm (shared cross-subtype "
          "identity) + tee_run_centre_to_end_mm + tee_branch_centre_to_end_mm - matches "
          "rules/buttweld.py's _tee() exactly (RunCtoE_mm/OutletCtoE_mm + OD).",
)

PROFILE_BUTTWELD_CAP = GeometryProfile(
    profile_id="buttweld_cap", version="1",
    product_family=VOC.PRODUCT_FAMILY_BUTTWELD_FITTING, subtypes=frozenset({VOC.FITTING_TYPE_CAP}),
    required_dimensions=frozenset({VOC.DIM_OUTSIDE_DIAMETER, VOC.DIM_CAP_LENGTH_STANDARD_WALL}),
    optional_dimensions=frozenset({VOC.DIM_CAP_LENGTH_HEAVY_WALL, VOC.DIM_CAP_WALL_THICKNESS_THRESHOLD}),
    notes="Confirmed live for ASME_B16.9 cap: outside_diameter_mm (shared cross-subtype identity, "
          "same relaxed-criteria mechanism as buttweld_elbow above - a fitting_type='cap'-scoped "
          "query alone does not find it) + cap_length_standard_wall_mm + cap_length_heavy_wall_mm "
          "+ cap_wall_thickness_threshold_mm, all VERIFIED_AUTHORITATIVE. "
          "Existing rules/buttweld.py._cap() ALWAYS uses Length_H_mm (standard-wall) unconditionally "
          "- it never compares the mating pipe's actual wall thickness against the published "
          "threshold to decide between H and H1 (see construction-rule register, coverage.py) - "
          "a legacy simplification, faithfully carried into this profile's required set. "
          "cap_en/cap_jis dimension names were not separately confirmed this session - left out "
          "of this profile's subtype set rather than guessed (Sec.21).",
)


# ---------------------------------------------------------------------------
# Buttweld reducer. Confirmed live: end_to_end_mm IS resolvable via
# large_end_nps/small_end_nps (the resolver's reducer-role query path).
# outside_diameter_mm is NOT - it only resolves via plain 'nps', which the
# reducer role never populates in base_criteria - a genuine gap between
# the resolver's reducer-role path and this dimension's shared identity
# (confirmed: read(outside_diameter_mm, large_end_nps='6') -> NO_MATCH;
# read(outside_diameter_mm, nps='6') -> EXACT_MATCH).
# ---------------------------------------------------------------------------
PROFILE_BUTTWELD_REDUCER = GeometryProfile(
    profile_id="buttweld_reducer", version="2",
    product_family=VOC.PRODUCT_FAMILY_BUTTWELD_FITTING,
    subtypes=frozenset({VOC.FITTING_TYPE_REDUCER_CONCENTRIC, VOC.FITTING_TYPE_REDUCER_ECCENTRIC}),
    required_dimensions=frozenset({VOC.DIM_END_TO_END}),
    construction_derivable_dimensions=frozenset({VOC.DIM_OUTSIDE_DIAMETER}),
    notes="Prompt 13 Sec.20 fix (v1->v2, a genuine blocking defect, not a routine edit): "
          "end_to_end_mm resolves cleanly via the reducer role (large_end_nps/small_end_nps) and "
          "remains required here. outside_diameter_mm does NOT resolve via this profile's normal "
          "per-dimension resolve() path at all - it is only queryable via the plain 'nps' field "
          "(the same shared cross-subtype identity elbows/tees/caps use), which the resolver's "
          "reducer-role base_criteria never populates - so listing it as REQUIRED here made "
          "GEOMETRY_READY structurally unreachable for every reducer request (v1's genuine "
          "blocking defect). v2 removes it from required_dimensions (matching the existing "
          "pipe-profile pattern, where bore_diameter_mm is likewise construction_derivable, not "
          "required) - kgpe.geometry.reducer_rules.ReducerPerEndOutsideDiameterRule now resolves "
          "large-end and small-end OD independently via TWO separate resolver.resolve() calls "
          "(nps=large_end_size, nps=small_end_size) at the GEOMETRY layer (Prompt 13), never "
          "through this compiler's single-dimension-bundle path. This is the only Prompt 11 file "
          "modification made in Prompt 13, made exactly because it structurally blocked geometry "
          "generation with no other addable-only fix available (Sec.8's 'smallest additive "
          "downstream extension' principle, applied here since the profile's OWN required-set "
          "was the blocker, not a downstream layer).",
)

# ---------------------------------------------------------------------------
# Socketweld elbow/tee/cross. Confirmed live and via Prompt 9's own curated
# gap: ASME_B16.11 itself does not publish outside diameter for socket-weld
# fittings at all (the mating pipe's OD, a DIFFERENT product_family/
# standard, is the correct source) - zero outside_diameter_mm facts under
# product_family='socketweld_fitting' anywhere.
# ---------------------------------------------------------------------------
_SOCKETWELD_BODY_SUBTYPES = frozenset({
    VOC.FITTING_TYPE_ELBOW_90_SW, VOC.FITTING_TYPE_ELBOW_45_SW,
    VOC.FITTING_TYPE_TEE_SW, VOC.FITTING_TYPE_CROSS_SW,
})
PROFILE_SOCKETWELD_ELBOW_TEE = GeometryProfile(
    profile_id="socketweld_elbow_tee", version="1",
    product_family=VOC.PRODUCT_FAMILY_SOCKETWELD_FITTING, subtypes=_SOCKETWELD_BODY_SUBTYPES,
    required_dimensions=frozenset({
        VOC.DIM_OUTSIDE_DIAMETER, VOC.DIM_CENTRE_TO_END, VOC.DIM_FITTING_BODY_WALL_THICKNESS,
        VOC.DIM_SOCKET_BORE_DIAMETER_MIN, VOC.DIM_SOCKET_BORE_DEPTH_MIN,
    }),
    optional_dimensions=frozenset({
        VOC.DIM_SOCKET_BORE_DIAMETER_MAX, VOC.DIM_SOCKET_BORE_DEPTH_MAX,
        VOC.DIM_SOCKET_WALL_THICKNESS_MIN, VOC.DIM_SOCKET_WALL_THICKNESS_MAX,
    }),
    construction_derivable_dimensions=frozenset({VOC.DIM_OUTSIDE_DIAMETER}),
    notes="ASME_B16.11 publishes socket bore/wall/depth and fitting_body_wall_thickness_mm, but "
          "NO outside_diameter_mm at all under product_family='socketweld_fitting' - this is a "
          "curated, documented source gap already established in Prompt 9 "
          "(data_layer_audit._CURATED_SOURCE_GAPS): the body OD is genuinely the mating pipe's "
          "OD (a cross-family lookup into ASME_B36 pipe data by NPS), not an ASME_B16.11 fact. "
          "Cross-family dimension resolution is not implemented by kgpe.resolver.engine - "
          "registered as a construction-rule requirement for Prompt 12.",
)


# ---------------------------------------------------------------------------
# Socketweld cap. Confirmed live: cap_body_diameter_mm (the cap's own body
# OD - a genuinely different, self-contained dimension from the mating-pipe
# OD problem above) + cap_socket_length_mm + socket_bore_depth_*_mm all
# VERIFIED_AUTHORITATIVE. This is engineering-data-ready even though
# generator.py has no 'socketweld_fitting' _DISPATCH entry at all (Sec.9's
# forward-looking geometry-input contract is independent of whether the
# CURRENT generator can consume it yet - that is Prompt 12's job).
# ---------------------------------------------------------------------------
PROFILE_SOCKETWELD_CAP = GeometryProfile(
    profile_id="socketweld_cap", version="1",
    product_family=VOC.PRODUCT_FAMILY_SOCKETWELD_FITTING, subtypes=frozenset({VOC.FITTING_TYPE_CAP_SW}),
    required_dimensions=frozenset({
        VOC.DIM_CAP_BODY_DIAMETER, VOC.DIM_CAP_SOCKET_LENGTH, VOC.DIM_SOCKET_BORE_DEPTH_MIN,
    }),
    optional_dimensions=frozenset({VOC.DIM_SOCKET_BORE_DEPTH_MAX}),
    notes="cap_body_diameter_mm is the cap's OWN body OD (source: CapDia_R_mm) - unlike "
          "elbow/tee/cross, socketweld caps do not need the mating pipe's OD, so this profile "
          "is fully authoritative-data-ready with no cross-family gap.",
)

# ---------------------------------------------------------------------------
# Olet body (weldolet/sockolet/threadolet manufacturer body dimensions).
# Confirmed live: the ONLY manufacturer profile present anywhere is
# 'Bonney Forge', and these body dims (height/face-to-face/base OD/bore
# [+socket dia for sockolet]) exist ONLY as VERIFIED_MANUFACTURER_SPECIFIC
# facts - no standard-text-authoritative alternative (matches Prompt 9's
# GAP_MANUFACTURER_SPECIFIC_ONLY finding exactly).
# ---------------------------------------------------------------------------
PROFILE_OLET_BODY = GeometryProfile(
    profile_id="olet_body", version="1",
    product_family=VOC.PRODUCT_FAMILY_OLET,
    subtypes=frozenset({VOC.FITTING_TYPE_WELDOLET, VOC.FITTING_TYPE_SOCKOLET, VOC.FITTING_TYPE_THREADOLET}),
    required_dimensions=frozenset({
        VOC.DIM_OLET_HEIGHT, VOC.DIM_OLET_FACE_TO_FACE, VOC.DIM_OLET_BASE_OUTSIDE_DIAMETER,
        VOC.DIM_OLET_BORE_DIAMETER,
    }),
    optional_dimensions=frozenset({VOC.DIM_OLET_SOCKET_DIAMETER}),
    manufacturer_specific=MFR_REQUIRED,
    notes="Every required dimension here exists ONLY as VERIFIED_MANUFACTURER_SPECIFIC "
          "(Bonney Forge) - no authoritative alternative in the source at all. Resolving without "
          "manufacturer_profile='Bonney Forge' + allow_manufacturer_specific=True returns "
          "MANUFACTURER_CONTEXT_REQUIRED, never a silent default (Sec.13/23).",
)

# ---------------------------------------------------------------------------
# Olet reinforcement/outlet height only (MSS SP-97's own official Table-A1-
# style figure, by run NPS+schedule+config) - VERIFIED_AUTHORITATIVE, not
# manufacturer-specific, but INSUFFICIENT ALONE to build a full olet body
# solid (no OD/bore/face-to-face). Kept as its own thin profile rather than
# folded into olet_body, since it is a genuinely different, authoritative-
# only engineering fact (Sec.21 - do not pretend partial coverage is full
# readiness).
# ---------------------------------------------------------------------------
PROFILE_OLET_OUTLET_HEIGHT = GeometryProfile(
    profile_id="olet_outlet_height", version="1",
    product_family=VOC.PRODUCT_FAMILY_OLET,
    subtypes=frozenset({VOC.FITTING_TYPE_WELDOLET_FULL, VOC.FITTING_TYPE_WELDOLET_REDUCING}),
    required_dimensions=frozenset({VOC.DIM_BRANCH_OUTLET_HEIGHT}),
    notes="branch_outlet_height_mm is VERIFIED_AUTHORITATIVE (official MSS SP-97 table, not "
          "manufacturer-specific) - GEOMETRY_READY for this ONE dimension, but this profile "
          "deliberately does not claim full olet-body readiness: no OD/bore/face-to-face exist "
          "under weldolet_full/weldolet_reducing at all (those only exist under the separate "
          "weldolet/sockolet/threadolet manufacturer-specific subtypes above).",
)

PROFILE_REGISTRY = [
    PROFILE_PIPE, PROFILE_FLANGE_WELD_NECK, PROFILE_BUTTWELD_ELBOW, PROFILE_BUTTWELD_TEE_EQUAL,
    PROFILE_BUTTWELD_CAP, PROFILE_BUTTWELD_REDUCER, PROFILE_SOCKETWELD_ELBOW_TEE,
    PROFILE_SOCKETWELD_CAP, PROFILE_OLET_BODY, PROFILE_OLET_OUTLET_HEIGHT,
]


def find_profile(product_family, subtype):
    """Sec.10/13: deterministic profile lookup - never a fuzzy match, never
    a default. Returns None (GEOMETRY_PROFILE_UNAVAILABLE) if no profile
    applies to this exact (product_family, subtype) pair."""
    for profile in PROFILE_REGISTRY:
        if profile.applies_to(product_family, subtype):
            return profile
    return None


def all_profiles():
    return list(PROFILE_REGISTRY)
