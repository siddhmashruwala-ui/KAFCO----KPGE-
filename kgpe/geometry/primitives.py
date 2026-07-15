# -*- coding: utf-8 -*-
"""
kgpe.geometry.primitives
============================
Prompt 12 Sec.10: reusable mathematical geometry primitives - the small
foundation later product modules build on. Pure standard-library
(`math` only) - no numpy/CAD dependency was added merely for convenience
(the environment has numpy available, but every existing kgpe module is
stdlib-only, and this kernel keeps that same zero-dependency footprint).

Every function here is a pure function: validated inputs, deterministic
output, explicit units (mm) and coordinate assumptions (kgpe.geometry.
policy), no hidden state, no randomness.
"""
import math
from dataclasses import dataclass
from typing import Tuple

from .policy import NEAR_ZERO_MM, is_effectively_zero


class InvalidPrimitiveInputError(Exception):
    """Raised when a primitive is given non-finite or physically invalid
    input (negative/zero radius, non-finite coordinate, etc). Fail closed,
    never silently produce a degenerate primitive."""
    pass


def _require_finite(value, label):
    if not math.isfinite(value):
        raise InvalidPrimitiveInputError(f"{label} must be finite, got {value!r}")
    return value


Point3 = Tuple[float, float, float]
Vector3 = Tuple[float, float, float]


def vec_add(a: Vector3, b: Vector3) -> Vector3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vec_sub(a: Vector3, b: Vector3) -> Vector3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vec_scale(a: Vector3, s: float) -> Vector3:
    return (a[0] * s, a[1] * s, a[2] * s)


def vec_dot(a: Vector3, b: Vector3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vec_cross(a: Vector3, b: Vector3) -> Vector3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def vec_length(a: Vector3) -> float:
    return math.sqrt(vec_dot(a, a))


def vec_normalize(a: Vector3) -> Vector3:
    length = vec_length(a)
    if is_effectively_zero(length):
        raise InvalidPrimitiveInputError(f"Cannot normalize a near-zero-length vector {a!r}")
    return vec_scale(a, 1.0 / length)


def translate(point: Point3, offset: Vector3) -> Point3:
    for v in (*point, *offset):
        _require_finite(v, "translate operand")
    return vec_add(point, offset)


def rotate_about_axis(point: Point3, axis_origin: Point3, axis_dir: Vector3, angle_rad: float) -> Point3:
    """Rodrigues' rotation formula - rotates `point` by `angle_rad` around
    the line through `axis_origin` with (already-normalized) direction
    `axis_dir`. Deterministic, no trig-library platform variance beyond
    ordinary IEEE-754 double precision."""
    _require_finite(angle_rad, "angle_rad")
    axis_dir = vec_normalize(axis_dir)
    p = vec_sub(point, axis_origin)
    cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
    term1 = vec_scale(p, cos_a)
    term2 = vec_scale(vec_cross(axis_dir, p), sin_a)
    term3 = vec_scale(axis_dir, vec_dot(axis_dir, p) * (1 - cos_a))
    rotated = vec_add(vec_add(term1, term2), term3)
    return vec_add(rotated, axis_origin)


def validate_positive(value, label):
    _require_finite(value, label)
    if value <= NEAR_ZERO_MM:
        raise InvalidPrimitiveInputError(f"{label} must be a positive length, got {value!r}")
    return value


def validate_segment_count(count, label, minimum=3):
    if not isinstance(count, int) or count < minimum:
        raise InvalidPrimitiveInputError(f"{label} must be an int >= {minimum}, got {count!r}")
    return count


def circle_ring(center: Point3, u_axis: Vector3, v_axis: Vector3, radius: float, segments: int):
    """Sec.10 'circle'/'ring' primitive: deterministic list of `segments`
    points around a circle of `radius` centred at `center`, lying in the
    plane spanned by the orthonormal basis (u_axis, v_axis). Point 0 is
    always at `center + radius*u_axis` (deterministic seam placement,
    Sec.20) and points proceed counter-clockwise toward v_axis."""
    validate_positive(radius, "radius")
    validate_segment_count(segments, "segments")
    u = vec_normalize(u_axis)
    v = vec_normalize(v_axis)
    points = []
    for i in range(segments):
        theta = 2.0 * math.pi * i / segments
        offset = vec_add(vec_scale(u, radius * math.cos(theta)), vec_scale(v, radius * math.sin(theta)))
        points.append(translate(center, offset))
    return points


def straight_axis_frame():
    """The deterministic local frame for a straight extrusion along the
    global +Z primary product axis (Sec.7): u=+X, v=+Y, axis=+Z."""
    return (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)


def arc_sweep_frames(bend_radius: float, total_angle_rad: float, sweep_segments: int):
    """Sec.10 'sweep along a deterministic path' / 'revolution around an
    axis': returns `sweep_segments + 1` deterministic local frames
    (center, u_axis, v_axis, tangent) for a circular arc of `bend_radius`
    swept through `total_angle_rad`, lying in the global XZ plane, entering
    at the origin travelling along +Z (Sec.7's primary product axis).

    Arc parametrization (bend pivot implicitly at (bend_radius, 0, 0)):
        center(theta) = (bend_radius - bend_radius*cos(theta), 0, bend_radius*sin(theta))
        tangent(theta) = (sin(theta), 0, cos(theta))          [unit, entering +Z at theta=0]
    v_axis is always the global +Y (always perpendicular to any XZ-plane
    tangent); u_axis = tangent x v_axis, giving a right-handed, orthonormal,
    deterministic cross-section basis at every step - no discontinuity, no
    seam drift, no randomness.
    """
    validate_positive(bend_radius, "bend_radius")
    _require_finite(total_angle_rad, "total_angle_rad")
    if total_angle_rad <= 0:
        raise InvalidPrimitiveInputError(f"total_angle_rad must be positive, got {total_angle_rad!r}")
    validate_segment_count(sweep_segments, "sweep_segments", minimum=1)

    frames = []
    v_axis = (0.0, 1.0, 0.0)
    for i in range(sweep_segments + 1):
        theta = total_angle_rad * i / sweep_segments
        center = (bend_radius - bend_radius * math.cos(theta), 0.0, bend_radius * math.sin(theta))
        tangent = (math.sin(theta), 0.0, math.cos(theta))
        u_axis = vec_cross(tangent, v_axis)
        frames.append({"center": center, "u_axis": vec_normalize(u_axis), "v_axis": v_axis, "tangent": tangent})
    return frames
