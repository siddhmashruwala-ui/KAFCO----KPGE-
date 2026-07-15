# -*- coding: utf-8 -*-
"""
kgpe.geometry.builders
==========================
Prompt 12 Sec.11: feature-based geometry construction on top of the
`Mesh` representation (Sec.6) and the primitive layer (Sec.10). Each
builder returns a `(Mesh, features)` pair - `features` is a deterministic
list of `{"name", "type", "vertex_range", "face_range", "params"}` dicts
describing each meaningful geometric region (outer wall, inner wall, end
caps, swept profile, ...), even though the underlying representation is a
single combined triangle mesh. This is what future debugging, dimensional
validation, hologram annotation, exploded/section views build on
(Sec.11) - none of that UI/rendering work happens in this prompt.
"""
from .primitives import circle_ring, straight_axis_frame, arc_sweep_frames, translate, vec_scale
from .mesh import Mesh


def _feature(name, ftype, v_start, v_end, f_start, f_end, params=None):
    return {"name": name, "type": ftype, "vertex_range": [v_start, v_end],
            "face_range": [f_start, f_end], "params": params or {}}


def build_hollow_cylinder(outer_radius, inner_radius, length, radial_segments):
    """Sec.18/21: a closed, hollow cylindrical solid (pipe segment) -
    outer cylindrical wall, inner cylindrical wall (bore), and two
    annular end-cap discs connecting them at each end. Extends along the
    global +Z primary product axis (Sec.7) starting at the origin.
    `inner_radius` must be strictly less than `outer_radius` (validated
    by the caller's construction rule, not re-derived here)."""
    u, v, _axis = straight_axis_frame()
    n = radial_segments
    mesh = Mesh()

    outer_start = mesh.add_vertices(circle_ring((0.0, 0.0, 0.0), u, v, outer_radius, n))
    outer_end = mesh.add_vertices(circle_ring((0.0, 0.0, length), u, v, outer_radius, n))
    inner_start = mesh.add_vertices(circle_ring((0.0, 0.0, 0.0), u, v, inner_radius, n))
    inner_end = mesh.add_vertices(circle_ring((0.0, 0.0, length), u, v, inner_radius, n))

    f0 = mesh.face_count()
    for i in range(n):
        j = (i + 1) % n
        mesh.add_quad(outer_start[i], outer_start[j], outer_end[j], outer_end[i])
    f1 = mesh.face_count()
    for i in range(n):
        j = (i + 1) % n
        mesh.add_quad(inner_start[j], inner_start[i], inner_end[i], inner_end[j])
    f2 = mesh.face_count()
    for i in range(n):
        j = (i + 1) % n
        mesh.add_quad(outer_start[i], outer_start[j], inner_start[j], inner_start[i])
    f3 = mesh.face_count()
    for i in range(n):
        j = (i + 1) % n
        mesh.add_quad(outer_end[j], outer_end[i], inner_end[i], inner_end[j])
    f4 = mesh.face_count()

    features = [
        _feature("outer_cylindrical_wall", "swept_outer_profile", outer_start[0], outer_end[-1], f0, f1,
                 {"radius_mm": outer_radius, "length_mm": length}),
        _feature("inner_cylindrical_wall_bore", "swept_inner_void", inner_start[0], inner_end[-1], f1, f2,
                 {"radius_mm": inner_radius, "length_mm": length}),
        _feature("end_cap_start", "annular_end_cap", outer_start[0], inner_start[-1], f2, f3,
                 {"z_mm": 0.0}),
        _feature("end_cap_end", "annular_end_cap", outer_end[0], inner_end[-1], f3, f4,
                 {"z_mm": length}),
    ]
    return mesh, features


def build_arc_swept_solid(outer_radius, bend_radius, total_angle_rad, radial_segments, sweep_segments):
    """Sec.10 'sweep along a deterministic path'/'revolution around an
    axis', Sec.11 elbow features ('swept outer circular profile'): a
    solid tube of circular cross-section `outer_radius`, swept along a
    circular arc of `bend_radius` through `total_angle_rad`, closed with
    flat circular end caps. No bore is modeled (the buttweld_elbow
    geometry profile - Prompt 11 - does not require wall_thickness/bore
    as a default dimension; this is documented honestly, not fabricated)."""
    frames = arc_sweep_frames(bend_radius, total_angle_rad, sweep_segments)
    n = radial_segments
    mesh = Mesh()

    rings = []
    for frame in frames:
        ring = mesh.add_vertices(circle_ring(frame["center"], frame["u_axis"], frame["v_axis"], outer_radius, n))
        rings.append(ring)

    f0 = mesh.face_count()
    for s in range(len(rings) - 1):
        ring_a, ring_b = rings[s], rings[s + 1]
        for i in range(n):
            j = (i + 1) % n
            mesh.add_quad(ring_a[i], ring_a[j], ring_b[j], ring_b[i])
    f1 = mesh.face_count()

    start_center = mesh.add_vertex(frames[0]["center"])
    for i in range(n):
        j = (i + 1) % n
        mesh.add_triangle(start_center, rings[0][j], rings[0][i])
    f2 = mesh.face_count()

    end_center = mesh.add_vertex(frames[-1]["center"])
    for i in range(n):
        j = (i + 1) % n
        mesh.add_triangle(end_center, rings[-1][i], rings[-1][j])
    f3 = mesh.face_count()

    features = [
        _feature("swept_outer_profile", "swept_outer_profile", rings[0][0], rings[-1][-1], f0, f1,
                 {"radius_mm": outer_radius, "bend_radius_mm": bend_radius, "total_angle_rad": total_angle_rad}),
        _feature("end_cap_start", "flat_end_cap", start_center, start_center, f1, f2, {}),
        _feature("end_cap_end", "flat_end_cap", end_center, end_center, f2, f3, {}),
    ]
    return mesh, features
