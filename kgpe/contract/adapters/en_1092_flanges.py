# -*- coding: utf-8 -*-
"""
kgpe.contract.adapters.en_1092_flanges
==========================================
Source adapter (Prompt 8): EN 1092-1:2018 steel flanges (Type 11,
weld-neck), PN6/10/16/25/40/63/100. Reads the existing JSON
dimension_library.py's FLANGE_FILES["EN_1092-1"] points at.

ACTUAL SOURCE STRUCTURE FOUND: one "pn_classes" dict keyed "PN6".."PN100",
each a flat row list with columns DN, OD_mm, BoltCircle_mm, BoltHoleDia_mm,
NumBolts, BoltSize, Thickness_mm - no RaisedFace/BoreID/NeckOD columns at
all (matches the existing dimension_library.get_flange("EN_1092-1", ...)
live-lookup, which already returns None for those three fields - no new
gap introduced here). Size identity is DN (normalize_dn()), never forced
into NPS or JIS A-size even where the numeric progression coincides
(Prompt 8 Sec.4/6).

Source header itself uses the combined "DIN 2448 (legacy).../EN 10220..."
style naming is NOT present here (that pattern is the pipe file, handled
in en_pipes.py) - this flange file's own header is unambiguously
"EN 1092-1:2018", so `standard="EN_1092-1"` (matching
dimension_library.FLANGE_FILES's own key) is used directly, no combined-
designation judgement call needed for this dataset.

PROVENANCE / CONFIDENCE NOTE: source's own notes state 3 independent
sources (Savoy Piping, wermac.org, roymech.org) cross-checked and matched
for PN10/16/25/40/63/100 - HIGH CONFIDENCE; PN6 is Savoy-only, cross-
confirmed only via a weight/tolerance table (not a direct dimensional
source) - MODERATE-HIGH CONFIDENCE, carried honestly per-class in
provenance rather than uniformly asserted as HIGH for the whole file.
The source also flags a real standard-revision caveat (raised-face
height varies 2mm flat in EN1092-1:2002 vs 1-5mm-by-DN-band in later
editions) - not relevant here since this adapter does not ingest RF
height at all (the source has no RF height column).
"""
from .. import vocabulary as VOC
from .. import verification as V
from ..applicability import Applicability
from ..units import Quantity, LENGTH_MM, COUNT, DESIGNATION
from ..normalization import normalize_dn, dn_sort_key, normalize_pressure_class
from ..vocabulary import RATING_SYSTEM_PN
from ..model import EngineeringFact, EngineeringFactProvenance, FactRegistry, SourceValidationError
from ... import dimension_library as dl
from ._shared import load_json_source, validate_positive_numeric_or_null, check_duplicate_key

STANDARD_ID = "EN_1092-1"  # matches dimension_library.FLANGE_FILES key verbatim
CLASS_KEYS = ("PN6", "PN10", "PN16", "PN25", "PN40", "PN63", "PN100")

_VALUE_COLS = ["OD_mm", "BoltCircle_mm", "BoltHoleDia_mm", "Thickness_mm"]

_CONFIDENCE_BY_CLASS = {
    "PN6": ("Savoy Piping (sole direct dimensional source) - cross-confirmed only via marcelforged's "
           "weight/tolerance tables, not a second direct dimensional source. MODERATE-HIGH CONFIDENCE."),
}
_DEFAULT_CONFIDENCE = ("3 independent sources (Savoy Piping official reproduction, wermac.org, roymech.org "
                       "for PN16/PN40) all matched exactly - HIGH CONFIDENCE.")


def _load_source():
    return load_json_source(dl.DIMLIB_ROOT, dl.FLANGE_FILES[STANDARD_ID])


def _validate_top_level(data):
    if "pn_classes" not in data or not isinstance(data["pn_classes"], dict):
        raise SourceValidationError("EN 1092-1 source missing top-level 'pn_classes' dict")
    missing = [c for c in CLASS_KEYS if c not in data["pn_classes"]]
    if missing:
        raise SourceValidationError(f"EN 1092-1 source missing class(es): {missing}")


def _validate_row(class_key, index, row):
    errs = []
    if "DN" not in row or not isinstance(row["DN"], (int, float)) or row["DN"] <= 0:
        errs.append(f"pn_classes/{class_key} row {index}: DN must be a positive number")
    for col in _VALUE_COLS:
        errs.extend(validate_positive_numeric_or_null(f"pn_classes/{class_key}", index, row, col, required=True))
    if "NumBolts" not in row or not isinstance(row["NumBolts"], int) or row["NumBolts"] <= 0:
        errs.append(f"pn_classes/{class_key} row {index}: NumBolts must be a positive integer")
    if "BoltSize" not in row or not isinstance(row["BoltSize"], str) or not row["BoltSize"].strip():
        errs.append(f"pn_classes/{class_key} row {index}: BoltSize must be a non-empty string")
    return errs


def _prov(source_file_rel, class_key, original_field):
    return EngineeringFactProvenance(
        source_name="KGPE EN 1092-1 AI-Readable dataset", source_type="internal_dataset",
        standard_designation=STANDARD_ID, source_file=source_file_rel, original_field=original_field,
        transcription_method=f"Programmatic ingestion (kgpe/contract/adapters/en_1092_flanges.py) from pn_classes/{class_key}",
        verification_method=_CONFIDENCE_BY_CLASS.get(class_key, _DEFAULT_CONFIDENCE),
    )


def _build_facts(row, class_key, source_file_rel):
    dn = normalize_dn(row["DN"])
    canon_class = normalize_pressure_class(class_key, RATING_SYSTEM_PN)
    applicability_kwargs = dict(product_family=VOC.PRODUCT_FAMILY_FLANGE, standard=STANDARD_ID,
                                flange_type="weld_neck", class_key=canon_class, dn=dn)
    facts = []
    field_map = [
        (VOC.DIM_OUTSIDE_DIAMETER, "OD_mm"),
        (VOC.DIM_BOLT_CIRCLE_DIAMETER, "BoltCircle_mm"),
        (VOC.DIM_BOLT_HOLE_DIAMETER, "BoltHoleDia_mm"),
        (VOC.DIM_FLANGE_THICKNESS_WELD_NECK, "Thickness_mm"),
    ]
    for dim_name, col in field_map:
        facts.append(EngineeringFact(
            dimension_name=dim_name, value=Quantity(float(row[col]), LENGTH_MM),
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


def ingest_en_1092_flanges(registry=None):
    """Reads, validates, and ingests the EN 1092-1 JSON. Deterministic
    order: PN classes in fixed ascending-pressure order (PN6..PN100, not
    dict iteration order), rows sorted by DN sort key."""
    if registry is None:
        registry = FactRegistry()

    data, source_file_rel = _load_source()
    _validate_top_level(data)

    all_errors = []
    for class_key in CLASS_KEYS:
        rows = data["pn_classes"][class_key]
        for i, row in enumerate(rows):
            all_errors.extend(_validate_row(class_key, i, row))
        all_errors.extend(check_duplicate_key(f"pn_classes/{class_key}", rows, lambda r: normalize_dn(r["DN"])))

    if all_errors:
        raise SourceValidationError(
            f"EN 1092-1 source failed validation ({len(all_errors)} problem(s)): " + " | ".join(all_errors)
        )

    ingested = []
    for class_key in CLASS_KEYS:
        rows = sorted(data["pn_classes"][class_key], key=lambda r: dn_sort_key(normalize_dn(r["DN"])))
        for row in rows:
            for fact in _build_facts(row, class_key, source_file_rel):
                registry.add_checked(fact)
                ingested.append(fact)

    return registry, ingested
