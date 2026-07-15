# -*- coding: utf-8 -*-
"""
kgpe.contract.adapters.asme_b36_pipes
=========================================
Source adapter (Prompt 6): reads the EXISTING ASME pipe JSON that
`kgpe/dimension_library.py` already reads (same file, same path
resolution - `dimension_library.DIMLIB_ROOT` +
`dimension_library.PIPE_FILES["ASME_B36"]`), validates it, and converts
each row/schedule-cell into canonical EngineeringFact records.

ACTUAL SOURCE STRUCTURE FOUND (Prompt 6 Sec.2 - inspected before writing
this adapter, not assumed from the prompt text):
  - ONE JSON file covers BOTH standards, in two SEPARATE top-level arrays:
    "B36_10M_wall_thickness_mm" (36 rows, NPS 1/8-48, 14 schedule columns:
    Sch5/10/20/30/40/STD/60/80/XS/100/120/140/160/XXS) and
    "B36_19M_wall_thickness_mm" (18 rows, NPS 1/8-12, 4 schedule columns:
    Sch5S/10S/40S/80S).
  - The file's own top-level "standards" dict names them explicitly as
    "ASME_B36.10M" and "ASME_B36.19M" - used verbatim here as the
    canonical `standard` identity (see normalization.normalize_asme_pipe_standard).
    This is deliberately NOT the same string as dimension_library.py's
    PIPE_FILES registry key "ASME_B36" - that key only selects which JSON
    file to load for the existing combined live lookup and is untouched.
  - Every NPS in the B36.19M range (1/8-12) ALSO has a row in the B36.10M
    table, with an IDENTICAL OD_mm value at every single overlapping NPS
    (confirmed by inspection, not assumed) - expected, since OD is
    governed by NPS alone, independent of pipe wall composition.
  - Sch5/Sch5S and Sch10/Sch10S are equal everywhere both are defined in
    this source, but Sch40/Sch40S and Sch80/Sch80S DIVERGE starting at
    NPS12 and NPS10 respectively (e.g. NPS12: Sch40=10.31mm vs
    Sch40S=9.53mm) - concrete, source-confirmed proof that these are NOT
    interchangeable aliases, just coincidentally equal at smaller sizes
    (Prompt 6 Sec.6) - never collapsed here.
  - Many schedule cells are JSON `null` (explicitly not applicable at
    that NPS/schedule combination) - these do NOT become EngineeringFact
    records (Sec.9.B) - they are absent, not zero, not quarantined.
  - Unlike the ASME B16.5 flange source, this file has NO top-level
    "units" key - units are conveyed only via each column name's "_mm"
    suffix. Validation here checks the ACTUAL structure of this file, not
    the flange file's structure.
  - KNOWN LIMITATION IN THE EXISTING LIVE `dimension_library.get_pipe()`
    (confirmed by direct testing, not fixed here - out of scope, and
    "preserve existing dimension_library.py behaviour" is a hard
    constraint): it concatenates B36_10M rows before B36_19M rows and
    takes the FIRST row matching a given NPS. For every NPS in 1/8-12
    (all of B36.19M's range), that is always the B36_10M row, which has
    no Sch*S keys at all - so `dl.get_pipe("ASME_B36", <nps in 1/8-12>,
    "Sch40S")` (or any S-suffix schedule) ALWAYS raises DimNotFound, even
    though the value genuinely exists in the B36_19M table. This means
    none of this adapter's S-suffix wall-thickness facts are comparable
    against the live lookup - see the Prompt 6 report's cross-check
    section for exact counts and this explanation.

This module contains no rendering logic and never touches the CRM HTML.
"""
import json
import os

from .. import vocabulary as VOC
from .. import verification as V
from ..applicability import Applicability
from ..units import Quantity, LENGTH_MM
from ..normalization import (
    normalize_nps, nps_sort_key, normalize_schedule, normalize_asme_pipe_standard,
    ASME_B36_10M, ASME_B36_19M,
)
from ..model import EngineeringFact, EngineeringFactProvenance, FactRegistry, SourceValidationError
from ... import dimension_library as dl

REQUIRED_TOP_KEYS = ("standards", "columns_B36_10M", "columns_B36_19M",
                     "B36_10M_wall_thickness_mm", "B36_19M_wall_thickness_mm")
_TABLE_10M = "B36_10M_wall_thickness_mm"
_TABLE_19M = "B36_19M_wall_thickness_mm"
_COLUMNS_10M_KEY = "columns_B36_10M"
_COLUMNS_19M_KEY = "columns_B36_19M"


def _load_source():
    rel_path = dl.PIPE_FILES["ASME_B36"]
    full_path = os.path.join(dl.DIMLIB_ROOT, rel_path)
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError as e:
        raise SourceValidationError(f"ASME pipe source file not found at {full_path!r}") from e
    except json.JSONDecodeError as e:
        raise SourceValidationError(f"ASME pipe source file is not valid JSON: {e}") from e
    return data, rel_path


def _validate_top_level(data):
    errors = [f"Missing required top-level key {k!r}" for k in REQUIRED_TOP_KEYS if k not in data]
    if errors:
        raise SourceValidationError("ASME pipe source failed top-level validation: " + "; ".join(errors))
    standards = data["standards"]
    if not isinstance(standards, dict) or ASME_B36_10M not in standards or ASME_B36_19M not in standards:
        raise SourceValidationError(
            f"ASME pipe source 'standards' dict must contain both {ASME_B36_10M!r} and {ASME_B36_19M!r}, "
            f"got keys {list(standards.keys()) if isinstance(standards, dict) else standards!r}"
        )
    for table_key in (_TABLE_10M, _TABLE_19M):
        if not isinstance(data[table_key], list):
            raise SourceValidationError(f"ASME pipe source: {table_key!r} must be a list of rows")
    for cols_key in (_COLUMNS_10M_KEY, _COLUMNS_19M_KEY):
        cols = data[cols_key]
        if not isinstance(cols, list) or len(cols) != len(set(cols)):
            raise SourceValidationError(f"ASME pipe source: {cols_key!r} must be a list of unique column names")


def _schedule_columns(data, columns_key):
    return [c for c in data[columns_key] if c not in ("NPS", "OD_mm")]


def _validate_row(table_label, index, row, schedule_cols):
    if not isinstance(row, dict):
        return [f"{table_label} row {index}: not an object, got {type(row).__name__}"]
    errs = []
    for required in ("NPS", "OD_mm"):
        if required not in row:
            errs.append(f"{table_label} row {index}: missing field {required!r}")
    if errs:
        return errs

    if not isinstance(row["NPS"], str) or not row["NPS"].strip():
        errs.append(f"{table_label} row {index}: NPS must be a non-empty string, got {row['NPS']!r}")
    else:
        try:
            normalize_nps(row["NPS"])
        except ValueError as e:
            errs.append(f"{table_label} row {index}: NPS {row['NPS']!r} could not be normalized: {e}")

    od = row["OD_mm"]
    if not isinstance(od, (int, float)) or isinstance(od, bool) or od <= 0:
        errs.append(f"{table_label} row {index}: OD_mm must be positive, got {od!r}")
        od = None

    for col in schedule_cols:
        if col not in row:
            errs.append(f"{table_label} row {index}: missing declared schedule column {col!r}")
            continue
        v = row[col]
        if v is None:
            continue  # explicitly unavailable at this NPS/schedule - valid, not an error (Sec.9.B)
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            errs.append(f"{table_label} row {index}: {col} must be numeric or null, got {v!r}")
            continue
        if v <= 0:
            errs.append(f"{table_label} row {index}: {col} must be positive, got {v!r}")
        elif od is not None and v >= od / 2:
            errs.append(f"{table_label} row {index}: {col}={v!r} is physically impossible "
                        f"(>= half the OD {od!r}) - would leave zero or negative bore")
    return errs


def _check_duplicate_nps(table_label, rows):
    seen = {}
    errs = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict) or not isinstance(row.get("NPS"), str):
            continue
        try:
            canon = normalize_nps(row["NPS"])
        except ValueError:
            continue  # already reported by _validate_row - not silently ignored, just not double-reported
        if canon in seen:
            errs.append(f"{table_label}: duplicate NPS {canon!r} at rows {seen[canon]} and {i}")
        else:
            seen[canon] = i
    return errs


def _build_od_fact(standard_id, row, source_file_rel, table_label):
    nps = normalize_nps(row["NPS"])
    applicability = Applicability(product_family=VOC.PRODUCT_FAMILY_PIPE, standard=standard_id, nps=nps)
    prov = EngineeringFactProvenance(
        source_name="KGPE ASME B36.10M/19M AI-Readable dataset",
        source_type="internal_dataset",
        standard_designation=standard_id,
        source_file=source_file_rel,
        original_field="OD_mm",
        transcription_method=f"Programmatic ingestion (kgpe/contract/adapters/asme_b36_pipes.py) from {table_label}",
        verification_method="OD_mm confirmed identical across the B36.10M and B36.19M tables at every "
                             "overlapping NPS in this source (Prompt 6 overlap analysis) - not a coincidence, "
                             "OD is governed by NPS alone regardless of pipe wall composition.",
    )
    return EngineeringFact(
        dimension_name=VOC.DIM_OUTSIDE_DIAMETER, value=Quantity(float(row["OD_mm"]), LENGTH_MM),
        applicability=applicability, verification_status=V.VERIFIED_AUTHORITATIVE, provenance=prov,
    )


def _build_wt_facts(standard_id, row, schedule_cols, source_file_rel, table_label):
    nps = normalize_nps(row["NPS"])
    facts = []
    for col in schedule_cols:
        value = row.get(col)
        if value is None:
            continue  # explicitly unavailable - no fact created, not zero, not quarantined (Sec.9.B)
        schedule = normalize_schedule(col)
        applicability = Applicability(product_family=VOC.PRODUCT_FAMILY_PIPE, standard=standard_id,
                                       nps=nps, schedule=schedule)
        prov = EngineeringFactProvenance(
            source_name="KGPE ASME B36.10M/19M AI-Readable dataset",
            source_type="internal_dataset",
            standard_designation=standard_id,
            source_file=source_file_rel,
            original_field=col,
            transcription_method=f"Programmatic ingestion (kgpe/contract/adapters/asme_b36_pipes.py) from {table_label}",
        )
        facts.append(EngineeringFact(
            dimension_name=VOC.DIM_WALL_THICKNESS, value=Quantity(float(value), LENGTH_MM),
            applicability=applicability, verification_status=V.VERIFIED_AUTHORITATIVE, provenance=prov,
        ))
    return facts


def ingest_asme_pipes(registry=None):
    """Reads, validates, and ingests the existing ASME B36.10M/19M pipe
    JSON into `registry` (a new FactRegistry if none given). Produces one
    outside-diameter fact per source row (per standard) and one
    wall-thickness fact per non-null schedule cell (per standard),
    keeping ASME_B36.10M and ASME_B36.19M as distinct `standard` values
    throughout - never merged.

    Deterministic order: B36.10M table before B36.19M, rows sorted by
    NPS's exact-rational sort key within each table, OD facts before
    wall-thickness facts, wall-thickness facts in the source's own
    declared column order.

    Returns (registry, ingested_facts). Raises SourceValidationError if
    the source is structurally malformed - all problems are collected
    before raising, across both tables."""
    if registry is None:
        registry = FactRegistry()

    data, source_file_rel = _load_source()
    _validate_top_level(data)

    schedule_cols_10m = _schedule_columns(data, _COLUMNS_10M_KEY)
    schedule_cols_19m = _schedule_columns(data, _COLUMNS_19M_KEY)

    all_errors = []
    for table_label, table_key, schedule_cols in (
        ("ASME_B36.10M table", _TABLE_10M, schedule_cols_10m),
        ("ASME_B36.19M table", _TABLE_19M, schedule_cols_19m),
    ):
        rows = data[table_key]
        for i, row in enumerate(rows):
            all_errors.extend(_validate_row(table_label, i, row, schedule_cols))
        all_errors.extend(_check_duplicate_nps(table_label, rows))
    if all_errors:
        raise SourceValidationError(
            f"ASME pipe source failed row-level validation ({len(all_errors)} problem(s)): "
            + " | ".join(all_errors)
        )

    ingested = []
    for table_label, table_key, schedule_cols, raw_standard in (
        ("ASME_B36.10M table", _TABLE_10M, schedule_cols_10m, ASME_B36_10M),
        ("ASME_B36.19M table", _TABLE_19M, schedule_cols_19m, ASME_B36_19M),
    ):
        standard_id = normalize_asme_pipe_standard(raw_standard)
        rows = sorted(data[table_key], key=lambda r: nps_sort_key(normalize_nps(r["NPS"])))

        for row in rows:
            od_fact = _build_od_fact(standard_id, row, source_file_rel, table_label)
            registry.add_checked(od_fact)
            ingested.append(od_fact)

        for row in rows:
            for wt_fact in _build_wt_facts(standard_id, row, schedule_cols, source_file_rel, table_label):
                registry.add_checked(wt_fact)
                ingested.append(wt_fact)

    return registry, ingested
