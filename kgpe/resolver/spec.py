# -*- coding: utf-8 -*-
"""
kgpe.resolver.spec
======================
Sec.6-7: `ResolvedEngineeringSpecification` (the resolver's output model)
and the `ResolutionStatus` vocabulary.

Never includes rendering parameters or arbitrary visual defaults (Sec.6)
- this is a validated ENGINEERING identity + a set of resolved canonical
dimensions, nothing about how to draw it.
"""
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any


class ResolutionStatus:
    """Sec.7: small, explicit, machine-readable resolution-status
    vocabulary. Never a generic FAILED for every negative case - each
    status tells the caller exactly what kind of situation this is."""
    RESOLVED = "RESOLVED"
    INCOMPLETE_REQUEST = "INCOMPLETE_REQUEST"
    AMBIGUOUS_REQUEST = "AMBIGUOUS_REQUEST"
    UNSUPPORTED_REQUEST = "UNSUPPORTED_REQUEST"
    MALFORMED_REQUEST = "MALFORMED_REQUEST"
    QUARANTINED_ENGINEERING_DATA = "QUARANTINED_ENGINEERING_DATA"
    MANUFACTURER_CONTEXT_REQUIRED = "MANUFACTURER_CONTEXT_REQUIRED"


ALL_RESOLUTION_STATUSES = frozenset({
    ResolutionStatus.RESOLVED, ResolutionStatus.INCOMPLETE_REQUEST,
    ResolutionStatus.AMBIGUOUS_REQUEST, ResolutionStatus.UNSUPPORTED_REQUEST,
    ResolutionStatus.MALFORMED_REQUEST, ResolutionStatus.QUARANTINED_ENGINEERING_DATA,
    ResolutionStatus.MANUFACTURER_CONTEXT_REQUIRED,
})


@dataclass
class ResolvedEngineeringSpecification:
    status: str

    # --- resolved engineering identity (Sec.6) ---
    product_family: Optional[str] = None
    subtype: Optional[str] = None
    standard: Optional[str] = None
    size_system: Optional[str] = None
    sizes: Dict[str, str] = field(default_factory=dict)          # e.g. {"nps": "6"} or {"large_end_nps": "6", "small_end_nps": "4"}
    rating_system: Optional[str] = None
    rating_value: Optional[str] = None
    manufacturer_profile: Optional[str] = None

    # --- resolved dimensions (Sec.17) ---
    resolved_dimensions: Dict[str, Any] = field(default_factory=dict)  # dim_name -> {"value","unit","verification_status","source_file"}
    available_dimensions: List[str] = field(default_factory=list)

    # --- progressive / ambiguity / gap information (Sec.19-20) ---
    missing_criteria: List[str] = field(default_factory=list)
    available_options: Dict[str, List[str]] = field(default_factory=dict)
    ambiguous_candidates: Dict[str, List[str]] = field(default_factory=dict)
    unsupported_reason: Optional[str] = None

    # --- quarantine / manufacturer detail (Sec.21-23) ---
    quarantine_details: List[Dict[str, Any]] = field(default_factory=list)
    available_manufacturer_profiles: List[str] = field(default_factory=list)

    # --- audit (Sec.24-25) ---
    trace: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    data_layer_fingerprint: Optional[str] = None

    def is_resolved(self):
        return self.status == ResolutionStatus.RESOLVED

    def to_dict(self):
        return asdict(self)
