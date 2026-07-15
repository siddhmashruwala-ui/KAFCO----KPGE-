# -*- coding: utf-8 -*-
"""
kgpe.geometry.validation
============================
Prompt 12 Sec.24-26: reusable structural + dimensional validation.
Returns structured findings - never hides a failure inside a log line
only. `measure_*` functions (Sec.25) compute numeric measurements off the
actual generated `Mesh`, compared against the requested engineering
dimensions with `kgpe.geometry.policy.within_tolerance`.
"""
import math
from dataclasses import dataclass, field
from typing import List, Dict, Any

from .policy import within_tolerance, DEGENERATE_AREA_THRESHOLD_MM2
from .mesh import Mesh


@dataclass
class ValidationCheck:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class ValidationResult:
    checks: List[ValidationCheck] = field(default_factory=list)

    @property
    def passed(self):
        return all(c.passed for c in self.checks)

    def add(self, name, passed, detail=""):
        self.checks.append(ValidationCheck(name, passed, detail))

    def to_dict(self):
        return {"passed": self.passed, "checks": [{"name": c.name, "passed": c.passed, "detail": c.detail}
                                                    for c in self.checks]}


def validate_mesh_structure(mesh: Mesh, expected_feature_count=None, features=None) -> ValidationResult:
    """Sec.24: structural validation - finite coordinates, no degenerate
    faces, no invalid indices, expected feature count."""
    result = ValidationResult()
    non_finite = mesh.has_non_finite_coordinates()
    result.add("finite_coordinates", not non_finite,
               "" if not non_finite else "Mesh contains non-finite vertex coordinates.")

    bad_indices = mesh.invalid_indices()
    result.add("valid_indices", len(bad_indices) == 0,
               "" if not bad_indices else f"{len(bad_indices)} face(s) with invalid/duplicate indices.")

    degenerate = mesh.degenerate_faces(DEGENERATE_AREA_THRESHOLD_MM2)
    result.add("no_degenerate_faces", len(degenerate) == 0,
               "" if not degenerate else f"{len(degenerate)} degenerate face(s) below area threshold.")

    result.add("non_empty_topology", mesh.vertex_count() > 0 and mesh.face_count() > 0,
               "" if mesh.vertex_count() > 0 and mesh.face_count() > 0 else "Mesh has no vertices/faces.")

    if expected_feature_count is not None:
        actual = len(features or [])
        result.add("expected_feature_count", actual == expected_feature_count,
                   f"expected {expected_feature_count} features, got {actual}")
    return result


def validate_dimensions(measurements: Dict[str, float], expected: Dict[str, float],
                         tolerance_mm=None) -> ValidationResult:
    """Sec.21/25: numeric comparison of MEASURED (off the actual generated
    geometry) vs INTENDED (engineering-dimension-derived) values - never
    assumed correct merely because generation didn't raise."""
    from .policy import LINEAR_TOLERANCE_MM
    tol = tolerance_mm if tolerance_mm is not None else LINEAR_TOLERANCE_MM
    result = ValidationResult()
    for name, expected_value in expected.items():
        measured_value = measurements.get(name)
        ok = measured_value is not None and within_tolerance(measured_value, expected_value, tol)
        result.add(f"dimension:{name}", ok,
                   f"measured={measured_value!r} expected={expected_value!r} tolerance={tol!r}")
    return result
