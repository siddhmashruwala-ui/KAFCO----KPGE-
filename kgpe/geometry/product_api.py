# -*- coding: utf-8 -*-
"""
kgpe.geometry.product_api
=============================
Shared contract between `kgpe.geometry.kernel.GeometryKernel` and each
per-profile builder in `kgpe.geometry.products.*`. Kept in its own module
(rather than on `kernel.py`) so product builders never need to import the
kernel itself (no circular import) - the kernel dispatches TO products,
products never call back into the kernel.
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


class GeometryInputError(Exception):
    """A product builder raises this for invalid/missing engineering
    dimensions (maps to INVALID_ENGINEERING_DIMENSIONS at the kernel
    boundary) - never for a genuine programmer bug."""
    pass


class ConstructionRuleUnavailableError(Exception):
    """A product builder raises this when a required construction rule
    could not be applied (maps to CONSTRUCTION_RULE_UNAVAILABLE)."""
    pass


@dataclass
class ProductGeometryBuild:
    geometry_type: str
    mesh: Any
    features: List[Dict[str, Any]] = field(default_factory=list)
    construction_values: List[Any] = field(default_factory=list)
    measurements: Dict[str, float] = field(default_factory=dict)
    expected_dimensions: Dict[str, float] = field(default_factory=dict)
    trace: List[str] = field(default_factory=list)
    # Prompt 13 additions (both optional/backward-compatible - Prompt 12's
    # pipe/elbow builders may omit them entirely):
    ports: List[Any] = field(default_factory=list)               # kgpe.geometry.ports.ConnectionPort
    topology_representation: Optional[str] = None
