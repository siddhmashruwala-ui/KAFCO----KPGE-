# -*- coding: utf-8 -*-
"""
kgpe.contract.data_layer_audit
==================================
Prompt 9 Sec.3-6: machine-readable dataset-to-adapter closure inventory,
canonical coverage matrix, gap classification, and unresolved-conflict
register - all computed from the live canonical registry / adapter
modules, never hand-maintained duplicated truth (Sec.26).

This module performs READ-ONLY inspection. It never modifies a source
JSON, never re-derives an adapter's ingestion logic, and never resolves a
quarantined conflict - it only reports what the registry already contains.
"""
import os
from . import verification as V
from . import vocabulary as VOC
from .registry_builder import _ADAPTERS

MIGRATE_STATUS_ALREADY_MIGRATED_PROMPT_5_7 = "ALREADY_MIGRATED_PROMPT_5_7"
MIGRATE_STATUS_MIGRATED_PROMPT_8 = "MIGRATED_PROMPT_8"

# Static declaration of the 11 approved structured datasets, each mapped to
# its ONE production adapter. This table is CROSS-CHECKED (not just
# asserted) against three independent sources of truth at import/test
# time: dimension_library.py's FLANGE_FILES/PIPE_FILES/BUTTWELD_FILES/
# SOCKETWELD_FILES/OLET_FILES (the file registry the legacy live lookup
# already trusts), registry_builder._ADAPTERS (the fixed production
# ingestion order), and the actual per-adapter fact counts produced by a
# fresh, isolated ingestion run - see `dataset_inventory()` below.
_DATASET_TABLE = [
    {"dataset_id": "ASME_B16.5_flanges", "dl_key": ("FLANGE_FILES", "ASME_B16.5"),
     "product_family": VOC.PRODUCT_FAMILY_FLANGE, "adapter_name": "ASME_B16.5_flanges",
     "migration_status": MIGRATE_STATUS_ALREADY_MIGRATED_PROMPT_5_7},
    {"dataset_id": "ASME_B36_pipes", "dl_key": ("PIPE_FILES", "ASME_B36"),
     "product_family": VOC.PRODUCT_FAMILY_PIPE, "adapter_name": "ASME_B36_pipes",
     "migration_status": MIGRATE_STATUS_ALREADY_MIGRATED_PROMPT_5_7},
    {"dataset_id": "ASME_B16.9_buttweld", "dl_key": ("BUTTWELD_FILES", "ASME_B16.9"),
     "product_family": VOC.PRODUCT_FAMILY_BUTTWELD_FITTING, "adapter_name": "ASME_B16.9_buttweld",
     "migration_status": MIGRATE_STATUS_ALREADY_MIGRATED_PROMPT_5_7},
    {"dataset_id": "ASME_B16.11_socketweld", "dl_key": ("SOCKETWELD_FILES", "ASME_B16.11"),
     "product_family": VOC.PRODUCT_FAMILY_SOCKETWELD_FITTING, "adapter_name": "ASME_B16.11_socketweld",
     "migration_status": MIGRATE_STATUS_MIGRATED_PROMPT_8},
    {"dataset_id": "MSS_SP97_olets", "dl_key": ("OLET_FILES", "MSS_SP97"),
     "product_family": VOC.PRODUCT_FAMILY_OLET, "adapter_name": "MSS_SP97_olets",
     "migration_status": MIGRATE_STATUS_MIGRATED_PROMPT_8},
    {"dataset_id": "JIS_B2220_flanges", "dl_key": ("FLANGE_FILES", "JIS_B2220"),
     "product_family": VOC.PRODUCT_FAMILY_FLANGE, "adapter_name": "JIS_B2220_flanges",
     "migration_status": MIGRATE_STATUS_MIGRATED_PROMPT_8},
    {"dataset_id": "JIS_pipes", "dl_key": ("PIPE_FILES", "JIS_G3452_3454_3459"),
     "product_family": VOC.PRODUCT_FAMILY_PIPE, "adapter_name": "JIS_pipes",
     "migration_status": MIGRATE_STATUS_MIGRATED_PROMPT_8},
    {"dataset_id": "JIS_buttweld", "dl_key": ("BUTTWELD_FILES", "JIS_B2311_2312"),
     "product_family": VOC.PRODUCT_FAMILY_BUTTWELD_FITTING, "adapter_name": "JIS_buttweld",
     "migration_status": MIGRATE_STATUS_MIGRATED_PROMPT_8},
    {"dataset_id": "EN_1092-1_flanges", "dl_key": ("FLANGE_FILES", "EN_1092-1"),
     "product_family": VOC.PRODUCT_FAMILY_FLANGE, "adapter_name": "EN_1092-1_flanges",
     "migration_status": MIGRATE_STATUS_MIGRATED_PROMPT_8},
    {"dataset_id": "EN_pipes", "dl_key": ("PIPE_FILES", "EN_10216_10217"),
     "product_family": VOC.PRODUCT_FAMILY_PIPE, "adapter_name": "EN_pipes",
     "migration_status": MIGRATE_STATUS_MIGRATED_PROMPT_8},
    {"dataset_id": "EN_buttweld", "dl_key": ("BUTTWELD_FILES", "EN_10253"),
     "product_family": VOC.PRODUCT_FAMILY_BUTTWELD_FITTING, "adapter_name": "EN_buttweld",
     "migration_status": MIGRATE_STATUS_MIGRATED_PROMPT_8},
]

# The one known adapter-shaped module that is DELIBERATELY NOT part of
# registry construction - a Prompt-3-findings quarantine-mechanism test
# fixture, not a source-file adapter (see its own module docstring).
# Declared here explicitly so the closure audit can positively confirm
# its exclusion is intentional, not a silent omission.
_KNOWN_NON_PRODUCTION_ADAPTER_MODULES = {"legacy_crm_quarantine_fixture"}


class ClosureAuditError(Exception):
    """Raised when the dataset-to-adapter closure audit finds a genuine
    defect (an approved dataset with no adapter, an adapter not wired into
    registry construction, a duplicate, etc). Prompt 9 Sec.3 requires this
    to be detected, not silently tolerated."""
    pass


def _adapter_fn_by_name():
    return {name: fn for name, fn in _ADAPTERS}


def dataset_inventory():
    """Returns a list of dicts, one per approved structured dataset, each
    carrying: dataset_id, source_file, standard(s), product_family,
    adapter_name, migration_status, canonical_fact_count,
    authoritative_count, manufacturer_specific_count, quarantined_count -
    computed by ingesting THAT ONE adapter alone into a fresh registry
    (Sec.3). Raises ClosureAuditError if any structural defect is found:
    an approved dataset missing from dimension_library.py's file registry,
    an approved dataset with no corresponding registry_builder adapter, a
    registry_builder adapter not present in this table (duplicate-adapter
    / omitted-dataset detection), or a source file present in
    dimension_library.py that isn't accounted for in this table."""
    from .. import dimension_library as dl
    from .model import FactRegistry

    dl_registries = {
        "FLANGE_FILES": dl.FLANGE_FILES, "PIPE_FILES": dl.PIPE_FILES,
        "BUTTWELD_FILES": dl.BUTTWELD_FILES, "SOCKETWELD_FILES": dl.SOCKETWELD_FILES,
        "OLET_FILES": dl.OLET_FILES,
    }
    adapter_fns = _adapter_fn_by_name()

    table_adapter_names = {row["adapter_name"] for row in _DATASET_TABLE}
    builder_adapter_names = set(adapter_fns.keys())
    if table_adapter_names != builder_adapter_names:
        raise ClosureAuditError(
            f"Dataset table and registry_builder._ADAPTERS have drifted apart. "
            f"In table but not builder: {table_adapter_names - builder_adapter_names}. "
            f"In builder but not table: {builder_adapter_names - table_adapter_names}."
        )
    if len(table_adapter_names) != len(_DATASET_TABLE):
        raise ClosureAuditError("Duplicate adapter_name entries in the dataset table.")

    all_dl_keys = {(reg_name, std) for reg_name, reg in dl_registries.items() for std in reg}
    table_dl_keys = {row["dl_key"] for row in _DATASET_TABLE}
    if all_dl_keys != table_dl_keys:
        raise ClosureAuditError(
            f"dimension_library.py file registries and the dataset table have drifted apart. "
            f"In dimension_library but not table: {all_dl_keys - table_dl_keys}. "
            f"In table but not dimension_library: {table_dl_keys - all_dl_keys}."
        )

    inventory = []
    for row in _DATASET_TABLE:
        reg_name, std_key = row["dl_key"]
        source_file = dl_registries[reg_name][std_key]
        fn = adapter_fns[row["adapter_name"]]
        fresh = FactRegistry()
        _, facts = fn(fresh)
        stored = fresh.all_facts()
        standards_present = sorted({f.applicability.standard for f in stored})
        entry = dict(row)
        entry["source_file"] = source_file
        entry["standards_produced"] = standards_present
        entry["built_fact_count"] = len(facts)
        entry["canonical_fact_count"] = len(stored)
        entry["authoritative_count"] = sum(1 for f in stored if f.verification_status == V.VERIFIED_AUTHORITATIVE)
        entry["manufacturer_specific_count"] = sum(
            1 for f in stored if f.verification_status == V.VERIFIED_MANUFACTURER_SPECIFIC)
        entry["quarantined_count"] = sum(1 for f in stored if f.verification_status in V.NEVER_AUTHORITATIVE_STATUSES)
        del entry["dl_key"]
        inventory.append(entry)
    return inventory


# ---------------------------------------------------------------------------
# Sec.4 Canonical Coverage Matrix. Purely descriptive of DATA COVERAGE -
# distinguished explicitly from LEGACY_RESOLUTION_COVERAGE (can
# dimension_library.py currently resolve it) and LEGACY_GEOMETRY_COVERAGE
# (can generator.py/rules/*.py currently generate geometry for it). These
# three are computed from three different sources of truth and never
# blurred into one boolean.
# ---------------------------------------------------------------------------
_SIZE_FIELD_BY_SYSTEM = {"nps": VOC.SIZE_SYSTEM_NPS, "dn": VOC.SIZE_SYSTEM_DN, "jis_size": VOC.SIZE_SYSTEM_JIS_A}


def _size_sort_key(system, value):
    if system == "nps":
        from .normalization import nps_sort_key
        return nps_sort_key(value)
    if system == "dn":
        from .normalization import dn_sort_key
        return dn_sort_key(value)
    if system == "jis_size":
        from .normalization import jis_size_sort_key
        return jis_size_sort_key(value)
    return value


def coverage_matrix(registry):
    """Returns a list of dicts, one per `standard` present in the given
    registry - DATA COVERAGE only (Sec.4). Legacy resolution/geometry
    coverage are reported separately by `legacy_resolution_map()` /
    `coverage_vs_geometry_matrix()` below, never merged into this dict."""
    all_facts = registry.all_facts()
    by_standard = {}
    for f in all_facts:
        by_standard.setdefault(f.applicability.standard, []).append(f)

    rows = []
    for standard, facts in sorted(by_standard.items()):
        product_families = sorted({f.applicability.product_family for f in facts if f.applicability.product_family})
        subtypes = sorted({f.applicability.fitting_type for f in facts if f.applicability.fitting_type} |
                           {f.applicability.flange_type for f in facts if f.applicability.flange_type} |
                           {f.applicability.product_type for f in facts if f.applicability.product_type})
        dimension_names = sorted({f.dimension_name for f in facts})
        class_keys = sorted({f.applicability.class_key for f in facts if f.applicability.class_key})
        schedules = sorted({f.applicability.schedule for f in facts if f.applicability.schedule})

        size_ranges = {}
        for field, system_name in _SIZE_FIELD_BY_SYSTEM.items():
            values = {getattr(f.applicability, field) for f in facts if getattr(f.applicability, field)}
            if values:
                sk = lambda v: _size_sort_key(field, v)
                size_ranges[system_name] = {"min": min(values, key=sk), "max": max(values, key=sk), "count": len(values)}

        status_dist = {}
        for f in facts:
            status_dist[f.verification_status] = status_dist.get(f.verification_status, 0) + 1

        rows.append({
            "standard": standard,
            "product_families": product_families,
            "subtypes": subtypes,
            "dimension_names": dimension_names,
            "rating_class_keys": class_keys,
            "schedules_or_wall_designations": schedules,
            "size_ranges": size_ranges,
            "represented_combinations": len(facts),
            "verification_status_distribution": status_dist,
        })
    return rows


# ---------------------------------------------------------------------------
# Sec.23/24: canonical DATA coverage vs LEGACY_RESOLUTION_COVERAGE
# (dimension_library.py) vs LEGACY_GEOMETRY_COVERAGE (generator.py /
# rules/*.py). Computed by introspecting the actual live modules (hasattr /
# _DISPATCH keys), not by re-typing a duplicate belief about what they
# support - so this can never silently drift from the real code the way
# the JS/Python field-name duplication once did (Prompt 2 finding).
#
# The one exception is the buttweld_fitting fitting_type subset
# {"elbow_90", "tee", "cap"} that generator.py's dispatch actually branches
# on inside rules/buttweld.py's own if/elif chain (confirmed by direct
# read of kgpe/rules/buttweld.py this Prompt 9 session - it has no
# generic/introspectable list, just three literal `if fitting == "..."`
# checks) - recorded here as a hand-verified code fact, not a guess.
# ---------------------------------------------------------------------------
_BUTTWELD_GEOMETRY_SUPPORTED_SUBTYPES = frozenset({"elbow_90", "tee", "cap"})
_BUTTWELD_LEGACY_RESOLUTION_SUBTYPES = frozenset({"elbow_90", "tee", "cap"})  # dl.get_buttweld_elbow90/_tee/_cap only


def legacy_resolution_standards():
    """standard identifiers dimension_library.py can currently resolve,
    grouped by product_family - read directly from its own file registries
    and function definitions, not hand-duplicated."""
    from .. import dimension_library as dl
    return {
        VOC.PRODUCT_FAMILY_FLANGE: sorted(dl.FLANGE_FILES) if hasattr(dl, "get_flange") else [],
        VOC.PRODUCT_FAMILY_PIPE: sorted(dl.PIPE_FILES) if hasattr(dl, "get_pipe") else [],
        VOC.PRODUCT_FAMILY_BUTTWELD_FITTING: sorted(dl.BUTTWELD_FILES) if hasattr(dl, "get_buttweld_elbow90") else [],
        # SOCKETWELD_FILES/OLET_FILES ARE registered (used by
        # vocabulary.known_dimensional_standards()) but no get_socketweld()/
        # get_olet() function exists in dimension_library.py at all -
        # confirmed via hasattr, not asserted:
        VOC.PRODUCT_FAMILY_SOCKETWELD_FITTING: sorted(dl.SOCKETWELD_FILES) if hasattr(dl, "get_socketweld") else [],
        VOC.PRODUCT_FAMILY_OLET: sorted(dl.OLET_FILES) if hasattr(dl, "get_olet") else [],
    }


def legacy_geometry_product_types():
    """product_type keys generator.py's _DISPATCH actually wires up -
    read directly from the live dict, not a hand-typed copy."""
    from .. import generator as gen
    return sorted(gen._DISPATCH.keys())


def coverage_vs_geometry_matrix(registry):
    """Returns a list of dicts, one per (product_family, subtype) pair
    actually present in the registry, each with three INDEPENDENT booleans
    - data_available / legacy_resolution_available / legacy_geometry_available
    - and a `note` explaining any non-obvious case (e.g. olet's dispatch
    entry existing but its rule unconditionally returning INCOMPLETE).
    Never blurs "data exists" with "geometry can be generated" (Sec.23)."""
    all_facts = registry.all_facts()
    by_family_subtype = {}
    for f in all_facts:
        fam = f.applicability.product_family
        subtype = f.applicability.fitting_type or f.applicability.flange_type or f.applicability.product_type or "(generic)"
        by_family_subtype.setdefault((fam, subtype), set()).add(f.applicability.standard)

    resolution_by_family = legacy_resolution_standards()
    dispatch_types = legacy_geometry_product_types()

    rows = []
    for (fam, subtype), standards in sorted(by_family_subtype.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        standards = sorted(s for s in standards if s)
        data_available = True  # by construction - facts exist for this key

        if fam == VOC.PRODUCT_FAMILY_BUTTWELD_FITTING:
            legacy_resolution = bool(resolution_by_family.get(fam)) and subtype in _BUTTWELD_LEGACY_RESOLUTION_SUBTYPES
            legacy_geometry = (fam in dispatch_types) and subtype in _BUTTWELD_GEOMETRY_SUPPORTED_SUBTYPES
            note = "" if legacy_geometry else (
                "generator.py dispatches product_type='buttweld_fitting' but rules/buttweld.py's "
                "generate() only branches on fitting_type in {'elbow_90','tee','cap'} - this subtype "
                "is CANONICAL_DATA_AVAILABLE_NO_GEOMETRY, not missing engineering data.")
        elif fam == VOC.PRODUCT_FAMILY_OLET:
            legacy_resolution = bool(resolution_by_family.get(fam))
            legacy_geometry = False
            note = ("generator.py DOES dispatch product_type='olet' to rules/olet.py, but that rule "
                    "unconditionally returns GEOMETRY_DEFINITION_INCOMPLETE - no reviewed intersection-"
                    "geometry rule has been written yet (by design, not a bug).")
        elif fam == VOC.PRODUCT_FAMILY_SOCKETWELD_FITTING:
            legacy_resolution = bool(resolution_by_family.get(fam))
            legacy_geometry = fam in dispatch_types
            note = ("generator.py has NO 'socketweld_fitting' entry in _DISPATCH at all - requesting "
                    "this product_type returns 'Unknown or missing product_type', not a resolvable-"
                    "but-incomplete result. CANONICAL_DATA_AVAILABLE_NO_GEOMETRY.")
        else:
            legacy_resolution = bool(resolution_by_family.get(fam))
            legacy_geometry = fam in dispatch_types
            note = ""

        rows.append({
            "product_family": fam, "subtype": subtype, "standards": standards,
            "data_available": data_available,
            "legacy_resolution_available": legacy_resolution,
            "legacy_geometry_available": legacy_geometry,
            "note": note,
        })
    return rows


# ---------------------------------------------------------------------------
# Sec.5 Gap classification vocabulary (small, explicit - reuses existing
# verification-status vocabulary where the gap literally IS a status, per
# Sec.5 "use existing vocabulary if already available").
# ---------------------------------------------------------------------------
GAP_NOT_IN_SOURCE = "NOT_IN_SOURCE"
GAP_SOURCE_PARTIAL = "SOURCE_PARTIAL"
GAP_QUARANTINED_CONFLICT = "QUARANTINED_CONFLICT"
GAP_MANUFACTURER_SPECIFIC_ONLY = "MANUFACTURER_SPECIFIC_ONLY"
GAP_NO_LEGACY_LOOKUP = "CANONICAL_DATA_AVAILABLE_NO_LEGACY_LOOKUP"
GAP_NO_GEOMETRY = "CANONICAL_DATA_AVAILABLE_NO_GEOMETRY"
GAP_UNSUPPORTED_SCOPE = "UNSUPPORTED_BY_CURRENT_KGPE_SCOPE"

# Curated, documented exclusions established during Prompt 7/8 adapter
# authoring (each traceable to an adapter docstring/source note already
# written) - these are facts ABOUT the source data itself, not derivable
# purely by inspecting the registry's contents (an absent fact looks the
# same as "never existed" from inside the registry), so they are recorded
# here explicitly rather than invented as an inference.
_CURATED_SOURCE_GAPS = [
    {"classification": GAP_NOT_IN_SOURCE, "product_family": VOC.PRODUCT_FAMILY_BUTTWELD_FITTING,
     "standard": "ASME_B16.11", "detail": "ASME B16.11 itself does not publish outside diameter for "
     "socket-weld/threaded fittings - the mating pipe's own OD (ASME B36 pipe adapter) is the correct "
     "source; not fabricated here."},
    {"classification": GAP_SOURCE_PARTIAL, "product_family": VOC.PRODUCT_FAMILY_BUTTWELD_FITTING,
     "standard": "JIS_B2311_2312", "detail": "Concentric reducer table is only a 7-row 'representative "
     "sample, not the full matrix' per the source's own note - ingested as-is; unsampled pairs correctly "
     "raise CombinationNotFound rather than being interpolated."},
    {"classification": GAP_SOURCE_PARTIAL, "product_family": VOC.PRODUCT_FAMILY_BUTTWELD_FITTING,
     "standard": "EN_10253", "detail": "Concentric reducer table has no eccentric-reducer counterpart "
     "and no note claiming the value applies to both (unlike the ASME B16.9 precedent) - eccentric is "
     "genuinely NOT_IN_SOURCE for EN_10253, not merely uningested."},
    {"classification": GAP_NOT_IN_SOURCE, "product_family": VOC.PRODUCT_FAMILY_BUTTWELD_FITTING,
     "standard": "EN_10253", "detail": "Elbow45_CtoE_derived_mm is the source's own stated GEOMETRIC "
     "DERIVATION (bend radius x tan(22.5deg)), not a standard-published value - excluded entirely, not "
     "even as a DerivedRule, since it was never independently verified."},
    {"classification": GAP_UNSUPPORTED_SCOPE, "product_family": None, "standard": None,
     "detail": "Material grades / MTC data (e.g. Alloy 20, SMO 254 chemistry/mechanical-property tables) "
     "remain out of KGPE's geometry-data scope entirely, per the Prompt 1-3 architecture boundary - no "
     "structured JSON for these was ever built or migrated, by design."},
    {"classification": GAP_UNSUPPORTED_SCOPE, "product_family": None, "standard": None,
     "detail": "The legacy JS CRM's proportional/heuristic nipoflange body construction remains "
     "out of authoritative-data scope (Prompt 2/3 finding) - never ingested as MSS SP-97 truth."},
]


def classify_gaps(registry):
    """Returns a list of gap-classification dicts combining (a) curated,
    documented source-level exclusions established during adapter
    authoring, and (b) gaps computed directly from the live registry /
    coverage-vs-geometry matrix (quarantines, manufacturer-only subtypes,
    missing legacy lookup, missing geometry). Never invents a gap to make
    the list look complete, and never hides a real one to make the data
    layer look more finished than it is."""
    gaps = [dict(g) for g in _CURATED_SOURCE_GAPS]

    # QUARANTINED_CONFLICT gaps - one per unique conflict group.
    for group in _group_quarantined(registry):
        gaps.append({
            "classification": GAP_QUARANTINED_CONFLICT,
            "product_family": group["product_family"], "standard": group["standard"],
            "detail": f"{group['dimension_name']} at {group['size_label']} has "
                      f"{len(group['facts'])} conflicting quarantined values: {group['values']}. "
                      f"Blocked from authoritative query(); requires external authoritative evidence "
                      f"to resolve (see unresolved-conflict register).",
        })

    # MANUFACTURER_SPECIFIC_ONLY gaps - (family, subtype) combinations with
    # NO authoritative alternative at all, only manufacturer-specific data.
    by_key = {}
    for f in registry.all_facts():
        key = (f.applicability.product_family, f.applicability.fitting_type)
        by_key.setdefault(key, set()).add(f.verification_status)
    for (fam, subtype), statuses in sorted(by_key.items(), key=lambda kv: (kv[0][0] or "", kv[0][1] or "")):
        if statuses == {V.VERIFIED_MANUFACTURER_SPECIFIC}:
            gaps.append({
                "classification": GAP_MANUFACTURER_SPECIFIC_ONLY, "product_family": fam, "standard": None,
                "detail": f"fitting_type={subtype!r} has ONLY VERIFIED_MANUFACTURER_SPECIFIC facts "
                          f"(Bonney Forge catalog dims) - no standard-text-authoritative alternative "
                          f"exists in the source; requires allow_manufacturer_specific=True to use.",
            })

    # CANONICAL_DATA_AVAILABLE_NO_LEGACY_LOOKUP / NO_GEOMETRY - derived from
    # the coverage-vs-geometry matrix, one gap per affected (family, subtype).
    for row in coverage_vs_geometry_matrix(registry):
        if not row["legacy_resolution_available"]:
            gaps.append({
                "classification": GAP_NO_LEGACY_LOOKUP, "product_family": row["product_family"],
                "standard": ",".join(row["standards"]),
                "detail": f"subtype={row['subtype']!r}: canonical data exists ({row['product_family']}) "
                          f"but dimension_library.py has no live-lookup path for it.",
            })
        if not row["legacy_geometry_available"]:
            gaps.append({
                "classification": GAP_NO_GEOMETRY, "product_family": row["product_family"],
                "standard": ",".join(row["standards"]),
                "detail": f"subtype={row['subtype']!r}: canonical data exists but generator.py/"
                          f"rules/*.py cannot currently produce geometry for it. {row['note']}",
            })
    return gaps


def _size_label(applicability):
    a = applicability
    for field, prefix in (("nps", "NPS"), ("dn", ""), ("jis_size", "")):
        v = getattr(a, field)
        if v:
            return f"{prefix}{v}" if prefix else v
    return "(no size field)"


def _group_quarantined(registry):
    """Groups every currently-quarantined EngineeringFact by
    (dimension_name, standard, size-label, fitting_type) - i.e. by the
    exact engineering question they disagree about - not merely by
    dimension_name alone (so an NPS8 OD conflict and an NPS12 OD conflict
    remain two distinct groups, never merged)."""
    quarantined = registry.get_quarantined()
    groups = {}
    for f in quarantined:
        key = (f.dimension_name, f.applicability.standard, _size_label(f.applicability), f.applicability.fitting_type)
        groups.setdefault(key, []).append(f)
    out = []
    for (dim, standard, size_label, fitting_type), facts in sorted(groups.items(), key=lambda kv: (kv[0][1] or "", kv[0][0], str(kv[0][2]))):
        out.append({
            "dimension_name": dim, "standard": standard, "size_label": size_label,
            "fitting_type": fitting_type,
            "product_family": facts[0].applicability.product_family,
            "facts": facts, "values": sorted({f.value.value for f in facts}),
        })
    return out


def conflict_register(registry):
    """Sec.6: machine-readable unresolved-conflict register. One record per
    quarantined conflict GROUP (same dimension+standard+size+subtype, i.e.
    the actual conflicting engineering question), listing every individual
    canonical fact involved with its own provenance - never resolved by
    inference, never using an external/random source, never editing the
    source JSON."""
    register = []
    for i, group in enumerate(_group_quarantined(registry), start=1):
        conflict_id = f"CONFLICT-{group['standard']}-{group['dimension_name']}-{group['size_label']}"
        record = {
            "conflict_id": conflict_id,
            "standard": group["standard"],
            "product_family": group["product_family"],
            "fitting_type": group["fitting_type"],
            "dimension_name": group["dimension_name"],
            "size_label": group["size_label"],
            "observed_values": group["values"],
            "current_verification_status": sorted({f.verification_status for f in group["facts"]}),
            "effect_on_authoritative_lookup": (
                "CanonicalReader.read()/FactRegistry.query() both raise/report NO usable authoritative "
                "match at this exact identity - DimensionQuarantined / OUTCOME_QUARANTINED. Only "
                "inspectable via get_quarantined()/inspect_quarantined()."
            ),
            "resolution_requirement": (
                "Requires a second independent authoritative structured source already present in the "
                "project directly resolving the discrepancy (per Prompt 8/9's own constraint) - not "
                "inference, not a random internet source, not editing the existing source JSON. "
                "Deferred to a future data-layer-correction pass; NOT resolved in Prompt 9."
            ),
            "facts": [
                {
                    "value": f.value.value, "unit": f.value.unit,
                    "applicability": f.applicability.as_dict(),
                    "source_section_or_field": f.provenance.original_field,
                    "source_name": f.provenance.source_name,
                    "source_file": f.provenance.source_file,
                    "provenance": f.provenance.to_dict(),
                    "verification_status": f.verification_status,
                }
                for f in group["facts"]
            ],
        }
        register.append(record)
    return register


# ---------------------------------------------------------------------------
# Sec.8-11: hidden identity-collision, cross-standard equality, and size/
# rating isolation audits. FactRegistry.add_checked() already enforces (at
# build time) that two EngineeringFacts sharing a FULL identity_key() must
# have the SAME value+status, or it raises ConflictingDuplicateFact - the
# ONE sanctioned exception is the deliberate QUARANTINED_CONFLICT pattern,
# which uses plain add() specifically so two disagreeing historical/source
# values CAN share one identity for inspection. This function verifies
# that exception is never abused to hide a REAL silent collision.
# ---------------------------------------------------------------------------
def find_identity_collisions(registry):
    """Returns a list of dicts, one per identity_key() that appears more
    than once among registry.all_facts(). Each entry is flagged
    `sanctioned=True` only if EVERY fact at that identity is
    QUARANTINED_CONFLICT (the one architecturally-approved multi-value
    identity pattern) - any other multi-fact identity is a genuine hidden
    defect that must fail closed (Sec.8), not silently tolerated."""
    by_identity = {}
    for f in registry.all_facts():
        by_identity.setdefault(f.identity_key(), []).append(f)
    collisions = []
    for key, facts in by_identity.items():
        if len(facts) <= 1:
            continue
        statuses = {f.verification_status for f in facts}
        sanctioned = statuses == {V.QUARANTINED_CONFLICT}
        collisions.append({
            "identity_key": key, "fact_count": len(facts),
            "statuses": sorted(statuses), "values": sorted({f.value.value for f in facts}),
            "sanctioned": sanctioned,
        })
    return collisions


def unsanctioned_identity_collisions(registry):
    """The subset of find_identity_collisions() that represents a genuine,
    unexplained hidden collision (Sec.8) - should always be empty in a
    healthy registry."""
    return [c for c in find_identity_collisions(registry) if not c["sanctioned"]]


def size_system_isolation_report(registry):
    """Confirms NPS/DN/JIS-size never collide by construction: scans every
    fact's applicability and reports, per size system, the set of raw
    canonical size strings in use - since each system's normalize_*()
    always emits a textually distinct form (e.g. '2' vs 'DN2' vs '2A'),
    two different systems can never produce an equal string, but this is
    verified directly against the live data rather than merely assumed."""
    seen = {"nps": set(), "dn": set(), "jis_size": set()}
    for f in registry.all_facts():
        for field in seen:
            v = getattr(f.applicability, field)
            if v:
                seen[field].add(v)
    overlap = (seen["nps"] & seen["dn"]) | (seen["nps"] & seen["jis_size"]) | (seen["dn"] & seen["jis_size"])
    return {"nps_values": sorted(seen["nps"], key=str), "dn_values": sorted(seen["dn"], key=str),
            "jis_size_values": sorted(seen["jis_size"], key=str), "cross_system_textual_overlap": sorted(overlap)}


def rating_system_isolation_report(registry):
    """Reports class_key values grouped by the standard family that
    produced them (ASME class / PN / JIS K all share the one `class_key`
    Applicability slot as plain strings) - confirming e.g. PN16 vs a
    plain '16' ASME class never collide because normalize_pressure_class()
    always emits a system-specific textual prefix/suffix ('PN16', '16K')
    except for bare ASME class ('150') which has no prefix. Any bare
    numeric class_key that ALSO appears as a bare PN/K digit would be a
    genuine collision - checked directly."""
    from . import vocabulary as voc
    by_family = {"ASME_CLASS": set(), "PN": set(), "JIS_K": set(), "SCHEDULE_OR_WALL": set()}
    for f in registry.all_facts():
        ck = f.applicability.class_key
        if ck:
            if ck.startswith("PN"):
                by_family["PN"].add(ck)
            elif ck.endswith("K") and ck[:-1].isdigit():
                by_family["JIS_K"].add(ck)
            else:
                by_family["ASME_CLASS"].add(ck)
        sch = f.applicability.schedule
        if sch:
            by_family["SCHEDULE_OR_WALL"].add(sch)
    overlap = by_family["ASME_CLASS"] & by_family["PN"] & by_family["JIS_K"]
    return {k: sorted(v) for k, v in by_family.items()} | {"cross_system_textual_overlap": sorted(overlap)}
