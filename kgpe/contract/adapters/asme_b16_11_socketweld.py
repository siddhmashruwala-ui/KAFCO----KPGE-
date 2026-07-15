# -*- coding: utf-8 -*-
"""
kgpe.contract.adapters.asme_b16_11_socketweld
=================================================
Source adapter (Prompt 8): ASME B16.11 forged socket-weld/threaded
fittings - elbows (90/45deg), tees/crosses, couplings/half-couplings,
caps. Reads the existing JSON dimension_library.py already reads
(`SOCKETWELD_FILES["ASME_B16.11"]`).

ACTUAL SOURCE STRUCTURE FOUND (inspected before writing this adapter):
  - Scope: NPS 1/2-4 only, Class 3000 and 6000 (Class 9000 explicitly
    NOT included by the source's own notes - "request separately if
    needed"; not fabricated here).
  - Four product sections, each with "class_3000"/"class_6000" row
    lists: "elbows_90_45" (bundles 90deg AND 45deg centre-to-bottom-of-
    socket dimensions as two columns on one row, same pattern as ASME
    B16.9's elbow table), "tees_and_crosses" (the source's own note
    states cross geometry is identical to the 90deg-elbow-of-same-class
    body-socket dims - this table is shared by both tee and cross, so
    this adapter deliberately duplicates each row's values under BOTH
    fitting_type identities, exactly mirroring the Prompt 7 precedent of
    ingesting one reducer-length value under both concentric and
    eccentric identities), "couplings_and_half_couplings" (bundles two
    distinct products - full coupling and half coupling - sharing one
    socket geometry but with separate laying-length columns E/F),
    "caps" (SocketBoreDepth_B, J, SocketLength_Q, CapDia_R - a
    genuinely different set of columns from the other three sections).
  - Every socket geometry field (SocketBoreDepth_B, SocketBoreDia_D,
    SocketWT_C) is published as an explicit max/min PAIR, never a single
    nominal value - both ends of each pair are ingested as distinct
    facts, never averaged.
  - The source's own notes document two of its own prior corrections
    (an OCR "46.4mm" typo fixed to 76.4mm; an earlier build that dropped
    SocketWT_C_min) - both already fixed in the file as it stands; no
    action needed here beyond trusting the current values as authoritative.
  - class_key ("3000"/"6000") uses the same ASME_CLASS designation
    convention as ASME B16.5 flange classes (numeric, no PSI suffix) -
    reusing normalize_pressure_class(RATING_SYSTEM_ASME_CLASS) here is
    NOT "forcing a non-ASME standard into ASME semantics" (Prompt 8
    Sec.4's rule targets JIS/EN, not other ASME standards); B16.11 IS an
    ASME standard using the identical class-designation format. No
    collision risk with B16.5's class_key="150" etc regardless, since
    identity_key() also includes `standard` and `product_family`.
"""
import re

from .. import vocabulary as VOC
from .. import verification as V
from ..applicability import Applicability
from ..units import Quantity, LENGTH_MM
from ..normalization import normalize_nps, nps_sort_key, normalize_pressure_class
from ..model import EngineeringFact, EngineeringFactProvenance, FactRegistry, SourceValidationError
from ... import dimension_library as dl
from ._shared import load_json_source, validate_positive_numeric_or_null, check_duplicate_key

STANDARD_ID = "ASME_B16.11"  # matches dimension_library.SOCKETWELD_FILES key verbatim

REQUIRED_TOP_KEYS = ("standard", "elbows_90_45", "tees_and_crosses",
                     "couplings_and_half_couplings", "caps")
CLASS_KEYS = ("class_3000", "class_6000")

_ELBOW_45_90_VALUE_COLS = ["SocketBoreDepth_B_max_mm", "SocketBoreDepth_B_min_mm", "J_mm",
                           "SocketBoreDia_D_max_mm", "SocketBoreDia_D_min_mm",
                           "SocketWT_C_max_mm", "SocketWT_C_min_mm", "BodyWT_G_mm",
                           "CtoBottomSocket_A_90deg_mm", "CtoBottomSocket_A_45deg_mm"]
_COUPLING_VALUE_COLS = ["SocketBoreDepth_B_max_mm", "SocketBoreDepth_B_min_mm", "J_mm",
                        "SocketBoreDia_D_max_mm", "SocketBoreDia_D_min_mm",
                        "SocketWT_C_max_mm", "SocketWT_C_min_mm",
                        "LayingLength_Coupling_E_mm", "LayingLength_HalfCoupling_F_mm"]
_CAP_VALUE_COLS = ["SocketBoreDepth_B_max_mm", "SocketBoreDepth_B_min_mm", "J_mm",
                   "SocketLength_Q_mm", "CapDia_R_mm"]


def _load_source():
    return load_json_source(dl.DIMLIB_ROOT, dl.SOCKETWELD_FILES[STANDARD_ID])


def _validate_top_level(data):
    errors = [f"Missing required top-level key {k!r}" for k in REQUIRED_TOP_KEYS if k not in data]
    if errors:
        raise SourceValidationError("ASME B16.11 source failed top-level validation: " + "; ".join(errors))
    for section in REQUIRED_TOP_KEYS[1:]:
        for class_key in CLASS_KEYS:
            if class_key not in data[section] or not isinstance(data[section][class_key], list):
                raise SourceValidationError(
                    f"ASME B16.11 source: section {section!r} must have a {class_key!r} list")


def _validate_row(section_label, index, row, value_cols, required_cols=()):
    if not isinstance(row, dict):
        return [f"{section_label} row {index}: not an object"]
    errs = []
    if "NPS" not in row or not isinstance(row["NPS"], str) or not row["NPS"].strip():
        errs.append(f"{section_label} row {index}: NPS must be a non-empty string")
    else:
        try:
            normalize_nps(row["NPS"])
        except ValueError as e:
            errs.append(f"{section_label} row {index}: NPS {row['NPS']!r} could not be normalized: {e}")
    for col in value_cols:
        errs.extend(validate_positive_numeric_or_null(section_label, index, row, col,
                                                        required=(col in required_cols)))
    return errs


def _od_source_note():
    return ("ASME B16.11 does not itself publish outside diameter (fitting OD is the mating pipe's "
            "own OD, e.g. from ASME B36.10M/19M) - not ingested here to avoid fabricating a fact this "
            "source doesn't state.")


def _prov(source_file_rel, section_label, class_key, original_field, extra_note=None):
    return EngineeringFactProvenance(
        source_name="KGPE ASME B16.11 AI-Readable dataset", source_type="internal_dataset",
        standard_designation=STANDARD_ID, source_file=source_file_rel, original_field=original_field,
        transcription_method=f"Programmatic ingestion (kgpe/contract/adapters/asme_b16_11_socketweld.py) "
                              f"from {section_label}/{class_key}",
        notes=extra_note,
    )


def _fact(dim_name, value, fitting_type, nps, class_key, source_file_rel, section_label, original_field,
          extra_note=None):
    applicability = Applicability(product_family=VOC.PRODUCT_FAMILY_SOCKETWELD_FITTING, standard=STANDARD_ID,
                                   fitting_type=fitting_type, class_key=class_key, nps=nps)
    return EngineeringFact(dimension_name=dim_name, value=Quantity(float(value), LENGTH_MM),
                           applicability=applicability, verification_status=V.VERIFIED_AUTHORITATIVE,
                           provenance=_prov(source_file_rel, section_label, class_key, original_field, extra_note))


def _build_elbow_facts(row, class_key, source_file_rel):
    nps = normalize_nps(row["NPS"])
    facts = []
    pairs = [
        (VOC.DIM_SOCKET_BORE_DEPTH_MAX, "SocketBoreDepth_B_max_mm"), (VOC.DIM_SOCKET_BORE_DEPTH_MIN, "SocketBoreDepth_B_min_mm"),
        (VOC.DIM_SOCKET_BORE_DIAMETER_MAX, "SocketBoreDia_D_max_mm"), (VOC.DIM_SOCKET_BORE_DIAMETER_MIN, "SocketBoreDia_D_min_mm"),
        (VOC.DIM_SOCKET_WALL_THICKNESS_MAX, "SocketWT_C_max_mm"), (VOC.DIM_SOCKET_WALL_THICKNESS_MIN, "SocketWT_C_min_mm"),
        (VOC.DIM_FITTING_BODY_WALL_THICKNESS, "BodyWT_G_mm"),
    ]
    for angle_deg, fitting_type, col in ((90, VOC.FITTING_TYPE_ELBOW_90_SW, "CtoBottomSocket_A_90deg_mm"),
                                          (45, VOC.FITTING_TYPE_ELBOW_45_SW, "CtoBottomSocket_A_45deg_mm")):
        facts.append(_fact(VOC.DIM_CENTRE_TO_END, row[col], fitting_type, nps, class_key,
                            source_file_rel, "elbows_90_45", col))
        for dim_name, col2 in pairs:
            facts.append(_fact(dim_name, row[col2], fitting_type, nps, class_key,
                                source_file_rel, "elbows_90_45", col2))
    return facts


def _build_tee_and_cross_facts(row, class_key, source_file_rel):
    # NOTE: this section's rows also carry a "CtoBottomSocket_A_45deg_mm"
    # field (identical schema to the elbow table, likely copied from it)
    # but a tee/cross has no 45-degree engineering meaning - only the
    # 90deg value is ingested here; the 45deg field is deliberately left
    # un-ingested rather than fabricating a "45-degree tee" fact that
    # doesn't correspond to any real product.
    nps = normalize_nps(row["NPS"])
    facts = []
    shared_note = ("Source note: socket geometry identical to the 90deg elbow of the same class/NPS, "
                   "and this one table is explicitly shared by both tee and cross - the same tabulated "
                   "value is deliberately ingested under both fitting_type identities (mirrors the "
                   "Prompt 7 reducer concentric/eccentric precedent), not collapsed into one.")
    field_map = [
        (VOC.DIM_SOCKET_BORE_DEPTH_MAX, "SocketBoreDepth_B_max_mm"), (VOC.DIM_SOCKET_BORE_DEPTH_MIN, "SocketBoreDepth_B_min_mm"),
        (VOC.DIM_SOCKET_BORE_DIAMETER_MAX, "SocketBoreDia_D_max_mm"), (VOC.DIM_SOCKET_BORE_DIAMETER_MIN, "SocketBoreDia_D_min_mm"),
        (VOC.DIM_SOCKET_WALL_THICKNESS_MAX, "SocketWT_C_max_mm"), (VOC.DIM_SOCKET_WALL_THICKNESS_MIN, "SocketWT_C_min_mm"),
        (VOC.DIM_FITTING_BODY_WALL_THICKNESS, "BodyWT_G_mm"), (VOC.DIM_CENTRE_TO_END, "CtoBottomSocket_A_90deg_mm"),
    ]
    for fitting_type in (VOC.FITTING_TYPE_TEE_SW, VOC.FITTING_TYPE_CROSS_SW):
        for dim_name, col in field_map:
            facts.append(_fact(dim_name, row[col], fitting_type, nps, class_key,
                                source_file_rel, "tees_and_crosses", col, extra_note=shared_note))
    return facts


def _build_coupling_facts(row, class_key, source_file_rel):
    nps = normalize_nps(row["NPS"])
    facts = []
    shared_cols = [
        (VOC.DIM_SOCKET_BORE_DEPTH_MAX, "SocketBoreDepth_B_max_mm"), (VOC.DIM_SOCKET_BORE_DEPTH_MIN, "SocketBoreDepth_B_min_mm"),
        (VOC.DIM_SOCKET_BORE_DIAMETER_MAX, "SocketBoreDia_D_max_mm"), (VOC.DIM_SOCKET_BORE_DIAMETER_MIN, "SocketBoreDia_D_min_mm"),
        (VOC.DIM_SOCKET_WALL_THICKNESS_MAX, "SocketWT_C_max_mm"), (VOC.DIM_SOCKET_WALL_THICKNESS_MIN, "SocketWT_C_min_mm"),
    ]
    for fitting_type in (VOC.FITTING_TYPE_COUPLING_SW, VOC.FITTING_TYPE_HALF_COUPLING_SW):
        for dim_name, col in shared_cols:
            facts.append(_fact(dim_name, row[col], fitting_type, nps, class_key,
                                source_file_rel, "couplings_and_half_couplings", col))
    facts.append(_fact(VOC.DIM_END_TO_END, row["LayingLength_Coupling_E_mm"], VOC.FITTING_TYPE_COUPLING_SW,
                        nps, class_key, source_file_rel, "couplings_and_half_couplings", "LayingLength_Coupling_E_mm"))
    facts.append(_fact(VOC.DIM_END_TO_END, row["LayingLength_HalfCoupling_F_mm"], VOC.FITTING_TYPE_HALF_COUPLING_SW,
                        nps, class_key, source_file_rel, "couplings_and_half_couplings", "LayingLength_HalfCoupling_F_mm"))
    return facts


def _build_cap_facts(row, class_key, source_file_rel):
    nps = normalize_nps(row["NPS"])
    facts = []
    field_map = [
        (VOC.DIM_SOCKET_BORE_DEPTH_MAX, "SocketBoreDepth_B_max_mm"), (VOC.DIM_SOCKET_BORE_DEPTH_MIN, "SocketBoreDepth_B_min_mm"),
        (VOC.DIM_CAP_SOCKET_LENGTH, "SocketLength_Q_mm"), (VOC.DIM_CAP_BODY_DIAMETER, "CapDia_R_mm"),
    ]
    for dim_name, col in field_map:
        facts.append(_fact(dim_name, row[col], VOC.FITTING_TYPE_CAP_SW, nps, class_key,
                            source_file_rel, "caps", col))
    return facts


def ingest_asme_b16_11_socketweld(registry=None):
    """Reads, validates, and ingests the ASME B16.11 JSON. Deterministic
    order: elbows_90_45 -> tees_and_crosses -> couplings_and_half_couplings
    -> caps, each class_3000 before class_6000, rows sorted by NPS sort
    key. Outside diameter is deliberately NOT ingested here - see
    `_od_source_note()` - ASME B16.11 does not publish it; the mating
    pipe's own OD (already ingested in Prompt 6) is the correct source
    for that dimension, and fabricating an OD fact here would duplicate
    a fact this standard doesn't itself state."""
    if registry is None:
        registry = FactRegistry()

    data, source_file_rel = _load_source()
    _validate_top_level(data)

    all_errors = []
    for section, cols, required in (
        ("elbows_90_45", _ELBOW_45_90_VALUE_COLS, ["SocketBoreDepth_B_max_mm", "SocketBoreDepth_B_min_mm", "J_mm",
                                                    "SocketBoreDia_D_max_mm", "SocketBoreDia_D_min_mm",
                                                    "SocketWT_C_max_mm", "SocketWT_C_min_mm", "BodyWT_G_mm",
                                                    "CtoBottomSocket_A_90deg_mm", "CtoBottomSocket_A_45deg_mm"]),
        ("tees_and_crosses", _ELBOW_45_90_VALUE_COLS, ["SocketBoreDepth_B_max_mm", "SocketBoreDepth_B_min_mm", "J_mm",
                                                        "SocketBoreDia_D_max_mm", "SocketBoreDia_D_min_mm",
                                                        "SocketWT_C_max_mm", "SocketWT_C_min_mm", "BodyWT_G_mm",
                                                        "CtoBottomSocket_A_90deg_mm"]),
        ("couplings_and_half_couplings", _COUPLING_VALUE_COLS, _COUPLING_VALUE_COLS),
        ("caps", _CAP_VALUE_COLS, _CAP_VALUE_COLS),
    ):
        for class_key in CLASS_KEYS:
            rows = data[section][class_key]
            for i, row in enumerate(rows):
                all_errors.extend(_validate_row(f"{section}/{class_key}", i, row, cols, required))
            all_errors.extend(check_duplicate_key(
                f"{section}/{class_key}", rows,
                lambda r: normalize_nps(r["NPS"])))

    if all_errors:
        raise SourceValidationError(
            f"ASME B16.11 source failed validation ({len(all_errors)} problem(s)): " + " | ".join(all_errors)
        )

    ingested = []

    def _sorted(rows):
        return sorted(rows, key=lambda r: nps_sort_key(normalize_nps(r["NPS"])))

    for class_key in CLASS_KEYS:
        canon_class = normalize_pressure_class(class_key.replace("class_", ""))
        for row in _sorted(data["elbows_90_45"][class_key]):
            for fact in _build_elbow_facts(row, canon_class, source_file_rel):
                registry.add_checked(fact)
                ingested.append(fact)

    for class_key in CLASS_KEYS:
        canon_class = normalize_pressure_class(class_key.replace("class_", ""))
        for row in _sorted(data["tees_and_crosses"][class_key]):
            for fact in _build_tee_and_cross_facts(row, canon_class, source_file_rel):
                registry.add_checked(fact)
                ingested.append(fact)

    for class_key in CLASS_KEYS:
        canon_class = normalize_pressure_class(class_key.replace("class_", ""))
        for row in _sorted(data["couplings_and_half_couplings"][class_key]):
            for fact in _build_coupling_facts(row, canon_class, source_file_rel):
                registry.add_checked(fact)
                ingested.append(fact)

    for class_key in CLASS_KEYS:
        canon_class = normalize_pressure_class(class_key.replace("class_", ""))
        for row in _sorted(data["caps"][class_key]):
            for fact in _build_cap_facts(row, canon_class, source_file_rel):
                registry.add_checked(fact)
                ingested.append(fact)

    return registry, ingested
