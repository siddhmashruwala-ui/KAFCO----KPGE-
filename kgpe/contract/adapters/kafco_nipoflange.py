# -*- coding: utf-8 -*-
"""
kgpe.contract.adapters.kafco_nipoflange
===========================================
Source adapter: KAFCO's own Nipoflange product datasheet (a forged
branch-outlet fitting terminating in an integral raised-face flange,
Branch NB 1/2"-2", ANSI classes 150#-2500#).

WHY THIS EXISTS: prior KGPE work (mss_sp97_olets.py's own docstring, and
model.py's ConstructionParameter docstring) explicitly flagged that the
legacy CRM's nipoflange geometry was a hand-rolled *proportional*
construction with no standard/manufacturer data behind it, and
deliberately refused to ingest that construction as authoritative. This
adapter is the first genuine primary source for Nipoflange dimensions -
a real KAFCO catalog page, transcribed verbatim, not derived from the
CRM's JS.

SOURCE CHARACTER (read from the source's own notes, not assumed):
  - "Flange dimensions to ANSI B16.5" (source Note 1) - stated but NOT
    independently cross-checked cell-by-cell against this project's own
    ASME B16.5 ingestion, so Flange OD (A) and Flange THK (D) are kept as
    their own nipoflange-specific dimension identities
    (DIM_NIPOFLANGE_FLANGE_OD / DIM_NIPOFLANGE_FLANGE_THICKNESS), never
    silently aliased to DIM_OUTSIDE_DIAMETER / DIM_FLANGE_THICKNESS_*.
  - Overall Length (B) is explicitly purchaser-modifiable (source Note 2)
    - ingested as a ConstructionParameter (CONSTRUCTION_PARAMETER status,
      mandatory disclaimer), never as a fixed authoritative fact.
  - Bore/schedule (C) is purchaser-specified and not tabulated at all
    (source Note 4) - no schedule field is populated on any fact here.
  - Weight is explicitly labelled "APPROX" in the source - ingested as
    VERIFIED_MANUFACTURER_SPECIFIC with that caveat carried in `notes`,
    using the existing generic DIM_MASS (no new dimension name needed).
  - The source's own ANSI 900# and ANSI 1500# tables are identical
    row-for-row (A/B/D/Weight) - ingested exactly as printed, not merged
    or "corrected".

Every fact/construction-parameter here is VERIFIED_MANUFACTURER_SPECIFIC
or CONSTRUCTION_PARAMETER (manufacturer_profile="KAFCO") - never
VERIFIED_AUTHORITATIVE, because this is one vendor's own catalog, not an
ASME/MSS standard text.
"""
from .. import vocabulary as VOC
from .. import verification as V
from ..applicability import Applicability
from ..units import Quantity, LENGTH_MM, MASS_KG
from ..normalization import normalize_nps, nps_sort_key, normalize_dn, normalize_pressure_class
from ..model import (EngineeringFact, ConstructionParameter, EngineeringFactProvenance,
                      FactRegistry, SourceValidationError)
from ._shared import load_json_source, validate_positive_numeric_or_null, check_duplicate_key

STANDARD_ID = "KAFCO_NIPOFLANGE"
SOURCE_REL_PATH = "Nipoflange/KAFCO_Nipoflange_Dimensions.json"
MANUFACTURER_PROFILE = "KAFCO"

REQUIRED_TOP_KEYS = ("standard", "tables")
REQUIRED_TABLE = "nipoflange_body_dims"

_ROW_NUMERIC_FIELDS = ("FlangeOD_A_mm", "OverallLength_B_mm", "FlangeThk_D_mm", "Weight_kg_approx")


def _dimlib_root():
    # This source lives alongside the other AI-Readable standards data,
    # not inside dimension_library.py's own registries (Nipoflange has no
    # live-lookup counterpart in dimension_library.py - it's new).
    from ... import dimension_library as dl
    return dl.DIMLIB_ROOT


def _load_source():
    return load_json_source(_dimlib_root(), SOURCE_REL_PATH)


def _validate_top_level(data):
    errors = [f"Missing required top-level key {k!r}" for k in REQUIRED_TOP_KEYS if k not in data]
    if errors:
        raise SourceValidationError("KAFCO Nipoflange source failed top-level validation: " + "; ".join(errors))
    if REQUIRED_TABLE not in data["tables"] or "rows" not in data["tables"][REQUIRED_TABLE]:
        raise SourceValidationError(f"KAFCO Nipoflange source missing required table {REQUIRED_TABLE!r} (or its 'rows' list)")


def _validate_row(index, row):
    errs = []
    if "ClassKey" not in row:
        errs.append(f"nipoflange_body_dims row {index}: missing ClassKey")
    else:
        try:
            normalize_pressure_class(row["ClassKey"])
        except ValueError as e:
            errs.append(f"nipoflange_body_dims row {index}: ClassKey invalid: {e}")
    if "BranchNPS" not in row or not isinstance(row["BranchNPS"], str) or not row["BranchNPS"].strip():
        errs.append(f"nipoflange_body_dims row {index}: BranchNPS must be a non-empty string")
    else:
        try:
            normalize_nps(row["BranchNPS"])
        except ValueError as e:
            errs.append(f"nipoflange_body_dims row {index}: BranchNPS invalid: {e}")
    for field in _ROW_NUMERIC_FIELDS:
        errs.extend(validate_positive_numeric_or_null("nipoflange_body_dims", index, row, field, required=True))
    return errs


def _prov(original_field, extra_note=None):
    return EngineeringFactProvenance(
        source_name="KAFCO Nipoflange product datasheet", source_type="supplier_reference",
        standard_designation=STANDARD_ID, standard_edition=None, source_file=SOURCE_REL_PATH,
        original_field=original_field,
        transcription_method="Manual transcription from a manufacturer catalog page supplied in chat (2026-07-20), "
                              "programmatic ingestion via kgpe/contract/adapters/kafco_nipoflange.py",
        notes=extra_note,
    )


def _build_row_facts(row):
    facts = []
    class_key = normalize_pressure_class(row["ClassKey"])
    nps = normalize_nps(row["BranchNPS"])
    dn = normalize_dn(row["BranchDN"]) if "BranchDN" in row and row["BranchDN"] is not None else None

    applicability = Applicability(
        product_family=VOC.PRODUCT_FAMILY_OLET, standard=STANDARD_ID,
        fitting_type=VOC.FITTING_TYPE_NIPOFLANGE, class_key=class_key, nps=nps, dn=dn,
        manufacturer_profile=MANUFACTURER_PROFILE,
    )

    facts.append(EngineeringFact(
        dimension_name=VOC.DIM_NIPOFLANGE_FLANGE_OD, value=Quantity(float(row["FlangeOD_A_mm"]), LENGTH_MM),
        applicability=applicability, verification_status=V.VERIFIED_MANUFACTURER_SPECIFIC,
        provenance=_prov("FlangeOD_A_mm", "Source Note 1: flange dimensions stated as 'to ANSI B16.5', "
                                           "not independently cross-checked against this project's own "
                                           "ASME B16.5 ingestion - kept as its own manufacturer-specific "
                                           "identity rather than aliased to the ASME canonical name."),
    ))
    facts.append(EngineeringFact(
        dimension_name=VOC.DIM_NIPOFLANGE_FLANGE_THICKNESS, value=Quantity(float(row["FlangeThk_D_mm"]), LENGTH_MM),
        applicability=applicability, verification_status=V.VERIFIED_MANUFACTURER_SPECIFIC,
        provenance=_prov("FlangeThk_D_mm", "Source Note 3: includes raised-face thickness (not a separate figure)."),
    ))
    facts.append(EngineeringFact(
        dimension_name=VOC.DIM_MASS, value=Quantity(float(row["Weight_kg_approx"]), MASS_KG),
        applicability=applicability, verification_status=V.VERIFIED_MANUFACTURER_SPECIFIC,
        provenance=_prov("Weight_kg_approx", "Source column is explicitly labelled 'APPROX' - approximate "
                                              "catalog mass, not an exact computed value."),
        notes="Approximate (source-labelled), not exact.",
    ))
    return facts


def _build_row_construction_param(row):
    class_key = normalize_pressure_class(row["ClassKey"])
    nps = normalize_nps(row["BranchNPS"])
    dn = normalize_dn(row["BranchDN"]) if "BranchDN" in row and row["BranchDN"] is not None else None
    applicability = Applicability(
        product_family=VOC.PRODUCT_FAMILY_OLET, standard=STANDARD_ID,
        fitting_type=VOC.FITTING_TYPE_NIPOFLANGE, class_key=class_key, nps=nps, dn=dn,
        manufacturer_profile=MANUFACTURER_PROFILE,
    )
    return ConstructionParameter(
        dimension_name=VOC.DIM_NIPOFLANGE_OVERALL_LENGTH, value=Quantity(float(row["OverallLength_B_mm"]), LENGTH_MM),
        applicability=applicability,
        provenance=_prov("OverallLength_B_mm", "Source Note 2: this dimension can be modified to suit "
                                                "purchaser's requirements - the source's own reference value, "
                                                "not a fixed standard dimension."),
        disclaimer="Per KAFCO Nipoflange datasheet Note 2: 'Dimension B can be modified to suit purchaser's "
                   "requirements.' This is a catalog reference/default overall length, not an authoritative "
                   "fixed dimension - confirm the actual required length with the customer before finalizing "
                   "a drawing.",
    )


def ingest_kafco_nipoflange(registry=None):
    """Reads, validates, and ingests the KAFCO Nipoflange JSON. Per row:
    3 EngineeringFacts (Flange OD, Flange THK, Weight - all
    VERIFIED_MANUFACTURER_SPECIFIC) + 1 ConstructionParameter (Overall
    Length, purchaser-modifiable per the source's own Note 2). Sorted by
    (class_key, NPS) for deterministic ingestion order."""
    if registry is None:
        registry = FactRegistry()

    data, source_file_rel = _load_source()
    _validate_top_level(data)
    rows = data["tables"][REQUIRED_TABLE]["rows"]

    all_errors = []
    for i, row in enumerate(rows):
        all_errors.extend(_validate_row(i, row))
    all_errors.extend(check_duplicate_key(
        "nipoflange_body_dims", rows,
        lambda r: (normalize_pressure_class(r["ClassKey"]), normalize_nps(r["BranchNPS"])),
    ))
    if all_errors:
        raise SourceValidationError(
            f"KAFCO Nipoflange source failed validation ({len(all_errors)} problem(s)): " + " | ".join(all_errors)
        )

    def _sort_key(r):
        return (int(normalize_pressure_class(r["ClassKey"])), nps_sort_key(normalize_nps(r["BranchNPS"])))

    ingested = []
    for row in sorted(rows, key=_sort_key):
        for fact in _build_row_facts(row):
            registry.add_checked(fact)
            ingested.append(fact)
        cp = _build_row_construction_param(row)
        registry.add(cp)
        ingested.append(cp)

    return registry, ingested
