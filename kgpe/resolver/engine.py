# -*- coding: utf-8 -*-
"""
kgpe.resolver.engine
========================
Sec.2/28: the core deterministic resolution engine. Public entry point:

    from kgpe.resolver import resolve_engineering_request, EngineeringRequest
    spec = resolve_engineering_request(EngineeringRequest(product_family="flange", ...))

Architecture (Sec.2, strictly followed):
  EngineeringRequest -> alias normalization -> engineering intent/
  specification resolution -> CanonicalReader -> ResolvedEngineeringSpecification

Consumes the frozen canonical data layer ONLY through `CanonicalReader`/
`build_canonical_reader()` and `kgpe.contract.snapshot` (Sec.26) - no
adapter import, no source JSON, no `dimension_library.py` lookup. Pure
deterministic Python: no LLM, no network, no fuzzy matching (Sec.3/33).
"""
from ..contract.canonical_reader import (
    CanonicalReader, build_canonical_reader,
    OUTCOME_EXACT_MATCH, OUTCOME_NO_MATCH, OUTCOME_QUARANTINED, OUTCOME_AMBIGUOUS,
    OUTCOME_MANUFACTURER_CONTEXT_REQUIRED, OUTCOME_MALFORMED_CRITERIA, OUTCOME_UNSUPPORTED_CRITERIA,
)
from ..contract.snapshot import registry_fingerprint
from ..contract.normalization import (
    normalize_nps, normalize_dn, normalize_jis_size, normalize_pressure_class, normalize_schedule,
    normalize_wall_designation,
)
from ..contract import vocabulary as VOC
from ..contract import verification as V
from .request import EngineeringRequest
from .spec import ResolvedEngineeringSpecification, ResolutionStatus
from . import aliases as A

RATING_ASME_CLASS = "ASME_CLASS"
RATING_PN = "PN"
RATING_JIS_K = "JIS_K"
RATING_SCHEDULE = "SCHEDULE"
RATING_WALL_DESIGNATION = "WALL_DESIGNATION"

# Sec.14: which rating SYSTEM applies to which standard - a small explicit
# resolver rule, cross-checked against live canonical coverage at runtime
# (not blindly trusted) rather than assumed. `None` means this standard's
# facts carry no class_key/schedule identity at all (e.g. ASME B16.9
# buttweld fittings are identified by NPS + fitting_type alone).
STANDARD_RATING_SYSTEM = {
    "ASME_B16.5": RATING_ASME_CLASS, "JIS_B2220": RATING_JIS_K, "EN_1092-1": RATING_PN,
    "ASME_B16.11": RATING_ASME_CLASS,
    "ASME_B36.10M": RATING_SCHEDULE, "ASME_B36.19M": RATING_SCHEDULE,
    "JIS_G3452": None, "JIS_G3454": RATING_SCHEDULE, "JIS_G3459": RATING_SCHEDULE,
    "EN_10216_10217": RATING_WALL_DESIGNATION,
    "MSS_SP97": RATING_SCHEDULE,
    "ASME_B16.9": None, "JIS_B2311_2312": None, "EN_10253": None,
}

# which EngineeringRequest field carries the raw value for each rating system
_RATING_REQUEST_FIELD = {
    RATING_ASME_CLASS: "pressure_class", RATING_PN: "pn", RATING_JIS_K: "jis_k",
    RATING_SCHEDULE: "schedule", RATING_WALL_DESIGNATION: "wall_designation",
}
_RATING_APPLICABILITY_FIELD = {
    RATING_ASME_CLASS: "class_key", RATING_PN: "class_key", RATING_JIS_K: "class_key",
    RATING_SCHEDULE: "schedule", RATING_WALL_DESIGNATION: "schedule",
}
_RATING_FIELDS_ON_APPLICABILITY = frozenset({"class_key", "schedule"})


class _ShortCircuit(Exception):
    """Internal control-flow only - never escapes `resolve()`. Carries the
    final ResolutionStatus plus whatever partial ResolvedEngineeringSpecification
    fields are already known at the point resolution had to stop."""
    def __init__(self, status, **kwargs):
        self.status = status
        self.kwargs = kwargs


def _subtype_field_for_family(product_family):
    """Which Applicability field carries 'subtype' identity for a given
    product family - None for pipe (no subtype concept in this project's
    canonical data)."""
    if product_family == VOC.PRODUCT_FAMILY_FLANGE:
        return "flange_type"
    if product_family in (VOC.PRODUCT_FAMILY_BUTTWELD_FITTING, VOC.PRODUCT_FAMILY_SOCKETWELD_FITTING,
                           VOC.PRODUCT_FAMILY_OLET):
        return "fitting_type"
    return None


def _is_already_canonical_subtype(raw, product_family):
    """True if `raw` is already one of the canonical fitting_type/flange_type
    strings for this family (so a caller passing the canonical value
    directly, e.g. 'weld_neck' or 'elbow_90_lr', is accepted without
    needing an alias table entry)."""
    known = {
        VOC.PRODUCT_FAMILY_FLANGE: {"weld_neck"},
        VOC.PRODUCT_FAMILY_BUTTWELD_FITTING: VOC.BUTTWELD_FITTING_TYPES,
        VOC.PRODUCT_FAMILY_SOCKETWELD_FITTING: VOC.SOCKETWELD_FITTING_TYPES,
        VOC.PRODUCT_FAMILY_OLET: VOC.OLET_FITTING_TYPES,
    }.get(product_family, frozenset())
    return raw in known


_SIZE_NORMALIZERS = {"nps": normalize_nps, "dn": normalize_dn, "jis_size": normalize_jis_size}
_SIZE_SORT_KEYS = {}


def _size_sort_key(system, value):
    if system == "nps":
        from ..contract.normalization import nps_sort_key
        return nps_sort_key(value)
    if system == "dn":
        from ..contract.normalization import dn_sort_key
        return dn_sort_key(value)
    if system == "jis_size":
        from ..contract.normalization import jis_size_sort_key
        return jis_size_sort_key(value)
    raise ValueError(f"Unknown size system {system!r}")


def _normalize_size_or_raise(raw, system, field_label, trace):
    if system not in _SIZE_NORMALIZERS:
        raise _ShortCircuit(ResolutionStatus.MALFORMED_REQUEST,
                             warnings=[f"Unknown size_system {system!r} - must be one of {sorted(_SIZE_NORMALIZERS)}"])
    try:
        normalized = _SIZE_NORMALIZERS[system](raw)
    except ValueError as e:
        raise _ShortCircuit(ResolutionStatus.MALFORMED_REQUEST,
                             warnings=[f"Cannot normalize {field_label} {raw!r} as {system}: {e}"])
    trace.append(f"{field_label} normalized: {raw!r} -> {normalized!r} ({system})")
    return normalized


class EngineeringResolver:
    """Wraps one `CanonicalReader` (normally built fresh via
    `build_canonical_reader()`) and resolves `EngineeringRequest` objects
    against it. Stateless across calls other than the wrapped reader/
    fingerprint - safe to reuse for many requests."""

    def __init__(self, reader: CanonicalReader, fingerprint: str):
        self.reader = reader
        self.fingerprint = fingerprint

    # -- Sec.8: product-family resolution --------------------------------
    def _resolve_family(self, request, trace):
        raw = request.product_family
        if raw is None:
            raise _ShortCircuit(ResolutionStatus.INCOMPLETE_REQUEST,
                                 missing_criteria=["product_family"],
                                 available_options={"product_family": sorted(VOC.PRODUCT_FAMILIES)})
        try:
            fam = A.normalize_product_family_alias(raw)
        except KeyError:
            raise _ShortCircuit(ResolutionStatus.UNSUPPORTED_REQUEST,
                                 unsupported_reason=f"Unknown product_family {raw!r}",
                                 available_options={"product_family": sorted(VOC.PRODUCT_FAMILIES)})
        trace.append(f"product_family normalized: {raw!r} -> {fam!r}")
        return fam

    # -- Sec.9: product-subtype resolution --------------------------------
    def _resolve_subtype(self, request, product_family, trace):
        raw = request.subtype
        if raw is None:
            trace.append("subtype not supplied - deferred to per-dimension resolution")
            return None
        try:
            subtype = A.normalize_subtype_alias(raw, product_family)
        except KeyError:
            if _is_already_canonical_subtype(raw, product_family):
                subtype = raw
            else:
                raise _ShortCircuit(
                    ResolutionStatus.UNSUPPORTED_REQUEST,
                    unsupported_reason=f"Unknown subtype alias {raw!r} for product_family {product_family!r}",
                )
        trace.append(f"subtype normalized: {raw!r} -> {subtype!r}")
        return subtype

    # -- Sec.12: standard resolution --------------------------------------
    def _resolve_standard(self, request, product_family, subtype, trace):
        subtype_field = _subtype_field_for_family(product_family)
        subtype_filter = {subtype_field: subtype} if (subtype_field and subtype) else {}

        raw = request.standard
        if raw is not None:
            try:
                standard = A.normalize_standard_alias(raw)
            except KeyError:
                raise _ShortCircuit(ResolutionStatus.UNSUPPORTED_REQUEST,
                                     unsupported_reason=f"Unknown standard alias {raw!r}")
            valid = set(self.reader.discover("standard", product_family=product_family, **subtype_filter))
            if standard not in valid:
                raise _ShortCircuit(
                    ResolutionStatus.UNSUPPORTED_REQUEST,
                    unsupported_reason=(f"{standard!r} does not support product_family={product_family!r}"
                                        + (f" subtype={subtype!r}" if subtype else "")),
                    available_options={"standard": sorted(valid)},
                )
            trace.append(f"standard normalized+validated: {raw!r} -> {standard!r}")
            return standard

        candidates = sorted(self.reader.discover("standard", product_family=product_family, **subtype_filter))
        if len(candidates) == 0:
            raise _ShortCircuit(
                ResolutionStatus.UNSUPPORTED_REQUEST,
                unsupported_reason=f"No standard supports product_family={product_family!r} subtype={subtype!r}",
            )
        if len(candidates) == 1:
            trace.append(f"standard inferred (unique): {candidates[0]!r}")
            return candidates[0]
        raise _ShortCircuit(
            ResolutionStatus.AMBIGUOUS_REQUEST,
            missing_criteria=["standard"],
            ambiguous_candidates={"standard": candidates},
        )


    # -- Sec.13/15: size-system + multi-size role resolution --------------
    def _infer_size_system(self, standard, field_prefix, trace):
        """field_prefix is '' for single-size or 'large_end_'/'small_end_'
        for reducer roles. Infers which of nps/dn/jis_size the standard
        actually populates for that role - never cross-converts, never
        guesses when more than one is genuinely possible."""
        systems = {}
        for sys_name in ("nps", "dn", "jis_size"):
            field = f"{field_prefix}{sys_name}"
            values = self.reader.discover(field, standard=standard)
            if values:
                systems[sys_name] = values
        return systems

    def _resolve_size(self, request, standard, trace):
        sizes = {}
        size_system = request.size_system

        if request.large_end_size is not None or request.small_end_size is not None:
            if request.large_end_size is None or request.small_end_size is None:
                raise _ShortCircuit(ResolutionStatus.INCOMPLETE_REQUEST,
                                     missing_criteria=["large_end_size", "small_end_size"])
            systems = self._infer_size_system(standard, "large_end_", trace)
            sys_name = size_system or (list(systems)[0] if len(systems) == 1 else None)
            if sys_name is None:
                if len(systems) == 0:
                    raise _ShortCircuit(ResolutionStatus.UNSUPPORTED_REQUEST,
                                         unsupported_reason=f"{standard!r} has no reducer large/small-end sizing")
                raise _ShortCircuit(ResolutionStatus.AMBIGUOUS_REQUEST, missing_criteria=["size_system"],
                                     ambiguous_candidates={"size_system": sorted(systems)})
            large = _normalize_size_or_raise(request.large_end_size, sys_name, "large_end_size", trace)
            small = _normalize_size_or_raise(request.small_end_size, sys_name, "small_end_size", trace)
            if _size_sort_key(sys_name, large) < _size_sort_key(sys_name, small):
                raise _ShortCircuit(
                    ResolutionStatus.MALFORMED_REQUEST,
                    warnings=[f"Reversed reducer pair: large_end_size {request.large_end_size!r} is smaller than "
                              f"small_end_size {request.small_end_size!r} - large end must be >= small end."],
                )
            sizes[f"large_end_{sys_name}"] = large
            sizes[f"small_end_{sys_name}"] = small
            return sizes, sys_name

        if request.run_size is not None or request.branch_size is not None:
            if request.run_size is not None:
                sizes["run_nps"] = _normalize_size_or_raise(request.run_size, "nps", "run_size", trace)
            if request.branch_size is not None:
                sizes["branch_nps"] = _normalize_size_or_raise(request.branch_size, "nps", "branch_size", trace)
            return sizes, "nps"

        if request.primary_size is not None:
            systems = self._infer_size_system(standard, "", trace)
            sys_name = size_system or (list(systems)[0] if len(systems) == 1 else None)
            if sys_name is None:
                if len(systems) == 0:
                    raise _ShortCircuit(ResolutionStatus.UNSUPPORTED_REQUEST,
                                         unsupported_reason=f"{standard!r} does not use a single primary size "
                                                             f"(it uses reducer or run/branch sizing instead)")
                raise _ShortCircuit(ResolutionStatus.AMBIGUOUS_REQUEST, missing_criteria=["size_system"],
                                     ambiguous_candidates={"size_system": sorted(systems)})
            sizes[sys_name] = _normalize_size_or_raise(request.primary_size, sys_name, "primary_size", trace)
            return sizes, sys_name

        raise _ShortCircuit(
            ResolutionStatus.INCOMPLETE_REQUEST,
            missing_criteria=["primary_size (or large_end_size/small_end_size, or run_size/branch_size)"],
        )


    # -- Sec.14: rating-system resolution ----------------------------------
    def _resolve_rating(self, request, standard, trace, warnings):
        """Normalizes whatever rating field the caller actually supplied,
        validated against which rating SYSTEM this standard uses (never a
        generic bare number interpreted without context - Sec.14). Does
        NOT force a rating to be present here: whether a specific
        requested dimension actually needs it is decided per-dimension
        (data-driven, Sec.18) so OD-style requests aren't over-required
        to supply a schedule/class they don't need."""
        expected_system = STANDARD_RATING_SYSTEM.get(standard)
        provided = {
            RATING_ASME_CLASS: request.pressure_class, RATING_PN: request.pn,
            RATING_JIS_K: request.jis_k, RATING_SCHEDULE: request.schedule,
            RATING_WALL_DESIGNATION: request.wall_designation,
        }
        # Warn (never silently drop) if the caller supplied a rating field
        # that does not correspond to this standard's own rating system.
        for sys_name, value in provided.items():
            if value is not None and sys_name != expected_system:
                warnings.append(f"{standard!r} uses rating system {expected_system!r} - the supplied "
                                 f"{_RATING_REQUEST_FIELD[sys_name]}={value!r} does not apply and was ignored.")

        if expected_system is None:
            return None, None

        raw = provided[expected_system]
        if raw is None:
            trace.append(f"rating system for {standard!r} is {expected_system!r} - not supplied yet")
            return expected_system, None

        try:
            if expected_system in (RATING_ASME_CLASS, RATING_PN, RATING_JIS_K):
                voc_system = {RATING_ASME_CLASS: VOC.RATING_SYSTEM_ASME_CLASS, RATING_PN: VOC.RATING_SYSTEM_PN,
                              RATING_JIS_K: VOC.RATING_SYSTEM_JIS_K}[expected_system]
                value = normalize_pressure_class(raw, voc_system)
            elif expected_system == RATING_SCHEDULE:
                value = normalize_schedule(raw)
            elif expected_system == RATING_WALL_DESIGNATION:
                value = normalize_wall_designation(raw)
            else:
                raise ValueError(f"Unhandled rating system {expected_system!r}")
        except ValueError as e:
            raise _ShortCircuit(ResolutionStatus.MALFORMED_REQUEST,
                                 warnings=[f"Cannot normalize {_RATING_REQUEST_FIELD[expected_system]} "
                                           f"{raw!r} as {expected_system}: {e}"])
        trace.append(f"rating normalized: {raw!r} -> {value!r} ({expected_system})")
        return expected_system, value


_APPLICABILITY_DIFF_FIELDS = (
    "product_family", "product_type", "flange_type", "fitting_type", "standard",
    "class_key", "schedule", "nps", "dn", "jis_size", "manufacturer_profile",
    "large_end_nps", "small_end_nps", "large_end_dn", "small_end_dn",
    "large_end_jis_size", "small_end_jis_size", "run_nps", "branch_nps",
)


def _diff_fields(facts):
    """Sorted list of Applicability field names that differ among a set of
    candidate facts - used to classify WHY a dimension request is
    ambiguous (Sec.18/19): a rating-only difference is INCOMPLETE
    (the object identity is coherent, one more criterion is needed), any
    other difference is a genuine AMBIGUOUS_REQUEST (a different
    engineering object entirely)."""
    diffs = []
    for field in _APPLICABILITY_DIFF_FIELDS:
        values = {getattr(f.applicability, field) for f in facts}
        if len(values) > 1:
            diffs.append(field)
    return diffs


def _conflict_id(fact):
    # Matches the conflict-id format established in Prompt 9's
    # data_layer_audit.conflict_register() exactly, so a conflict_id
    # surfaced here can be cross-referenced against that register.
    a = fact.applicability
    if a.nps:
        size_label = f"NPS{a.nps}"
    elif a.dn:
        size_label = a.dn
    elif a.jis_size:
        size_label = a.jis_size
    elif a.large_end_nps:
        size_label = f"NPS{a.large_end_nps}"
    elif a.large_end_dn:
        size_label = a.large_end_dn
    elif a.large_end_jis_size:
        size_label = a.large_end_jis_size
    else:
        size_label = "(no size field)"
    return f"CONFLICT-{a.standard}-{fact.dimension_name}-{size_label}"


class _DimensionOutcome:
    __slots__ = ("kind", "fact", "detail", "missing_criteria", "available_options",
                 "ambiguous_candidates", "available_manufacturer_profiles", "quarantine_details")

    def __init__(self, kind, fact=None, detail="", missing_criteria=None, available_options=None,
                 ambiguous_candidates=None, available_manufacturer_profiles=None, quarantine_details=None):
        self.kind = kind
        self.fact = fact
        self.detail = detail
        self.missing_criteria = missing_criteria or []
        self.available_options = available_options or {}
        self.ambiguous_candidates = ambiguous_candidates or {}
        self.available_manufacturer_profiles = available_manufacturer_profiles or []
        self.quarantine_details = quarantine_details or []


def _resolve_one_dimension(self, dim_name, criteria, allow_mfr, allow_constr, trace, relaxed_criteria=None):
    trace.append(f"querying canonical reader: dimension={dim_name!r} criteria={criteria!r}")
    r = self.reader.read(dim_name, allow_manufacturer_specific=allow_mfr,
                          allow_construction_parameter=allow_constr, **criteria)

    # Some canonical facts (e.g. ASME B16.9 / EN 10253 OD and wall-thickness
    # cross-section-consistency facts, Prompts 7-9) deliberately carry NO
    # fitting_type at all - a SHARED identity across multiple product
    # sections. If the subtype-scoped query finds nothing, retry once
    # without the subtype filter - this never picks between ambiguous
    # candidates (read() still fails closed on ambiguity/quarantine), it
    # only recognizes that this specific dimension's identity is not
    # subtype-scoped in the canonical data.
    if r.outcome in (OUTCOME_NO_MATCH, OUTCOME_UNSUPPORTED_CRITERIA) and relaxed_criteria is not None:
        trace.append(f"dimension={dim_name!r} not found under subtype-scoped criteria - retrying with "
                      f"subtype filter relaxed (shared cross-subtype identity check)")
        r2 = self.reader.read(dim_name, allow_manufacturer_specific=allow_mfr,
                               allow_construction_parameter=allow_constr, **relaxed_criteria)
        if r2.outcome != OUTCOME_NO_MATCH:
            r = r2

    if r.outcome == OUTCOME_EXACT_MATCH:
        return _DimensionOutcome("EXACT", fact=r.fact, detail=r.detail)

    if r.outcome == OUTCOME_MALFORMED_CRITERIA:
        raise _ShortCircuit(ResolutionStatus.MALFORMED_REQUEST, warnings=[r.detail])

    if r.outcome == OUTCOME_UNSUPPORTED_CRITERIA:
        return _DimensionOutcome("UNSUPPORTED", detail=r.detail)

    if r.outcome == OUTCOME_NO_MATCH:
        return _DimensionOutcome("UNSUPPORTED", detail=r.detail)

    if r.outcome == OUTCOME_QUARANTINED:
        details = [{"conflict_id": _conflict_id(f), "value": f.value.value, "unit": f.value.unit,
                    "verification_status": f.verification_status} for f in r.facts]
        return _DimensionOutcome("QUARANTINED", detail=r.detail, quarantine_details=details)

    if r.outcome == OUTCOME_MANUFACTURER_CONTEXT_REQUIRED:
        return _DimensionOutcome("MANUFACTURER_CONTEXT_REQUIRED", detail=r.detail,
                                  available_manufacturer_profiles=r.available_manufacturer_profiles)

    if r.outcome == OUTCOME_AMBIGUOUS:
        diffs = _diff_fields(r.facts)
        if diffs and set(diffs) <= _RATING_FIELDS_ON_APPLICABILITY:
            options = {}
            for field in diffs:
                options[field] = sorted({str(getattr(f.applicability, field)) for f in r.facts
                                          if getattr(f.applicability, field) is not None})
            return _DimensionOutcome("INCOMPLETE", detail=r.detail, missing_criteria=list(diffs),
                                      available_options=options)
        candidates = {}
        for field in (diffs or ["(unknown)"]):
            candidates[field] = sorted({str(getattr(f.applicability, field)) for f in r.facts
                                         if getattr(f.applicability, field) is not None})
        return _DimensionOutcome("AMBIGUOUS", detail=r.detail, ambiguous_candidates=candidates)

    raise _ShortCircuit(ResolutionStatus.MALFORMED_REQUEST, warnings=[f"Unrecognized reader outcome {r.outcome!r}"])


EngineeringResolver._resolve_one_dimension = _resolve_one_dimension


def _available_dimension_names(self, base_criteria, allow_mfr):
    """Sec.17.B: dimension NAMES available for a resolved identity - only
    those with at least one AUTHORITATIVE fact (or manufacturer-specific
    fact when explicitly opted in). Never includes a name whose only
    matching facts are quarantined, and never includes manufacturer-
    specific-only names without explicit opt-in (Sec.17)."""
    candidate_names = self.reader.available_dimensions(**base_criteria)
    out = []
    for name in candidate_names:
        facts = self.reader._matching_facts(dimension_name=name, **base_criteria)
        statuses = {f.verification_status for f in facts}
        if V.VERIFIED_AUTHORITATIVE in statuses or (allow_mfr and V.VERIFIED_MANUFACTURER_SPECIFIC in statuses):
            out.append(name)
    return sorted(out)


EngineeringResolver._available_dimension_names = _available_dimension_names


def _aggregate(self, fam, subtype, standard, size_system, sizes, rating_system, rating_value,
               mfr_profile, outcomes, trace, warnings):
    """Sec.19-22: merges every requested dimension's outcome into one
    overall status, WITHOUT discarding successfully-resolved unrelated
    dimensions just because another requested dimension hit a problem
    (Sec.22 - one quarantined dimension must not invalidate an unrelated
    authoritative one the caller explicitly also asked for)."""
    resolved_dimensions = {}
    missing_criteria, available_options, ambiguous_candidates = [], {}, {}
    quarantine_details, available_mfr_profiles, unsupported_reasons = [], [], []

    kind_priority = {"AMBIGUOUS": 0, "MANUFACTURER_CONTEXT_REQUIRED": 1, "INCOMPLETE": 2,
                     "QUARANTINED": 3, "UNSUPPORTED": 4, "EXACT": 5}
    worst_kind = "EXACT"

    for dim_name, outcome in outcomes.items():
        if outcome.kind == "EXACT":
            f = outcome.fact
            resolved_dimensions[dim_name] = {
                "value": f.value.value, "unit": f.value.unit,
                "verification_status": f.verification_status, "source_file": f.provenance.source_file,
            }
            trace.append(f"dimension resolved: {dim_name} = {f.value.value}{f.value.unit}")
        else:
            trace.append(f"dimension {dim_name} outcome: {outcome.kind} - {outcome.detail}")
            missing_criteria.extend(outcome.missing_criteria)
            available_options.update(outcome.available_options)
            ambiguous_candidates.update(outcome.ambiguous_candidates)
            quarantine_details.extend(outcome.quarantine_details)
            available_mfr_profiles.extend(outcome.available_manufacturer_profiles)
            if outcome.kind == "UNSUPPORTED":
                unsupported_reasons.append(f"{dim_name}: {outcome.detail}")
        if kind_priority[outcome.kind] < kind_priority[worst_kind]:
            worst_kind = outcome.kind

    status = {
        "EXACT": ResolutionStatus.RESOLVED, "AMBIGUOUS": ResolutionStatus.AMBIGUOUS_REQUEST,
        "MANUFACTURER_CONTEXT_REQUIRED": ResolutionStatus.MANUFACTURER_CONTEXT_REQUIRED,
        "INCOMPLETE": ResolutionStatus.INCOMPLETE_REQUEST,
        "QUARANTINED": ResolutionStatus.QUARANTINED_ENGINEERING_DATA,
        "UNSUPPORTED": ResolutionStatus.UNSUPPORTED_REQUEST,
    }[worst_kind]

    return ResolvedEngineeringSpecification(
        status=status, product_family=fam, subtype=subtype, standard=standard, size_system=size_system,
        sizes=sizes, rating_system=rating_system, rating_value=rating_value, manufacturer_profile=mfr_profile,
        resolved_dimensions=resolved_dimensions, missing_criteria=sorted(set(missing_criteria)),
        available_options=available_options, ambiguous_candidates=ambiguous_candidates,
        unsupported_reason="; ".join(unsupported_reasons) or None, quarantine_details=quarantine_details,
        available_manufacturer_profiles=sorted(set(available_mfr_profiles)),
        trace=trace, warnings=warnings, data_layer_fingerprint=self.fingerprint,
    )


EngineeringResolver._aggregate = _aggregate


def _resolve(self, request):
    """Sec.28: the one public per-instance entry point. Never raises a
    raw internal exception to the caller - every outcome is a structured
    `ResolvedEngineeringSpecification`."""
    trace = []
    warnings = []
    state = {"product_family": None, "subtype": None, "standard": None,
             "size_system": None, "sizes": {}, "rating_system": None, "rating_value": None}

    if not isinstance(request, EngineeringRequest):
        return ResolvedEngineeringSpecification(
            status=ResolutionStatus.MALFORMED_REQUEST, trace=trace,
            warnings=["request must be an EngineeringRequest instance"],
            data_layer_fingerprint=self.fingerprint,
        )
    if request.dimensions is not None and not isinstance(request.dimensions, list):
        return ResolvedEngineeringSpecification(
            status=ResolutionStatus.MALFORMED_REQUEST, trace=trace,
            warnings=["'dimensions' must be a list of dimension-name strings, or empty/None"],
            data_layer_fingerprint=self.fingerprint,
        )

    try:
        state["product_family"] = self._resolve_family(request, trace)
        state["subtype"] = self._resolve_subtype(request, state["product_family"], trace)
        state["standard"] = self._resolve_standard(request, state["product_family"], state["subtype"], trace)
        state["sizes"], state["size_system"] = self._resolve_size(request, state["standard"], trace)
        state["rating_system"], state["rating_value"] = self._resolve_rating(
            request, state["standard"], trace, warnings)

        subtype_field = _subtype_field_for_family(state["product_family"])
        base_criteria = {"product_family": state["product_family"], "standard": state["standard"]}
        if subtype_field and state["subtype"]:
            base_criteria[subtype_field] = state["subtype"]
        base_criteria.update(state["sizes"])
        if state["rating_value"] is not None:
            base_criteria[_RATING_APPLICABILITY_FIELD[state["rating_system"]]] = state["rating_value"]
        if request.manufacturer_profile:
            base_criteria["manufacturer_profile"] = request.manufacturer_profile

        # A relaxed variant (subtype filter dropped) for the shared cross-
        # subtype identity fallback in _resolve_one_dimension - only
        # meaningful when a subtype filter was actually applied above.
        relaxed_criteria = None
        if subtype_field and state["subtype"]:
            relaxed_criteria = {k: v for k, v in base_criteria.items() if k != subtype_field}

        allow_mfr = bool(request.allow_manufacturer_specific or request.manufacturer_profile)
        requested_dims = request.dimensions or []

        if not requested_dims:
            available = self._available_dimension_names(base_criteria, allow_mfr)
            trace.append(f"no explicit dimensions requested - discovered {len(available)} available dimension(s)")
            return ResolvedEngineeringSpecification(
                status=ResolutionStatus.RESOLVED, product_family=state["product_family"],
                subtype=state["subtype"], standard=state["standard"], size_system=state["size_system"],
                sizes=state["sizes"], rating_system=state["rating_system"], rating_value=state["rating_value"],
                manufacturer_profile=request.manufacturer_profile, available_dimensions=available,
                trace=trace, warnings=warnings, data_layer_fingerprint=self.fingerprint,
            )

        outcomes = {dim_name: self._resolve_one_dimension(dim_name, base_criteria, allow_mfr, False, trace,
                                                           relaxed_criteria=relaxed_criteria)
                    for dim_name in requested_dims}
        return self._aggregate(state["product_family"], state["subtype"], state["standard"],
                                state["size_system"], state["sizes"], state["rating_system"],
                                state["rating_value"], request.manufacturer_profile, outcomes, trace, warnings)

    except _ShortCircuit as sc:
        kwargs = dict(sc.kwargs)
        sc_warnings = kwargs.pop("warnings", [])
        return ResolvedEngineeringSpecification(
            status=sc.status, product_family=state["product_family"], subtype=state["subtype"],
            standard=state["standard"], size_system=state["size_system"], sizes=state["sizes"],
            rating_system=state["rating_system"], rating_value=state["rating_value"],
            trace=trace, warnings=warnings + sc_warnings, data_layer_fingerprint=self.fingerprint, **kwargs,
        )


EngineeringResolver.resolve = _resolve


def resolve_engineering_request(request, resolver=None):
    """Sec.28: the module-level public entry point. Builds a fresh frozen
    canonical reader (and binds its fingerprint) if no resolver is given -
    the caller never needs to construct a registry, know adapter names, or
    catch a raw internal exception."""
    if resolver is None:
        reader, _ = build_canonical_reader()
        fingerprint = registry_fingerprint(reader.registry)
        resolver = EngineeringResolver(reader, fingerprint)
    return resolver.resolve(request)
