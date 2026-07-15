# -*- coding: utf-8 -*-
"""
kgpe.geometry.cross_family
==============================
Prompt 12 Sec.16: the framework for explicit cross-family engineering
dependencies (a geometry profile needing an authoritative dimension from
a RELATED engineering family - e.g. a flange's bore from pipe schedule
data). A `CrossFamilyDependencyRule`:

  - is declared explicitly (a named, versioned rule object - never an
    implicit lookup buried in a product builder);
  - uses ONLY the approved `EngineeringResolver`/`CanonicalReader`
    interfaces (never source JSON, never an adapter import);
  - preserves both the TARGET engineering identity (what needed the
    value) and the SOURCE engineering identity (where the value actually
    came from) in the resulting `ConstructionValue`'s provenance;
  - never searches for a "close" value, never cross-converts NPS/DN/JIS
    size systems implicitly, never picks a schedule that was not
    explicitly supplied.

Prompt 12 does not wire any cross-family rule into the pipe or elbow
product builders (neither reference product needs one). This module
proves the framework with exactly one low-risk rule - the flange-bore-
via-pipe-schedule case Prompt 11's construction-rule register already
identified - tested standalone, not invoked by the kernel dispatch yet.
"""
from dataclasses import dataclass
from typing import Optional

from .construction_rules import ConstructionRuleStatus, ConstructionRuleOutcome, PipeBoreConstructionRule


class CrossFamilyDependencyRule:
    rule_id = "base_cross_family_dependency_rule"
    rule_version = "0"

    def resolve(self, resolver, **kwargs) -> ConstructionRuleOutcome:
        raise NotImplementedError


class FlangeBoreViaPipeScheduleRule(CrossFamilyDependencyRule):
    """Proof-of-concept cross-family rule (Sec.16): derives a flange's
    bore from an EXPLICITLY supplied mating pipe standard + schedule, via
    the normal `EngineeringResolver` public interface only. Only supports
    NPS-based flanges/pipes for now (ASME) - never silently cross-converts
    DN/JIS sizes onto an NPS pipe lookup; any other size system is
    `RULE_NOT_APPLICABLE`, not guessed."""
    rule_id = "flange_bore_via_pipe_schedule_cross_reference"
    rule_version = "1"

    def resolve(self, resolver, target_standard, target_size_system, target_size,
                pipe_standard, pipe_schedule):
        from ..resolver import EngineeringRequest, ResolutionStatus

        if target_size_system != "nps":
            return ConstructionRuleOutcome(
                ConstructionRuleStatus.RULE_NOT_APPLICABLE, self.rule_id, self.rule_version,
                detail=f"Only NPS-based flange/pipe cross-reference is supported - "
                       f"target_size_system={target_size_system!r} is not eligible (no implicit "
                       f"NPS/DN/JIS conversion is ever performed).")
        if not pipe_standard or not pipe_schedule:
            return ConstructionRuleOutcome(
                ConstructionRuleStatus.RULE_INPUT_MISSING, self.rule_id, self.rule_version,
                detail="An explicit pipe_standard and pipe_schedule are both required - never inferred.")

        # NOTE: kgpe.resolver.engine.EngineeringResolver applies ONE shared
        # base_criteria (including `schedule`) to every dimension in a
        # single resolve() call - and a pipe's outside_diameter_mm is a
        # rating-independent dimension (only wall_thickness_mm varies by
        # schedule; see orchestration.py's own documented finding for the
        # same resolver limitation). Querying both dimensions in one call
        # would spuriously fail OD with the schedule filter attached, so
        # - exactly like Prompt 11's orchestration-level rating-relaxation
        # fallback - this rule issues TWO separate resolver.resolve() calls
        # instead: one for the rating-independent OD (no schedule), one for
        # the rating-dependent wall thickness (with schedule). This is a
        # local, rule-specific application of the same already-established
        # principle, not a modification of kgpe.resolver.engine itself.
        od_req = EngineeringRequest(product_family="pipe", standard=pipe_standard, primary_size=target_size,
                                     dimensions=["outside_diameter_mm"])
        wt_req = EngineeringRequest(product_family="pipe", standard=pipe_standard, primary_size=target_size,
                                     schedule=pipe_schedule, dimensions=["wall_thickness_mm"])
        od_resolved = resolver.resolve(od_req)
        wt_resolved = resolver.resolve(wt_req)

        for resolved, label in ((od_resolved, "outside_diameter_mm"), (wt_resolved, "wall_thickness_mm")):
            if resolved.status == ResolutionStatus.QUARANTINED_ENGINEERING_DATA:
                return ConstructionRuleOutcome(
                    ConstructionRuleStatus.RULE_BLOCKED_QUARANTINE, self.rule_id, self.rule_version,
                    detail=f"Mating pipe {label} is quarantined: {resolved.quarantine_details}")
            if resolved.status != ResolutionStatus.RESOLVED:
                return ConstructionRuleOutcome(
                    ConstructionRuleStatus.RULE_INPUT_MISSING, self.rule_id, self.rule_version,
                    detail=f"Mating pipe ({pipe_standard} NPS{target_size} {pipe_schedule}) {label} did not "
                           f"resolve: status={resolved.status}")

        od_entry = od_resolved.resolved_dimensions.get("outside_diameter_mm")
        wt_entry = wt_resolved.resolved_dimensions.get("wall_thickness_mm")
        bore_rule = PipeBoreConstructionRule()
        bore_outcome = bore_rule.apply(
            od_value=od_entry["value"], od_unit=od_entry["unit"],
            od_source_ref={"product_family": "pipe", "standard": pipe_standard, "nps": target_size,
                            "schedule": pipe_schedule, "source_file": od_entry.get("source_file")},
            wt_value=wt_entry["value"], wt_unit=wt_entry["unit"],
            wt_source_ref={"product_family": "pipe", "standard": pipe_standard, "nps": target_size,
                            "schedule": pipe_schedule, "source_file": wt_entry.get("source_file")},
        )
        if not bore_outcome.is_applied():
            return ConstructionRuleOutcome(ConstructionRuleStatus.RULE_UNSUPPORTED, self.rule_id,
                                            self.rule_version, detail=bore_outcome.detail)

        cv = bore_outcome.value
        cv.derivation_trace.append(
            f"cross-family: target=flange({target_standard} NPS{target_size}) <- "
            f"source=pipe({pipe_standard} NPS{target_size} {pipe_schedule})")
        return ConstructionRuleOutcome(ConstructionRuleStatus.RULE_APPLIED, self.rule_id, self.rule_version,
                                        value=cv, detail="Applied via cross-family pipe-schedule reference.")
