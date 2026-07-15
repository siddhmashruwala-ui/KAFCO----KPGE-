# -*- coding: utf-8 -*-
"""
Result schema for KGPE. Plain-dict based (not a heavy ORM) so it serializes
to JSON trivially for the CLI / future REST API / Python SDK callers alike.

Status values (see architecture spec, "Critical architectural separation"):
  OK                            - geometry generated successfully
  GEOMETRY_DEFINITION_INCOMPLETE - required dimension(s) missing/not resolvable
  ENGINEERING_REVIEW_REQUIRED    - dimensions resolved but a rule flagged an
                                    ambiguity/contradiction a human should check
"""
import hashlib
import json
import datetime

STATUS_OK = "OK"
STATUS_INCOMPLETE = "GEOMETRY_DEFINITION_INCOMPLETE"
STATUS_REVIEW_REQUIRED = "ENGINEERING_REVIEW_REQUIRED"

ENGINEERING_STATE_FINISHED = "FINISHED_MACHINED_COMPONENT"
# The following 3 states are KFEE's responsibility to define the VALUES for;
# KGPE will only be able to generate geometry for them once KFEE (a separate
# system, per the architecture doc) supplies structured geometry-state data.
ENGINEERING_STATE_MACHINING_ENVELOPE = "MINIMUM_MACHINING_STOCK_ENVELOPE"
ENGINEERING_STATE_TARGET_FORGING = "TARGET_MANUFACTURING_FORGING_GEOMETRY"
ENGINEERING_STATE_STARTING_STOCK = "STARTING_STOCK_CUT_PIECE"


def _input_hash(request: dict) -> str:
    """Deterministic hash of the resolved request, so identical inputs can be
    verified to produce identical geometry (a core KGPE requirement)."""
    blob = json.dumps(request, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def make_provenance(source, ruleset_version, mapper_version, dimlib_version, request, extra=None):
    prov = {
        "source_standard": source.get("standard"),
        "source_file": source.get("source_file"),
        "size_class": source.get("size_class"),
        "dimension_library_version": dimlib_version,
        "ruleset_version": ruleset_version,
        "mapper_version": mapper_version,
        "generated_at_utc": datetime.datetime.utcnow().isoformat() + "Z",
        "input_hash": _input_hash(request),
    }
    if extra:
        prov.update(extra)
    return prov


def make_result(status, product_type=None, engineering_state=None, geometry=None,
                provenance=None, warnings=None, error=None):
    return {
        "status": status,
        "product_type": product_type,
        "engineering_state": engineering_state,
        "geometry": geometry,
        "provenance": provenance,
        "warnings": warnings or [],
        "error": error,
    }


def incomplete(reason, product_type=None, request=None):
    """Fail-closed helper: use whenever a dimension can't be resolved or a
    rule can't proceed, instead of guessing a plausible-looking shape."""
    return make_result(
        STATUS_INCOMPLETE,
        product_type=product_type,
        error=reason,
        warnings=[reason],
    )


def review_required(reason, product_type=None, geometry=None, provenance=None):
    return make_result(
        STATUS_REVIEW_REQUIRED,
        product_type=product_type,
        geometry=geometry,
        provenance=provenance,
        error=reason,
        warnings=[reason],
    )
