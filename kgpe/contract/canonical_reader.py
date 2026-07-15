# -*- coding: utf-8 -*-
"""
kgpe.contract.canonical_reader
==================================
Prompt 9 Sec.15-18: the stable, low-level CANONICAL READ BOUNDARY over a
built FactRegistry. This is the ONE thing a future resolution engine
(Prompt 10+) should import to read canonical engineering facts - it must
never need to know source JSON structures, import individual adapters,
inspect filesystem paths, or know adapter loading order. All of that
already lives behind `kgpe.contract.registry_builder.build_canonical_registry()`;
this module wraps the resulting FactRegistry with deterministic, fail-
closed query semantics.

This is NOT the resolution engine itself (Prompt 10). It does not do
natural-language parsing, fuzzy matching, or inference of missing
engineering criteria (Sec.15/17). Every criterion the caller wants
applied must be passed explicitly as an Applicability field name/value -
exactly the same discipline `Applicability.matches()` already uses.
"""
from dataclasses import dataclass, field
from typing import Optional, List

from .model import FactRegistry, EngineeringFact
from . import verification as V

# ---------------------------------------------------------------------------
# Query result semantics (Sec.16). A single caller-facing outcome vocabulary,
# deliberately small, that every `CanonicalReader.read()` call resolves to.
# Callers branch on `.outcome`, never on parsing a message string.
# ---------------------------------------------------------------------------
OUTCOME_EXACT_MATCH = "EXACT_MATCH"
OUTCOME_NO_MATCH = "NO_MATCH"
OUTCOME_QUARANTINED = "QUARANTINED_MATCH"
OUTCOME_AMBIGUOUS = "AMBIGUOUS_MATCH"
OUTCOME_MANUFACTURER_CONTEXT_REQUIRED = "MANUFACTURER_CONTEXT_REQUIRED"
OUTCOME_CONSTRUCTION_CONTEXT_REQUIRED = "CONSTRUCTION_CONTEXT_REQUIRED"
OUTCOME_UNSUPPORTED_CRITERIA = "UNSUPPORTED_CRITERIA"
OUTCOME_MALFORMED_CRITERIA = "MALFORMED_CRITERIA"

ALL_OUTCOMES = frozenset({
    OUTCOME_EXACT_MATCH, OUTCOME_NO_MATCH, OUTCOME_QUARANTINED, OUTCOME_AMBIGUOUS,
    OUTCOME_MANUFACTURER_CONTEXT_REQUIRED, OUTCOME_CONSTRUCTION_CONTEXT_REQUIRED,
    OUTCOME_UNSUPPORTED_CRITERIA, OUTCOME_MALFORMED_CRITERIA,
})


@dataclass
class CanonicalReadResult:
    """Structured outcome of a single `CanonicalReader.read()` call. Exactly
    one of `.fact` / `.facts` is populated depending on `.outcome` - never a
    bare Python traceback, never an arbitrary first match (Sec.16/17)."""
    outcome: str
    dimension_name: Optional[str] = None
    criteria: dict = field(default_factory=dict)
    fact: Optional[EngineeringFact] = None            # populated only for EXACT_MATCH
    facts: List[EngineeringFact] = field(default_factory=list)  # AMBIGUOUS / QUARANTINED candidates
    detail: str = ""
    available_manufacturer_profiles: List[str] = field(default_factory=list)

    def is_ok(self):
        return self.outcome == OUTCOME_EXACT_MATCH

    def to_dict(self):
        return {
            "outcome": self.outcome,
            "dimension_name": self.dimension_name,
            "criteria": self.criteria,
            "fact": self.fact.to_dict() if self.fact else None,
            "facts": [f.to_dict() for f in self.facts],
            "detail": self.detail,
            "available_manufacturer_profiles": self.available_manufacturer_profiles,
        }


# Applicability's own field set (used to validate criteria before ever
# touching the registry - Sec.16 "malformed criteria" / Sec.17 fail-closed
# on underspecified/unsupported input). Derived from the live dataclass,
# never hand-duplicated.
def _known_applicability_fields():
    from .applicability import Applicability
    return frozenset(Applicability.__dataclass_fields__.keys())


class CanonicalReader:
    """Wraps a single built FactRegistry (normally the one returned by
    `registry_builder.build_canonical_registry()`) and exposes a stable,
    deterministic read boundary. Holds no adapter/filesystem knowledge of
    its own."""

    def __init__(self, registry: FactRegistry):
        self._registry = registry
        self._applicability_fields = _known_applicability_fields()

    @property
    def registry(self):
        return self._registry

    def read(self, dimension_name, allow_manufacturer_specific=False,
             allow_construction_parameter=False, **criteria):
        """The single low-level canonical read entry point (Sec.15-17).

        Never raises for an expected engineering outcome - always returns a
        CanonicalReadResult with one of the OUTCOME_* codes. Only a genuine
        programming error (e.g. an unknown kwarg spelling) is reported via
        OUTCOME_MALFORMED_CRITERIA rather than an exception, so a caller can
        always branch on `.outcome` instead of catching exceptions for
        ordinary "no data yet" cases.

        Ambiguity is never silently resolved: if more than one authoritative
        fact matches the given criteria, the result is OUTCOME_AMBIGUOUS and
        `.facts` lists every candidate - the caller must supply more
        criteria, never receive an arbitrary first pick (Sec.16/17)."""
        unknown = set(criteria) - self._applicability_fields
        if unknown:
            return CanonicalReadResult(
                outcome=OUTCOME_MALFORMED_CRITERIA, dimension_name=dimension_name, criteria=criteria,
                detail=f"Unknown applicability criteria: {sorted(unknown)}. "
                       f"Known fields: {sorted(self._applicability_fields)}.",
            )

        bucket = self._registry._by_dimension.get(dimension_name, [])
        if not bucket:
            from .vocabulary import DIMENSION_NAMES
            if dimension_name not in DIMENSION_NAMES:
                return CanonicalReadResult(
                    outcome=OUTCOME_UNSUPPORTED_CRITERIA, dimension_name=dimension_name, criteria=criteria,
                    detail=f"{dimension_name!r} is not a known canonical dimension name.",
                )
            return CanonicalReadResult(
                outcome=OUTCOME_NO_MATCH, dimension_name=dimension_name, criteria=criteria,
                detail=f"No canonical fact exists at all for dimension_name={dimension_name!r}.",
            )

        candidates = [c for c in bucket if isinstance(c, EngineeringFact) and c.applicability.matches(**criteria)]
        if not candidates:
            return CanonicalReadResult(
                outcome=OUTCOME_NO_MATCH, dimension_name=dimension_name, criteria=criteria,
                detail=f"No canonical fact matches dimension_name={dimension_name!r} with criteria {criteria!r}.",
            )
        return self._resolve_candidates(dimension_name, criteria, candidates,
                                         allow_manufacturer_specific, allow_construction_parameter)

    def _resolve_candidates(self, dimension_name, criteria, candidates,
                             allow_manufacturer_specific, allow_construction_parameter):
        authoritative = [c for c in candidates if c.verification_status in V.ALWAYS_USABLE_STATUSES]
        manufacturer = [c for c in candidates if c.verification_status == V.VERIFIED_MANUFACTURER_SPECIFIC]
        construction = [c for c in candidates if c.verification_status == V.CONSTRUCTION_PARAMETER]
        blocked = [c for c in candidates if c.verification_status in V.NEVER_AUTHORITATIVE_STATUSES]

        pool = list(authoritative)
        if allow_manufacturer_specific:
            pool += manufacturer
        if allow_construction_parameter:
            pool += construction

        if len(pool) == 1:
            return CanonicalReadResult(
                outcome=OUTCOME_EXACT_MATCH, dimension_name=dimension_name, criteria=criteria,
                fact=pool[0], detail="Exactly one authoritative canonical fact matched.",
            )
        if len(pool) > 1:
            return CanonicalReadResult(
                outcome=OUTCOME_AMBIGUOUS, dimension_name=dimension_name, criteria=criteria, facts=pool,
                detail=f"{len(pool)} authoritative canonical facts matched these criteria - supply "
                       f"additional applicability criteria to disambiguate. Never resolved by picking "
                       f"a first/default match.",
            )
        # pool is empty: nothing usable without further context/opt-in.
        if manufacturer and not allow_manufacturer_specific:
            profiles = sorted({c.applicability.manufacturer_profile for c in manufacturer
                                if c.applicability.manufacturer_profile})
            return CanonicalReadResult(
                outcome=OUTCOME_MANUFACTURER_CONTEXT_REQUIRED, dimension_name=dimension_name, criteria=criteria,
                facts=manufacturer, available_manufacturer_profiles=profiles,
                detail=f"{len(manufacturer)} manufacturer-specific fact(s) matched, but "
                       f"allow_manufacturer_specific=True (and, ideally, an explicit manufacturer_profile "
                       f"criterion) is required before this data can be treated as authoritative. "
                       f"Available manufacturer profiles: {profiles}.",
            )
        if construction and not allow_construction_parameter:
            return CanonicalReadResult(
                outcome=OUTCOME_CONSTRUCTION_CONTEXT_REQUIRED, dimension_name=dimension_name, criteria=criteria,
                facts=construction,
                detail=f"{len(construction)} construction-parameter record(s) matched, but "
                       f"allow_construction_parameter=True is required before this data can be used to "
                       f"build geometry - it was never a standard-tabulated dimension.",
            )
        if blocked:
            return CanonicalReadResult(
                outcome=OUTCOME_QUARANTINED, dimension_name=dimension_name, criteria=criteria, facts=blocked,
                detail=f"{len(blocked)} record(s) matched but all are quarantined/visual/deprecated "
                       f"(statuses: {sorted({c.verification_status for c in blocked})}) and are never "
                       f"usable as authoritative input, no opt-in possible.",
            )
        # Unreachable given candidates is non-empty and every status is one of
        # the four buckets above - fail closed rather than silently OK.
        return CanonicalReadResult(
            outcome=OUTCOME_NO_MATCH, dimension_name=dimension_name, criteria=criteria,
            detail="No usable canonical fact matched under any classification (unexpected).",
        )

    # -----------------------------------------------------------------
    # Coverage / option discovery (Sec.18) - "what valid options exist
    # for the criteria already supplied?" Purely data-driven: every
    # answer is computed by scanning the live registry's own facts, never
    # a hand-maintained option list that could drift out of sync with the
    # actual ingested data.
    # -----------------------------------------------------------------
    def _matching_facts(self, dimension_name=None, **criteria):
        if dimension_name is not None:
            bucket = self._registry._by_dimension.get(dimension_name, [])
        else:
            bucket = self._registry.all_facts()
        return [c for c in bucket if isinstance(c, EngineeringFact) and c.applicability.matches(**criteria)]

    def discover(self, field, dimension_name=None, **criteria):
        """Sorted list of distinct non-None values of Applicability.<field>
        (e.g. 'standard', 'nps', 'dn', 'jis_size', 'class_key', 'schedule',
        'fitting_type', 'manufacturer_profile') among facts matching the
        given dimension_name/criteria. `field` must be a real Applicability
        field - this never invents or hard-codes a value list."""
        if field not in self._applicability_fields:
            raise AttributeError(f"Applicability has no field {field!r}; known fields: "
                                  f"{sorted(self._applicability_fields)}")
        facts = self._matching_facts(dimension_name, **criteria)
        values = {getattr(f.applicability, field) for f in facts}
        values.discard(None)
        return sorted(values, key=str)

    def available_dimensions(self, **criteria):
        """Sorted list of distinct canonical dimension_names that have at
        least one fact matching the given applicability criteria."""
        facts = self._matching_facts(dimension_name=None, **criteria)
        return sorted({f.dimension_name for f in facts})

    def available_manufacturer_profiles(self, dimension_name=None, **criteria):
        return self.discover("manufacturer_profile", dimension_name=dimension_name, **criteria)

    def available_reducing_pairs(self, dimension_name=None, size_system="nps", **criteria):
        """Sorted list of (large, small) tuples for reducer-role facts,
        for whichever size system the caller asks for ('nps', 'dn', or
        'jis_size') - reads Applicability.large_end_<system>/small_end_<system>
        directly, never a hard-coded pair list."""
        large_field, small_field = f"large_end_{size_system}", f"small_end_{size_system}"
        if large_field not in self._applicability_fields or small_field not in self._applicability_fields:
            raise AttributeError(f"Unsupported size_system {size_system!r} for reducing pairs")
        facts = self._matching_facts(dimension_name, **criteria)
        pairs = {(getattr(f.applicability, large_field), getattr(f.applicability, small_field)) for f in facts}
        pairs.discard((None, None))
        return sorted(p for p in pairs if p[0] is not None and p[1] is not None)

    def available_run_branch_pairs(self, dimension_name=None, **criteria):
        facts = self._matching_facts(dimension_name, **criteria)
        pairs = {(f.applicability.run_nps, f.applicability.branch_nps) for f in facts}
        return sorted(p for p in pairs if p[0] is not None)

    # -----------------------------------------------------------------
    # Explicit inspection views (Sec.7/12/13) - deliberately separate,
    # differently-named methods from `read()` so nobody stumbles into
    # quarantined or manufacturer-specific data through the normal query
    # path (mirrors FactRegistry.get_quarantined()'s own naming discipline).
    # -----------------------------------------------------------------
    def inspect_quarantined(self, dimension_name=None):
        return self._registry.get_quarantined(dimension_name=dimension_name)

    def inspect_manufacturer_specific(self, dimension_name=None, **criteria):
        facts = self._matching_facts(dimension_name, **criteria)
        return [f for f in facts if f.verification_status == V.VERIFIED_MANUFACTURER_SPECIFIC]


def build_canonical_reader():
    """Convenience factory: builds a fresh complete canonical registry
    (via registry_builder.build_canonical_registry()) and wraps it in a
    CanonicalReader in one call. This is the ONE import a future
    resolution-engine module needs - it never has to know about
    individual adapters, source JSON paths, or adapter loading order."""
    from .registry_builder import build_canonical_registry
    registry, per_adapter_counts = build_canonical_registry()
    return CanonicalReader(registry), per_adapter_counts
