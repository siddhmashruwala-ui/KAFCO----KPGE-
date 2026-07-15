# -*- coding: utf-8 -*-
"""
kgpe.geometry.construction_rules
====================================
Prompt 12 Sec.12-14: the construction-rule framework. A construction rule
is a documented, deterministic, VERSIONED geometric derivation required
to build geometry from authoritative engineering dimensions - never an
automatic authoritative engineering fact, never a silent guess.
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

from .construction_value import ConstructionValue
from .primitives import InvalidPrimitiveInputError
from .policy import NEAR_ZERO_MM


class ConstructionRuleStatus:
    RULE_APPLIED = "RULE_APPLIED"
    RULE_NOT_APPLICABLE = "RULE_NOT_APPLICABLE"
    RULE_INPUT_MISSING = "RULE_INPUT_MISSING"
    RULE_BLOCKED_QUARANTINE = "RULE_BLOCKED_QUARANTINE"
    RULE_UNSUPPORTED = "RULE_UNSUPPORTED"


ALL_CONSTRUCTION_RULE_STATUSES = frozenset({
    ConstructionRuleStatus.RULE_APPLIED, ConstructionRuleStatus.RULE_NOT_APPLICABLE,
    ConstructionRuleStatus.RULE_INPUT_MISSING, ConstructionRuleStatus.RULE_BLOCKED_QUARANTINE,
    ConstructionRuleStatus.RULE_UNSUPPORTED,
})


@dataclass
class ConstructionRuleOutcome:
    status: str
    rule_id: str
    rule_version: str
    value: Optional[ConstructionValue] = None
    detail: str = ""

    def is_applied(self):
        return self.status == ConstructionRuleStatus.RULE_APPLIED


class ConstructionRule:
    """Base shape every construction rule follows (Sec.12): rule_id,
    rule_version, apply(). Subclasses implement `apply()` and must never
    raise for an expected engineering situation - only for a genuine
    programmer error - returning a `ConstructionRuleOutcome` instead."""
    rule_id = "base_construction_rule"
    rule_version = "0"

    def apply(self, **kwargs) -> ConstructionRuleOutcome:
        raise NotImplementedError


class PipeBoreConstructionRule(ConstructionRule):
    """Sec.14: formalizes bore = outside_diameter - 2*wall_thickness as a
    versioned deterministic construction rule. Inputs must already be
    resolved AUTHORITATIVE dimensions (VERIFIED_AUTHORITATIVE/
    VERIFIED_DERIVED_RULE) - this rule does not itself check quarantine
    status; the caller (kernel product builder) must have already
    obtained these values from a GEOMETRY_READY GeometrySpecification,
    whose compiler (Prompt 11) already fails closed on quarantine."""
    rule_id = "pipe_bore_from_od_wall_thickness"
    rule_version = "1"

    def apply(self, od_value, od_unit, od_source_ref, wt_value, wt_unit, wt_source_ref):
        trace = []
        if od_value is None or wt_value is None:
            return ConstructionRuleOutcome(
                ConstructionRuleStatus.RULE_INPUT_MISSING, self.rule_id, self.rule_version,
                detail="outside_diameter_mm and wall_thickness_mm are both required inputs.")
        if od_unit != "mm" or wt_unit != "mm":
            return ConstructionRuleOutcome(
                ConstructionRuleStatus.RULE_UNSUPPORTED, self.rule_id, self.rule_version,
                detail=f"Rule only supports mm inputs, got od_unit={od_unit!r} wt_unit={wt_unit!r}.")
        try:
            od = float(od_value)
            wt = float(wt_value)
        except (TypeError, ValueError):
            return ConstructionRuleOutcome(
                ConstructionRuleStatus.RULE_UNSUPPORTED, self.rule_id, self.rule_version,
                detail=f"Non-numeric input: od={od_value!r} wt={wt_value!r}.")

        if not (od == od and wt == wt) or od in (float("inf"), float("-inf")) or wt in (float("inf"), float("-inf")):
            return ConstructionRuleOutcome(
                ConstructionRuleStatus.RULE_UNSUPPORTED, self.rule_id, self.rule_version,
                detail="Non-finite input value.")
        if od <= NEAR_ZERO_MM:
            return ConstructionRuleOutcome(
                ConstructionRuleStatus.RULE_UNSUPPORTED, self.rule_id, self.rule_version,
                detail=f"outside_diameter_mm must be positive, got {od!r}.")
        if wt <= NEAR_ZERO_MM:
            return ConstructionRuleOutcome(
                ConstructionRuleStatus.RULE_UNSUPPORTED, self.rule_id, self.rule_version,
                detail=f"wall_thickness_mm must be positive, got {wt!r}.")
        if not (2.0 * wt < od):
            return ConstructionRuleOutcome(
                ConstructionRuleStatus.RULE_UNSUPPORTED, self.rule_id, self.rule_version,
                detail=f"2*wall_thickness_mm ({2.0 * wt!r}) must be less than outside_diameter_mm ({od!r}).")

        bore = od - 2.0 * wt
        trace.append(f"bore_diameter_mm = outside_diameter_mm({od}) - 2*wall_thickness_mm({wt}) = {bore}")
        if bore <= NEAR_ZERO_MM:
            return ConstructionRuleOutcome(
                ConstructionRuleStatus.RULE_UNSUPPORTED, self.rule_id, self.rule_version,
                detail=f"Derived bore {bore!r} is not positive.")

        value = ConstructionValue(
            name="bore_diameter_mm", value=bore, unit="mm",
            rule_id=self.rule_id, rule_version=self.rule_version,
            input_dimension_refs=[
                {"name": "outside_diameter_mm", "value": od, "unit": "mm", "source_ref": od_source_ref},
                {"name": "wall_thickness_mm", "value": wt, "unit": "mm", "source_ref": wt_source_ref},
            ],
            derivation_trace=trace,
        )
        return ConstructionRuleOutcome(ConstructionRuleStatus.RULE_APPLIED, self.rule_id, self.rule_version,
                                        value=value, detail="Applied successfully.")
