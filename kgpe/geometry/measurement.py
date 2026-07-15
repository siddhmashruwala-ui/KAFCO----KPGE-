# -*- coding: utf-8 -*-
"""
kgpe.geometry.measurement
=============================
Prompt 12 Sec.25: reusable dimensional-measurement framework - computes
numeric measurements directly off generated `Mesh` vertex data (never
"visual inspection") so `kgpe.geometry.validation.validate_dimensions`
has real measured values to compare against intended engineering
dimensions.
"""
import math

from .mesh import Mesh


def measure_radial_distance(mesh: Mesh, vertex_indices, axis_point=(0.0, 0.0), axis_plane="xy"):
    """Max distance from the product axis (default: the Z axis, measured
    in the XY plane) among the given vertex indices - used for outer/bore
    diameter measurement (Sec.25)."""
    ax, ay = axis_point
    max_r = 0.0
    for idx in vertex_indices:
        x, y, _z = mesh.vertices[idx]
        r = math.hypot(x - ax, y - ay)
        if r > max_r:
            max_r = r
    return max_r


def measure_axial_length(mesh: Mesh, axis="z"):
    """Bounding-box extent along the given global axis (Sec.25) - used to
    validate a pipe's generated length against its generation parameter."""
    bbox = mesh.bounding_box()
    if bbox is None:
        return 0.0
    axis_idx = {"x": 0, "y": 1, "z": 2}[axis]
    return bbox["max"][axis_idx] - bbox["min"][axis_idx]


def measure_bend_radius(mesh: Mesh, ring_center_indices, pivot=(0.0, 0.0, 0.0)):
    """Distance from the bend pivot to each swept ring's centre (average),
    used to validate an elbow's generated bend radius against its
    centre_to_end_mm engineering dimension (Sec.25)."""
    if not ring_center_indices:
        return 0.0
    total = 0.0
    for idx in ring_center_indices:
        vx, vy, vz = mesh.vertices[idx]
        px, py, pz = pivot
        total += math.sqrt((vx - px) ** 2 + (vy - py) ** 2 + (vz - pz) ** 2)
    return total / len(ring_center_indices)
