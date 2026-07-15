# -*- coding: utf-8 -*-
"""
kgpe.contract.adapters.jis_buttweld
=======================================
Source adapter (Prompt 8): JIS B2311 (general) / B2312 (steel pressure)
buttwelding fittings - elbow 90LR+45, equal tee, cap, and a representative
concentric-reducer sample. Reads the existing JSON dimension_library.py's
BUTTWELD_FILES["JIS_B2311_2312"] points at.

ACTUAL SOURCE STRUCTURE FOUND: "fittings" dict with FOUR sections:
"elbow_90LR_and_45" (16 rows, A_mm 15-400, both CtoE columns always
populated - unlike ASME B16.9 there is no separate SR/3D subtype here,
and no null-handling needed), "equal_tee" (16 rows), "cap" (16 rows),
"concentric_reducer_sample" (ONLY 7 rows - the source's own notes call
this out explicitly as "a representative sample... not the full size/
reduction matrix", so this adapter ingests exactly those 7 pairs and
does not attempt to interpolate or extrapolate the rest of the matrix).
Size identity is JIS A-size (`SizeLarge_mm`/`SizeSmall_mm` for the
reducer - normalized via normalize_jis_size(), stored in the new
Prompt-8 `large_end_jis_size`/`small_end_jis_size` Applicability fields,
never forced into the Prompt 7 NPS-specific large_end_nps/small_end_nps
fields).

CRITICAL OD-SERIES WARNING FROM THE SOURCE (preserved, not silently
dropped): "OD values here use the JIS/SGP series (21.7, 27.2, 34.0mm...)
which is DIFFERENT from the ASME/ISO OD series (21.3, 26.7, 33.4mm...)
- do not mix the two when quoting JIS-spec fittings." This is exactly
why this adapter's OD facts are tagged with `standard=JIS_B2311_2312`
and product_family=buttweld_fitting, never collapsed with the ASME B16.9
OD facts from Prompt 7 even at overlapping-looking sizes.

PROVENANCE / CONFIDENCE NOTE (Prompt 8 Sec.20): the source's own notes
state both sources used (pipelinedubai.com, steeljrv.com) "are mirrors of
the same company (Yaang Pipe Industry) - this is NOT independently
cross-verified... Treat as MODERATE CONFIDENCE pending a true second-
source check." A third site's mislabeled "JIS B2311" page (actually
ASME B16.9 dimensions) was deliberately excluded as a source - documented
by the source itself, not something this adapter needed to detect.
Ingested as VERIFIED_AUTHORITATIVE (this project's established tier for
AI-Readable JSON standard files) with the moderate-confidence caveat
carried honestly in provenance.verification_method.

No fitting wall-thickness-by-schedule table exists in this source at
all (the source's own notes state this plainly) - not fabricated here.
"""
from .. import vocabulary as VOC
from .. import verification as V
from ..applicability import Applicability
from ..units import Quantity, LENGTH_MM
from ..normalization import normalize_jis_size, jis_size_sort_key
from ..model import EngineeringFact, EngineeringFactProvenance, FactRegistry, SourceValidationError
from ... import dimension_library as dl
from ._shared import load_json_source, validate_positive_numeric_or_null, check_duplicate_key

STANDARD_ID = "JIS_B2311_2312"  # matches dimension_library.BUTTWELD_FILES key verbatim

REQUIRED_SECTIONS = ("elbow_90LR_and_45", "equal_tee", "cap", "concentric_reducer_sample")

_CONFIDENCE_NOTE = ("Both sources used (pipelinedubai.com, steeljrv.com) are mirrors of the same company "
                    "(Yaang Pipe Industry) - NOT independently cross-verified. MODERATE CONFIDENCE pending "
                    "a true second-source check (Prompt 8 Sec.20).")


def _load_source():
    return load_json_source(dl.DIMLIB_ROOT, dl.BUTTWELD_FILES[STANDARD_ID])


def _validate_top_level(data):
    if "fittings" not in data or not isinstance(data["fittings"], dict):
        raise SourceValidationError("JIS buttweld source missing top-level 'fittings' dict")
    missing = [s for s in REQUIRED_SECTIONS if s not in data["fittings"]]
    if missing:
        raise SourceValidationError(f"JIS buttweld source missing section(s): {missing}")
    for s in REQUIRED_SECTIONS:
        if "rows" not in data["fittings"][s]:
            raise SourceValidationError(f"JIS buttweld source: section {s!r} missing 'rows'")


def _validate_single_size_row(section_label, index, row, value_cols):
    errs = []
    if "A_mm" not in row or not isinstance(row["A_mm"], (int, float)) or row["A_mm"] <= 0:
        errs.append(f"{section_label} row {index}: A_mm must be a positive number")
    errs.extend(validate_positive_numeric_or_null(section_label, index, row, "OD_mm", required=True))
    for col in value_cols:
        errs.extend(validate_positive_numeric_or_null(section_label, index, row, col, required=True))
    return errs


def _validate_reducer_row(index, row):
    errs = []
    for field in ("SizeLarge_mm", "SizeSmall_mm", "OD_Large_mm", "OD_Small_mm", "EndToEnd_mm"):
        errs.extend(validate_positive_numeric_or_null("concentric_reducer_sample", index, row, field, required=True))
    if errs:
        return errs
    large = normalize_jis_size(row["SizeLarge_mm"])
    small = normalize_jis_size(row["SizeSmall_mm"])
    if not (jis_size_sort_key(large) > jis_size_sort_key(small)):
        errs.append(f"concentric_reducer_sample row {index}: SizeLarge_mm ({large}) must be strictly "
                    f"greater than SizeSmall_mm ({small})")
    return errs


def _prov(source_file_rel, section_label, original_field):
    return EngineeringFactProvenance(
        source_name="KGPE JIS B2311/2312 AI-Readable dataset", source_type="internal_dataset",
        standard_designation=STANDARD_ID, source_file=source_file_rel, original_field=original_field,
        transcription_method=f"Programmatic ingestion (kgpe/contract/adapters/jis_buttweld.py) from {section_label}",
        verification_method=_CONFIDENCE_NOTE,
        notes="OD uses the JIS/SGP series, distinct from ASME/ISO OD at nominally-similar sizes - see module docstring.",
    )


def _od_fact(row, fitting_type, section_label, source_file_rel):
    jis_size = normalize_jis_size(row["A_mm"])
    applicability = Applicability(product_family=VOC.PRODUCT_FAMILY_BUTTWELD_FITTING, standard=STANDARD_ID,
                                  fitting_type=fitting_type, jis_size=jis_size)
    return EngineeringFact(dimension_name=VOC.DIM_OUTSIDE_DIAMETER, value=Quantity(float(row["OD_mm"]), LENGTH_MM),
                           applicability=applicability, verification_status=V.VERIFIED_AUTHORITATIVE,
                           provenance=_prov(source_file_rel, section_label, "OD_mm"))


def _build_elbow_facts(row, source_file_rel):
    jis_size = normalize_jis_size(row["A_mm"])
    facts = []
    for fitting_type, col in ((VOC.FITTING_TYPE_ELBOW_90_LR_JIS, "Elbow90LR_CtoE_mm"),
                              (VOC.FITTING_TYPE_ELBOW_45_JIS, "Elbow45_CtoE_mm")):
        facts.append(_od_fact(row, fitting_type, "elbow_90LR_and_45", source_file_rel))
        applicability = Applicability(product_family=VOC.PRODUCT_FAMILY_BUTTWELD_FITTING, standard=STANDARD_ID,
                                      fitting_type=fitting_type, jis_size=jis_size)
        facts.append(EngineeringFact(dimension_name=VOC.DIM_CENTRE_TO_END, value=Quantity(float(row[col]), LENGTH_MM),
                                     applicability=applicability, verification_status=V.VERIFIED_AUTHORITATIVE,
                                     provenance=_prov(source_file_rel, "elbow_90LR_and_45", col)))
    return facts


def _build_tee_facts(row, source_file_rel):
    jis_size = normalize_jis_size(row["A_mm"])
    facts = [_od_fact(row, VOC.FITTING_TYPE_TEE_EQUAL_JIS, "equal_tee", source_file_rel)]
    applicability = Applicability(product_family=VOC.PRODUCT_FAMILY_BUTTWELD_FITTING, standard=STANDARD_ID,
                                  fitting_type=VOC.FITTING_TYPE_TEE_EQUAL_JIS, jis_size=jis_size)
    facts.append(EngineeringFact(dimension_name=VOC.DIM_CENTRE_TO_END, value=Quantity(float(row["CtoE_mm"]), LENGTH_MM),
                                 applicability=applicability, verification_status=V.VERIFIED_AUTHORITATIVE,
                                 provenance=_prov(source_file_rel, "equal_tee", "CtoE_mm")))
    return facts


def _build_cap_facts(row, source_file_rel):
    jis_size = normalize_jis_size(row["A_mm"])
    facts = [_od_fact(row, VOC.FITTING_TYPE_CAP_JIS, "cap", source_file_rel)]
    applicability = Applicability(product_family=VOC.PRODUCT_FAMILY_BUTTWELD_FITTING, standard=STANDARD_ID,
                                  fitting_type=VOC.FITTING_TYPE_CAP_JIS, jis_size=jis_size)
    facts.append(EngineeringFact(dimension_name=VOC.DIM_END_TO_END, value=Quantity(float(row["EndToEnd_mm"]), LENGTH_MM),
                                 applicability=applicability, verification_status=V.VERIFIED_AUTHORITATIVE,
                                 provenance=_prov(source_file_rel, "cap", "EndToEnd_mm")))
    return facts


def _build_reducer_facts(row, source_file_rel):
    large = normalize_jis_size(row["SizeLarge_mm"])
    small = normalize_jis_size(row["SizeSmall_mm"])
    facts = []
    for role, od_col in (("large", "OD_Large_mm"), ("small", "OD_Small_mm")):
        size = large if role == "large" else small
        applicability = Applicability(product_family=VOC.PRODUCT_FAMILY_BUTTWELD_FITTING, standard=STANDARD_ID,
                                      jis_size=size)
        facts.append(EngineeringFact(dimension_name=VOC.DIM_OUTSIDE_DIAMETER, value=Quantity(float(row[od_col]), LENGTH_MM),
                                     applicability=applicability, verification_status=V.VERIFIED_AUTHORITATIVE,
                                     provenance=_prov(source_file_rel, "concentric_reducer_sample", od_col)))
    applicability = Applicability(product_family=VOC.PRODUCT_FAMILY_BUTTWELD_FITTING, standard=STANDARD_ID,
                                  fitting_type=VOC.FITTING_TYPE_REDUCER_CONCENTRIC_JIS,
                                  large_end_jis_size=large, small_end_jis_size=small)
    facts.append(EngineeringFact(dimension_name=VOC.DIM_END_TO_END, value=Quantity(float(row["EndToEnd_mm"]), LENGTH_MM),
                                 applicability=applicability, verification_status=V.VERIFIED_AUTHORITATIVE,
                                 provenance=_prov(source_file_rel, "concentric_reducer_sample", "EndToEnd_mm")))
    return facts


def ingest_jis_buttweld(registry=None):
    """Reads, validates, and ingests the JIS B2311/2312 JSON. Deterministic
    order: elbow_90LR_and_45 -> equal_tee -> cap -> concentric_reducer_sample,
    single-size rows sorted by JIS-size sort key, reducer rows sorted by
    (large, small) JIS-size sort key tuple."""
    if registry is None:
        registry = FactRegistry()

    data, source_file_rel = _load_source()
    _validate_top_level(data)

    elbow_rows = data["fittings"]["elbow_90LR_and_45"]["rows"]
    tee_rows = data["fittings"]["equal_tee"]["rows"]
    cap_rows = data["fittings"]["cap"]["rows"]
    reducer_rows = data["fittings"]["concentric_reducer_sample"]["rows"]

    all_errors = []
    for i, row in enumerate(elbow_rows):
        all_errors.extend(_validate_single_size_row("elbow_90LR_and_45", i, row,
                                                     ["Elbow90LR_CtoE_mm", "Elbow45_CtoE_mm"]))
    all_errors.extend(check_duplicate_key("elbow_90LR_and_45", elbow_rows, lambda r: normalize_jis_size(r["A_mm"])))

    for i, row in enumerate(tee_rows):
        all_errors.extend(_validate_single_size_row("equal_tee", i, row, ["CtoE_mm"]))
    all_errors.extend(check_duplicate_key("equal_tee", tee_rows, lambda r: normalize_jis_size(r["A_mm"])))

    for i, row in enumerate(cap_rows):
        all_errors.extend(_validate_single_size_row("cap", i, row, ["EndToEnd_mm"]))
    all_errors.extend(check_duplicate_key("cap", cap_rows, lambda r: normalize_jis_size(r["A_mm"])))

    for i, row in enumerate(reducer_rows):
        all_errors.extend(_validate_reducer_row(i, row))
    all_errors.extend(check_duplicate_key(
        "concentric_reducer_sample", reducer_rows,
        lambda r: (normalize_jis_size(r["SizeLarge_mm"]), normalize_jis_size(r["SizeSmall_mm"]))))

    if all_errors:
        raise SourceValidationError(
            f"JIS buttweld source failed validation ({len(all_errors)} problem(s)): " + " | ".join(all_errors)
        )

    ingested = []

    def _sorted(rows):
        return sorted(rows, key=lambda r: jis_size_sort_key(normalize_jis_size(r["A_mm"])))

    for row in _sorted(elbow_rows):
        for fact in _build_elbow_facts(row, source_file_rel):
            registry.add_checked(fact)
            ingested.append(fact)

    for row in _sorted(tee_rows):
        for fact in _build_tee_facts(row, source_file_rel):
            registry.add_checked(fact)
            ingested.append(fact)

    for row in _sorted(cap_rows):
        for fact in _build_cap_facts(row, source_file_rel):
            registry.add_checked(fact)
            ingested.append(fact)

    for row in sorted(reducer_rows, key=lambda r: (jis_size_sort_key(normalize_jis_size(r["SizeLarge_mm"])),
                                                    jis_size_sort_key(normalize_jis_size(r["SizeSmall_mm"])))):
        for fact in _build_reducer_facts(row, source_file_rel):
            registry.add_checked(fact)
            ingested.append(fact)

    return registry, ingested
