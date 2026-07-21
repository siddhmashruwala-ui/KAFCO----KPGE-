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
from .cross_family import NipoflangeNeckODViaBranchPipeODRule

NIPOFLANGE_PROFILE_ID = "flange_nipoflange"

_OVERALL_LENGTH_RULE_ID = "nipoflange_overall_length_catalog_reference"
_OVERALL_LENGTH_RULE_VERSION = "1"


def derive_nipoflange_product_kwargs(request, geometry_specification, resolver, reduced_tip_size=None):
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

    if reduced_tip_size is not None:
        try:
            from ..contract.normalization import normalize_nps
            small_nps = normalize_nps(reduced_tip_size)
        except Exception:
            small_nps = None
        if small_nps is not None:
            tip_outcome = od_rule.resolve(resolver, target_size_system="nps",
                                           target_size=small_nps, value_name="tip_outside_diameter_mm")
            if tip_outcome.is_applied():
                derived["tip_od_value"] = tip_outcome.value

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
