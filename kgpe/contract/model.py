# -*- coding: utf-8 -*-
"""
kgpe.contract.model
======================
The canonical record model for KGPE's engineering-data contract (Prompt 4).

Keeps four record concepts explicitly separate, per Prompt 4 Sec. 3,
rather than collapsing them into one generic object:

  C. AUTHORITATIVE ENGINEERING FACT  -> EngineeringFact
  D. DERIVED ENGINEERING RULE        -> DerivedRule
  E. GEOMETRY CONSTRUCTION PARAMETER -> ConstructionParameter
  F. RENDERING PARAMETER             -> RenderingParameter

(A. SOURCE DATA FORMAT and B. CANONICAL INTERNAL MODEL are not record
types - A is whatever the existing JSON/legacy files already are, and B
is this module as a whole.)

None of the four record types is a subclass of another - they are
deliberately distinct, flat dataclasses (not one class with a "kind"
flag), so a reader can see at a glance which kind of engineering claim a
piece of code is making. Four flat, non-inheriting dataclasses is judged
not to be "excessive class hierarchy" (Prompt 4 Sec. 18) - there is no
hierarchy at all, and the count matches the four kinds of fact Prompt 3/4
already required KGPE to distinguish.
"""
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Callable, Any
import hashlib
import json

from . import verification as V
from .applicability import Applicability
from .units import Quantity


# ---------------------------------------------------------------------------
# Structured missing-data / error semantics (Prompt 4 Sec. 10)
# ---------------------------------------------------------------------------
class KGPEDataError(Exception):
    """Base class for all canonical-layer structured data errors. Every
    subclass carries a stable machine-readable `.code` - callers (and any
    future API layer) should branch on `.code`, not on parsing `str(e)`.
    Per Sec. 10, these must never surface as a bare Python traceback; a
    calling rule/service should catch KGPEDataError and turn it into a
    GEOMETRY_DEFINITION_INCOMPLETE-style structured result (see
    kgpe/schema.py's `incomplete()`, already used this way by rules/*.py
    for the pre-existing DimNotFound case)."""
    code = "UNKNOWN_DATA_ERROR"

    def __init__(self, detail, **context):
        self.detail = detail
        self.context = context
        super().__init__(detail)

    def to_dict(self):
        d = {"code": self.code, "detail": self.detail}
        if self.context:
            d["context"] = self.context
        return d


class DimensionNotApplicable(KGPEDataError):
    """The requested dimension does not apply to this product/type at all
    (e.g. asking for raised_face_diameter_mm on a plain pipe). Distinct
    from DimensionUnavailable: here the concept itself doesn't exist for
    this applicability, it isn't merely missing from a dataset."""
    code = "DIMENSION_NOT_APPLICABLE"


class DimensionUnavailable(KGPEDataError):
    """The dimension is conceptually applicable but the current dataset
    doesn't publish it (e.g. ASME B16.5's JSON has no raised-face-diameter
    column at all - a real, confirmed Prompt 1/2 gap)."""
    code = "DIMENSION_UNAVAILABLE"


class DimensionQuarantined(KGPEDataError):
    """A value exists for this exact lookup but its verification_status is
    blocked (QUARANTINED_CONFLICT / QUARANTINED_UNVERIFIED / VISUAL_ONLY /
    DEPRECATED_LEGACY, or a context-required status without the required
    opt-in) and the caller did not explicitly request quarantined data via
    the registry's `get_quarantined()` inspector. Raised by
    FactRegistry.query() - see below."""
    code = "DIMENSION_QUARANTINED"


class CombinationNotFound(KGPEDataError):
    """The (standard, size, class/schedule, ...) combination requested is
    not present at all. Conceptually the same case dimension_library.py's
    existing `DimNotFound` already covers for the live lookups; this
    canonical-layer equivalent exists for the new FactRegistry so callers
    of the new contract get the same fail-closed behaviour without
    importing the older exception type."""
    code = "COMBINATION_NOT_FOUND"


class UnsupportedProductFamily(KGPEDataError):
    code = "UNSUPPORTED_PRODUCT_FAMILY"


class MalformedInput(KGPEDataError):
    code = "MALFORMED_INPUT"


class SourceValidationError(KGPEDataError):
    """Raised by a source adapter (Prompt 5) when the underlying JSON/
    legacy dataset is structurally malformed - missing required keys,
    wrong types, non-positive dimensions, etc. Adapters must collect and
    report ALL problems found, not fail silently on the first one and not
    skip a malformed authoritative row (Prompt 5 Sec.8)."""
    code = "SOURCE_VALIDATION_ERROR"


class ConflictingDuplicateFact(KGPEDataError):
    """Raised by FactRegistry.add_checked() when a fact with the same
    engineering identity (see EngineeringFact.identity_key()) already
    exists in the registry with a DIFFERENT value. Per Prompt 5 Sec.9,
    this must never be silently resolved by overwriting - the caller must
    decide (fix the source, quarantine one side, or investigate)."""
    code = "CONFLICTING_DUPLICATE_FACT"


# ---------------------------------------------------------------------------
# Provenance (Prompt 4 Sec. 7) - engineering-FACT provenance.
#
# NOT to be confused with kgpe/schema.py's `make_provenance()`, which
# stamps a GENERATED GEOMETRY RESULT with ruleset/mapper/dimlib version + an
# input hash - provenance of a COMPUTATION. This is provenance of a raw
# engineering FACT (where a number came from, who verified it, against
# what). Both are legitimately called "provenance" but answer different
# questions - kept as two separate structures rather than merged, to avoid
# exactly the kind of ambiguity Prompts 2-3 spent two prompts untangling
# in the JS/Python data.
# ---------------------------------------------------------------------------
@dataclass
class EngineeringFactProvenance:
    source_name: Optional[str] = None            # e.g. "Texas Flange dimension table"
    source_type: Optional[str] = None            # e.g. "official_standard_document", "supplier_reference",
                                                   # "internal_dataset", "legacy_code", "cross_comparison"
    standard_designation: Optional[str] = None    # e.g. "ASME B16.5"
    standard_edition: Optional[str] = None        # e.g. "2020" - None means genuinely unknown, never fabricated
    source_file: Optional[str] = None             # relative path, if from a KGPE-local file
    source_url: Optional[str] = None
    original_field: Optional[str] = None          # e.g. "T" (Texas Flange column) or "FLG[cls][nps][1]" (JS)
    transcription_method: Optional[str] = None    # e.g. "manual transcription", "programmatic diff"
    verification_method: Optional[str] = None     # e.g. "cross-checked against 3rd independent source"
    verification_sources: List[str] = field(default_factory=list)
    verification_date: Optional[str] = None       # ISO date string, only if genuinely known
    notes: Optional[str] = None

    def to_dict(self):
        d = asdict(self)
        return {k: v for k, v in d.items() if v not in (None, [], "")}


# ---------------------------------------------------------------------------
# C. AUTHORITATIVE ENGINEERING FACT
# ---------------------------------------------------------------------------
@dataclass
class EngineeringFact:
    dimension_name: str                  # canonical name, see contract.vocabulary
    value: Quantity
    applicability: Applicability
    verification_status: str
    provenance: EngineeringFactProvenance
    notes: Optional[str] = None

    def __post_init__(self):
        if not V.is_known_status(self.verification_status):
            raise MalformedInput(f"Unknown verification_status {self.verification_status!r}",
                                  dimension_name=self.dimension_name)

    def identity_key(self):
        """Deterministic engineering-identity tuple (Prompt 5 Sec.9/14):
        same dimension + standard + product/flange/fitting type + size +
        class + manufacturer profile => same identity, regardless of
        Python object identity, insertion order, or dict ordering. Used
        for duplicate/conflict detection and indexing - NEVER a random
        UUID, always derived from the actual applicability fields."""
        a = self.applicability
        return (
            self.dimension_name,
            a.standard, a.product_family, a.product_type, a.flange_type, a.fitting_type,
            a.class_key, a.schedule, a.nps, a.dn, a.jis_size,
            a.reducing_pair, a.run_branch_pair, a.manufacturer_profile,
            # Prompt 7 additive fields (appended, not inserted, so existing
            # identity comparisons for Prompt 5/6 facts are unaffected -
            # every pre-Prompt-7 fact simply gets (None, None) here):
            a.large_end_nps, a.small_end_nps,
            # Prompt 8 additive fields (appended, not inserted, for the
            # same backward-compatibility reason - every pre-Prompt-8 fact
            # simply gets (None, None, None, None, None, None) here):
            a.large_end_dn, a.small_end_dn,
            a.large_end_jis_size, a.small_end_jis_size,
            a.run_nps, a.branch_nps,
        )

    def identity_hash(self):
        """Short deterministic hash of identity_key() - convenient for
        indexing/caching, but the underlying tuple (identity_key()) always
        remains the inspectable source of truth (Prompt 5 Sec.14)."""
        blob = json.dumps(self.identity_key(), default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

    def to_dict(self):
        return {
            "record_kind": "engineering_fact",
            "dimension_name": self.dimension_name,
            "value": self.value.to_dict(),
            "applicability": self.applicability.as_dict(),
            "verification_status": self.verification_status,
            "provenance": self.provenance.to_dict(),
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# E. GEOMETRY CONSTRUCTION PARAMETER
# ---------------------------------------------------------------------------
@dataclass
class ConstructionParameter:
    """A value used to help construct geometry (e.g. the CRM hologram's
    nipoflange proportional cone/bevel lengths, Prompt 2/3 finding) that
    must NEVER be represented as a standard-tabulated dimension. The
    `disclaimer` field is mandatory (not merely Optional) precisely so
    this can't be constructed silently without a human-readable warning
    attached."""
    dimension_name: str
    value: Quantity
    applicability: Applicability
    provenance: EngineeringFactProvenance
    disclaimer: str
    verification_status: str = V.CONSTRUCTION_PARAMETER

    def __post_init__(self):
        if self.verification_status != V.CONSTRUCTION_PARAMETER:
            raise MalformedInput("ConstructionParameter.verification_status must be CONSTRUCTION_PARAMETER")
        if not self.disclaimer:
            raise MalformedInput("ConstructionParameter requires a non-empty disclaimer")

    def to_dict(self):
        return {
            "record_kind": "construction_parameter",
            "dimension_name": self.dimension_name,
            "value": self.value.to_dict(),
            "applicability": self.applicability.as_dict(),
            "verification_status": self.verification_status,
            "provenance": self.provenance.to_dict(),
            "disclaimer": self.disclaimer,
        }


# ---------------------------------------------------------------------------
# F. RENDERING PARAMETER
# ---------------------------------------------------------------------------
@dataclass
class RenderingParameter:
    """A visual-only parameter (e.g. the CRM hologram's fillet-easing
    curve). Deliberately has no `value: Quantity` requirement - rendering
    parameters are frequently not physical quantities at all (colors,
    curve-easing coefficients, camera angles)."""
    name: str
    value: Any
    applicability: Applicability
    notes: Optional[str] = None
    verification_status: str = V.VISUAL_ONLY

    def __post_init__(self):
        if self.verification_status != V.VISUAL_ONLY:
            raise MalformedInput("RenderingParameter.verification_status must be VISUAL_ONLY")

    def to_dict(self):
        return {
            "record_kind": "rendering_parameter",
            "name": self.name,
            "value": self.value,
            "applicability": self.applicability.as_dict(),
            "verification_status": self.verification_status,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# D. DERIVED ENGINEERING RULE
# ---------------------------------------------------------------------------
@dataclass
class DerivedRule:
    """A verified, deterministic RULE (not a bare tabulated value) - e.g.
    'raised-face height = 1.6mm at Class<=300, else 6.35mm' (Prompt 3
    Sec.6, VERIFIED_DERIVED_RULE). `evaluate` is a plain callable, not
    itself serializable - `to_dict()` deliberately omits it; callers must
    keep the DerivedRule Python object around to actually evaluate it (a
    rule is logic, not data - only its metadata is a canonical record)."""
    rule_name: str
    description: str
    applicability: Applicability
    provenance: EngineeringFactProvenance
    evaluate: Callable[..., Quantity]
    verification_status: str = V.VERIFIED_DERIVED_RULE

    def __post_init__(self):
        if self.verification_status != V.VERIFIED_DERIVED_RULE:
            raise MalformedInput("DerivedRule.verification_status must be VERIFIED_DERIVED_RULE")
        if not callable(self.evaluate):
            raise MalformedInput("DerivedRule.evaluate must be callable")

    def to_dict(self):
        return {
            "record_kind": "derived_rule",
            "rule_name": self.rule_name,
            "description": self.description,
            "applicability": self.applicability.as_dict(),
            "verification_status": self.verification_status,
            "provenance": self.provenance.to_dict(),
        }


def canonical_json(record):
    """Deterministic JSON serialization of any canonical record - same
    record produces byte-identical JSON every time, for the same reason
    kgpe/schema.py hashes geometry results: a downstream consumer or test
    must be able to detect an unchanged fact byte-for-byte."""
    return json.dumps(record.to_dict(), sort_keys=True, default=str)


# ---------------------------------------------------------------------------
# Fact registry - in-memory store with quarantine enforcement (Prompt 4
# Sec. 6 + Sec. 13). This is NOT a database and NOT a generic rules engine
# - a small list + linear filter, matching the actual known dataset sizes
# (dozens to low hundreds of rows per standard), per Sec. 18's
# "don't overengineer" instruction.
# ---------------------------------------------------------------------------
class FactRegistry:
    def __init__(self):
        self._facts = []
        self._construction_params = []
        self._rendering_params = []
        self._rules = []
        # Minimal indexing (Prompt 5 Sec.15): a dict keyed by dimension_name
        # is sufficient at KGPE's actual scale (low hundreds of facts per
        # standard) - query() only needs to linearly filter WITHIN one
        # dimension's bucket, not the whole registry. A full secondary
        # index by standard/class/NPS was evaluated and judged premature
        # (see Prompt 5 report, Sec. "Registry Indexing") - this dict is
        # the entire indexing layer, not a database.
        self._by_dimension = {}
        # Identity index for O(1) duplicate/conflict detection (Sec.9/14).
        self._facts_by_identity = {}

    def add(self, record):
        if isinstance(record, EngineeringFact):
            self._facts.append(record)
            self._by_dimension.setdefault(record.dimension_name, []).append(record)
        elif isinstance(record, ConstructionParameter):
            self._construction_params.append(record)
            self._by_dimension.setdefault(record.dimension_name, []).append(record)
        elif isinstance(record, RenderingParameter):
            self._rendering_params.append(record)
        elif isinstance(record, DerivedRule):
            self._rules.append(record)
        else:
            raise MalformedInput(f"Unsupported record type for FactRegistry: {type(record)!r}")
        return record

    def add_checked(self, fact):
        """Add an EngineeringFact with duplicate/conflict detection keyed
        by its engineering identity (Prompt 5 Sec.9), NOT Python object
        identity:

          - No existing fact at this identity -> added normally.
          - An existing fact at this identity with the SAME value and
            verification_status -> treated as an exact duplicate; the
            existing record is returned unchanged, nothing is re-added.
          - An existing fact at this identity with a DIFFERENT value
            -> raises ConflictingDuplicateFact. Never silently overwritten.

        Only use this for facts that are meant to be uniquely authoritative
        at a given identity (e.g. real standard ingestion). The quarantine
        fixture path deliberately uses the plain `add()` instead, because
        it intentionally stores two already-known-conflicting historical
        values side by side under QUARANTINED_CONFLICT for inspection."""
        if not isinstance(fact, EngineeringFact):
            raise MalformedInput(f"add_checked() only supports EngineeringFact, got {type(fact)!r}")
        key = fact.identity_key()
        existing = self._facts_by_identity.get(key)
        if existing is not None:
            if existing.value == fact.value and existing.verification_status == fact.verification_status:
                return existing
            raise ConflictingDuplicateFact(
                f"Conflicting duplicate at identity {key!r}: existing value {existing.value!r} "
                f"({existing.verification_status}) vs new value {fact.value!r} ({fact.verification_status})",
                identity_key=key,
            )
        self._facts_by_identity[key] = fact
        return self.add(fact)

    def all_facts(self):
        """All EngineeringFact records added so far, in insertion order."""
        return list(self._facts)

    def query(self, dimension_name, allow_manufacturer_specific=False,
              allow_construction_parameter=False, **applicability_filters):
        """Return the list of EngineeringFacts/ConstructionParameters
        matching dimension_name + applicability_filters whose
        verification_status is usable as authoritative under the given
        opt-ins. Fails closed - never silently returns None/empty-as-ok:

          - No matching record at all for this dimension_name+applicability
            -> CombinationNotFound.
          - Matches exist but ALL are blocked under the given opt-ins
            -> DimensionQuarantined.
        """
        bucket = self._by_dimension.get(dimension_name, [])
        candidates = [c for c in bucket if c.applicability.matches(**applicability_filters)]

        if not candidates:
            raise CombinationNotFound(
                f"No record at all for dimension_name={dimension_name!r} with applicability {applicability_filters!r}",
                dimension_name=dimension_name, applicability=applicability_filters,
            )

        usable = [c for c in candidates if V.is_usable_as_authoritative(
            c.verification_status, allow_manufacturer_specific, allow_construction_parameter)]

        if not usable:
            blocked_statuses = sorted({c.verification_status for c in candidates})
            raise DimensionQuarantined(
                f"{len(candidates)} record(s) found for {dimension_name!r} but none are usable as "
                f"authoritative under the given opt-ins (statuses present: {blocked_statuses}). "
                f"Call get_quarantined() to inspect them explicitly.",
                dimension_name=dimension_name, statuses=blocked_statuses,
            )
        return usable

    def get_quarantined(self, dimension_name=None):
        """Explicit inspector for quarantined/visual/deprecated records -
        deliberately a DIFFERENT method name from `query()` so nobody can
        stumble into quarantined data through the normal lookup path. The
        caller must know they're asking for quarantined data."""
        out = [f for f in self._facts if f.verification_status in V.NEVER_AUTHORITATIVE_STATUSES]
        if dimension_name:
            out = [f for f in out if f.dimension_name == dimension_name]
        return out

    def rules(self, rule_name=None):
        if rule_name:
            return [r for r in self._rules if r.rule_name == rule_name]
        return list(self._rules)
