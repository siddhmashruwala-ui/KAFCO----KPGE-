# -*- coding: utf-8 -*-
"""
kgpe.geometry.reducer_rules
===============================
Prompt 13 Sec.20-21: the reducer per-end outside-diameter dependency
Prompt 11 registered as blocking (CONSTRUCTION_RULE_REQUIREMENT_REGISTER).
This is NOT a cross-family dependency (both facts live in the same
buttweld_fitting/ASME_B16.9 identity space) - it is a per-ROLE resolution
gap: `outside_diameter_mm` is a shared cross-subtype identity queried by
plain `nps`, but the resolver's reducer-role base_criteria only populates
`large_end_nps`/`small_end_nps`, never `nps` - so one shared resolve()
call can never find either end's OD. This rule issues TWO separate
`resolver.resolve()` calls (one per end, each via the approved public
`EngineeringResolver` interface only), preserving each end's role,
source fact, and quarantine status independently - a reducer is NEVER
represented with one shared OD, and large/small ends are never swapped.
"""
from dataclasses import dataclass
from typing import Optional

from .construction_rules import ConstructionRuleStatus, ConstructionRuleOutcome
from .construction_value import ConstructionValue


class ReducerPerEndOutsideDiameterRule:
    rule_id = "reducer_per_end_outside_diameter_resolution"
    rule_version = "1"

    def resolve(self, resolver, standard, large_end_size, small_end_size):
        from ..resolver import EngineeringRequest, ResolutionStatus

        results = {}
        for role, size in (("large_end", large_end_size), ("small_end", small_end_size)):
            req = EngineeringRequest(product_family="buttweld_fitting", standard=standard,
                                      primary_size=size, dimensions=["outside_diameter_mm"])
            resolved = resolver.resolve(req)
            if resolved.status == ResolutionStatus.QUARANTINED_ENGINEERING_DATA:
                return ConstructionRuleOutcome(
                    ConstructionRuleStatus.RULE_BLOCKED_QUARANTINE, self.rule_id, self.rule_version,
                    detail=f"{role} (NPS{size}) outside_diameter_mm is quarantined: "
                           f"{resolved.quarantine_details}")
            if resolved.status != ResolutionStatus.RESOLVED:
                return ConstructionRuleOutcome(
                    ConstructionRuleStatus.RULE_INPUT_MISSING, self.rule_id, self.rule_version,
                    detail=f"{role} (NPS{size}) outside_diameter_mm did not resolve: "
                           f"status={resolved.status}")
            results[role] = resolved.resolved_dimensions["outside_diameter_mm"]

        large_entry, small_entry = results["large_end"], results["small_end"]
        large_cv = ConstructionValue(
            name="large_end_outside_diameter_mm", value=float(large_entry["value"]), unit=large_entry["unit"],
            rule_id=self.rule_id, rule_version=self.rule_version,
            input_dimension_refs=[{"name": "outside_diameter_mm", "value": large_entry["value"],
                                    "unit": large_entry["unit"], "source_ref": {
                                        "role": "large_end", "standard": standard, "nps": large_end_size,
                                        "source_file": large_entry.get("source_file")}}],
            derivation_trace=[f"per-end resolution: large_end (NPS{large_end_size}) outside_diameter_mm "
                               f"= {large_entry['value']}mm"],
        )
        small_cv = ConstructionValue(
            name="small_end_outside_diameter_mm", value=float(small_entry["value"]), unit=small_entry["unit"],
            rule_id=self.rule_id, rule_version=self.rule_version,
            input_dimension_refs=[{"name": "outside_diameter_mm", "value": small_entry["value"],
                                    "unit": small_entry["unit"], "source_ref": {
                                        "role": "small_end", "standard": standard, "nps": small_end_size,
                                        "source_file": small_entry.get("source_file")}}],
            derivation_trace=[f"per-end resolution: small_end (NPS{small_end_size}) outside_diameter_mm "
                               f"= {small_entry['value']}mm"],
        )
        return ConstructionRuleOutcome(ConstructionRuleStatus.RULE_APPLIED, self.rule_id, self.rule_version,
                                        value=(large_cv, small_cv),
                                        detail="Both ends resolved independently via the reducer's shared "
                                               "cross-subtype outside_diameter_mm identity.")
