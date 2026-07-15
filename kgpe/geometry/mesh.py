# -*- coding: utf-8 -*-
"""
kgpe.geometry.mesh
======================
Prompt 12 Sec.6: the chosen internal geometry representation - a
deterministic indexed triangle mesh (vertices + triangle index tuples).

Chosen because:
  - it directly supports future 3D visualization / triangulated mesh
    export (Sec.6) with no translation step;
  - vertex/face counts give an immediate, deterministic topology summary
    (Sec.26);
  - dimensional validation (Sec.24-25) can measure directly off vertex
    coordinates;
  - it needs no new dependency - a plain list-of-tuples representation is
    sufficient for Prompt 12's reference products and keeps the kernel
    stdlib-only.

Vertex ordering is always deterministic (append-only, in the order each
primitive/product builder constructs them - never a set/dict iteration
order). Face ordering is always deterministic (append-only in construction
order). Units are always mm (kgpe.geometry.policy.LENGTH_UNIT).
"""
import math
from dataclasses import dataclass, field
from typing import List, Tuple

from .policy import LENGTH_UNIT, DEGENERATE_AREA_THRESHOLD_MM2


@dataclass
class Mesh:
    vertices: List[Tuple[float, float, float]] = field(default_factory=list)
    faces: List[Tuple[int, int, int]] = field(default_factory=list)  # triangle vertex indices
    units: str = LENGTH_UNIT

    def add_vertex(self, point):
        self.vertices.append((float(point[0]), float(point[1]), float(point[2])))
        return len(self.vertices) - 1

    def add_vertices(self, points):
        return [self.add_vertex(p) for p in points]

    def add_triangle(self, i, j, k):
        self.faces.append((i, j, k))

    def add_quad(self, i, j, k, l):
        """Deterministic quad-to-triangle split: (i,j,k) then (i,k,l)."""
        self.add_triangle(i, j, k)
        self.add_triangle(i, k, l)

    def vertex_count(self):
        return len(self.vertices)

    def face_count(self):
        return len(self.faces)

    def bounding_box(self):
        if not self.vertices:
            return None
        xs = [v[0] for v in self.vertices]
        ys = [v[1] for v in self.vertices]
        zs = [v[2] for v in self.vertices]
        return {"min": (min(xs), min(ys), min(zs)), "max": (max(xs), max(ys), max(zs))}

    def triangle_area(self, face):
        i, j, k = face
        a, b, c = self.vertices[i], self.vertices[j], self.vertices[k]
        ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
        cx, cy, cz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        return 0.5 * math.sqrt(cx * cx + cy * cy + cz * cz)

    def degenerate_faces(self, threshold=DEGENERATE_AREA_THRESHOLD_MM2):
        return [f for f in self.faces if self.triangle_area(f) < threshold]

    def has_non_finite_coordinates(self):
        return any(not all(math.isfinite(c) for c in v) for v in self.vertices)

    def invalid_indices(self):
        n = len(self.vertices)
        bad = []
        for f in self.faces:
            if len(set(f)) != 3 or any((idx < 0 or idx >= n) for idx in f):
                bad.append(f)
        return bad

    def to_dict(self):
        return {
            "units": self.units,
            "vertex_count": self.vertex_count(),
            "face_count": self.face_count(),
            "vertices": [list(v) for v in self.vertices],
            "faces": [list(f) for f in self.faces],
        }
