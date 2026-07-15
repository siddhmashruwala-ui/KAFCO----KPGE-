# -*- coding: utf-8 -*-
"""
kgpe.geometry.fingerprint
=============================
Prompt 12 Sec.27: deterministic geometry fingerprint - represents the
ACTUAL GENERATED geometry (not merely the input specification). Reflects
normalized (rounded) vertex data, face/index data, units, the coordinate
convention, generation parameters, and the geometry-kernel version.
Excludes timestamps and object identity. Same inputs -> same fingerprint;
a meaningful geometry change -> a different one.
"""
import hashlib
import json

from .policy import round_for_fingerprint, COORDINATE_CONVENTION
from .mesh import Mesh


def compute_geometry_fingerprint(mesh: Mesh, generation_parameters, kernel_version):
    payload = {
        "units": mesh.units,
        "coordinate_convention": COORDINATE_CONVENTION,
        "kernel_version": kernel_version,
        "generation_parameters": generation_parameters.to_dict() if generation_parameters else None,
        "vertices": [[round_for_fingerprint(c) for c in v] for v in mesh.vertices],
        "faces": [list(f) for f in mesh.faces],
    }
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()
