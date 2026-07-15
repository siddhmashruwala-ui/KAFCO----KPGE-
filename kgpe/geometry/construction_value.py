# -*- coding: utf-8 -*-
"""
kgpe.geometry.construction_value
====================================
Prompt 12 Sec.15: the model for values DERIVED by a construction rule -
kept explicitly separate from `kgpe.contract.model.EngineeringFact`
(canonical, source-verified) so nothing downstream can confuse a derived
value's provenance with an authoritative published dimension.
"""
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any

PROVENANCE_LABEL_DERIVED = "DERIVED_CONSTRUCTION_VALUE"


@dataclass(frozen=True)
class ConstructionValue:
    name: str
    value: float
    unit: str
    rule_id: str
    rule_version: str
    input_dimension_refs: List[Dict[str, Any]] = field(default_factory=list)
    derivation_trace: List[str] = field(default_factory=list)
    provenance_label: str = PROVENANCE_LABEL_DERIVED

    def to_dict(self):
        return asdict(self)
