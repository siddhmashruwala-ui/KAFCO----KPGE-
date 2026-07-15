# -*- coding: utf-8 -*-
"""
kgpe.contract.adapters.jis_pipes
====================================
Source adapter (Prompt 8): JIS G3452 (SGP, ordinary piping) / JIS G3454
(STPG, pressure-service carbon steel) / JIS G3459 (SUS, stainless) steel
pipes. Reads the existing JSON dimension_library.py's
PIPE_FILES["JIS_G3452_3454_3459"] points at.

ACTUAL SOURCE STRUCTURE FOUND: one file, "tables" dict with THREE
sub-tables, each its own genuinely distinct steel-pipe standard - not
one standard with three schedule options. Mirroring the Prompt 6 ASME
B36.10M/19M treatment, each sub-table gets its OWN `standard` identity
(JIS_G3452 / JIS_G3454 / JIS_G3459 - module constants below), never a
merged "JIS pipe" identity:
  - SGP_G3452_ordinary_piping (24 rows, A_mm 6-500): single WallThk_mm
    column - SGP has no schedule concept at all (`schedule` stays None).
  - STPG_G3454_pressure_service_carbon (20 rows, A_mm 6-400): Sch10/20/
    30/40/60/80 columns, heavily null at small sizes (matches the real
    standard - not every schedule is defined at every size).
  - SUS_G3459_stainless (19 rows, A_mm 6-300... plus 350/400 with only
    Sch40/Sch80 populated): Sch5S/10S/20S/40/80 columns.
  - OD_mm is present in and IDENTICAL across all three sub-tables for
    every matching A-size (confirmed by inspection) - each sub-table
    still gets its own OD fact under its own `standard` identity (same
    value, different identity - Prompt 8 Sec.14, proven by test, not
    silently merged).
  - STPG's "Sch40"/"Sch80" and SUS's "Sch40"/"Sch80" are the SAME
    schedule designation string under DIFFERENT `standard` values - also
    same-value-different-identity, not a conflict (confirmed: every
    matching A-size gives an identical wall thickness for STPG vs SUS at
    Sch40/Sch80 in this source, which is itself an interesting
    consistency data point, not assumed).

PROVENANCE / CONFIDENCE NOTE (Prompt 8 Sec.20): the source's own notes
grade confidence per sub-table - SGP "2 independent sources... HIGH
CONFIDENCE"; STPG "only 1 clean full-table source... MODERATE
CONFIDENCE, recommend a second full-table cross-check"; SUS "4 sources
cross-checked... HIGH CONFIDENCE" (Sch120/160 exist in the real standard
but could not be reliably extracted - NOT included, a genuine gap, not
filled here). All three are ingested as VERIFIED_AUTHORITATIVE (matching
this project's established tier for AI-Readable JSON standard files),
carrying the exact confidence-tier text honestly in provenance.

KNOWN PRE-EXISTING LIVE-LOOKUP LIMITATION (documented, not fixed - same
class of issue as Prompt 6's B36.10M/19M finding): dimension_library.
get_pipe("JIS_G3452_3454_3459", ...) flattens all three sub-tables into
one list and returns the first row where the requested schedule KEY
merely exists (non-null) - since STPG and SUS both declare literal
"Sch40"/"Sch80" keys, and STPG's table is concatenated first, the live
lookup can never reach SUS's Sch40/Sch80 values for any A-size STPG also
defines them at. This adapter does not touch dimension_library.py.
"""
from .. import vocabulary as VOC
from .. import verification as V
from ..applicability import Applicability
from ..units import Quantity, LENGTH_MM
from ..normalization import normalize_jis_size, jis_size_sort_key, normalize_schedule
from ..model import EngineeringFact, EngineeringFactProvenance, FactRegistry, SourceValidationError
from ... import dimension_library as dl
from ._shared import load_json_source, validate_positive_numeric_or_null, check_duplicate_key

FILE_STANDARD_KEY = "JIS_G3452_3454_3459"  # matches dimension_library.PIPE_FILES key verbatim
JIS_G3452 = "JIS_G3452"  # SGP
JIS_G3454 = "JIS_G3454"  # STPG
JIS_G3459 = "JIS_G3459"  # SUS

_SGP_TABLE = "SGP_G3452_ordinary_piping"
_STPG_TABLE = "STPG_G3454_pressure_service_carbon"
_SUS_TABLE = "SUS_G3459_stainless"

_STPG_SCHEDULE_COLS = ["Sch10", "Sch20", "Sch30", "Sch40", "Sch60", "Sch80"]
_SUS_SCHEDULE_COLS = ["Sch5S", "Sch10S", "Sch20S", "Sch40", "Sch80"]

_CONFIDENCE_NOTES = {
    JIS_G3452: "2 independent sources (alpinepipe.com, union-steels.com) agreed exactly - HIGH CONFIDENCE.",
    JIS_G3454: ("Only 1 clean full-table source (emirerristeel.com) - MODERATE CONFIDENCE; a conflicting "
               "AI-summarized fragment was rejected as unreliable (see source notes). Recommend a second "
               "full-table cross-check before using for a critical quote."),
    JIS_G3459: ("4 sources cross-checked, consistent on Sch5S/10S/20S/40; Sch80 confirmed by 2 sources - "
               "HIGH CONFIDENCE. Sch120/160 exist in the real standard but could not be reliably extracted "
               "(source PDF OCR corrupted) - not included in this file, a genuine documented gap."),
}


def _load_source():
    return load_json_source(dl.DIMLIB_ROOT, dl.PIPE_FILES[FILE_STANDARD_KEY])


def _validate_top_level(data):
    if "tables" not in data or not isinstance(data["tables"], dict):
        raise SourceValidationError("JIS pipe source missing top-level 'tables' dict")
    missing = [t for t in (_SGP_TABLE, _STPG_TABLE, _SUS_TABLE) if t not in data["tables"]]
    if missing:
        raise SourceValidationError(f"JIS pipe source missing table(s): {missing}")
    for t in (_SGP_TABLE, _STPG_TABLE, _SUS_TABLE):
        if "rows" not in data["tables"][t]:
            raise SourceValidationError(f"JIS pipe source: table {t!r} missing 'rows'")


def _validate_row(table_label, index, row, schedule_cols):
    errs = []
    if "A_mm" not in row or not isinstance(row["A_mm"], (int, float)) or row["A_mm"] <= 0:
        errs.append(f"{table_label} row {index}: A_mm must be a positive number")
    errs.extend(validate_positive_numeric_or_null(table_label, index, row, "OD_mm", required=True))
    for col in schedule_cols:
        errs.extend(validate_positive_numeric_or_null(table_label, index, row, col, required=False))
    return errs


def _prov(source_file_rel, standard, table_label, original_field):
    return EngineeringFactProvenance(
        source_name="KGPE JIS Pipes AI-Readable dataset", source_type="internal_dataset",
        standard_designation=standard, source_file=source_file_rel, original_field=original_field,
        transcription_method=f"Programmatic ingestion (kgpe/contract/adapters/jis_pipes.py) from {table_label}",
        verification_method=_CONFIDENCE_NOTES[standard],
    )


def _od_fact(row, standard, table_label, source_file_rel):
    jis_size = normalize_jis_size(row["A_mm"])
    applicability = Applicability(product_family=VOC.PRODUCT_FAMILY_PIPE, standard=standard, jis_size=jis_size)
    return EngineeringFact(dimension_name=VOC.DIM_OUTSIDE_DIAMETER, value=Quantity(float(row["OD_mm"]), LENGTH_MM),
                           applicability=applicability, verification_status=V.VERIFIED_AUTHORITATIVE,
                           provenance=_prov(source_file_rel, standard, table_label, "OD_mm"))


def _build_sgp_facts(row, source_file_rel):
    jis_size = normalize_jis_size(row["A_mm"])
    facts = [_od_fact(row, JIS_G3452, _SGP_TABLE, source_file_rel)]
    applicability = Applicability(product_family=VOC.PRODUCT_FAMILY_PIPE, standard=JIS_G3452, jis_size=jis_size)
    facts.append(EngineeringFact(dimension_name=VOC.DIM_WALL_THICKNESS, value=Quantity(float(row["WallThk_mm"]), LENGTH_MM),
                                 applicability=applicability, verification_status=V.VERIFIED_AUTHORITATIVE,
                                 provenance=_prov(source_file_rel, JIS_G3452, _SGP_TABLE, "WallThk_mm")))
    return facts


def _build_schedule_facts(row, standard, table_label, schedule_cols, source_file_rel):
    jis_size = normalize_jis_size(row["A_mm"])
    facts = [_od_fact(row, standard, table_label, source_file_rel)]
    for col in schedule_cols:
        value = row.get(col)
        if value is None:
            continue
        schedule = normalize_schedule(col.replace("Sch", ""))
        applicability = Applicability(product_family=VOC.PRODUCT_FAMILY_PIPE, standard=standard,
                                       jis_size=jis_size, schedule=schedule)
        facts.append(EngineeringFact(dimension_name=VOC.DIM_WALL_THICKNESS, value=Quantity(float(value), LENGTH_MM),
                                     applicability=applicability, verification_status=V.VERIFIED_AUTHORITATIVE,
                                     provenance=_prov(source_file_rel, standard, table_label, col)))
    return facts


def ingest_jis_pipes(registry=None):
    """Reads, validates, and ingests the JIS pipe JSON. Deterministic
    order: SGP -> STPG -> SUS, rows sorted by JIS-size sort key within
    each."""
    if registry is None:
        registry = FactRegistry()

    data, source_file_rel = _load_source()
    _validate_top_level(data)

    sgp_rows = data["tables"][_SGP_TABLE]["rows"]
    stpg_rows = data["tables"][_STPG_TABLE]["rows"]
    sus_rows = data["tables"][_SUS_TABLE]["rows"]

    all_errors = []
    for i, row in enumerate(sgp_rows):
        all_errors.extend(_validate_row(_SGP_TABLE, i, row, ["WallThk_mm"]))
    all_errors.extend(check_duplicate_key(_SGP_TABLE, sgp_rows, lambda r: normalize_jis_size(r["A_mm"])))

    for i, row in enumerate(stpg_rows):
        all_errors.extend(_validate_row(_STPG_TABLE, i, row, _STPG_SCHEDULE_COLS))
    all_errors.extend(check_duplicate_key(_STPG_TABLE, stpg_rows, lambda r: normalize_jis_size(r["A_mm"])))

    for i, row in enumerate(sus_rows):
        all_errors.extend(_validate_row(_SUS_TABLE, i, row, _SUS_SCHEDULE_COLS))
    all_errors.extend(check_duplicate_key(_SUS_TABLE, sus_rows, lambda r: normalize_jis_size(r["A_mm"])))

    if all_errors:
        raise SourceValidationError(
            f"JIS pipe source failed validation ({len(all_errors)} problem(s)): " + " | ".join(all_errors)
        )

    ingested = []

    def _sorted(rows):
        return sorted(rows, key=lambda r: jis_size_sort_key(normalize_jis_size(r["A_mm"])))

    for row in _sorted(sgp_rows):
        for fact in _build_sgp_facts(row, source_file_rel):
            registry.add_checked(fact)
            ingested.append(fact)

    for row in _sorted(stpg_rows):
        for fact in _build_schedule_facts(row, JIS_G3454, _STPG_TABLE, _STPG_SCHEDULE_COLS, source_file_rel):
            registry.add_checked(fact)
            ingested.append(fact)

    for row in _sorted(sus_rows):
        for fact in _build_schedule_facts(row, JIS_G3459, _SUS_TABLE, _SUS_SCHEDULE_COLS, source_file_rel):
            registry.add_checked(fact)
            ingested.append(fact)

    return registry, ingested
