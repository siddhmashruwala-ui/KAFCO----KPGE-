# -*- coding: utf-8 -*-
"""
kgpe.contract.adapters.asme_b16_9_buttweld
==============================================
Source adapter (Prompt 7): reads the EXISTING ASME B16.9 JSON that
`kgpe/dimension_library.py` already reads (same file, same path
resolution - `dimension_library.DIMLIB_ROOT` +
`dimension_library.BUTTWELD_FILES["ASME_B16.9"]`), validates it, and
converts every row/subtype into canonical EngineeringFact records.

ACTUAL SOURCE STRUCTURE FOUND (Prompt 7 Sec.2 - inspected before writing
this adapter, not assumed):
  - Top-level "standard" string has NO edition year ("ASME B16.9 -
    Factory-Made Wrought Buttwelding Fittings") - unlike the B16.5 flange
    source, no standard_edition is ever set here; left None throughout,
    never fabricated.
  - FIVE product sections, each its own top-level key:
    "elbows_90_45_LR_3D" (32 rows, NPS 1/2-48; ONE row bundles FOUR elbow
      subtypes as separate columns: Elbow90LR, Elbow45LR, Elbow90_3D,
      Elbow45_3D - "3D" = 3x-diameter bend radius, a DISTINCT radius type
      from "LR"=long-radius/1.5x and "SR"=short-radius/1.0x. The two 3D
      columns are null at the smallest NPS; the two LR columns are always
      present.)
    "elbows_90_SR" (19 rows, NPS 1-24 only - a narrower range than every
      other section) - the 5th elbow subtype.
    "tees_straight_equal" (32 rows, NPS 1/2-48) - ONLY equal tees exist in
      this source; there is NO reducing-tee table, so no "tee_reducing"
      fitting type is defined here (would be invented, not migrated).
      Run_CtoE_C_mm and Outlet_CtoE_M_mm are EQUAL for most sizes but
      genuinely DIVERGE at NPS>=42 (e.g. NPS42: Run=762mm, Outlet=711mm) -
      confirmed by inspection, not assumed - so these are two distinct
      canonical dimensions, never collapsed.
    "caps" (32 rows, NPS 1/2-48) - has THREE dimensional columns, not one:
      Length_H_mm (always present), Length_H1_mm and WT_threshold_mm
      (both present together for NPS 1/2-24, both null together for
      NPS>=26 - confirmed paired, never one-without-the-other). H applies
      when the actual pipe wall thickness is below the threshold; H1
      applies at/above it - two genuinely different engineering facts,
      not a duplicate of the same "cap length".
    "reducers_concentric_eccentric" (rows keyed by a combined
      "NPS_Large-Small" display string, e.g. "6 - 4") - explicit
      large/small size roles, NOT a matrix. The section's own note states:
      "Same OD/length table applies to both concentric and eccentric
      reducers per B16.9" - i.e. this source does NOT distinguish
      concentric from eccentric at all; both product identities are
      derived here from the one shared table (Prompt 7 Sec.9 proof case).
  - KNOWN SOURCE INCONSISTENCY DISCOVERED DURING THIS PROMPT (not fixed
    here - see the Prompt 7 report's "Known Limitations" and the
    dedicated finding below): OD_mm is repeated across every section and
    is IDENTICAL for a given NPS everywhere EXCEPT at NPS8 (219.1mm in
    elbows/tees/caps/most reducer rows vs 219.0mm in one reducer row,
    "16 - 8") and NPS12 (323.8mm in elbows/tees/caps vs 323.9mm in every
    reducers_concentric_eccentric row referencing NPS12). This adapter
    does NOT silently pick a winner or average these - see
    "_find_od_conflicts()" below; both NPS8 and NPS12's OD facts are
    ingested as QUARANTINED_CONFLICT (both disagreeing values retained,
    neither usable as authoritative) rather than VERIFIED_AUTHORITATIVE,
    discovered live from real production data, not a test fixture.
  - No nulls found in tees or elbows_90_SR; nulls found (and expected) in
    elbows_90_45_LR_3D's two 3D columns at small NPS, and in caps'
    Length_H1_mm/WT_threshold_mm at NPS>=26.

This module contains no rendering logic and never touches the CRM HTML.
Does not ingest CAP_WT (manufacturer-specific, out of scope) or any
legacy JS table.
"""
import json
import os
import re
from collections import defaultdict

from .. import vocabulary as VOC
from .. import verification as V
from ..applicability import Applicability
from ..units import Quantity, LENGTH_MM
from ..normalization import normalize_nps, nps_sort_key
from ..model import EngineeringFact, EngineeringFactProvenance, FactRegistry, SourceValidationError
from ... import dimension_library as dl

STANDARD_ID = "ASME_B16.9"  # matches dimension_library.BUTTWELD_FILES key verbatim - reused, not reinvented

REQUIRED_TOP_KEYS = ("standard", "elbows_90_45_LR_3D", "elbows_90_SR",
                     "tees_straight_equal", "caps", "reducers_concentric_eccentric")

_ELBOW_LR_3D_SPEC = (
    ("Elbow90LR_CtoE_mm", VOC.FITTING_TYPE_ELBOW_90_LR, "90deg Long-Radius Elbow"),
    ("Elbow45LR_CtoE_mm", VOC.FITTING_TYPE_ELBOW_45_LR, "45deg Long-Radius Elbow"),
    ("Elbow90_3D_CtoE_mm", VOC.FITTING_TYPE_ELBOW_90_3D, "90deg 3D-Radius Elbow"),
    ("Elbow45_3D_CtoE_mm", VOC.FITTING_TYPE_ELBOW_45_3D, "45deg 3D-Radius Elbow"),
)

_REDUCER_PAIR_SPLIT_RE = re.compile(r"\s-\s")


def _load_source():
    rel_path = dl.BUTTWELD_FILES[STANDARD_ID]
    full_path = os.path.join(dl.DIMLIB_ROOT, rel_path)
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError as e:
        raise SourceValidationError(f"ASME B16.9 source file not found at {full_path!r}") from e
    except json.JSONDecodeError as e:
        raise SourceValidationError(f"ASME B16.9 source file is not valid JSON: {e}") from e
    return data, rel_path


def _validate_top_level(data):
    errors = [f"Missing required top-level key {k!r}" for k in REQUIRED_TOP_KEYS if k not in data]
    if errors:
        raise SourceValidationError("ASME B16.9 source failed top-level validation: " + "; ".join(errors))
    for section in ("elbows_90_45_LR_3D", "elbows_90_SR", "tees_straight_equal", "caps"):
        if "rows" not in data[section] or not isinstance(data[section]["rows"], list):
            raise SourceValidationError(f"ASME B16.9 source: section {section!r} must have a 'rows' list")
    if "rows" not in data["reducers_concentric_eccentric"] or not isinstance(
            data["reducers_concentric_eccentric"]["rows"], list):
        raise SourceValidationError("ASME B16.9 source: 'reducers_concentric_eccentric' must have a 'rows' list")


def _validate_single_size_row(section_label, index, row, value_cols, required_value_cols=()):
    if not isinstance(row, dict):
        return [f"{section_label} row {index}: not an object, got {type(row).__name__}"]
    errs = []
    for required in ("NPS", "OD_mm"):
        if required not in row:
            errs.append(f"{section_label} row {index}: missing field {required!r}")
    if errs:
        return errs

    if not isinstance(row["NPS"], str) or not row["NPS"].strip():
        errs.append(f"{section_label} row {index}: NPS must be a non-empty string, got {row['NPS']!r}")
    else:
        try:
            normalize_nps(row["NPS"])
        except ValueError as e:
            errs.append(f"{section_label} row {index}: NPS {row['NPS']!r} could not be normalized: {e}")

    od = row["OD_mm"]
    if not isinstance(od, (int, float)) or isinstance(od, bool) or od <= 0:
        errs.append(f"{section_label} row {index}: OD_mm must be positive, got {od!r}")

    for col in value_cols:
        if col not in row:
            errs.append(f"{section_label} row {index}: missing declared column {col!r}")
            continue
        v = row[col]
        if v is None:
            if col in required_value_cols:
                errs.append(f"{section_label} row {index}: {col} is required and must not be null")
            continue
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            errs.append(f"{section_label} row {index}: {col} must be numeric or null, got {v!r}")
        elif v <= 0:
            errs.append(f"{section_label} row {index}: {col} must be positive, got {v!r}")
    return errs


def _validate_cap_row(index, row):
    errs = _validate_single_size_row("caps", index, row,
                                      ["Length_H_mm", "Length_H1_mm", "WT_threshold_mm"],
                                      required_value_cols=["Length_H_mm"])
    if errs:
        return errs
    h1 = row.get("Length_H1_mm")
    thresh = row.get("WT_threshold_mm")
    if (h1 is None) != (thresh is None):
        errs.append(f"caps row {index}: Length_H1_mm and WT_threshold_mm must be present together or null "
                    f"together (got Length_H1_mm={h1!r}, WT_threshold_mm={thresh!r}) - inconsistent pairing")
    return errs


def _check_duplicate_nps(section_label, rows):
    seen = {}
    errs = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict) or not isinstance(row.get("NPS"), str):
            continue
        try:
            canon = normalize_nps(row["NPS"])
        except ValueError:
            continue  # already reported by the row validator
        if canon in seen:
            errs.append(f"{section_label}: duplicate NPS {canon!r} at rows {seen[canon]} and {i}")
        else:
            seen[canon] = i
    return errs


def _parse_reducer_pair(raw):
    """Splits the source's "LARGE - SMALL" display string (e.g.
    "1-1/4 - 1/2") on the ' - ' separator (space-hyphen-space) - safe
    because an individual NPS's own internal hyphen (e.g. "1-1/4") never
    has surrounding spaces, only the pair separator does."""
    parts = _REDUCER_PAIR_SPLIT_RE.split(str(raw).strip())
    if len(parts) != 2:
        raise ValueError(f"Cannot parse reducer NPS pair {raw!r} - expected 'LARGE - SMALL'")
    return normalize_nps(parts[0]), normalize_nps(parts[1])


def _validate_reducer_row(index, row):
    if not isinstance(row, dict):
        return [f"reducer row {index}: not an object"]
    errs = [f"reducer row {index}: missing field {f!r}" for f in
            ("NPS_Large-Small", "OD_Large_D_mm", "OD_Small_D1_mm", "Length_H_mm") if f not in row]
    if errs:
        return errs

    pair_raw = row["NPS_Large-Small"]
    if not isinstance(pair_raw, str) or not pair_raw.strip():
        errs.append(f"reducer row {index}: NPS_Large-Small must be a non-empty string, got {pair_raw!r}")
        return errs
    try:
        large_nps, small_nps = _parse_reducer_pair(pair_raw)
    except ValueError as e:
        errs.append(f"reducer row {index}: {e}")
        return errs

    large_key = nps_sort_key(large_nps)
    small_key = nps_sort_key(small_nps)
    if not (large_key > small_key):
        errs.append(f"reducer row {index}: large end {large_nps!r} must be strictly greater than small end "
                    f"{small_nps!r} (sort keys {large_key} vs {small_key}) - reversed or malformed reducer "
                    f"pair; not silently corrected or swapped")

    for field in ("OD_Large_D_mm", "OD_Small_D1_mm", "Length_H_mm"):
        v = row[field]
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v <= 0:
            errs.append(f"reducer row {index}: {field} must be positive, got {v!r}")
    return errs


def _check_duplicate_reducer_pairs(rows):
    seen = {}
    errs = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict) or not isinstance(row.get("NPS_Large-Small"), str):
            continue
        try:
            pair = _parse_reducer_pair(row["NPS_Large-Small"])
        except ValueError:
            continue
        if pair in seen:
            errs.append(f"reducers: duplicate pair {pair!r} at rows {seen[pair]} and {i}")
        else:
            seen[pair] = i
    return errs


# ---------------------------------------------------------------------------
# Cross-section OD consistency pre-scan (discovers the NPS8/NPS12
# inconsistency documented in the module docstring above, BEFORE any
# EngineeringFact is built - so the affected NPS values can be routed to
# QUARANTINED_CONFLICT deliberately, rather than raising mid-ingestion or
# silently picking whichever section happened to be processed first).
# ---------------------------------------------------------------------------
def _collect_od_observations(data):
    observations = []
    for row in data["elbows_90_45_LR_3D"]["rows"]:
        observations.append((normalize_nps(row["NPS"]), float(row["OD_mm"]), "elbows_90_45_LR_3D"))
    for row in data["elbows_90_SR"]["rows"]:
        observations.append((normalize_nps(row["NPS"]), float(row["OD_mm"]), "elbows_90_SR"))
    for row in data["tees_straight_equal"]["rows"]:
        observations.append((normalize_nps(row["NPS"]), float(row["OD_mm"]), "tees_straight_equal"))
    for row in data["caps"]["rows"]:
        observations.append((normalize_nps(row["NPS"]), float(row["OD_mm"]), "caps"))
    for row in data["reducers_concentric_eccentric"]["rows"]:
        large_nps, small_nps = _parse_reducer_pair(row["NPS_Large-Small"])
        observations.append((large_nps, float(row["OD_Large_D_mm"]), "reducers_concentric_eccentric (large end)"))
        observations.append((small_nps, float(row["OD_Small_D1_mm"]), "reducers_concentric_eccentric (small end)"))
    return observations


def _find_od_conflicts(observations):
    """Returns {nps: {value: [section_labels]}} for every NPS where more
    than one distinct OD value was observed across sections."""
    by_nps = defaultdict(lambda: defaultdict(list))
    for nps, value, section in observations:
        by_nps[nps][value].append(section)
    return {nps: dict(values) for nps, values in by_nps.items() if len(values) > 1}


def _od_fact(nps, od_value, source_file_rel, section_label, conflicted_nps, original_field="OD_mm"):
    """Shared/common OD identity (no fitting_type) so add_checked() both
    deduplicates consistent repeats across sections AND would ordinarily
    raise ConflictingDuplicateFact on a real cross-section inconsistency -
    except for NPS values already known (via _find_od_conflicts, run
    before any fact is built) to disagree across sections, which are
    ingested as QUARANTINED_CONFLICT instead so BOTH disagreeing values
    are retained for inspection rather than the ingestion failing on the
    first one encountered."""
    is_conflicted = nps in conflicted_nps
    status = V.QUARANTINED_CONFLICT if is_conflicted else V.VERIFIED_AUTHORITATIVE
    notes = None
    verification_method = ("OD consistency across every ASME B16.9 section referencing this NPS is enforced "
                            "structurally by add_checked()'s identity-based conflict detection, not merely asserted.")
    if is_conflicted:
        notes = (f"QUARANTINED_CONFLICT: this source's OD_mm for NPS{nps} is NOT consistent across all ASME "
                 f"B16.9 sections - discovered live during Prompt 7 ingestion via cross-section comparison "
                 f"(not a test fixture). See the Prompt 7 report for the full value breakdown.")
        verification_method = ("CONFLICT: cross-section OD comparison found disagreeing values for this NPS "
                                "across ASME B16.9 sections - see notes.")
    applicability = Applicability(product_family=VOC.PRODUCT_FAMILY_BUTTWELD_FITTING, standard=STANDARD_ID, nps=nps)
    prov = EngineeringFactProvenance(
        source_name="KGPE ASME B16.9 AI-Readable dataset", source_type="internal_dataset",
        standard_designation=STANDARD_ID, source_file=source_file_rel, original_field=original_field,
        transcription_method=f"Programmatic ingestion (kgpe/contract/adapters/asme_b16_9_buttweld.py) from {section_label}",
        verification_method=verification_method,
    )
    return EngineeringFact(dimension_name=VOC.DIM_OUTSIDE_DIAMETER, value=Quantity(float(od_value), LENGTH_MM),
                            applicability=applicability, verification_status=status, provenance=prov, notes=notes)


def _add_fact(registry, fact):
    """Dispatch helper: a QUARANTINED_CONFLICT fact is added via the plain
    `add()` (deliberately bypassing identity-conflict enforcement, since
    the whole point is to retain multiple disagreeing values side by
    side); every other fact goes through `add_checked()` as normal.

    `add()` alone has no exact-duplicate detection (that only lives in
    `add_checked()`'s identity index), so a QUARANTINED_CONFLICT fact needs
    its own explicit exact-duplicate check here - otherwise re-ingesting
    into the same registry (Prompt 5/6/7's own idempotency requirement)
    would silently double every conflicted record on each re-run. An
    "exact duplicate" for this purpose means same identity_key(), same
    value, and same verification_status - anything else is intentionally
    still additive (e.g. a genuinely new disagreeing value would need a
    human decision, not a silent merge)."""
    if fact.verification_status == V.QUARANTINED_CONFLICT:
        key = fact.identity_key()
        bucket = registry._by_dimension.get(fact.dimension_name, [])
        for existing in bucket:
            if (existing.verification_status == V.QUARANTINED_CONFLICT
                    and existing.identity_key() == key
                    and existing.value == fact.value):
                return existing
        return registry.add(fact)
    return registry.add_checked(fact)


def _build_elbow_lr_3d_facts(row, source_file_rel, conflicted_nps):
    nps = normalize_nps(row["NPS"])
    facts = [_od_fact(nps, row["OD_mm"], source_file_rel, "elbows_90_45_LR_3D", conflicted_nps)]
    for col, fitting_type, label in _ELBOW_LR_3D_SPEC:
        value = row.get(col)
        if value is None:
            continue
        applicability = Applicability(product_family=VOC.PRODUCT_FAMILY_BUTTWELD_FITTING, standard=STANDARD_ID,
                                       fitting_type=fitting_type, nps=nps)
        prov = EngineeringFactProvenance(
            source_name="KGPE ASME B16.9 AI-Readable dataset", source_type="internal_dataset",
            standard_designation=STANDARD_ID, source_file=source_file_rel, original_field=col,
            transcription_method=f"Programmatic ingestion (kgpe/contract/adapters/asme_b16_9_buttweld.py) "
                                  f"from elbows_90_45_LR_3D ({label})",
        )
        facts.append(EngineeringFact(dimension_name=VOC.DIM_CENTRE_TO_END, value=Quantity(float(value), LENGTH_MM),
                                      applicability=applicability, verification_status=V.VERIFIED_AUTHORITATIVE,
                                      provenance=prov))
    return facts


def _build_elbow_sr_facts(row, source_file_rel, conflicted_nps):
    nps = normalize_nps(row["NPS"])
    facts = [_od_fact(nps, row["OD_mm"], source_file_rel, "elbows_90_SR", conflicted_nps)]
    value = row.get("Elbow90SR_CtoE_mm")
    if value is not None:
        applicability = Applicability(product_family=VOC.PRODUCT_FAMILY_BUTTWELD_FITTING, standard=STANDARD_ID,
                                       fitting_type=VOC.FITTING_TYPE_ELBOW_90_SR, nps=nps)
        prov = EngineeringFactProvenance(
            source_name="KGPE ASME B16.9 AI-Readable dataset", source_type="internal_dataset",
            standard_designation=STANDARD_ID, source_file=source_file_rel, original_field="Elbow90SR_CtoE_mm",
            transcription_method="Programmatic ingestion (kgpe/contract/adapters/asme_b16_9_buttweld.py) from elbows_90_SR",
        )
        facts.append(EngineeringFact(dimension_name=VOC.DIM_CENTRE_TO_END, value=Quantity(float(value), LENGTH_MM),
                                      applicability=applicability, verification_status=V.VERIFIED_AUTHORITATIVE,
                                      provenance=prov))
    return facts


def _build_tee_facts(row, source_file_rel, conflicted_nps):
    nps = normalize_nps(row["NPS"])
    facts = [_od_fact(nps, row["OD_mm"], source_file_rel, "tees_straight_equal", conflicted_nps)]
    for col, dim_name in (("Run_CtoE_C_mm", VOC.DIM_TEE_RUN_CENTRE_TO_END),
                          ("Outlet_CtoE_M_mm", VOC.DIM_TEE_BRANCH_CENTRE_TO_END)):
        value = row.get(col)
        if value is None:
            continue
        applicability = Applicability(product_family=VOC.PRODUCT_FAMILY_BUTTWELD_FITTING, standard=STANDARD_ID,
                                       fitting_type=VOC.FITTING_TYPE_TEE_EQUAL, nps=nps)
        prov = EngineeringFactProvenance(
            source_name="KGPE ASME B16.9 AI-Readable dataset", source_type="internal_dataset",
            standard_designation=STANDARD_ID, source_file=source_file_rel, original_field=col,
            transcription_method="Programmatic ingestion (kgpe/contract/adapters/asme_b16_9_buttweld.py) from tees_straight_equal",
            notes=("Source column 'Outlet' = branch direction in ASME B16.9 terminology." if col == "Outlet_CtoE_M_mm" else None),
        )
        facts.append(EngineeringFact(dimension_name=dim_name, value=Quantity(float(value), LENGTH_MM),
                                      applicability=applicability, verification_status=V.VERIFIED_AUTHORITATIVE,
                                      provenance=prov))
    return facts


def _build_cap_facts(row, source_file_rel, conflicted_nps):
    nps = normalize_nps(row["NPS"])
    facts = [_od_fact(nps, row["OD_mm"], source_file_rel, "caps", conflicted_nps)]
    base_app_kwargs = dict(product_family=VOC.PRODUCT_FAMILY_BUTTWELD_FITTING, standard=STANDARD_ID,
                            fitting_type=VOC.FITTING_TYPE_CAP, nps=nps)

    h = row.get("Length_H_mm")
    if h is not None:
        prov = EngineeringFactProvenance(
            source_name="KGPE ASME B16.9 AI-Readable dataset", source_type="internal_dataset",
            standard_designation=STANDARD_ID, source_file=source_file_rel, original_field="Length_H_mm",
            transcription_method="Programmatic ingestion (kgpe/contract/adapters/asme_b16_9_buttweld.py) from caps",
            verification_method="Matches the value KGPE Prompt 3/40 confirmed identical to the legacy JS CRM's "
                                 "CAP_LEN table (21/21 exact match, 0 mismatches).",
            notes="Applies when the actual pipe wall thickness being capped is below WT_threshold_mm.",
        )
        facts.append(EngineeringFact(dimension_name=VOC.DIM_CAP_LENGTH_STANDARD_WALL,
                                      value=Quantity(float(h), LENGTH_MM),
                                      applicability=Applicability(**base_app_kwargs),
                                      verification_status=V.VERIFIED_AUTHORITATIVE, provenance=prov))

    h1 = row.get("Length_H1_mm")
    if h1 is not None:
        prov = EngineeringFactProvenance(
            source_name="KGPE ASME B16.9 AI-Readable dataset", source_type="internal_dataset",
            standard_designation=STANDARD_ID, source_file=source_file_rel, original_field="Length_H1_mm",
            transcription_method="Programmatic ingestion (kgpe/contract/adapters/asme_b16_9_buttweld.py) from caps",
            notes="Applies when the actual pipe wall thickness being capped is at/above WT_threshold_mm - "
                  "a genuinely different fact from Length_H, not a duplicate (Prompt 7 Sec.10/11).",
        )
        facts.append(EngineeringFact(dimension_name=VOC.DIM_CAP_LENGTH_HEAVY_WALL,
                                      value=Quantity(float(h1), LENGTH_MM),
                                      applicability=Applicability(**base_app_kwargs),
                                      verification_status=V.VERIFIED_AUTHORITATIVE, provenance=prov))

    thresh = row.get("WT_threshold_mm")
    if thresh is not None:
        prov = EngineeringFactProvenance(
            source_name="KGPE ASME B16.9 AI-Readable dataset", source_type="internal_dataset",
            standard_designation=STANDARD_ID, source_file=source_file_rel, original_field="WT_threshold_mm",
            transcription_method="Programmatic ingestion (kgpe/contract/adapters/asme_b16_9_buttweld.py) from caps",
        )
        facts.append(EngineeringFact(dimension_name=VOC.DIM_CAP_WALL_THICKNESS_THRESHOLD,
                                      value=Quantity(float(thresh), LENGTH_MM),
                                      applicability=Applicability(**base_app_kwargs),
                                      verification_status=V.VERIFIED_AUTHORITATIVE, provenance=prov))
    return facts


def _build_reducer_facts(row, source_file_rel, conflicted_nps):
    large_nps, small_nps = _parse_reducer_pair(row["NPS_Large-Small"])
    facts = [
        _od_fact(large_nps, row["OD_Large_D_mm"], source_file_rel, "reducers_concentric_eccentric",
                 conflicted_nps, original_field="OD_Large_D_mm"),
        _od_fact(small_nps, row["OD_Small_D1_mm"], source_file_rel, "reducers_concentric_eccentric",
                 conflicted_nps, original_field="OD_Small_D1_mm"),
    ]
    length = row["Length_H_mm"]
    for fitting_type in (VOC.FITTING_TYPE_REDUCER_CONCENTRIC, VOC.FITTING_TYPE_REDUCER_ECCENTRIC):
        applicability = Applicability(product_family=VOC.PRODUCT_FAMILY_BUTTWELD_FITTING, standard=STANDARD_ID,
                                       fitting_type=fitting_type, large_end_nps=large_nps, small_end_nps=small_nps,
                                       reducing_pair=f"{large_nps}x{small_nps}")
        prov = EngineeringFactProvenance(
            source_name="KGPE ASME B16.9 AI-Readable dataset", source_type="internal_dataset",
            standard_designation=STANDARD_ID, source_file=source_file_rel, original_field="Length_H_mm",
            transcription_method="Programmatic ingestion (kgpe/contract/adapters/asme_b16_9_buttweld.py) "
                                  "from reducers_concentric_eccentric",
            verification_method="Matches the value KGPE Prompt 3/40 confirmed identical to the legacy JS CRM's "
                                 "REDUCER_LEN table (16/16 matched entries, 0 mismatches).",
            notes="Source note: 'Same OD/length table applies to both concentric and eccentric reducers per "
                  "B16.9' - this fact is deliberately duplicated under both fitting_type identities with the "
                  "SAME value, proving dimensional equality does not erase product identity (Prompt 7 Sec.9).",
        )
        facts.append(EngineeringFact(dimension_name=VOC.DIM_END_TO_END, value=Quantity(float(length), LENGTH_MM),
                                      applicability=applicability, verification_status=V.VERIFIED_AUTHORITATIVE,
                                      provenance=prov))
    return facts


def ingest_asme_b16_9_buttweld(registry=None):
    """Reads, validates, and ingests the existing ASME B16.9 JSON into
    `registry` (a new FactRegistry if none given). Deterministic order:
    elbows_90_45_LR_3D -> elbows_90_SR -> tees_straight_equal -> caps ->
    reducers_concentric_eccentric, each sorted by exact-rational NPS sort
    key (reducers sorted by (large, small)). Raises SourceValidationError
    with ALL problems collected across every section if the source is
    malformed. OD facts for NPS values with a genuine cross-section
    inconsistency (see module docstring) are ingested as
    QUARANTINED_CONFLICT rather than VERIFIED_AUTHORITATIVE."""
    if registry is None:
        registry = FactRegistry()

    data, source_file_rel = _load_source()
    _validate_top_level(data)

    elbow_lr3d_rows = data["elbows_90_45_LR_3D"]["rows"]
    elbow_sr_rows = data["elbows_90_SR"]["rows"]
    tee_rows = data["tees_straight_equal"]["rows"]
    cap_rows = data["caps"]["rows"]
    reducer_rows = data["reducers_concentric_eccentric"]["rows"]

    all_errors = []
    for i, row in enumerate(elbow_lr3d_rows):
        all_errors.extend(_validate_single_size_row(
            "elbows_90_45_LR_3D", i, row,
            ["Elbow90LR_CtoE_mm", "Elbow45LR_CtoE_mm", "Elbow90_3D_CtoE_mm", "Elbow45_3D_CtoE_mm"],
            required_value_cols=["Elbow90LR_CtoE_mm", "Elbow45LR_CtoE_mm"]))
    all_errors.extend(_check_duplicate_nps("elbows_90_45_LR_3D", elbow_lr3d_rows))

    for i, row in enumerate(elbow_sr_rows):
        all_errors.extend(_validate_single_size_row(
            "elbows_90_SR", i, row, ["Elbow90SR_CtoE_mm"], required_value_cols=["Elbow90SR_CtoE_mm"]))
    all_errors.extend(_check_duplicate_nps("elbows_90_SR", elbow_sr_rows))

    for i, row in enumerate(tee_rows):
        all_errors.extend(_validate_single_size_row(
            "tees_straight_equal", i, row, ["Run_CtoE_C_mm", "Outlet_CtoE_M_mm"],
            required_value_cols=["Run_CtoE_C_mm", "Outlet_CtoE_M_mm"]))
    all_errors.extend(_check_duplicate_nps("tees_straight_equal", tee_rows))

    for i, row in enumerate(cap_rows):
        all_errors.extend(_validate_cap_row(i, row))
    all_errors.extend(_check_duplicate_nps("caps", cap_rows))

    for i, row in enumerate(reducer_rows):
        all_errors.extend(_validate_reducer_row(i, row))
    all_errors.extend(_check_duplicate_reducer_pairs(reducer_rows))

    if all_errors:
        raise SourceValidationError(
            f"ASME B16.9 source failed validation ({len(all_errors)} problem(s)): " + " | ".join(all_errors)
        )

    conflicted_nps = set(_find_od_conflicts(_collect_od_observations(data)).keys())

    ingested = []

    for row in sorted(elbow_lr3d_rows, key=lambda r: nps_sort_key(normalize_nps(r["NPS"]))):
        for fact in _build_elbow_lr_3d_facts(row, source_file_rel, conflicted_nps):
            _add_fact(registry, fact)
            ingested.append(fact)

    for row in sorted(elbow_sr_rows, key=lambda r: nps_sort_key(normalize_nps(r["NPS"]))):
        for fact in _build_elbow_sr_facts(row, source_file_rel, conflicted_nps):
            _add_fact(registry, fact)
            ingested.append(fact)

    for row in sorted(tee_rows, key=lambda r: nps_sort_key(normalize_nps(r["NPS"]))):
        for fact in _build_tee_facts(row, source_file_rel, conflicted_nps):
            _add_fact(registry, fact)
            ingested.append(fact)

    for row in sorted(cap_rows, key=lambda r: nps_sort_key(normalize_nps(r["NPS"]))):
        for fact in _build_cap_facts(row, source_file_rel, conflicted_nps):
            _add_fact(registry, fact)
            ingested.append(fact)

    for row in sorted(reducer_rows, key=lambda r: tuple(nps_sort_key(x) for x in _parse_reducer_pair(r["NPS_Large-Small"]))):
        for fact in _build_reducer_facts(row, source_file_rel, conflicted_nps):
            _add_fact(registry, fact)
            ingested.append(fact)

    return registry, ingested
