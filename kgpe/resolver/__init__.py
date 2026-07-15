# -*- coding: utf-8 -*-
"""
kgpe.resolver - Engineering Specification Resolution (Phase 3 / Prompt 10).

Converts an external engineering request into a precise, validated,
machine-readable `ResolvedEngineeringSpecification`, built entirely on
top of the frozen canonical data layer (`kgpe.contract.canonical_reader.
CanonicalReader` / `build_canonical_reader()`). Deterministic Python only
- no LLM, no network, no fuzzy matching, no embeddings.

Architecture (Sec.2):
  External Request -> Request Normalization -> Engineering Intent/
  Specification Resolution -> CanonicalReader -> Resolved Engineering
  Specification

This package stops at the resolved specification. It does not generate
geometry (that remains `kgpe/generator.py`'s and later prompts' job) and
it does not modify the frozen canonical data layer (Prompt 9) in any way.

Public surface:
  request  - EngineeringRequest (the external-request model)
  spec     - ResolvedEngineeringSpecification + ResolutionStatus vocabulary
  aliases  - deterministic, inspectable nomenclature alias tables
  engine   - resolve_engineering_request() / EngineeringResolver (the one
             public entry point)
"""
from .request import EngineeringRequest
from .spec import ResolvedEngineeringSpecification, ResolutionStatus, ALL_RESOLUTION_STATUSES
from .engine import EngineeringResolver, resolve_engineering_request

RESOLVER_SCHEMA_VERSION = "resolver-schema-2026.07.15"

__all__ = [
    "EngineeringRequest", "ResolvedEngineeringSpecification", "ResolutionStatus",
    "ALL_RESOLUTION_STATUSES", "EngineeringResolver", "resolve_engineering_request",
    "RESOLVER_SCHEMA_VERSION",
]
