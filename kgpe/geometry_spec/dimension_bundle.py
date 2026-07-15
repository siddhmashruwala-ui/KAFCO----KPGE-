# -*- coding: utf-8 -*-
"""
kgpe.geometry_spec.dimension_bundle
=====================================
Prompt 11 Sec.6: a structured, traceable representation for dimensions
handed to geometry. Every `ResolvedDimension` retains its canonical name,
value, unit, verification status, and a compact provenance reference -
this is never reduced to an untraceable dict of bare floats. Geometry code
may still want convenient numeric access; `EngineeringDimensionBundle.
numeric_values()` provides that explicitly, alongside (never instead of)
the traceable form.
"""
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any


@dataclass(frozen=True)
class ResolvedDimension:
    name: str
    value: Any
    unit: str
    verification_status: str
    source_file: Optional[str] = None
    provenance_summary: Optional[str] = None

    @classmethod
    def from_resolved_dict(cls, name, d):
        """Builds from one entry of `ResolvedEngineeringSpecification.
        resolved_dimensions[name]` (Prompt 10's shape: value/unit/
        verification_status/source_file)."""
        source_file = d.get("source_file")
        status = d.get("verification_status")
        summary = f"{status} from {source_file}" if source_file else status
        return cls(name=name, value=d.get("value"), unit=d.get("unit"),
                    verification_status=status, source_file=source_file,
                    provenance_summary=summary)

    def to_dict(self):
        return asdict(self)


@dataclass
class EngineeringDimensionBundle:
    """An ordered, named collection of `ResolvedDimension` entries."""
    dimensions: Dict[str, ResolvedDimension] = field(default_factory=dict)

    def __contains__(self, name):
        return name in self.dimensions

    def __getitem__(self, name):
        return self.dimensions[name]

    def __iter__(self):
        return iter(self.dimensions[n] for n in sorted(self.dimensions))

    def __len__(self):
        return len(self.dimensions)

    def names(self):
        return sorted(self.dimensions)

    def numeric_values(self):
        """Convenience dict of name -> value only, for geometry code that
        just wants numbers. The authoritative bundle (this object) remains
        what traceability/audits use - this is an explicit, clearly-named
        accessor, never the bundle's only representation (Sec.6)."""
        return {name: d.value for name, d in self.dimensions.items()}

    def add(self, resolved_dimension: ResolvedDimension):
        self.dimensions[resolved_dimension.name] = resolved_dimension

    def to_dict(self):
        return {name: self.dimensions[name].to_dict() for name in sorted(self.dimensions)}

    @classmethod
    def empty(cls):
        return cls(dimensions={})
