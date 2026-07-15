# -*- coding: utf-8 -*-
"""
kgpe.contract - canonical engineering-data contract (Phase 2 / Prompt 4).

Public surface:
  vocabulary    - canonical names for product/standard/size/rating/dimension identity
  verification  - the 8 verification statuses + usability policy
  units         - Quantity + strict units policy
  applicability - Applicability (what a fact/rule/parameter applies to)
  model         - EngineeringFact, DerivedRule, ConstructionParameter,
                  RenderingParameter, FactRegistry, structured data errors
  derived_rules - concrete verified DerivedRule instances (RF height, and
                  2 of the 8 B16.5 general tolerance bands)

This package is purely ADDITIVE: nothing in kgpe/schema.py, kgpe/generator.py,
kgpe/dimension_library.py, or kgpe/rules/*.py imports from here, and this
package imports nothing that would change their behaviour. Existing lookups
and geometry generation are unaffected - see the Prompt 4 report's
"Backward-Compatibility Assessment" section.

CANONICAL_SCHEMA_VERSION versions the DATA CONTRACT defined in this package
(the shape of EngineeringFact/DerivedRule/etc, the verification-status
vocabulary, the applicability model). It is deliberately separate from:
  - kgpe.version.KGPE_VERSION (the software release as a whole)
  - kgpe.version.RULESET_VERSION / MAPPER_VERSION / DIMENSION_LIBRARY_ADAPTER_VERSION
    (which version pieces of GEOMETRY-GENERATION logic, not this data contract)
Bump it when the shape of the canonical model changes, not when a dataset's
content changes.
"""
from .units import Quantity, convert, UnknownUnitError, IncompatibleUnitError
from .applicability import Applicability
from . import verification
from . import vocabulary
from .model import (
    EngineeringFact, DerivedRule, ConstructionParameter, RenderingParameter,
    EngineeringFactProvenance, FactRegistry, canonical_json,
    KGPEDataError, DimensionNotApplicable, DimensionUnavailable,
    DimensionQuarantined, CombinationNotFound, UnsupportedProductFamily, MalformedInput,
    SourceValidationError, ConflictingDuplicateFact,
)
from . import normalization

CANONICAL_SCHEMA_VERSION = "canonical-schema-2026.07.14"

__all__ = [
    "Quantity", "convert", "UnknownUnitError", "IncompatibleUnitError",
    "Applicability", "verification", "vocabulary",
    "EngineeringFact", "DerivedRule", "ConstructionParameter", "RenderingParameter",
    "EngineeringFactProvenance", "FactRegistry", "canonical_json",
    "KGPEDataError", "DimensionNotApplicable", "DimensionUnavailable",
    "DimensionQuarantined", "CombinationNotFound", "UnsupportedProductFamily", "MalformedInput",
    "SourceValidationError", "ConflictingDuplicateFact", "normalization",
    "CANONICAL_SCHEMA_VERSION",
]
