# -*- coding: utf-8 -*-
"""
kgpe.contract.adapters.jis_b2220_flanges
============================================
Source adapter (Prompt 8): JIS B2220 steel pipe flanges (weld-neck
type), classes 5K/10K/16K/20K. Reads the existing JSON
dimension_library.py's FLANGE_FILES["JIS_B2220"] points at.

ACTUAL SOURCE STRUCTURE FOUND: one "classes" dict keyed "5K"/"10K"/
"16K"/"20K", each a flat row list with columns NPS_A_mm, OD_mm,
BoltCircle_mm, RaisedFace_mm, BoreID_mm, PipeOD_mm, Thickness_mm,
NumBolts, BoltSize, BoltHoleDia_mm - all populated, no nulls found.
Size identity is JIS A-size (normalize_jis_size()), NEVER forced into
NPS or DN (Prompt 8 Sec.4/5) even though the numeric progression
(15,20,25,32...) coincides with EN's DN progression - `standard` alone
already prevents any identity collision regardless.

PROVENANCE NOTE (Prompt 8 Sec.20 - do not auto-promote structured JSON
to authoritative merely by format): this source's own notes state it is
"Only single-sourced (weldflange.com) - not yet cross-verified against a
second independent source... GOOD CONFIDENCE... but not yet independently
verified the way the ASME files were." Ingested as VERIFIED_AUTHORITATIVE
(matching the tier every other AI-Readable JSON standard file in this
project has received - none of them are re-verified from scratch inside
KGPE itself, they inherit Prompt 3's baseline confidence), but this
single-source caveat is carried honestly in every fact's
provenance.verification_method rather than silently dropped.

`PipeOD_mm` is DELIBERATELY NOT ingested as a separate canonical fact
here: the source's own notes state it is cross-referenced against (and
matches) the JIS pipe standard's own OD series for the same A-size -
i.e. it is a redundant copy of a fact already ingested, under its own
distinct identity, by `jis_pipe.py`. Re-ingesting it here under a
flange-scoped identity would create a second, confusingly-named
identity for the exact same physical quantity. Sec.14's "test this
explicitly" requirement is satisfied instead by a dedicated cross-check
test comparing this file's PipeOD_mm values against the JIS pipe
adapter's ingested OD facts (see tests/test_jis_ingestion.py).
"""
from .. import vocabulary as VOC
from .. import verification as V
from ..applicability import Applicability
from ..units import Quantity, LENGTH_MM, COUNT, DESIGNATION
from ..normalization import normalize_jis_size, jis_size_sort_key, normalize_pressure_class
from ..vocabulary import RATING_SYSTEM_JIS_K
from ..model import EngineeringFact, EngineeringFactProvenance, FactRegistry, SourceValidationError
from ... import dimension_library as dl
from ._shared import load_json_source, validate_positive_numeric_or_null, check_duplicate_key

STANDARD_ID = "JIS_B2220"  # matches dimension_library.FLANGE_FILES key verbatim
CLASS_KEYS = ("5K", "10K", "16K", "20K")

_VALUE_COLS = ["OD_mm", "BoltCircle_mm", "RaisedFace_mm", "BoreID_mm", "Thickness_mm", "BoltHoleDia_mm"]

_CONFIDENCE_NOTE = ("Single-sourced (weldflange.com) - GOOD CONFIDENCE (internally consistent, formula-"
                    "plausible, cross-checked against the JIS pipe OD series) but not independently "
                    "cross-verified against a second source the way the ASME files were (Prompt 8 Sec.20).")


def _load_source():
    return load_json_source(dl.DIMLIB_ROOT, dl.FLANGE_FILES[STANDARD_ID])


def _validate_top_level(data):
    if "classes" not in data or not isinstance(data["classes"], dict):
        raise SourceValidationError("JIS B2220 source missing top-level 'classes' dict")
    missing = [c for c in CLASS_KEYS if c not in data["classes"]]
    if missing:
        raise SourceValidationError(f"JIS B2220 source missing class(es): {missing}")


def _validate_row(class_key, index, row):
    errs = []
    if "NPS_A_mm" not in row or not isinstance(row["NPS_A_mm"], (int, float)) or row["NPS_A_mm"] <= 0:
        errs.append(f"classes/{class_key} row {index}: NPS_A_mm must be a positive number")
    for col in _VALUE_COLS:
        errs.extend(validate_positive_numeric_or_null(f"classes/{class_key}", index, row, col, required=True))
    if "NumBolts" not in row or not isinstance(row["NumBolts"], int) or row["NumBolts"] <= 0:
        errs.append(f"classes/{class_key} row {index}: NumBolts must be a positive integer")
    if "BoltSize" not in row or not isinstance(row["BoltSize"], str) or not row["BoltSize"].strip():
        errs.append(f"classes/{class_key} row {index}: BoltSize must be a non-empty string")
    return errs


def _prov(source_file_rel, class_key, original_field):
    return EngineeringFactProvenance(
        source_name="KGPE JIS B2220 AI-Readable dataset", source_type="internal_dataset",
        standard_designation=STANDARD_ID, source_file=source_file_rel, original_field=original_field,
        transcription_method=f"Programmatic ingestion (kgpe/contract/adapters/jis_b2220_flanges.py) from classes/{class_key}",
        verification_method=_CONFIDENCE_NOTE,
    )


def _build_facts(row, class_key, source_file_rel):
    jis_size = normalize_jis_size(row["NPS_A_mm"])
    applicability_kwargs = dict(product_family=VOC.PRODUCT_FAMILY_FLANGE, standard=STANDARD_ID,
                                flange_type="weld_neck", class_key=class_key, jis_size=jis_size)
    facts = []
    field_map = [
        (VOC.DIM_OUTSIDE_DIAMETER, "OD_mm", LENGTH_MM),
        (VOC.DIM_BOLT_CIRCLE_DIAMETER, "BoltCircle_mm", LENGTH_MM),
        (VOC.DIM_RAISED_FACE_DIAMETER, "RaisedFace_mm", LENGTH_MM),
        (VOC.DIM_BORE_DIAMETER, "BoreID_mm", LENGTH_MM),
        (VOC.DIM_FLANGE_THICKNESS_WELD_NECK, "Thickness_mm", LENGTH_MM),
        (VOC.DIM_BOLT_HOLE_DIAMETER, "BoltHoleDia_mm", LENGTH_MM),
    ]
    for dim_name, col, unit in field_map:
        facts.append(EngineeringFact(
            dimension_name=dim_name, value=Quantity(float(row[col]), unit),
            applicability=Applicability(**applicability_kwargs), verification_status=V.VERIFIED_AUTHORITATIVE,
            provenance=_prov(source_file_rel, class_key, col)))
    facts.append(EngineeringFact(
        dimension_name=VOC.DIM_NUM_BOLTS, value=Quantity(int(row["NumBolts"]), COUNT),
        applicability=Applicability(**applicability_kwargs), verification_status=V.VERIFIED_AUTHORITATIVE,
        provenance=_prov(source_file_rel, class_key, "NumBolts")))
    facts.append(EngineeringFact(
        dimension_name=VOC.DIM_BOLT_SIZE_DESIGNATION, value=Quantity(row["BoltSize"], DESIGNATION),
        applicability=Applicability(**applicability_kwargs), verification_status=V.VERIFIED_AUTHORITATIVE,
        provenance=_prov(source_file_rel, class_key, "BoltSize")))
    return facts


def ingest_jis_b2220_flanges(registry=None):
    """Reads, validates, and ingests the JIS B2220 JSON. Deterministic
    order: classes sorted "5K","10K","16K","20K" (fixed known order, not
    dict iteration), rows sorted by JIS-size sort key."""
    if registry is None:
        registry = FactRegistry()

    data, source_file_rel = _load_source()
    _validate_top_level(data)

    all_errors = []
    for class_key in CLASS_KEYS:
        rows = data["classes"][class_key]
        for i, row in enumerate(rows):
            all_errors.extend(_validate_row(class_key, i, row))
        all_errors.extend(check_duplicate_key(f"classes/{class_key}", rows,
                                              lambda r: normalize_jis_size(r["NPS_A_mm"])))

    if all_errors:
        raise SourceValidationError(
            f"JIS B2220 source failed validation ({len(all_errors)} problem(s)): " + " | ".join(all_errors)
        )

    ingested = []
    for class_key in CLASS_KEYS:
        rows = sorted(data["classes"][class_key], key=lambda r: jis_size_sort_key(normalize_jis_size(r["NPS_A_mm"])))
        for row in rows:
            for fact in _build_facts(row, class_key, source_file_rel):
                registry.add_checked(fact)
                ingested.append(fact)

    return registry, ingested
