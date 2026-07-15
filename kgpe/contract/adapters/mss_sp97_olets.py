# -*- coding: utf-8 -*-
"""
kgpe.contract.adapters.mss_sp97_olets
=========================================
Source adapter (Prompt 8): MSS SP-97 integrally-reinforced forged
branch-outlet fittings (weldolet/sockolet/threadolet). Reads the
existing JSON dimension_library.py's OLET_FILES registry points at.

ACTUAL SOURCE STRUCTURE FOUND (inspected before writing this adapter):
  - The source's own primary_source text draws a hard line between TWO
    categorically different kinds of data in this one file, and this
    adapter preserves that line rather than treating "structured JSON"
    as automatically authoritative (Prompt 8 Sec.20):
      1. "weldolet_branch_outlet_height_official" - branch-outlet HEIGHT
         only, explicitly sourced from the official MSS SP-97-2006
         standard text itself. Ingested as VERIFIED_AUTHORITATIVE.
      2. "weldolet_size_on_size_STD_body_dims" /
         "sockolet_class3000_body_dims" / "threadolet_class3000_body_dims"
         - base OD, overall height, face-to-face length, bore, socket
         diameter. The source's own notes state PLAINLY these are NOT
         from the MSS SP-97 standard text - they are Bonney Forge (a
         manufacturer)'s own conformant catalog dimensions, proof-tested
         per the standard's Annex B, not standardized values themselves.
         Ingested as VERIFIED_MANUFACTURER_SPECIFIC with
         manufacturer_profile="Bonney Forge" - never silently promoted
         to VERIFIED_AUTHORITATIVE merely because the file format is the
         same AI-Readable JSON as the official table.
  - The official height table gives branch-outlet height as a function
    of RUN pipe NPS/DN + run schedule (STD/XS/Sch160) + configuration
    (Reducing vs Full/size-on-size) - it does NOT give an exact branch
    NPS (MSS SP-97 tables of this kind cover a *range* of branch sizes
    per configuration class, not one specific branch size) - so only
    `run_nps`/`dn` are populated here, never a fabricated `branch_nps`.
    Two rows (DN200/NPS8, DN250/NPS10, DN300/NPS12) have NO Sch160
    columns at all (not merely null) - handled as "column not present
    for this row", not an error.
  - The three body-dims tables are all "size-on-size" (weldolet) or
    branch-size-only (sockolet/threadolet, since socket/thread end
    sizing does not depend on the run pipe's size) - so weldolet body
    dims get run_nps == branch_nps == NPS (the table's own title states
    "size_on_size"), while sockolet/threadolet get only `branch_nps`
    (the source does not tie these to any specific run size - not
    fabricated here).
  - Class 9000 and the weldolet reducing-configuration body-dims table
    are explicitly NOT in this source (documented gaps, not silently
    filled). Latrolet/Elbolet (45-degree outlets) were "researched but
    not transcribed" per the source's own notes - genuinely absent, not
    a migration omission on this adapter's part.
  - Per Prompt 8 Sec.9's explicit instruction, this adapter does NOT
    ingest the legacy CRM's JS nipoflange proportional-geometry
    construction as authoritative MSS data - it never reads any CRM
    file at all, only this structured JSON.
"""
from .. import vocabulary as VOC
from .. import verification as V
from ..applicability import Applicability
from ..units import Quantity, LENGTH_MM
from ..normalization import normalize_nps, nps_sort_key, normalize_dn, normalize_schedule
from ..model import EngineeringFact, EngineeringFactProvenance, FactRegistry, SourceValidationError
from ... import dimension_library as dl
from ._shared import load_json_source, validate_positive_numeric_or_null, check_duplicate_key

STANDARD_ID = "MSS_SP97"  # matches dimension_library.OLET_FILES key verbatim

REQUIRED_TOP_KEYS = ("standard", "tables")
REQUIRED_TABLES = ("weldolet_branch_outlet_height_official", "weldolet_size_on_size_STD_body_dims",
                   "sockolet_class3000_body_dims", "threadolet_class3000_body_dims")

_HEIGHT_SCHEDULE_CONFIG_COLS = (
    ("STD_Reducing_mm", "STD", VOC.FITTING_TYPE_WELDOLET_REDUCING),
    ("STD_Full_mm", "STD", VOC.FITTING_TYPE_WELDOLET_FULL),
    ("XS_Reducing_mm", "XS", VOC.FITTING_TYPE_WELDOLET_REDUCING),
    ("XS_Full_mm", "XS", VOC.FITTING_TYPE_WELDOLET_FULL),
    ("Sch160_Reducing_mm", "160", VOC.FITTING_TYPE_WELDOLET_REDUCING),
    ("Sch160_Full_mm", "160", VOC.FITTING_TYPE_WELDOLET_FULL),
)

_BODY_DIM_COLS_COMMON = [
    (VOC.DIM_OLET_HEIGHT, "A_height_mm"), (VOC.DIM_OLET_FACE_TO_FACE, "B_faceToFace_mm"),
    (VOC.DIM_OLET_BASE_OUTSIDE_DIAMETER, "C_baseOD_mm"), (VOC.DIM_OLET_BORE_DIAMETER, "D_bore_mm"),
]

MANUFACTURER_PROFILE = "Bonney Forge"


def _load_source():
    return load_json_source(dl.DIMLIB_ROOT, dl.OLET_FILES[STANDARD_ID])


def _validate_top_level(data):
    errors = [f"Missing required top-level key {k!r}" for k in REQUIRED_TOP_KEYS if k not in data]
    if errors:
        raise SourceValidationError("MSS SP-97 source failed top-level validation: " + "; ".join(errors))
    for table in REQUIRED_TABLES:
        if table not in data["tables"] or "rows" not in data["tables"][table]:
            errors.append(f"Missing required table {table!r} (or its 'rows' list)")
    if errors:
        raise SourceValidationError("MSS SP-97 source failed table-structure validation: " + "; ".join(errors))


def _validate_height_row(index, row):
    errs = []
    if "DN" not in row or not isinstance(row["DN"], (int, float)) or row["DN"] <= 0:
        errs.append(f"weldolet_branch_outlet_height_official row {index}: DN must be a positive number")
    if "NPS" not in row or not isinstance(row["NPS"], str) or not row["NPS"].strip():
        errs.append(f"weldolet_branch_outlet_height_official row {index}: NPS must be a non-empty string")
    else:
        try:
            normalize_nps(row["NPS"])
        except ValueError as e:
            errs.append(f"weldolet_branch_outlet_height_official row {index}: NPS invalid: {e}")
    for col, _sched, _ft in _HEIGHT_SCHEDULE_CONFIG_COLS:
        if col in row:
            errs.extend(validate_positive_numeric_or_null("weldolet_branch_outlet_height_official", index, row, col))
    return errs


def _validate_body_dim_row(section_label, index, row, extra_cols=()):
    errs = []
    if "NPS" not in row or not isinstance(row["NPS"], str) or not row["NPS"].strip():
        errs.append(f"{section_label} row {index}: NPS must be a non-empty string")
    else:
        try:
            normalize_nps(row["NPS"])
        except ValueError as e:
            errs.append(f"{section_label} row {index}: NPS invalid: {e}")
    for _dim, col in _BODY_DIM_COLS_COMMON + list(extra_cols):
        errs.extend(validate_positive_numeric_or_null(section_label, index, row, col, required=True))
    return errs


def _prov(source_file_rel, table_label, original_field, manufacturer_profile=None, extra_note=None,
          verification_method=None):
    return EngineeringFactProvenance(
        source_name="KGPE MSS SP-97 AI-Readable dataset", source_type="internal_dataset",
        standard_designation=STANDARD_ID, source_file=source_file_rel, original_field=original_field,
        transcription_method=f"Programmatic ingestion (kgpe/contract/adapters/mss_sp97_olets.py) from {table_label}",
        verification_method=verification_method,
        notes=extra_note,
    )


def _build_height_facts(row, source_file_rel):
    facts = []
    run_nps = normalize_nps(row["NPS"])
    dn = normalize_dn(row["DN"])
    for col, sched_raw, fitting_type in _HEIGHT_SCHEDULE_CONFIG_COLS:
        if col not in row or row[col] is None:
            continue
        schedule = normalize_schedule(sched_raw)
        applicability = Applicability(product_family=VOC.PRODUCT_FAMILY_OLET, standard=STANDARD_ID,
                                       fitting_type=fitting_type, run_nps=run_nps, dn=dn, schedule=schedule)
        prov = _prov(source_file_rel, "weldolet_branch_outlet_height_official", col,
                     verification_method="Sourced from the official MSS SP-97-2006 standard text (htpipe.com "
                                          "mirror) - the one table in this source explicitly NOT manufacturer "
                                          "catalog data.")
        facts.append(EngineeringFact(dimension_name=VOC.DIM_BRANCH_OUTLET_HEIGHT, value=Quantity(float(row[col]), LENGTH_MM),
                                      applicability=applicability, verification_status=V.VERIFIED_AUTHORITATIVE,
                                      provenance=prov))
    return facts


def _build_weldolet_body_facts(row, source_file_rel):
    nps = normalize_nps(row["NPS"])
    facts = []
    applicability = Applicability(product_family=VOC.PRODUCT_FAMILY_OLET, standard=STANDARD_ID,
                                   fitting_type=VOC.FITTING_TYPE_WELDOLET, run_nps=nps, branch_nps=nps,
                                   manufacturer_profile=MANUFACTURER_PROFILE)
    note = ("Size-on-size (run NPS == branch NPS) per this table's own title - not fabricated; the source "
            "does not provide a weldolet reducing-configuration body-dims table.")
    for dim_name, col in _BODY_DIM_COLS_COMMON:
        prov = _prov(source_file_rel, "weldolet_size_on_size_STD_body_dims", col,
                     manufacturer_profile=MANUFACTURER_PROFILE, extra_note=note)
        facts.append(EngineeringFact(dimension_name=dim_name, value=Quantity(float(row[col]), LENGTH_MM),
                                      applicability=applicability, verification_status=V.VERIFIED_MANUFACTURER_SPECIFIC,
                                      provenance=prov))
    return facts


def _build_sockolet_body_facts(row, source_file_rel):
    nps = normalize_nps(row["NPS"])
    facts = []
    applicability = Applicability(product_family=VOC.PRODUCT_FAMILY_OLET, standard=STANDARD_ID,
                                   fitting_type=VOC.FITTING_TYPE_SOCKOLET, branch_nps=nps,
                                   manufacturer_profile=MANUFACTURER_PROFILE)
    cols = _BODY_DIM_COLS_COMMON + [(VOC.DIM_OLET_SOCKET_DIAMETER, "E_socketDia_mm")]
    for dim_name, col in cols:
        prov = _prov(source_file_rel, "sockolet_class3000_body_dims", col, manufacturer_profile=MANUFACTURER_PROFILE)
        facts.append(EngineeringFact(dimension_name=dim_name, value=Quantity(float(row[col]), LENGTH_MM),
                                      applicability=applicability, verification_status=V.VERIFIED_MANUFACTURER_SPECIFIC,
                                      provenance=prov))
    return facts


def _build_threadolet_body_facts(row, source_file_rel):
    nps = normalize_nps(row["NPS"])
    facts = []
    applicability = Applicability(product_family=VOC.PRODUCT_FAMILY_OLET, standard=STANDARD_ID,
                                   fitting_type=VOC.FITTING_TYPE_THREADOLET, branch_nps=nps,
                                   manufacturer_profile=MANUFACTURER_PROFILE)
    for dim_name, col in _BODY_DIM_COLS_COMMON:
        prov = _prov(source_file_rel, "threadolet_class3000_body_dims", col, manufacturer_profile=MANUFACTURER_PROFILE)
        facts.append(EngineeringFact(dimension_name=dim_name, value=Quantity(float(row[col]), LENGTH_MM),
                                      applicability=applicability, verification_status=V.VERIFIED_MANUFACTURER_SPECIFIC,
                                      provenance=prov))
    return facts


def ingest_mss_sp97_olets(registry=None):
    """Reads, validates, and ingests the MSS SP-97 JSON. Deterministic
    order: weldolet_branch_outlet_height_official -> weldolet body dims
    -> sockolet body dims -> threadolet body dims, each sorted by NPS
    sort key. The official height table's facts are VERIFIED_AUTHORITATIVE;
    all three body-dims tables are VERIFIED_MANUFACTURER_SPECIFIC (Bonney
    Forge) - a real, source-driven distinction, not a downgrade applied
    for convenience (Prompt 8 Sec.9/20)."""
    if registry is None:
        registry = FactRegistry()

    data, source_file_rel = _load_source()
    _validate_top_level(data)

    tables = data["tables"]
    height_rows = tables["weldolet_branch_outlet_height_official"]["rows"]
    weldolet_rows = tables["weldolet_size_on_size_STD_body_dims"]["rows"]
    sockolet_rows = tables["sockolet_class3000_body_dims"]["rows"]
    threadolet_rows = tables["threadolet_class3000_body_dims"]["rows"]

    all_errors = []
    for i, row in enumerate(height_rows):
        all_errors.extend(_validate_height_row(i, row))
    all_errors.extend(check_duplicate_key("weldolet_branch_outlet_height_official", height_rows,
                                          lambda r: normalize_nps(r["NPS"])))

    for i, row in enumerate(weldolet_rows):
        all_errors.extend(_validate_body_dim_row("weldolet_size_on_size_STD_body_dims", i, row))
    all_errors.extend(check_duplicate_key("weldolet_size_on_size_STD_body_dims", weldolet_rows,
                                          lambda r: normalize_nps(r["NPS"])))

    for i, row in enumerate(sockolet_rows):
        all_errors.extend(_validate_body_dim_row("sockolet_class3000_body_dims", i, row,
                                                  extra_cols=[(VOC.DIM_OLET_SOCKET_DIAMETER, "E_socketDia_mm")]))
    all_errors.extend(check_duplicate_key("sockolet_class3000_body_dims", sockolet_rows,
                                          lambda r: normalize_nps(r["NPS"])))

    for i, row in enumerate(threadolet_rows):
        all_errors.extend(_validate_body_dim_row("threadolet_class3000_body_dims", i, row))
    all_errors.extend(check_duplicate_key("threadolet_class3000_body_dims", threadolet_rows,
                                          lambda r: normalize_nps(r["NPS"])))

    if all_errors:
        raise SourceValidationError(
            f"MSS SP-97 source failed validation ({len(all_errors)} problem(s)): " + " | ".join(all_errors)
        )

    ingested = []

    def _sorted(rows):
        return sorted(rows, key=lambda r: nps_sort_key(normalize_nps(r["NPS"])))

    for row in _sorted(height_rows):
        for fact in _build_height_facts(row, source_file_rel):
            registry.add_checked(fact)
            ingested.append(fact)

    for row in _sorted(weldolet_rows):
        for fact in _build_weldolet_body_facts(row, source_file_rel):
            registry.add_checked(fact)
            ingested.append(fact)

    for row in _sorted(sockolet_rows):
        for fact in _build_sockolet_body_facts(row, source_file_rel):
            registry.add_checked(fact)
            ingested.append(fact)

    for row in _sorted(threadolet_rows):
        for fact in _build_threadolet_body_facts(row, source_file_rel):
            registry.add_checked(fact)
            ingested.append(fact)

    return registry, ingested
