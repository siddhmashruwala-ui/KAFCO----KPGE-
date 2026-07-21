# -*- coding: utf-8 -*-
"""
kgpe.geometry.nipoflange_inputs
===================================
2026-07-21 (nipoflange product generator): pipeline-level derivation of
the ConstructionValue inputs kgpe.geometry.products.nipoflange.build()
needs beyond its resolved canonical dims. This sits at the PIPELINE
layer (run_pipeline), exactly where cross-family construction inputs
belong: the kernel never resolves anything itself, the bridge/CRM never
performs engineering, and every derivation below goes through declared,
versioned rules with full provenance.

Derived (only when the caller did not already supply them):
  - overall_length_value: KAFCO catalog Overall Length B, read as an
    explicitly opted-in CONSTRUCTION_PARAMETER via CanonicalReader.read()
    (purchaser-modifiable per the source's own Note 2 - the mandatory
    disclaimer travels in the derivation trace).
  - neck_od_value: branch-size pipe OD via
    kgpe.geometry.cross_family.NipoflangeNeckODViaBranchPipeODRule.
  - tip_od_value: reduced-size pipe OD via the same rule, ONLY when the
    caller supplied a raw "reduced_tip_size" product kwarg (the per-order
    "REDUCED TO <size>" fact - real customer data, never assumed). It is
    deliberately NOT an EngineeringRequest identity field: the KAFCO
    catalog rows are keyed by class + Branch NB only, and the resolver's
    large/small_end_size fields carry strict REDUCER-family semantics
    (large_end_*/small_end_* criteria) that would never match these
    facts. run_pipeline pops the raw kwarg before the kernel ever sees
    it, so the kernel's already-resolved-inputs-only contract holds.

Fail-open contract: any derivation that cannot complete simply leaves
its kwarg absent - the product builder then fails CLOSED with an honest
CONSTRUCTION_RULE_UNAVAILABLE, never a fabricated value.
"""
from .construction_value import ConstructionValue
from .cross_family import NipoflangeNeckODViaBranchPipeODRule, FlangeBoreViaPipeScheduleRule

NIPOFLANGE_PROFILE_ID = "flange_nipoflange"

_OVERALL_LENGTH_RULE_ID = "nipoflange_overall_length_catalog_reference"
_OVERALL_LENGTH_RULE_VERSION = "1"
_TRIM_RULE_ID = "nipoflange_purchaser_specified_overall_length"
_TRIM_RULE_VERSION = "1"
_BORE_PIPE_STANDARD = "ASME_B36.10M"


def derive_nipoflange_product_kwargs(request, geometry_specification, resolver, reduced_tip_size=None,
                                       bore_schedule=None, overall_length_override=None):
    """Returns a dict with any of overall_length_value / neck_od_value /
    tip_od_value that could be derived. Never raises for an expected
    engineering outcome; never overwrites caller-supplied kwargs (the
    caller merges with its own values winning)."""
    derived = {}
    if resolver is None:
        return derived
    identity = geometry_specification.engineering_object_identity or {}
    size_system = identity.get("size_system")
    primary_size = identity.get("primary_size")
    if size_system != "nps" or primary_size is None:
        return derived

    od_rule = NipoflangeNeckODViaBranchPipeODRule()
    neck_outcome = od_rule.resolve(resolver, target_size_system=size_system,
                                    target_size=primary_size, value_name="neck_outside_diameter_mm")
    if neck_outcome.is_applied():
        derived["neck_od_value"] = neck_outcome.value

    outlet_nps = primary_size
    if reduced_tip_size is not None:
        try:
            from ..contract.normalization import normalize_nps
            small_nps = normalize_nps(reduced_tip_size)
        except Exception:
            small_nps = None
        if small_nps is not None:
            outlet_nps = small_nps
            tip_outcome = od_rule.resolve(resolver, target_size_system="nps",
                                           target_size=small_nps, value_name="tip_outside_diameter_mm")
            if tip_outcome.is_applied():
                derived["tip_od_value"] = tip_outcome.value

    # Bore (rule v4): the order's stated schedule fully determines the bore
    # at the OUTLET size (branch-pipe ID = OD - 2*WT), derived through the
    # existing cross-family FlangeBoreViaPipeScheduleRule with an explicit
    # pipe standard - real order data, never a default. Source priority:
    # the raw "bore_schedule" product kwarg, else request.schedule.
    schedule = bore_schedule or getattr(request, "schedule", None)
    if schedule and outlet_nps is not None:
        bore_rule = FlangeBoreViaPipeScheduleRule()
        bore_outcome = bore_rule.resolve(resolver, target_standard="KAFCO_NIPOFLANGE",
                                          target_size_system="nps", target_size=outlet_nps,
                                          pipe_standard=_BORE_PIPE_STANDARD, pipe_schedule=schedule)
        if bore_outcome.is_applied():
            derived["bore_value"] = bore_outcome.value

        # Reducing nipoflange dual bore (2026-07-21, per Siddh): a genuinely
        # reducing item (outlet_nps != primary_size, i.e. reduced_tip_size
        # was supplied and normalized to a smaller NPS) has a FLANGE-side
        # bore that is the flange's OWN (larger) size's branch-pipe ID, not
        # the outlet's - e.g. a 2"x1" reducing nipoflange bores through the
        # flange and hub at the 2" ID, only stepping down to the 1" ID after
        # the Hub-to-Neck Transition (kgpe.geometry.products.nipoflange
        # builds the actual conical transition; this only derives the
        # second, flange-side ConstructionValue). Same schedule as the
        # outlet (the KAFCO source states one schedule per order; only the
        # NPS differs between the two ends) - never a separate/default
        # schedule. Never derived for a size-on-size item, where it would
        # just duplicate bore_value.
        if outlet_nps != primary_size:
            flange_bore_rule = FlangeBoreViaPipeScheduleRule()
            flange_bore_outcome = flange_bore_rule.resolve(
                resolver, target_standard="KAFCO_NIPOFLANGE", target_size_system="nps",
                target_size=primary_size, pipe_standard=_BORE_PIPE_STANDARD, pipe_schedule=schedule)
            if flange_bore_outcome.is_applied():
                derived["flange_bore_value"] = flange_bore_outcome.value

    # Purchaser-trimmed overall length (Note 2): a raw mm override supplied
    # per order; wrapped as a provenance-carrying ConstructionValue. The
    # catalog-default overall_length_value below stays untouched - it fixes
    # the taper geometry; the override only resizes the straight trim zone.
    if overall_length_override is not None:
        try:
            b_actual = float(overall_length_override)
        except (TypeError, ValueError):
            b_actual = None
        if b_actual is not None and b_actual > 0.0:
            derived["actual_overall_length_value"] = ConstructionValue(
                name="nipoflange_actual_overall_length_mm", value=b_actual, unit="mm",
                rule_id=_TRIM_RULE_ID, rule_version=_TRIM_RULE_VERSION,
                derivation_trace=[
                    "Purchaser-specified overall length (KAFCO source Note 2: 'Dimension B can be "
                    "modified to suit purchaser's requirements') - per-order data, applied to the "
                    "straight outlet trim zone only."],
            )

    # Overall Length B: an explicitly opted-in construction parameter from
    # the KAFCO catalog row matching this exact identity.
    try:
        from ..contract import vocabulary as VOC
        reader = getattr(resolver, "reader", None)
        class_key = identity.get("class_key") or identity.get("pressure_class")
        if reader is not None:
            criteria = {"product_family": "flange", "standard": "KAFCO_NIPOFLANGE",
                        "flange_type": "nipoflange", "nps": primary_size,
                        "manufacturer_profile": "KAFCO"}
            if class_key is not None:
                criteria["class_key"] = str(class_key)
            # FactRegistry.query() is the sanctioned public path that can
            # return ConstructionParameter records under an explicit
            # allow_construction_parameter=True opt-in (CanonicalReader.
            # read() only ever returns EngineeringFacts, by design).
            usable = reader.registry.query(VOC.DIM_NIPOFLANGE_OVERALL_LENGTH,
                                            allow_manufacturer_specific=True,
                                            allow_construction_parameter=True, **criteria)
            if len(usable) == 1:
                fact = usable[0]
                derived["overall_length_value"] = ConstructionValue(
                    name="nipoflange_overall_length_mm", value=float(fact.value.value),
                    unit=str(fact.value.unit), rule_id=_OVERALL_LENGTH_RULE_ID,
                    rule_version=_OVERALL_LENGTH_RULE_VERSION,
                    input_dimension_refs=[{"name": VOC.DIM_NIPOFLANGE_OVERALL_LENGTH,
                                            "value": fact.value.value, "unit": str(fact.value.unit),
                                            "source_ref": {"standard": "KAFCO_NIPOFLANGE",
                                                            "nps": primary_size, "class_key": class_key,
                                                            "manufacturer_profile": "KAFCO"}}],
                    derivation_trace=[
                        "KAFCO catalog Overall Length B, opted in as a CONSTRUCTION_PARAMETER "
                        "(source Note 2: 'Dimension B can be modified to suit purchaser's "
                        "requirements') - a catalog reference/default, not a fixed authoritative "
                        "dimension; confirm the actual required length with the customer before "
                        "finalizing a drawing."],
                )
    except Exception:
        # Fail-open here / fail-closed in the builder - see module docstring.
        pass

    return derived
