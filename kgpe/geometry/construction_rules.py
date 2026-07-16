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


class CapLengthSelectionRule(ConstructionRule):
    """Prompt 13 Sec.16-17: formalizes the H-vs-H1 cap-length selection
    policy Prompt 11 identified as missing (legacy rules/buttweld.py._cap()
    always uses standard-wall H unconditionally). Both
    cap_length_standard_wall_mm and cap_length_heavy_wall_mm/
    cap_wall_thickness_threshold_mm are already VERIFIED_AUTHORITATIVE
    (Prompt 7) - only the SELECTION between them was missing.

    Policy: if no actual mating-pipe wall thickness is supplied at all,
    the standard-wall length is used (matches pre-existing legacy
    behaviour, applied when the caller made no wall-context request -
    RULE_NOT_APPLICABLE, not a guess). If an actual wall thickness IS
    supplied, both cap_length_heavy_wall_mm and
    cap_wall_thickness_threshold_mm must already be present (the caller
    must have explicitly requested these optional dimensions per Prompt
    11's "optional only when explicitly included" rule) - if either is
    absent, this fails closed (RULE_INPUT_MISSING) rather than guessing a
    threshold or fabricating a heavy-wall length."""
    rule_id = "cap_length_selection_standard_vs_heavy_wall"
    rule_version = "1"

    def apply(self, standard_length_value, standard_length_unit, actual_wall_thickness_mm=None,
              heavy_wall_length_entry=None, wall_threshold_entry=None):
        if actual_wall_thickness_mm is None:
            value = ConstructionValue(
                name="selected_cap_length_mm", value=float(standard_length_value), unit=standard_length_unit,
                rule_id=self.rule_id, rule_version=self.rule_version,
                input_dimension_refs=[{"name": "cap_length_standard_wall_mm", "value": standard_length_value,
                                        "unit": standard_length_unit}],
                derivation_trace=["no actual mating-pipe wall thickness supplied - "
                                   "standard-wall length (H) selected by default policy, not a guess"],
            )
            return ConstructionRuleOutcome(ConstructionRuleStatus.RULE_NOT_APPLICABLE, self.rule_id,
                                            self.rule_version, value=value,
                                            detail="No wall context supplied - standard-wall length used.")

        if heavy_wall_length_entry is None or wall_threshold_entry is None:
            return ConstructionRuleOutcome(
                ConstructionRuleStatus.RULE_INPUT_MISSING, self.rule_id, self.rule_version,
                detail="Actual wall thickness was supplied but cap_length_heavy_wall_mm/"
                       "cap_wall_thickness_threshold_mm were not explicitly requested/resolved - "
                       "cannot make a wall-based selection without both.")

        threshold = float(wall_threshold_entry["value"])
        if actual_wall_thickness_mm <= threshold:
            selected_value, selected_name = standard_length_value, "cap_length_standard_wall_mm"
            selection = "standard_wall (H): actual wall <= published threshold"
        else:
            selected_value, selected_name = heavy_wall_length_entry["value"], "cap_length_heavy_wall_mm"
            selection = "heavy_wall (H1): actual wall > published threshold"

        value = ConstructionValue(
            name="selected_cap_length_mm", value=float(selected_value), unit=standard_length_unit,
            rule_id=self.rule_id, rule_version=self.rule_version,
            input_dimension_refs=[
                {"name": selected_name, "value": selected_value, "unit": standard_length_unit},
                {"name": "cap_wall_thickness_threshold_mm", "value": threshold, "unit": standard_length_unit},
                {"name": "actual_mating_pipe_wall_thickness_mm", "value": actual_wall_thickness_mm,
                 "unit": "mm"},
            ],
            derivation_trace=[f"{selection} (actual_wall={actual_wall_thickness_mm}mm, threshold={threshold}mm)"],
        )
        return ConstructionRuleOutcome(ConstructionRuleStatus.RULE_APPLIED, self.rule_id, self.rule_version,
                                        value=value, detail=selection)


class OletReinforcementEnvelopeConstructionRule(ConstructionRule):
    """Prompt 15 Sec.9: MSS SP-97 does not publish a continuous
    reinforcement-body contour for weldolet/sockolet/threadolet - only
    discrete manufacturer body dimensions (height/face-to-face/base OD/
    bore[+socket dia], all Bonney Forge VERIFIED_MANUFACTURER_SPECIFIC).
    This rule formalizes a versioned, explicitly construction-derived
    approximation: a straight-sided frustum from the base OD (run
    interface, the wide end) to the branch bore diameter (branch
    interface, the narrow end) over the published height - never claimed
    as an MSS-published contour, only ever a labeled envelope
    approximation (kgpe.geometry.builders.build_frustum_solid, the same
    primitive Prompt 13's buttweld reducer uses)."""
    rule_id = "olet_reinforcement_body_envelope_frustum"
    rule_version = "1"

    def apply(self, base_od_value, branch_opening_value, height_value, unit="mm"):
        if base_od_value is None or branch_opening_value is None or height_value is None:
            return ConstructionRuleOutcome(
                ConstructionRuleStatus.RULE_INPUT_MISSING, self.rule_id, self.rule_version,
                detail="base_od_value, branch_opening_value, and height_value are all required.")
        try:
            base_od = float(base_od_value)
            branch = float(branch_opening_value)
            height = float(height_value)
        except (TypeError, ValueError):
            return ConstructionRuleOutcome(ConstructionRuleStatus.RULE_UNSUPPORTED, self.rule_id,
                                            self.rule_version, detail="Non-numeric input.")
        if base_od <= NEAR_ZERO_MM or branch <= NEAR_ZERO_MM or height <= NEAR_ZERO_MM:
            return ConstructionRuleOutcome(ConstructionRuleStatus.RULE_UNSUPPORTED, self.rule_id,
                                            self.rule_version, detail="All inputs must be positive.")
        if branch > base_od:
            return ConstructionRuleOutcome(
                ConstructionRuleStatus.RULE_UNSUPPORTED, self.rule_id, self.rule_version,
                detail=f"branch_opening_value ({branch!r}) exceeds base_od_value ({base_od!r}) - the "
                       f"envelope would taper outward, which this rule never constructs.")

        value = ConstructionValue(
            name="reinforcement_body_envelope", value=height, unit=unit,
            rule_id=self.rule_id, rule_version=self.rule_version,
            input_dimension_refs=[
                {"name": "olet_base_outside_diameter_mm", "value": base_od, "unit": unit},
                {"name": "olet_bore_diameter_mm", "value": branch, "unit": unit},
                {"name": "olet_height_mm", "value": height, "unit": unit},
            ],
            derivation_trace=[
                f"reinforcement envelope: frustum from base_OD={base_od}{unit} (run interface) to "
                f"branch_opening={branch}{unit} (branch interface) over height={height}{unit} - a "
                f"construction-derived approximate envelope, not an MSS SP-97-published contour."],
        )
        return ConstructionRuleOutcome(ConstructionRuleStatus.RULE_APPLIED, self.rule_id, self.rule_version,
                                        value=value, detail="Applied.")
