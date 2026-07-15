# -*- coding: utf-8 -*-
"""
kgpe.contract.adapters.en_buttweld
======================================
Source adapter (Prompt 8): DIN 2605 (elbow) / DIN 2615 (tee) / DIN 2616
(reducer) / DIN 2617 (cap), aligned to EN 10253-2, buttwelding fittings.
Reads the existing JSON dimension_library.py's
BUTTWELD_FILES["EN_10253"] points at.

STANDARD-IDENTITY DECISION: the source's own header names four DIN
numbers aligned to one EN standard ("aligned to EN 10253-2") -
`standard="EN_10253"` is used verbatim, matching
dimension_library.py's own pre-existing BUTTWELD_FILES key for this
file (Prompt 8 Sec.11 - preserve the source's own combined designation).

ACTUAL SOURCE STRUCTURE FOUND: "fittings" dict with FOUR sections:
"elbow_90_180" (19 rows, DN15-600; columns DN, OD_mm, WallThk_mm,
Elbow90_CtoE_mm, Return180_CtoC_mm, BendRadius_K_mm, and
Elbow45_CtoE_derived_mm), "equal_tee" (19 rows), "concentric_reducer"
(16 rows, DN_Large/DN_Small pair), "cap" (19 rows, Height_mm always
present + WallThk_options_mm, a slash-separated multi-value string).

TWO EXPLICIT EXCLUSIONS (Prompt 8 Sec.16/17 - do not fabricate or
mis-treat data the source itself flags as non-standard):
  - `Elbow45_CtoE_derived_mm`: the source's own notes state this is "a
    GEOMETRIC DERIVATION (bend radius x tan(22.5deg)), not a standard-
    published value... do not treat as an official dimension." Not
    ingested as a VERIFIED_AUTHORITATIVE (or any other) canonical fact -
    this project's DerivedRule record type is reserved for rules this
    project has itself independently verified (Prompt 4), which this
    is not; fabricating either kind of record here would overstate its
    reliability.
  - `WallThk_options_mm`: a slash-separated STRING of multiple wall-class
    options for one cap (e.g. "2.9/4.5/6.3/8.0/12.5"), not a single
    deterministic dimension value - ingesting one number from it would
    require an arbitrary, unstated selection. Not ingested.
  - The reducer table provides CONCENTRIC dimensions only - no eccentric
    table exists in this source and no note claims the two share values
    (unlike the ASME B16.9 precedent) - so, unlike Prompt 7, this
    adapter does NOT duplicate the concentric reducer's value under an
    eccentric identity; that would fabricate data for a product this
    source does not describe.

SHARED CROSS-SECTION IDENTITY FOR OD AND WALL THICKNESS (mirrors the
Prompt 7 ASME B16.9 free-consistency-check design): `OD_mm` and
`WallThk_mm` are repeated across elbow/tee/reducer(as WT_Large/WT_Small)
and (OD only) cap. Both are given a SHARED identity with no
`fitting_type` (dimension + standard + dn only), so `add_checked()`
structurally proves cross-section consistency rather than merely
asserting it. Any real disagreement is pre-scanned before any fact is
built (`_collect_shared_observations`/`_find_shared_conflicts`) and
routed to QUARANTINED_CONFLICT, exactly as Prompt 7 did for the real
NPS8/NPS12 ASME B16.9 finding - so this adapter can never crash on (and
never silently resolves) a genuine source inconsistency, should one
exist. (None was found during this ingestion - all cross-section OD/WT
values agreed at every spot-checked DN - but the mechanism runs
unconditionally, not just when a problem is expected.)
"""
from collections import defaultdict

from .. import vocabulary as VOC
from .. import verification as V
from ..applicability import Applicability
from ..units import Quantity, LENGTH_MM
from ..normalization import normalize_dn, dn_sort_key
from ..model import EngineeringFact, EngineeringFactProvenance, FactRegistry, SourceValidationError
from ... import dimension_library as dl
from ._shared import load_json_source, validate_positive_numeric_or_null, check_duplicate_key

STANDARD_ID = "EN_10253"  # matches dimension_library.BUTTWELD_FILES key verbatim

REQUIRED_SECTIONS = ("elbow_90_180", "equal_tee", "concentric_reducer", "cap")

_CONFIDENCE_NOTE_ELBOW = ("Elbow 90/180 cross-checked against a second independent source (skylandmetal/"
                          "excelmetal bend-radius table) - matched to within rounding.")
_CONFIDENCE_NOTE_CAP = "Only one independent source used for caps - MODERATE CONFIDENCE (per source notes)."
_CONFIDENCE_NOTE_DEFAULT = "metleader.com official-format reproduction."


def _load_source():
    return load_json_source(dl.DIMLIB_ROOT, dl.BUTTWELD_FILES[STANDARD_ID])


def _validate_top_level(data):
    if "fittings" not in data or not isinstance(data["fittings"], dict):
        raise SourceValidationError("EN buttweld source missing top-level 'fittings' dict")
    missing = [s for s in REQUIRED_SECTIONS if s not in data["fittings"]]
    if missing:
        raise SourceValidationError(f"EN buttweld source missing section(s): {missing}")
    for s in REQUIRED_SECTIONS:
        if "rows" not in data["fittings"][s]:
            raise SourceValidationError(f"EN buttweld source: section {s!r} missing 'rows'")


def _validate_single_dn_row(section_label, index, row, value_cols, required_cols=()):
    errs = []
    if "DN" not in row or not isinstance(row["DN"], (int, float)) or row["DN"] <= 0:
        errs.append(f"{section_label} row {index}: DN must be a positive number")
    for col in value_cols:
        errs.extend(validate_positive_numeric_or_null(section_label, index, row, col,
                                                       required=(col in required_cols)))
    return errs


def _validate_reducer_row(index, row):
    errs = []
    for field in ("DN_Large", "DN_Small", "OD_Large_mm", "OD_Small_mm", "WT_Large_mm", "WT_Small_mm", "Length_mm"):
        errs.extend(validate_positive_numeric_or_null("concentric_reducer", index, row, field, required=True))
    if errs:
        return errs
    large = normalize_dn(row["DN_Large"])
    small = normalize_dn(row["DN_Small"])
    if not (dn_sort_key(large) > dn_sort_key(small)):
        errs.append(f"concentric_reducer row {index}: DN_Large ({large}) must be strictly greater "
                    f"than DN_Small ({small})")
    return errs


# ---------------------------------------------------------------------------
# Shared cross-section OD/wall-thickness consistency pre-scan.
# ---------------------------------------------------------------------------
def _collect_shared_observations(data):
    od_obs, wt_obs = [], []
    for row in data["fittings"]["elbow_90_180"]["rows"]:
        dn = normalize_dn(row["DN"])
        od_obs.append((dn, float(row["OD_mm"]), "elbow_90_180"))
        wt_obs.append((dn, float(row["WallThk_mm"]), "elbow_90_180"))
    for row in data["fittings"]["equal_tee"]["rows"]:
        dn = normalize_dn(row["DN"])
        od_obs.append((dn, float(row["OD_mm"]), "equal_tee"))
        wt_obs.append((dn, float(row["WallThk_mm"]), "equal_tee"))
    for row in data["fittings"]["concentric_reducer"]["rows"]:
        large, small = normalize_dn(row["DN_Large"]), normalize_dn(row["DN_Small"])
        od_obs.append((large, float(row["OD_Large_mm"]), "concentric_reducer(large)"))
        od_obs.append((small, float(row["OD_Small_mm"]), "concentric_reducer(small)"))
        wt_obs.append((large, float(row["WT_Large_mm"]), "concentric_reducer(large)"))
        wt_obs.append((small, float(row["WT_Small_mm"]), "concentric_reducer(small)"))
    for row in data["fittings"]["cap"]["rows"]:
        od_obs.append((normalize_dn(row["DN"]), float(row["OD_mm"]), "cap"))
    return od_obs, wt_obs


def _find_conflicts(observations):
    by_dn = defaultdict(lambda: defaultdict(list))
    for dn, value, section in observations:
        by_dn[dn][value].append(section)
    return {dn: dict(values) for dn, values in by_dn.items() if len(values) > 1}


def _prov(source_file_rel, section_label, original_field, confidence_note, extra_note=None):
    return EngineeringFactProvenance(
        source_name="KGPE EN 10253 AI-Readable dataset", source_type="internal_dataset",
        standard_designation=STANDARD_ID, source_file=source_file_rel, original_field=original_field,
        transcription_method=f"Programmatic ingestion (kgpe/contract/adapters/en_buttweld.py) from {section_label}",
        verification_method=confidence_note, notes=extra_note,
    )


def _shared_fact(dim_name, dn, value, source_file_rel, section_label, original_field, conflicted_dns,
                 confidence_note):
    is_conflicted = dn in conflicted_dns
    status = V.QUARANTINED_CONFLICT if is_conflicted else V.VERIFIED_AUTHORITATIVE
    note = None
    if is_conflicted:
        note = (f"QUARANTINED_CONFLICT: cross-section comparison found disagreeing {dim_name} values for "
                f"{dn} across EN 10253 sections - see the Prompt 8 report for the value breakdown.")
    applicability = Applicability(product_family=VOC.PRODUCT_FAMILY_BUTTWELD_FITTING, standard=STANDARD_ID, dn=dn)
    return EngineeringFact(dimension_name=dim_name, value=Quantity(float(value), LENGTH_MM),
                           applicability=applicability, verification_status=status,
                           provenance=_prov(source_file_rel, section_label, original_field, confidence_note, note),
                           notes=note)


def _add_fact(registry, fact):
    """Same dispatcher pattern as Prompt 7's B16.9 adapter: a
    QUARANTINED_CONFLICT fact bypasses add_checked()'s identity-conflict
    enforcement (via plain add(), with its own exact-duplicate guard so
    re-ingestion stays idempotent); everything else goes through
    add_checked() as normal."""
    if fact.verification_status == V.QUARANTINED_CONFLICT:
        key = fact.identity_key()
        for existing in registry._by_dimension.get(fact.dimension_name, []):
            if (existing.verification_status == V.QUARANTINED_CONFLICT
                    and existing.identity_key() == key and existing.value == fact.value):
                return existing
        return registry.add(fact)
    return registry.add_checked(fact)


def _build_elbow_facts(row, source_file_rel, conflicted_od, conflicted_wt):
    dn = normalize_dn(row["DN"])
    facts = [
        _shared_fact(VOC.DIM_OUTSIDE_DIAMETER, dn, row["OD_mm"], source_file_rel, "elbow_90_180", "OD_mm",
                    conflicted_od, _CONFIDENCE_NOTE_ELBOW),
        _shared_fact(VOC.DIM_WALL_THICKNESS, dn, row["WallThk_mm"], source_file_rel, "elbow_90_180", "WallThk_mm",
                    conflicted_wt, _CONFIDENCE_NOTE_ELBOW),
    ]
    applicability_90 = Applicability(product_family=VOC.PRODUCT_FAMILY_BUTTWELD_FITTING, standard=STANDARD_ID,
                                     fitting_type=VOC.FITTING_TYPE_ELBOW_90_EN, dn=dn)
    facts.append(EngineeringFact(dimension_name=VOC.DIM_CENTRE_TO_END, value=Quantity(float(row["Elbow90_CtoE_mm"]), LENGTH_MM),
                                 applicability=applicability_90, verification_status=V.VERIFIED_AUTHORITATIVE,
                                 provenance=_prov(source_file_rel, "elbow_90_180", "Elbow90_CtoE_mm", _CONFIDENCE_NOTE_ELBOW)))
    facts.append(EngineeringFact(dimension_name=VOC.DIM_BEND_RADIUS, value=Quantity(float(row["BendRadius_K_mm"]), LENGTH_MM),
                                 applicability=applicability_90, verification_status=V.VERIFIED_AUTHORITATIVE,
                                 provenance=_prov(source_file_rel, "elbow_90_180", "BendRadius_K_mm", _CONFIDENCE_NOTE_ELBOW)))
    applicability_180 = Applicability(product_family=VOC.PRODUCT_FAMILY_BUTTWELD_FITTING, standard=STANDARD_ID,
                                      fitting_type=VOC.FITTING_TYPE_RETURN_180_EN, dn=dn)
    facts.append(EngineeringFact(dimension_name=VOC.DIM_RETURN_180_CENTRE_TO_CENTRE,
                                 value=Quantity(float(row["Return180_CtoC_mm"]), LENGTH_MM),
                                 applicability=applicability_180, verification_status=V.VERIFIED_AUTHORITATIVE,
                                 provenance=_prov(source_file_rel, "elbow_90_180", "Return180_CtoC_mm", _CONFIDENCE_NOTE_ELBOW)))
    # Elbow45_CtoE_derived_mm deliberately excluded - see module docstring.
    return facts


def _build_tee_facts(row, source_file_rel, conflicted_od, conflicted_wt):
    dn = normalize_dn(row["DN"])
    facts = [
        _shared_fact(VOC.DIM_OUTSIDE_DIAMETER, dn, row["OD_mm"], source_file_rel, "equal_tee", "OD_mm",
                    conflicted_od, _CONFIDENCE_NOTE_DEFAULT),
        _shared_fact(VOC.DIM_WALL_THICKNESS, dn, row["WallThk_mm"], source_file_rel, "equal_tee", "WallThk_mm",
                    conflicted_wt, _CONFIDENCE_NOTE_DEFAULT),
    ]
    applicability = Applicability(product_family=VOC.PRODUCT_FAMILY_BUTTWELD_FITTING, standard=STANDARD_ID,
                                  fitting_type=VOC.FITTING_TYPE_TEE_EQUAL_EN, dn=dn)
    facts.append(EngineeringFact(dimension_name=VOC.DIM_CENTRE_TO_END, value=Quantity(float(row["CtoE_mm"]), LENGTH_MM),
                                 applicability=applicability, verification_status=V.VERIFIED_AUTHORITATIVE,
                                 provenance=_prov(source_file_rel, "equal_tee", "CtoE_mm", _CONFIDENCE_NOTE_DEFAULT)))
    return facts


def _build_reducer_facts(row, source_file_rel, conflicted_od, conflicted_wt):
    large, small = normalize_dn(row["DN_Large"]), normalize_dn(row["DN_Small"])
    facts = [
        _shared_fact(VOC.DIM_OUTSIDE_DIAMETER, large, row["OD_Large_mm"], source_file_rel, "concentric_reducer(large)",
                    "OD_Large_mm", conflicted_od, _CONFIDENCE_NOTE_DEFAULT),
        _shared_fact(VOC.DIM_OUTSIDE_DIAMETER, small, row["OD_Small_mm"], source_file_rel, "concentric_reducer(small)",
                    "OD_Small_mm", conflicted_od, _CONFIDENCE_NOTE_DEFAULT),
        _shared_fact(VOC.DIM_WALL_THICKNESS, large, row["WT_Large_mm"], source_file_rel, "concentric_reducer(large)",
                    "WT_Large_mm", conflicted_wt, _CONFIDENCE_NOTE_DEFAULT),
        _shared_fact(VOC.DIM_WALL_THICKNESS, small, row["WT_Small_mm"], source_file_rel, "concentric_reducer(small)",
                    "WT_Small_mm", conflicted_wt, _CONFIDENCE_NOTE_DEFAULT),
    ]
    applicability = Applicability(product_family=VOC.PRODUCT_FAMILY_BUTTWELD_FITTING, standard=STANDARD_ID,
                                  fitting_type=VOC.FITTING_TYPE_REDUCER_CONCENTRIC_EN,
                                  large_end_dn=large, small_end_dn=small)
    facts.append(EngineeringFact(dimension_name=VOC.DIM_END_TO_END, value=Quantity(float(row["Length_mm"]), LENGTH_MM),
                                 applicability=applicability, verification_status=V.VERIFIED_AUTHORITATIVE,
                                 provenance=_prov(source_file_rel, "concentric_reducer", "Length_mm", _CONFIDENCE_NOTE_DEFAULT,
                                                  extra_note="Concentric only - source provides no eccentric table; "
                                                             "not duplicated under an eccentric identity (unlike the "
                                                             "ASME B16.9 precedent, where the source explicitly stated "
                                                             "the value applies to both).")))
    return facts


def _build_cap_facts(row, source_file_rel, conflicted_od):
    dn = normalize_dn(row["DN"])
    facts = [
        _shared_fact(VOC.DIM_OUTSIDE_DIAMETER, dn, row["OD_mm"], source_file_rel, "cap", "OD_mm",
                    conflicted_od, _CONFIDENCE_NOTE_CAP),
    ]
    applicability = Applicability(product_family=VOC.PRODUCT_FAMILY_BUTTWELD_FITTING, standard=STANDARD_ID,
                                  fitting_type=VOC.FITTING_TYPE_CAP_EN, dn=dn)
    facts.append(EngineeringFact(dimension_name=VOC.DIM_END_TO_END, value=Quantity(float(row["Height_mm"]), LENGTH_MM),
                                 applicability=applicability, verification_status=V.VERIFIED_AUTHORITATIVE,
                                 provenance=_prov(source_file_rel, "cap", "Height_mm", _CONFIDENCE_NOTE_CAP)))
    # WallThk_options_mm deliberately excluded (multi-value string) - see module docstring.
    return facts


def ingest_en_buttweld(registry=None):
    """Reads, validates, and ingests the EN 10253 JSON. Deterministic
    order: elbow_90_180 -> equal_tee -> concentric_reducer -> cap, rows
    sorted by DN sort key (reducer by (large, small) DN tuple)."""
    if registry is None:
        registry = FactRegistry()

    data, source_file_rel = _load_source()
    _validate_top_level(data)

    elbow_rows = data["fittings"]["elbow_90_180"]["rows"]
    tee_rows = data["fittings"]["equal_tee"]["rows"]
    reducer_rows = data["fittings"]["concentric_reducer"]["rows"]
    cap_rows = data["fittings"]["cap"]["rows"]

    all_errors = []
    for i, row in enumerate(elbow_rows):
        all_errors.extend(_validate_single_dn_row(
            "elbow_90_180", i, row,
            ["OD_mm", "WallThk_mm", "Elbow90_CtoE_mm", "Return180_CtoC_mm", "BendRadius_K_mm"],
            required_cols=["OD_mm", "WallThk_mm", "Elbow90_CtoE_mm", "Return180_CtoC_mm", "BendRadius_K_mm"]))
    all_errors.extend(check_duplicate_key("elbow_90_180", elbow_rows, lambda r: normalize_dn(r["DN"])))

    for i, row in enumerate(tee_rows):
        all_errors.extend(_validate_single_dn_row("equal_tee", i, row, ["OD_mm", "WallThk_mm", "CtoE_mm"],
                                                   required_cols=["OD_mm", "WallThk_mm", "CtoE_mm"]))
    all_errors.extend(check_duplicate_key("equal_tee", tee_rows, lambda r: normalize_dn(r["DN"])))

    for i, row in enumerate(reducer_rows):
        all_errors.extend(_validate_reducer_row(i, row))
    all_errors.extend(check_duplicate_key(
        "concentric_reducer", reducer_rows,
        lambda r: (normalize_dn(r["DN_Large"]), normalize_dn(r["DN_Small"]))))

    for i, row in enumerate(cap_rows):
        all_errors.extend(_validate_single_dn_row("cap", i, row, ["OD_mm", "Height_mm"],
                                                   required_cols=["OD_mm", "Height_mm"]))
    all_errors.extend(check_duplicate_key("cap", cap_rows, lambda r: normalize_dn(r["DN"])))

    if all_errors:
        raise SourceValidationError(
            f"EN buttweld source failed validation ({len(all_errors)} problem(s)): " + " | ".join(all_errors)
        )

    od_obs, wt_obs = _collect_shared_observations(data)
    conflicted_od = set(_find_conflicts(od_obs).keys())
    conflicted_wt = set(_find_conflicts(wt_obs).keys())

    ingested = []

    def _sorted(rows):
        return sorted(rows, key=lambda r: dn_sort_key(normalize_dn(r["DN"])))

    for row in _sorted(elbow_rows):
        for fact in _build_elbow_facts(row, source_file_rel, conflicted_od, conflicted_wt):
            _add_fact(registry, fact)
            ingested.append(fact)

    for row in _sorted(tee_rows):
        for fact in _build_tee_facts(row, source_file_rel, conflicted_od, conflicted_wt):
            _add_fact(registry, fact)
            ingested.append(fact)

    for row in sorted(reducer_rows, key=lambda r: (dn_sort_key(normalize_dn(r["DN_Large"])),
                                                    dn_sort_key(normalize_dn(r["DN_Small"])))):
        for fact in _build_reducer_facts(row, source_file_rel, conflicted_od, conflicted_wt):
            _add_fact(registry, fact)
            ingested.append(fact)

    for row in _sorted(cap_rows):
        for fact in _build_cap_facts(row, source_file_rel, conflicted_od):
            _add_fact(registry, fact)
            ingested.append(fact)

    return registry, ingested
