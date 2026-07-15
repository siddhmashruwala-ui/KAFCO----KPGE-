# -*- coding: utf-8 -*-
"""
kgpe.geometry_spec.discovery
================================
Prompt 11 Sec.3-4/24: completed first-class discovery. Every function here
answers "what valid options exist?" - NEVER "what does this request mean?"
(that remains resolution, kgpe.resolver). No function here picks a first/
default option or uses ordering as a hidden default (Sec.4). Every answer
is computed live from `CanonicalReader`'s already-existing, general-purpose
query surface (`discover()`, `available_dimensions()`,
`available_manufacturer_profiles()`, `available_reducing_pairs()`,
`available_run_branch_pairs()`) - no second, manually duplicated catalogue
of canonical coverage is introduced here.
"""
from ..contract import vocabulary as VOC


def _subtype_field(product_family):
    if product_family == VOC.PRODUCT_FAMILY_FLANGE:
        return "flange_type"
    if product_family in (VOC.PRODUCT_FAMILY_BUTTWELD_FITTING, VOC.PRODUCT_FAMILY_SOCKETWELD_FITTING,
                           VOC.PRODUCT_FAMILY_OLET):
        return "fitting_type"
    return None


def discover_product_families(reader):
    """Sec.3: product families actually present in the live registry -
    computed from the facts themselves, not the static VOC.PRODUCT_FAMILIES
    frozenset (which would include families with zero ingested data)."""
    facts = reader.registry.all_facts()
    return sorted({f.applicability.product_family for f in facts if f.applicability.product_family})


def discover_standards(reader, product_family=None, subtype=None):
    criteria = {}
    if product_family:
        criteria["product_family"] = product_family
    field = _subtype_field(product_family) if product_family else None
    if field and subtype:
        criteria[field] = subtype
    return reader.discover("standard", **criteria)


def discover_subtypes(reader, product_family, standard=None):
    """Sec.3's named limitation from Prompt 10: subtype discovery must work
    as a FIRST-CLASS capability, independent of any dimension request."""
    field = _subtype_field(product_family)
    if field is None:
        return []
    criteria = {"product_family": product_family}
    if standard:
        criteria["standard"] = standard
    return reader.discover(field, **criteria)


def discover_sizes(reader, product_family, standard, subtype=None, role=""):
    """role: '' (primary), 'large_end_', 'small_end_', 'run_', 'branch_'."""
    criteria = {"product_family": product_family, "standard": standard}
    field = _subtype_field(product_family)
    if field and subtype:
        criteria[field] = subtype
    out = {}
    for system in ("nps", "dn", "jis_size"):
        key = f"{role}{system}"
        values = reader.discover(key, **criteria)
        if values:
            out[system] = values
    return out


def discover_ratings(reader, product_family, standard, subtype=None):
    criteria = {"product_family": product_family, "standard": standard}
    field = _subtype_field(product_family)
    if field and subtype:
        criteria[field] = subtype
    out = {}
    class_keys = reader.discover("class_key", **criteria)
    if class_keys:
        out["class_key"] = class_keys
    schedules = reader.discover("schedule", **criteria)
    if schedules:
        out["schedule"] = schedules
    return out


def discover_manufacturer_profiles(reader, product_family=None, subtype=None, standard=None):
    criteria = {}
    if product_family:
        criteria["product_family"] = product_family
    field = _subtype_field(product_family) if product_family else None
    if field and subtype:
        criteria[field] = subtype
    if standard:
        criteria["standard"] = standard
    return reader.available_manufacturer_profiles(**criteria)


def discover_dimensions(reader, product_family, standard, subtype=None, **extra_criteria):
    criteria = {"product_family": product_family, "standard": standard}
    field = _subtype_field(product_family)
    if field and subtype:
        criteria[field] = subtype
    criteria.update(extra_criteria)
    return reader.available_dimensions(**criteria)


def discover_reducer_pairs(reader, product_family, standard, size_system="nps", subtype=None):
    criteria = {"product_family": product_family, "standard": standard}
    field = _subtype_field(product_family)
    if field and subtype:
        criteria[field] = subtype
    return reader.available_reducing_pairs(size_system=size_system, **criteria)


def discover_run_branch_pairs(reader, product_family, standard, subtype=None):
    criteria = {"product_family": product_family, "standard": standard}
    field = _subtype_field(product_family)
    if field and subtype:
        criteria[field] = subtype
    return reader.available_run_branch_pairs(**criteria)


def discover_geometry_profile_available(product_family, subtype):
    from .profile import find_profile
    return find_profile(product_family, subtype) is not None


def progressive_discovery(reader, product_family=None, standard=None, subtype=None):
    """Sec.24: one deterministic call answering the progressive chain a
    future UI/AI layer would ask, given whatever criteria are already
    known. Every level is reported explicitly - never a hidden default
    ordering (Sec.4)."""
    result = {"product_families": discover_product_families(reader)}
    if product_family:
        result["standards"] = discover_standards(reader, product_family, subtype)
        result["subtypes"] = discover_subtypes(reader, product_family, standard)
    if product_family and standard:
        result["sizes"] = discover_sizes(reader, product_family, standard, subtype)
        result["ratings"] = discover_ratings(reader, product_family, standard, subtype)
        result["manufacturer_profiles"] = discover_manufacturer_profiles(reader, product_family, subtype, standard)
        result["dimensions"] = discover_dimensions(reader, product_family, standard, subtype)
        result["geometry_profile_available"] = discover_geometry_profile_available(product_family, subtype)
    return result
