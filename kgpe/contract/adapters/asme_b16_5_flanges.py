# -*- coding: utf-8 -*-
"""
kgpe.contract.adapters.asme_b16_5_flanges
=============================================
Reference source adapter (Prompt 5): reads the EXISTING ASME B16.5 JSON
that `kgpe/dimension_library.py` already reads (same file, same path
resolution - `dimension_library.DIMLIB_ROOT` + `dimension_library.
FLANGE_FILES["ASME_B16.5"]` - so this adapter can never point at a
different file than the live lookups do), validates it, and converts each
row into canonical `EngineeringFact` records.

Pipeline: Source JSON -> (this module) -> EngineeringFact records ->
FactRegistry. This module contains NO rendering logic, no Three.js, and
never touches the CRM HTML - it only reads the AI-Readable JSON and the
kgpe.contract canonical model.

Fields ingested (only what Prompt 3 already verified as
VERIFIED_AUTHORITATIVE for this exact source file - nothing ingested
"because it exists"):
  OD_mm                  -> outside_diameter_mm            (flange_type=None: common to all flange types)
  Thickness_WeldNeck_mm  -> flange_thickness_weld_neck_mm   (flange_type="weld_neck": Prompt 3's T/TJ split)
  BoltCircle_mm          -> bolt_circle_diameter_mm         (flange_type=None)
  BoltHoleDia_mm         -> bolt_hole_diameter_mm           (flange_type=None)
  NumBolts               -> num_bolts                       (unit=count, not a length)
  BoltSize_in            -> bolt_size_designation            (unit=designation, not a length - Prompt 5 Sec.5)

NOT ingested: bore/raised-face/hub fields, because they simply are not
columns in this source file (confirmed Prompt 1/2) - there is nothing to
ingest, not a field being skipped.
"""
import json
import os
import re

from .. import vocabulary as VOC
from .. import verification as V
from ..applicability import Applicability
from ..units import Quantity, LENGTH_MM, COUNT, DESIGNATION
from ..normalization import normalize_nps, nps_sort_key, normalize_pressure_class
from ..vocabulary import RATING_SYSTEM_ASME_CLASS
from ..model import (
    EngineeringFact, EngineeringFactProvenance, FactRegistry, SourceValidationError,
)
from ... import dimension_library as dl

REQUIRED_TOP_KEYS = ("standard", "classes", "columns")
REQUIRED_ROW_FIELDS = ("NPS", "OD_mm", "Thickness_WeldNeck_mm", "BoltCircle_mm",
                       "BoltHoleDia_mm", "NumBolts", "BoltSize_in")

_EDITION_RE = re.compile(r"B16\.5-(\d{4})")

# (json_field, canonical_dimension_name, flange_type_applicability, verification_note)
_LENGTH_FIELD_SPECS = (
    (
        "OD_mm", VOC.DIM_OUTSIDE_DIAMETER, None,
        "Verified in KGPE Prompt 2/3: cross-checked against JS CRM FLG[] table, 0 mismatches "
        "across Class 150/300 (42 data points).",
    ),
    (
        "Thickness_WeldNeck_mm", VOC.DIM_FLANGE_THICKNESS_WELD_NECK, "weld_neck",
        "Verified in KGPE Prompt 3/40: matches Texas Flange's 'T' column exactly, 42/42 across "
        "Class 150/300. Confirmed DISTINCT from the non-weld-neck thickness figure found in the "
        "JS CRM (Texas Flange 'TJ' column) - these are two different ASME B16.5 dimensions, never merged.",
    ),
    (
        "BoltCircle_mm", VOC.DIM_BOLT_CIRCLE_DIAMETER, None,
        "Verified in KGPE Prompt 2/3: cross-checked against JS CRM FLG[] table, 0 mismatches.",
    ),
    (
        "BoltHoleDia_mm", VOC.DIM_BOLT_HOLE_DIAMETER, None,
        "Verified in KGPE Prompt 2/3: cross-checked against JS CRM BOLT_HOLE[] table, 0 mismatches.",
    ),
)


def _load_source():
    rel_path = dl.FLANGE_FILES["ASME_B16.5"]
    full_path = os.path.join(dl.DIMLIB_ROOT, rel_path)
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError as e:
        raise SourceValidationError(f"ASME B16.5 source file not found at {full_path!r}") from e
    except json.JSONDecodeError as e:
        raise SourceValidationError(f"ASME B16.5 source file is not valid JSON: {e}") from e
    return data, rel_path


def _validate_top_level(data):
    errors = [f"Missing required top-level key {k!r}" for k in REQUIRED_TOP_KEYS if k not in data]
    if "classes" in data and not isinstance(data["classes"], dict):
        errors.append("'classes' must be a dict of class_key -> list of rows")
    if errors:
        raise SourceValidationError("ASME B16.5 source failed top-level validation: " + "; ".join(errors))


def _validate_row(class_key, index, row):
    if not isinstance(row, dict):
        return [f"class {class_key} row {index}: not an object, got {type(row).__name__}"]
    errs = [f"class {class_key} row {index}: missing field {f!r}" for f in REQUIRED_ROW_FIELDS if f not in row]
    if errs:
        return errs
    if not isinstance(row["NPS"], str) or not row["NPS"].strip():
        errs.append(f"class {class_key} row {index}: NPS must be a non-empty string, got {row['NPS']!r}")
    for field in ("OD_mm", "Thickness_WeldNeck_mm", "BoltCircle_mm", "BoltHoleDia_mm"):
        v = row[field]
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            errs.append(f"class {class_key} row {index}: {field} must be numeric, got {v!r}")
        elif v <= 0:
            errs.append(f"class {class_key} row {index}: {field} must be positive, got {v!r}")
    nb = row["NumBolts"]
    if not isinstance(nb, int) or isinstance(nb, bool) or nb <= 0:
        errs.append(f"class {class_key} row {index}: NumBolts must be a positive integer, got {nb!r}")
    if not isinstance(row["BoltSize_in"], str) or not row["BoltSize_in"].strip():
        errs.append(f"class {class_key} row {index}: BoltSize_in must be a non-empty string, got {row['BoltSize_in']!r}")
    return errs


def _parse_standard_edition(standard_string):
    """Edition is read directly from the source file's own 'standard'
    header string (e.g. "ASME B16.5-2022 - ...") - never fabricated. If
    the string doesn't contain a recognizable edition, None is returned
    and left genuinely unknown (Prompt 5 Sec.10/Prompt 4 Sec.7)."""
    m = _EDITION_RE.search(standard_string or "")
    return m.group(1) if m else None


def _common_provenance_kwargs(source_file_rel, standard_edition, json_field, verification_note, extra_notes=None):
    return dict(
        source_name="KGPE ASME B16.5 AI-Readable dataset",
        source_type="internal_dataset",
        standard_designation="ASME B16.5",
        standard_edition=standard_edition,
        source_file=source_file_rel,
        original_field=json_field,
        transcription_method="Programmatic ingestion (kgpe/contract/adapters/asme_b16_5_flanges.py)",
        verification_method=verification_note,
        notes=extra_notes,
    )


def _build_facts_for_row(class_key_raw, row, source_file_rel, standard_edition):
    class_key = normalize_pressure_class(class_key_raw, RATING_SYSTEM_ASME_CLASS)
    nps = normalize_nps(row["NPS"])
    facts = []

    for json_field, dim_name, flange_type, verification_note in _LENGTH_FIELD_SPECS:
        applicability = Applicability(
            product_family=VOC.PRODUCT_FAMILY_FLANGE, standard="ASME_B16.5",
            flange_type=flange_type, class_key=class_key, nps=nps,
        )
        prov = EngineeringFactProvenance(**_common_provenance_kwargs(
            source_file_rel, standard_edition, json_field, verification_note))
        facts.append(EngineeringFact(
            dimension_name=dim_name, value=Quantity(float(row[json_field]), LENGTH_MM),
            applicability=applicability, verification_status=V.VERIFIED_AUTHORITATIVE, provenance=prov,
        ))

    facts.append(EngineeringFact(
        dimension_name=VOC.DIM_NUM_BOLTS,
        value=Quantity(int(row["NumBolts"]), COUNT),
        applicability=Applicability(product_family=VOC.PRODUCT_FAMILY_FLANGE, standard="ASME_B16.5",
                                     class_key=class_key, nps=nps),
        verification_status=V.VERIFIED_AUTHORITATIVE,
        provenance=EngineeringFactProvenance(**_common_provenance_kwargs(
            source_file_rel, standard_edition, "NumBolts",
            "Verified in KGPE Prompt 2/3: cross-checked against JS CRM FLG[] table, 0 mismatches.")),
    ))

    facts.append(EngineeringFact(
        dimension_name=VOC.DIM_BOLT_SIZE_DESIGNATION,
        value=Quantity(row["BoltSize_in"], DESIGNATION),
        applicability=Applicability(product_family=VOC.PRODUCT_FAMILY_FLANGE, standard="ASME_B16.5",
                                     class_key=class_key, nps=nps),
        verification_status=V.VERIFIED_AUTHORITATIVE,
        provenance=EngineeringFactProvenance(**_common_provenance_kwargs(
            source_file_rel, standard_edition, "BoltSize_in",
            "Verified in KGPE Prompt 2/3: cross-checked against JS CRM BOLT_DIA[] table, 0 mismatches.",
            extra_notes="Designation string (e.g. '5/8'), not a length quantity - deliberately not "
                        "forced into a mm field (Prompt 5 Sec.5).")),
    ))
    return facts


def ingest_asme_b16_5_flanges(registry=None):
    """Reads, validates, and ingests the existing ASME B16.5 AI-Readable
    JSON into `registry` (a new FactRegistry if none given), using
    add_checked() so any genuine duplicate/conflict is caught rather than
    silently overwritten. Ingestion order is deterministic (classes sorted
    numerically, rows sorted by NPS's exact-rational sort key) regardless
    of the source JSON's own dict ordering.

    Returns (registry, ingested_facts) where ingested_facts is the list of
    EngineeringFact objects added in this call, in deterministic order.

    Raises SourceValidationError if the source is structurally malformed -
    ALL row-level problems are collected before raising, so a single
    malformed row is never silently skipped and the caller gets a full
    diagnosable report in one exception."""
    if registry is None:
        registry = FactRegistry()

    data, source_file_rel = _load_source()
    _validate_top_level(data)
    standard_edition = _parse_standard_edition(data.get("standard", ""))

    all_errors = []
    for class_key_raw, rows in data["classes"].items():
        if not isinstance(rows, list):
            all_errors.append(f"class {class_key_raw}: expected a list of rows, got {type(rows).__name__}")
            continue
        for i, row in enumerate(rows):
            all_errors.extend(_validate_row(class_key_raw, i, row))
    if all_errors:
        raise SourceValidationError(
            f"ASME B16.5 source failed row-level validation ({len(all_errors)} problem(s)): "
            + " | ".join(all_errors)
        )

    ingested = []
    sorted_class_keys = sorted(data["classes"].keys(),
                                key=lambda k: int(normalize_pressure_class(k, RATING_SYSTEM_ASME_CLASS)))
    for class_key_raw in sorted_class_keys:
        rows = data["classes"][class_key_raw]
        sorted_rows = sorted(rows, key=lambda r: nps_sort_key(normalize_nps(r["NPS"])))
        for row in sorted_rows:
            for fact in _build_facts_for_row(class_key_raw, row, source_file_rel, standard_edition):
                registry.add_checked(fact)
                ingested.append(fact)

    return registry, ingested
