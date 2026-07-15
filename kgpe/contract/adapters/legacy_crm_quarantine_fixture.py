# -*- coding: utf-8 -*-
"""
kgpe.contract.adapters.legacy_crm_quarantine_fixture
=======================================================
NOT a source adapter for an engineering standard. This is a small, clearly
separated FIXTURE proving that KGPE's production ingestion architecture
(FactRegistry + EngineeringFact + verification-status quarantine
enforcement) can safely retain known-bad values without ever returning
them as authoritative geometry input (Prompt 5 Sec.18).

The three records loaded here originate from KGPE Prompt 3/40's audit of
the legacy JS CRM dashboard (KAFCO_CRM_Dashboard.html), NOT from any ASME
source JSON, and NOT re-read live from the CRM file by this module:

  1. NPS14/Class150 raised-face diameter CONFLICT: the JS CRM's RF_BORE
     table said 419.1mm; an independent source (Texas Flange) said
     412.75mm - a genuine, unresolved 6.35mm/0.25in discrepancy
     (Prompt 3 Sec.5). Both sides are recorded, deliberately, so neither
     is lost - see the note on `registry.add()` vs `add_checked()` below.
  2. Class-300 length-through-hub (HUB_DIM Y): the JS CRM's value is
     consistently ~1.5mm higher than the one cross-check source
     available (Texas Flange's L2 column), with no confirmed explanation
     (Prompt 3 Sec.4) - UNVERIFIED, not conflicting (only one number
     exists for this cell; it just isn't confirmed).

Do NOT extend this file to ingest the CRM JavaScript wholesale - that
remains explicitly out of scope (Prompt 5 Sec.18/24). This exists only to
prove quarantine works against real historical findings, not as a
migration path for the CRM's own data.
"""
from ..model import EngineeringFact, EngineeringFactProvenance, FactRegistry
from ..applicability import Applicability
from ..units import Quantity, LENGTH_MM
from .. import vocabulary as VOC
from .. import verification as V
from ..normalization import normalize_nps, normalize_pressure_class


def load_legacy_crm_quarantine_fixture(registry=None):
    """Adds 3 EngineeringFact records to `registry` (a new FactRegistry if
    none given) and returns it: two conflicting NPS14/Class150
    raised-face-diameter facts, and one unverified Class-300
    length-through-hub fact. Uses the registry's plain `add()`, NOT
    `add_checked()` - the two RF-diameter facts share the same
    engineering identity ON PURPOSE (that is what makes them a
    "conflict"), and add_checked() would (correctly, for a normal
    ingestion) refuse to store the second one. Here we want BOTH
    historical values retained side by side for inspection, each already
    tagged QUARANTINED_CONFLICT, rather than picking a winner."""
    if registry is None:
        registry = FactRegistry()

    nps14 = normalize_nps("14")
    cls150 = normalize_pressure_class("150")
    cls300 = normalize_pressure_class("300")

    js_rf = EngineeringFact(
        dimension_name=VOC.DIM_RAISED_FACE_DIAMETER,
        value=Quantity(419.1, LENGTH_MM),
        applicability=Applicability(product_family=VOC.PRODUCT_FAMILY_FLANGE, standard="ASME_B16.5",
                                     class_key=cls150, nps=nps14),
        verification_status=V.QUARANTINED_CONFLICT,
        provenance=EngineeringFactProvenance(
            source_name="Legacy JS CRM dashboard RF_BORE table (KAFCO_CRM_Dashboard.html)",
            source_type="legacy_code",
            standard_designation="ASME B16.5",
            original_field="RF_BORE['150']['14']",
            transcription_method="Manually recorded from KGPE Prompt 3/40 audit findings - "
                                  "NOT re-read from the live CRM file by this fixture.",
            verification_method="Cross-checked against Texas Flange's 'R' column in KGPE Prompt 3/40; "
                                 "conflicted by exactly 6.35mm/0.25in.",
            notes="Not authoritative source data. Retained only to prove the quarantine mechanism.",
        ),
        notes="QUARANTINED_CONFLICT - conflicts with the Texas Flange value below.",
    )
    texas_flange_rf = EngineeringFact(
        dimension_name=VOC.DIM_RAISED_FACE_DIAMETER,
        value=Quantity(412.75, LENGTH_MM),
        applicability=Applicability(product_family=VOC.PRODUCT_FAMILY_FLANGE, standard="ASME_B16.5",
                                     class_key=cls150, nps=nps14),
        verification_status=V.QUARANTINED_CONFLICT,
        provenance=EngineeringFactProvenance(
            source_name="Texas Flange dimension table",
            source_type="supplier_reference",
            standard_designation="ASME B16.5",
            original_field="R (Class 150 table)",
            transcription_method="Manually recorded from KGPE Prompt 3/40 audit findings.",
            verification_method="Fetched live and compared against JS CRM RF_BORE in KGPE Prompt 3/40; "
                                 "conflicted by exactly 6.35mm/0.25in.",
            notes="Not authoritative source data. Retained only to prove the quarantine mechanism.",
        ),
        notes="QUARANTINED_CONFLICT - conflicts with the JS CRM value above.",
    )
    unverified_hub_len = EngineeringFact(
        dimension_name=VOC.DIM_LENGTH_THROUGH_HUB,
        value=Quantity(114.3, LENGTH_MM),
        applicability=Applicability(product_family=VOC.PRODUCT_FAMILY_FLANGE, standard="ASME_B16.5",
                                     class_key=cls300, nps=normalize_nps("2")),
        verification_status=V.QUARANTINED_UNVERIFIED,
        provenance=EngineeringFactProvenance(
            source_name="Legacy JS CRM dashboard HUB_DIM table (KAFCO_CRM_Dashboard.html)",
            source_type="legacy_code",
            standard_designation="ASME B16.5",
            original_field="HUB_DIM['300']['2'][1]",
            transcription_method="Manually recorded from KGPE Prompt 3/40 audit findings.",
            verification_method="Compared against Texas Flange's 'L2' column in KGPE Prompt 3/40; found a "
                                 "consistent ~1.5mm/0.06in gap, unresolved.",
            notes="Not authoritative source data. Retained only to prove the quarantine mechanism.",
        ),
        notes="QUARANTINED_UNVERIFIED - unresolved ~1.5mm gap vs the one cross-check source available.",
    )

    for fact in (js_rf, texas_flange_rf, unverified_hub_len):
        registry.add(fact)
    return registry
