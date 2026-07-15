# -*- coding: utf-8 -*-
"""
kgpe.contract.adapters.en_pipes
===================================
Source adapter (Prompt 8): DIN 2448 (legacy) / DIN ISO 4200 OD series /
EN 10216 (seamless) / EN 10217 (welded) / EN 10220 (current dimensional
standard) steel pipes. Reads the existing JSON dimension_library.py's
PIPE_FILES["EN_10216_10217"] points at.

STANDARD-IDENTITY DECISION (Prompt 8 Sec.11 - preserve the source's own
combined designation, do not silently substitute one name for another):
this source's own top-level "standard" string names FIVE related
standards together ("DIN 2448 (legacy) / DIN ISO 4200 OD series /
EN 10216 (seamless) / EN 10217 (welded) / EN 10220 (current dimensional
standard)") and its own notes explain why: DIN 2448 is officially
superseded by EN 10220 for dimensions, material/testing now sits under
EN 10216/10217, but "DIN 2448 numbers are still widely quoted
commercially." This is a genuine combined-designation situation, not an
adapter judgement call - `standard="EN_10216_10217"` is used verbatim,
matching dimension_library.py's own pre-existing PIPE_FILES key for this
exact file (that key already reflects this same combined-standard
reality and was not invented here).

ACTUAL SOURCE STRUCTURE FOUND: one flat row list, columns DN, OD_mm,
Series1_mm..Series5_mm (wall-thickness bands, heavily null - especially
Series5, only populated at DN150+), Sch40_equiv_mm, Sch80_equiv_mm.

Series1-5 are a DIN/ISO legacy wall-thickness-band designation - NOT the
same rating system as ASME schedule, and never normalized through
normalize_schedule() (Prompt 8 Sec.4/7). normalize_wall_designation()
(new, Prompt 8) produces "EN_SERIES1".."EN_SERIES5", stored in
Applicability.schedule (a generic size-selector slot, not an ASME-only
field) - always EN_-prefixed so it can never collide with or be mistaken
for an ASME "SCH.." value even under careless comparison.

`Sch40_equiv_mm`/`Sch80_equiv_mm` are DELIBERATELY NOT INGESTED: the
source's own notes state these are "only populated where a direct
cross-check source gave them - use Series columns as the primary
reference, Sch equivalents as a rough ASME-comparison aid only." Treating
an explicitly-approximate cross-standard convenience column as an
authoritative EN wall-thickness fact would misrepresent it - excluded
here, not silently dropped (documented in the Prompt 8 report).
"""
from .. import vocabulary as VOC
from .. import verification as V
from ..applicability import Applicability
from ..units import Quantity, LENGTH_MM
from ..normalization import normalize_dn, dn_sort_key, normalize_wall_designation
from ..model import EngineeringFact, EngineeringFactProvenance, FactRegistry, SourceValidationError
from ... import dimension_library as dl
from ._shared import load_json_source, validate_positive_numeric_or_null, check_duplicate_key

FILE_STANDARD_KEY = "EN_10216_10217"  # matches dimension_library.PIPE_FILES key verbatim
STANDARD_ID = "EN_10216_10217"

_SERIES_COLS = ["Series1_mm", "Series2_mm", "Series3_mm", "Series4_mm", "Series5_mm"]

_CONFIDENCE_NOTE = ("All 3 sources (tubesolution.com, vmsteel.com, hu-steel.com) agree exactly on OD - "
                    "HIGH CONFIDENCE. Series1-5 wall-thickness bands from vmsteel.com's matrix.")


def _load_source():
    return load_json_source(dl.DIMLIB_ROOT, dl.PIPE_FILES[FILE_STANDARD_KEY])


def _validate_top_level(data):
    if "rows" not in data or not isinstance(data["rows"], list):
        raise SourceValidationError("EN pipe source missing top-level 'rows' list")


def _validate_row(index, row):
    errs = []
    if "DN" not in row or not isinstance(row["DN"], (int, float)) or row["DN"] <= 0:
        errs.append(f"row {index}: DN must be a positive number")
    errs.extend(validate_positive_numeric_or_null("rows", index, row, "OD_mm", required=True))
    for col in _SERIES_COLS:
        errs.extend(validate_positive_numeric_or_null("rows", index, row, col, required=False))
    return errs


def _prov(source_file_rel, original_field):
    return EngineeringFactProvenance(
        source_name="KGPE EN/DIN Pipes AI-Readable dataset", source_type="internal_dataset",
        standard_designation=STANDARD_ID, source_file=source_file_rel, original_field=original_field,
        transcription_method="Programmatic ingestion (kgpe/contract/adapters/en_pipes.py)",
        verification_method=_CONFIDENCE_NOTE,
    )


def _build_facts(row, source_file_rel):
    dn = normalize_dn(row["DN"])
    facts = [EngineeringFact(
        dimension_name=VOC.DIM_OUTSIDE_DIAMETER, value=Quantity(float(row["OD_mm"]), LENGTH_MM),
        applicability=Applicability(product_family=VOC.PRODUCT_FAMILY_PIPE, standard=STANDARD_ID, dn=dn),
        verification_status=V.VERIFIED_AUTHORITATIVE, provenance=_prov(source_file_rel, "OD_mm"))]
    for col in _SERIES_COLS:
        value = row.get(col)
        if value is None:
            continue
        series_n = col.replace("_mm", "")  # "Series1".."Series5"
        wall_designation = normalize_wall_designation(series_n)
        applicability = Applicability(product_family=VOC.PRODUCT_FAMILY_PIPE, standard=STANDARD_ID,
                                      dn=dn, schedule=wall_designation)
        facts.append(EngineeringFact(dimension_name=VOC.DIM_WALL_THICKNESS, value=Quantity(float(value), LENGTH_MM),
                                     applicability=applicability, verification_status=V.VERIFIED_AUTHORITATIVE,
                                     provenance=_prov(source_file_rel, col)))
    return facts


def ingest_en_pipes(registry=None):
    """Reads, validates, and ingests the EN/DIN pipe JSON. Deterministic
    order: rows sorted by DN sort key. Sch40_equiv_mm/Sch80_equiv_mm are
    deliberately not ingested - see module docstring."""
    if registry is None:
        registry = FactRegistry()

    data, source_file_rel = _load_source()
    _validate_top_level(data)

    rows = data["rows"]
    all_errors = []
    for i, row in enumerate(rows):
        all_errors.extend(_validate_row(i, row))
    all_errors.extend(check_duplicate_key("rows", rows, lambda r: normalize_dn(r["DN"])))

    if all_errors:
        raise SourceValidationError(
            f"EN pipe source failed validation ({len(all_errors)} problem(s)): " + " | ".join(all_errors)
        )

    ingested = []
    for row in sorted(rows, key=lambda r: dn_sort_key(normalize_dn(r["DN"]))):
        for fact in _build_facts(row, source_file_rel):
            registry.add_checked(fact)
            ingested.append(fact)

    return registry, ingested
