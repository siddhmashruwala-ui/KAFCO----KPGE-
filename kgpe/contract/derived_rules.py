# -*- coding: utf-8 -*-
"""
kgpe.contract.derived_rules
==============================
Concrete DerivedRule instances for rules KGPE Prompt 3/40 fully verified
(100% match against an independent reproduction of ASME B16.5's general
tolerance table, Prompt 3 Sec.6 and Sec.9): raised-face height by pressure
class, and 2 of the 8 general-dimensional-tolerance bands (outside
diameter/hub-base, and bolt-circle - chosen because both are simple
single-band or unconditional rules with zero risk of mis-transcribing an
asymmetric +/- tolerance from memory).

This is NOT a migration of the JS CRM's `rfHeightMM()`/`stdTol()` into
production use by generator.py/rules/*.py - out of scope for Prompt 4,
which explicitly says "do not necessarily migrate every rule in this
prompt." It exists to prove the DerivedRule interface defined in
kgpe/contract/model.py works for real, previously-verified rules, using
logic re-derived independently from the Prompt 3 verification evidence
(wermac.org's explicit tolerance-table reproduction), not copied from the
JS source code.

The remaining 6 tolerance families (bore, hub-at-weld, thickness, hub
length, raised-face-height-dependent RF tolerance) are deliberately NOT
encoded here - they involve asymmetric (+/-) bands, and re-typing all 8
from memory in this prompt risks exactly the kind of transcription error
this whole project exists to prevent. Left for a future prompt with the
source re-verified alongside the code, not guessed at now.
"""
from .model import DerivedRule, EngineeringFactProvenance
from .applicability import Applicability
from .units import Quantity, LENGTH_MM
from . import verification as V

_TOLERANCE_PROVENANCE_KWARGS = dict(
    source_name="wermac.org 'Dimensional Tolerances of Weld Neck Flanges ASME B16.5'",
    source_type="supplier_reference",
    standard_designation="ASME B16.5",
    standard_edition=None,  # not confirmed by any source used in Prompt 3 - do not fabricate
)


def _rf_height_evaluate(class_key):
    """ASME B16.5 raised-face height: 1.6mm for Class<=300, 6.35mm above.
    Verified in KGPE Prompt 3/40 Sec.6 against wermac.org's explicit
    tolerance-table reproduction (exact match against JS CRM's rfHeightMM())."""
    try:
        cls = int(str(class_key))
    except (TypeError, ValueError):
        raise ValueError(f"class_key must be numeric for the RF-height rule, got {class_key!r}")
    return Quantity(1.6 if cls <= 300 else 6.35, LENGTH_MM)


RF_HEIGHT_BY_CLASS = DerivedRule(
    rule_name="asme_b16_5_raised_face_height_by_class",
    description="Raised-face height = 1.6mm for Class<=300, 6.35mm for higher classes.",
    applicability=Applicability(standard="ASME_B16.5"),
    provenance=EngineeringFactProvenance(
        original_field="Diameter Contact Face tolerance rows",
        verification_method="Directly fetched and compared rule-for-rule against JS CRM's rfHeightMM(); exact match",
        verification_sources=["wermac.org (fetched live, Prompt 3)"],
        notes="Re-derived independently for KGPE; not copied from JS source code.",
        **_TOLERANCE_PROVENANCE_KWARGS,
    ),
    evaluate=_rf_height_evaluate,
)


def _tol_od_or_hub_base_evaluate(nps):
    """General OD / hub-at-base diameter tolerance: +/-1.6mm for NPS<=24,
    +/-3.2mm above. Verified in Prompt 3 Sec.9 (8/8 rule families matched)."""
    n = float(nps)
    return Quantity(1.6 if n <= 24 else 3.2, LENGTH_MM)


TOLERANCE_OUTSIDE_DIAMETER = DerivedRule(
    rule_name="asme_b16_5_tolerance_outside_diameter",
    description="General OD tolerance (symmetric): +/-1.6mm for NPS<=24, +/-3.2mm above. "
                "Also applies to hub-at-base diameter per the same source.",
    applicability=Applicability(standard="ASME_B16.5"),
    provenance=EngineeringFactProvenance(
        original_field="Diameter OD / Diameter Hub at Base tolerance rows",
        verification_method="Directly fetched and compared rule-for-rule against JS CRM's stdTol(); exact match",
        verification_sources=["wermac.org (fetched live, Prompt 3)"],
        **_TOLERANCE_PROVENANCE_KWARGS,
    ),
    evaluate=_tol_od_or_hub_base_evaluate,
)


def _tol_bolt_circle_evaluate(nps):
    """Bolt-circle diameter tolerance: +/-1.6mm at all sizes, unconditional.
    Verified in Prompt 3 Sec.9."""
    return Quantity(1.6, LENGTH_MM)


TOLERANCE_BOLT_CIRCLE = DerivedRule(
    rule_name="asme_b16_5_tolerance_bolt_circle",
    description="Bolt-circle diameter tolerance: +/-1.6mm at all sizes.",
    applicability=Applicability(standard="ASME_B16.5"),
    provenance=EngineeringFactProvenance(
        original_field="Drilling/Bolt Circle tolerance row",
        verification_method="Directly fetched and compared rule-for-rule against JS CRM's stdTol(); exact match",
        verification_sources=["wermac.org (fetched live, Prompt 3)"],
        **_TOLERANCE_PROVENANCE_KWARGS,
    ),
    evaluate=_tol_bolt_circle_evaluate,
)

ALL_DERIVED_RULES = (RF_HEIGHT_BY_CLASS, TOLERANCE_OUTSIDE_DIAMETER, TOLERANCE_BOLT_CIRCLE)
