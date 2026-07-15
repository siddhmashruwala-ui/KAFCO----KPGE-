# -*- coding: utf-8 -*-
"""
kgpe.contract.snapshot
==========================
Prompt 9 Sec.19-20: deterministic content fingerprint and machine-readable
data-layer snapshot/manifest for the complete canonical registry.

Fingerprint participation (documented exhaustively, per Sec.20 - "document
exactly what participates"):

  PARTICIPATES (data-identity-relevant):
    - EngineeringFact.identity_key() (dimension + full applicability tuple)
    - value.value, value.unit
    - verification_status
    - provenance.source_file, provenance.standard_designation,
      provenance.original_field, provenance.standard_edition

  DOES NOT PARTICIPATE (narrative/process metadata, not engineering-data
  identity - Sec.20 explicitly forbids timestamps/memory addresses/
  filesystem order, and this project's own provenance model already
  treats these as "how it was verified", not "what the fact is"):
    - provenance.source_name, source_type, source_url
    - provenance.transcription_method, verification_method,
      verification_sources, verification_date
    - notes (on any record)
    - Python object identity / memory address
    - wall-clock timestamp of the build
    - filesystem/directory enumeration order (facts are explicitly
      SORTED before hashing, so insertion order never affects the result)

Two fresh `build_canonical_registry()` calls over unchanged sources always
produce the same fingerprint (proven in tests/test_prompt9_data_layer_closure.py);
a controlled mutation of any participating field changes it.
"""
import hashlib
import json

CANONICAL_SCHEMA_VERSION = "kgpe-canonical-contract-v1"
REGISTRY_BUILD_VERSION = "kgpe-registry-builder-prompt9-2026.07.15"


def _fact_fingerprint_row(fact):
    p = fact.provenance
    return (
        fact.identity_key(),
        fact.value.value, fact.value.unit,
        fact.verification_status,
        p.source_file, p.standard_designation, p.original_field, p.standard_edition,
    )


def registry_fingerprint(registry):
    """Deterministic SHA-256 hex digest over every fact's fingerprint row,
    SORTED before hashing (so registry insertion/adapter order never
    affects the result - only the actual multiset of engineering content
    does). Same unchanged canonical registry -> same fingerprint, always."""
    rows = sorted(json.dumps(_fact_fingerprint_row(f), sort_keys=True, default=str)
                  for f in registry.all_facts())
    blob = "\n".join(rows)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_data_layer_snapshot(registry, per_adapter_counts):
    """Sec.19: machine-readable data-layer snapshot/manifest. Every count
    is derived from the live registry (never hand-estimated) via
    registry_builder.registry_statistics() and data_layer_audit's own
    inspection helpers - the fingerprint is the one piece of identity
    that does NOT depend on wall-clock time or filesystem order."""
    from .registry_builder import registry_statistics
    from .data_layer_audit import dataset_inventory, conflict_register

    stats = registry_statistics(registry)
    inventory = dataset_inventory()
    conflicts = conflict_register(registry)
    adapter_names = [name for name, _ in per_adapter_counts]

    return {
        "canonical_schema_version": CANONICAL_SCHEMA_VERSION,
        "registry_build_version": REGISTRY_BUILD_VERSION,
        "adapter_list": adapter_names,
        "dataset_count": len(inventory),
        "dataset_inventory": [
            {k: v for k, v in row.items()} for row in inventory
        ],
        "total_facts_built": sum(c for _, c in per_adapter_counts),
        "total_facts_stored": stats["total_facts"],
        "counts_by_verification_status": stats["by_status"],
        "counts_by_standard": stats["by_standard"],
        "counts_by_product_family": stats["by_product_family"],
        "unresolved_conflict_count": len(conflicts),
        "unresolved_conflict_ids": [c["conflict_id"] for c in conflicts],
        "fingerprint_sha256": registry_fingerprint(registry),
        "fingerprint_participates": [
            "identity_key() (dimension_name + full applicability tuple)",
            "value.value", "value.unit", "verification_status",
            "provenance.source_file", "provenance.standard_designation",
            "provenance.original_field", "provenance.standard_edition",
        ],
        "fingerprint_excludes": [
            "provenance.source_name", "provenance.source_type", "provenance.source_url",
            "provenance.transcription_method", "provenance.verification_method",
            "provenance.verification_sources", "provenance.verification_date",
            "notes (any record)", "python object identity", "build wall-clock timestamp",
            "filesystem/directory enumeration order",
        ],
    }
