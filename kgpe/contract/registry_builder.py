# -*- coding: utf-8 -*-
"""
kgpe.contract.registry_builder
==================================
Prompt 8 Sec.25: builds the COMPLETE canonical registry from every
approved, successfully-migrated structured engineering dataset in one
call. Purely additive - does not replace `kgpe/generator.py` or change
any existing live-lookup behaviour (`dimension_library.py` is untouched
and remains the path every existing `rules/*.py` file uses). No network
access, no CRM/JS/HTML file is read.

Deterministic adapter-loading order (fixed list below, NOT filesystem
enumeration order - Prompt 8 Sec.24): flanges -> pipes -> buttweld ->
socketweld -> olets, ASME before JIS before EN within each family,
mirroring the order the 11 source files were migrated across Prompts
5-8. Two fresh calls to `build_canonical_registry()` must produce
identical total fact counts and identity-key ordering - proven in
tests/test_canonical_registry_build.py.
"""
from .model import FactRegistry
from .adapters.asme_b16_5_flanges import ingest_asme_b16_5_flanges
from .adapters.asme_b36_pipes import ingest_asme_pipes
from .adapters.asme_b16_9_buttweld import ingest_asme_b16_9_buttweld
from .adapters.asme_b16_11_socketweld import ingest_asme_b16_11_socketweld
from .adapters.mss_sp97_olets import ingest_mss_sp97_olets
from .adapters.kafco_nipoflange import ingest_kafco_nipoflange
from .adapters.jis_b2220_flanges import ingest_jis_b2220_flanges
from .adapters.jis_pipes import ingest_jis_pipes
from .adapters.jis_buttweld import ingest_jis_buttweld
from .adapters.en_1092_flanges import ingest_en_1092_flanges
from .adapters.en_pipes import ingest_en_pipes
from .adapters.en_buttweld import ingest_en_buttweld

# Fixed, explicit, deterministic order - the ONE place that decides which
# adapters run and in what sequence. Adding a 12th migrated dataset in a
# future prompt means adding one line here, not changing this function's
# logic.
_ADAPTERS = (
    ("ASME_B16.5_flanges", ingest_asme_b16_5_flanges),
    ("ASME_B36_pipes", ingest_asme_pipes),
    ("ASME_B16.9_buttweld", ingest_asme_b16_9_buttweld),
    ("ASME_B16.11_socketweld", ingest_asme_b16_11_socketweld),
    ("MSS_SP97_olets", ingest_mss_sp97_olets),
    ("KAFCO_Nipoflange", ingest_kafco_nipoflange),
    ("JIS_B2220_flanges", ingest_jis_b2220_flanges),
    ("JIS_pipes", ingest_jis_pipes),
    ("JIS_buttweld", ingest_jis_buttweld),
    ("EN_1092-1_flanges", ingest_en_1092_flanges),
    ("EN_pipes", ingest_en_pipes),
    ("EN_buttweld", ingest_en_buttweld),
)


def build_canonical_registry():
    """Builds and returns (registry, per_adapter_counts) where
    per_adapter_counts is an ordered dict-like list of
    (adapter_name, fact_count) pairs in ingestion order - useful for the
    registry-statistics report without requiring a caller to re-derive
    it by hand. `registry` is a single shared FactRegistry containing
    every fact from every adapter; quarantined records (ASME B16.9's
    NPS8/NPS12 OD conflict, EN 10253's OD/WT conflicts) remain present
    and reachable only via `registry.get_quarantined()`, exactly as each
    adapter individually produces them - this function does not filter,
    resolve, or hide any of them."""
    registry = FactRegistry()
    per_adapter_counts = []
    for name, ingest_fn in _ADAPTERS:
        _, facts = ingest_fn(registry)
        per_adapter_counts.append((name, len(facts)))
    return registry, per_adapter_counts


def registry_statistics(registry):
    """Derives summary statistics directly from an already-built registry
    (never hand-counted - Prompt 8 Sec.26)."""
    from . import verification as V

    all_facts = registry.all_facts()
    by_standard = {}
    by_product_family = {}
    by_status = {}
    for f in all_facts:
        by_standard[f.applicability.standard] = by_standard.get(f.applicability.standard, 0) + 1
        by_product_family[f.applicability.product_family] = by_product_family.get(f.applicability.product_family, 0) + 1
        by_status[f.verification_status] = by_status.get(f.verification_status, 0) + 1

    bucket_sizes = {dim: len(bucket) for dim, bucket in registry._by_dimension.items()}
    largest_bucket = max(bucket_sizes.values()) if bucket_sizes else 0

    authoritative = sum(1 for f in all_facts if f.verification_status == V.VERIFIED_AUTHORITATIVE)
    quarantined = sum(1 for f in all_facts if f.verification_status in V.NEVER_AUTHORITATIVE_STATUSES)
    manufacturer_specific = sum(1 for f in all_facts if f.verification_status == V.VERIFIED_MANUFACTURER_SPECIFIC)

    return {
        "total_facts": len(all_facts),
        "authoritative_facts": authoritative,
        "quarantined_facts": quarantined,
        "manufacturer_specific_facts": manufacturer_specific,
        "by_standard": by_standard,
        "by_product_family": by_product_family,
        "by_status": by_status,
        "largest_dimension_bucket": largest_bucket,
        "dimension_bucket_sizes": bucket_sizes,
    }
