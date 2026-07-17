# -*- coding: utf-8 -*-
"""
kgpe.resolver.aliases
=========================
Sec.10-11: a small, explicit, deterministic, inspectable nomenclature
alias layer - kept entirely separate from canonical data facts and from
the resolution engine's control flow (no aliases buried inside scattered
`if` chains).

Only common, unambiguous aliases needed to support KGPE's ACTUAL migrated
vocabulary are included - not hundreds of speculative variants, and never
a fuzzy/edit-distance match. An input that isn't a key in these tables
(after simple case/whitespace normalization) is UNKNOWN and must fail
explicitly - see `kgpe.resolver.engine`.
"""
from ..contract import vocabulary as VOC

# ---------------------------------------------------------------------------
# Product-family aliases
# ---------------------------------------------------------------------------
PRODUCT_FAMILY_ALIASES = {
    "FLANGE": VOC.PRODUCT_FAMILY_FLANGE, "FLANGES": VOC.PRODUCT_FAMILY_FLANGE,
    "PIPE": VOC.PRODUCT_FAMILY_PIPE, "PIPES": VOC.PRODUCT_FAMILY_PIPE,
    "BUTTWELD": VOC.PRODUCT_FAMILY_BUTTWELD_FITTING, "BUTTWELD_FITTING": VOC.PRODUCT_FAMILY_BUTTWELD_FITTING,
    "BUTT WELD": VOC.PRODUCT_FAMILY_BUTTWELD_FITTING, "BUTT-WELD": VOC.PRODUCT_FAMILY_BUTTWELD_FITTING,
    "SOCKETWELD": VOC.PRODUCT_FAMILY_SOCKETWELD_FITTING, "SOCKETWELD_FITTING": VOC.PRODUCT_FAMILY_SOCKETWELD_FITTING,
    "SOCKET WELD": VOC.PRODUCT_FAMILY_SOCKETWELD_FITTING, "SOCKET-WELD": VOC.PRODUCT_FAMILY_SOCKETWELD_FITTING,
    "OLET": VOC.PRODUCT_FAMILY_OLET, "OLETS": VOC.PRODUCT_FAMILY_OLET,
    "BRANCH_OUTLET": VOC.PRODUCT_FAMILY_OLET, "BRANCH OUTLET": VOC.PRODUCT_FAMILY_OLET,
}

# ---------------------------------------------------------------------------
# Standard aliases - only forms this project's own 11 migrated sources
# actually use. Canonical values themselves are always accepted as-is too
# (checked separately in engine.py against the live registry, not here).
# ---------------------------------------------------------------------------
STANDARD_ALIASES = {
    "ASME B16.5": "ASME_B16.5", "ASME_B16.5": "ASME_B16.5", "B16.5": "ASME_B16.5",
    "ASME B16.9": "ASME_B16.9", "ASME_B16.9": "ASME_B16.9", "B16.9": "ASME_B16.9",
    "ASME B16.11": "ASME_B16.11", "ASME_B16.11": "ASME_B16.11", "B16.11": "ASME_B16.11",
    "ASME B36.10M": "ASME_B36.10M", "ASME_B36.10M": "ASME_B36.10M", "B36.10M": "ASME_B36.10M", "B36.10": "ASME_B36.10M",
    "ASME B36.19M": "ASME_B36.19M", "ASME_B36.19M": "ASME_B36.19M", "B36.19M": "ASME_B36.19M", "B36.19": "ASME_B36.19M",
    "JIS B2220": "JIS_B2220", "JIS_B2220": "JIS_B2220",
    "JIS B2311": "JIS_B2311_2312", "JIS B2312": "JIS_B2311_2312", "JIS B2311/2312": "JIS_B2311_2312",
    "JIS_B2311_2312": "JIS_B2311_2312",
    "JIS G3452": "JIS_G3452", "JIS_G3452": "JIS_G3452", "SGP": "JIS_G3452",
    "JIS G3454": "JIS_G3454", "JIS_G3454": "JIS_G3454", "STPG": "JIS_G3454",
    "JIS G3459": "JIS_G3459", "JIS_G3459": "JIS_G3459", "SUS": "JIS_G3459",
    "EN 1092-1": "EN_1092-1", "EN1092-1": "EN_1092-1", "EN_1092-1": "EN_1092-1", "DIN EN 1092-1": "EN_1092-1",
    "EN 10216": "EN_10216_10217", "EN 10217": "EN_10216_10217", "EN 10216/10217": "EN_10216_10217",
    "EN_10216_10217": "EN_10216_10217", "DIN EN10216-10217": "EN_10216_10217",
    "EN 10253": "EN_10253", "EN_10253": "EN_10253", "DIN EN10253": "EN_10253",
    "MSS SP-97": "MSS_SP97", "MSS SP97": "MSS_SP97", "MSS_SP97": "MSS_SP97", "SP-97": "MSS_SP97",
}


# ---------------------------------------------------------------------------
# Subtype aliases - scoped per product_family (the same word can mean a
# different canonical subtype in a different family, e.g. "cap" exists
# under both buttweld_fitting and socketweld_fitting with distinct
# canonical fitting_type values - scoping prevents any cross-family
# collision).
# ---------------------------------------------------------------------------
FLANGE_SUBTYPE_ALIASES = {
    "WN": "weld_neck", "WELD NECK": "weld_neck", "WELD-NECK": "weld_neck", "WELDNECK": "weld_neck",
    "WELD_NECK": "weld_neck",
    # Prompt 41 additions.
    "SO": "slip_on", "SLIP ON": "slip_on", "SLIP-ON": "slip_on", "SLIPON": "slip_on",
    "SLIP_ON": "slip_on",
    "TH": "threaded", "THD": "threaded", "THREADED": "threaded", "SCREWED": "threaded",
    "SW": "socket_weld", "SOCKET WELD": "socket_weld", "SOCKET-WELD": "socket_weld",
    "SOCKETWELD": "socket_weld", "SOCKET_WELD": "socket_weld",
    "LJ": "lap_joint", "LAP JOINT": "lap_joint", "LAP-JOINT": "lap_joint", "LAPJOINT": "lap_joint",
    "LAP_JOINT": "lap_joint",
    "BL": "blind", "BLIND": "blind", "BLRF": "blind", "BLIND FLANGE": "blind",
}

BUTTWELD_SUBTYPE_ALIASES = {
    "ELBOW 90": VOC.FITTING_TYPE_ELBOW_90_LR, "ELBOW_90": VOC.FITTING_TYPE_ELBOW_90_LR,
    "90 ELBOW": VOC.FITTING_TYPE_ELBOW_90_LR, "ELBOW90": VOC.FITTING_TYPE_ELBOW_90_LR,
    "ELBOW 90 LR": VOC.FITTING_TYPE_ELBOW_90_LR, "LR ELBOW": VOC.FITTING_TYPE_ELBOW_90_LR,
    "ELBOW 45": VOC.FITTING_TYPE_ELBOW_45_LR, "ELBOW_45": VOC.FITTING_TYPE_ELBOW_45_LR,
    "45 ELBOW": VOC.FITTING_TYPE_ELBOW_45_LR,
    "TEE": VOC.FITTING_TYPE_TEE_EQUAL, "EQUAL TEE": VOC.FITTING_TYPE_TEE_EQUAL,
    "CAP": VOC.FITTING_TYPE_CAP,
    "REDUCER": VOC.FITTING_TYPE_REDUCER_CONCENTRIC, "CONCENTRIC REDUCER": VOC.FITTING_TYPE_REDUCER_CONCENTRIC,
    "ECCENTRIC REDUCER": VOC.FITTING_TYPE_REDUCER_ECCENTRIC,
}

SOCKETWELD_SUBTYPE_ALIASES = {
    "ELBOW 90": VOC.FITTING_TYPE_ELBOW_90_SW, "SW ELBOW 90": VOC.FITTING_TYPE_ELBOW_90_SW,
    "ELBOW 45": VOC.FITTING_TYPE_ELBOW_45_SW,
    "TEE": VOC.FITTING_TYPE_TEE_SW, "CROSS": VOC.FITTING_TYPE_CROSS_SW,
    "COUPLING": VOC.FITTING_TYPE_COUPLING_SW, "HALF COUPLING": VOC.FITTING_TYPE_HALF_COUPLING_SW,
    "CAP": VOC.FITTING_TYPE_CAP_SW,
}

OLET_SUBTYPE_ALIASES = {
    "WELDOLET": VOC.FITTING_TYPE_WELDOLET, "SOCKOLET": VOC.FITTING_TYPE_SOCKOLET,
    "THREADOLET": VOC.FITTING_TYPE_THREADOLET,
    "WELDOLET REDUCING": VOC.FITTING_TYPE_WELDOLET_REDUCING, "WELDOLET FULL": VOC.FITTING_TYPE_WELDOLET_FULL,
}

_SUBTYPE_ALIASES_BY_FAMILY = {
    VOC.PRODUCT_FAMILY_FLANGE: FLANGE_SUBTYPE_ALIASES,
    VOC.PRODUCT_FAMILY_BUTTWELD_FITTING: BUTTWELD_SUBTYPE_ALIASES,
    VOC.PRODUCT_FAMILY_SOCKETWELD_FITTING: SOCKETWELD_SUBTYPE_ALIASES,
    VOC.PRODUCT_FAMILY_OLET: OLET_SUBTYPE_ALIASES,
}


def _normalize_key(raw):
    return str(raw).strip().upper()


def normalize_product_family_alias(raw):
    """Returns the canonical product_family string, or None if `raw` is
    None. Raises KeyError (caller decides how to classify) if `raw` is
    given but not a known alias/canonical value - never guesses."""
    if raw is None:
        return None
    key = _normalize_key(raw)
    if key in PRODUCT_FAMILY_ALIASES:
        return PRODUCT_FAMILY_ALIASES[key]
    if raw in VOC.PRODUCT_FAMILIES:  # already-canonical value passed through as-is
        return raw
    raise KeyError(f"Unknown product_family alias: {raw!r}")


def normalize_standard_alias(raw):
    if raw is None:
        return None
    key = _normalize_key(raw)
    if key in STANDARD_ALIASES:
        return STANDARD_ALIASES[key]
    raise KeyError(f"Unknown standard alias: {raw!r}")


def normalize_subtype_alias(raw, product_family):
    """Scoped by product_family - the SAME raw word can mean a different
    canonical subtype in a different family. Raises KeyError if unknown."""
    if raw is None:
        return None
    table = _SUBTYPE_ALIASES_BY_FAMILY.get(product_family, {})
    key = _normalize_key(raw)
    if key in table:
        return table[key]
    raise KeyError(f"Unknown subtype alias {raw!r} for product_family {product_family!r}")
