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
import math

from .primitives import circle_ring, straight_axis_frame, arc_sweep_frames, translate, vec_scale, rotate_about_axis
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


def build_arc_swept_hollow_solid(outer_radius, inner_radius, bend_radius, total_angle_rad,
                                  radial_segments, sweep_segments):
    """Prompt 13 Sec.9: hollow elbow upgrade - outer swept surface, inner
    swept surface (bore), and two annular end caps connecting them,
    mirroring `build_hollow_cylinder`'s annular-end-cap pattern but along
    the arc-swept path instead of a straight extrusion. Only used when an
    explicit `WallContext`-derived inner_radius is available (Sec.9) -
    never fabricated."""
    frames = arc_sweep_frames(bend_radius, total_angle_rad, sweep_segments)
    n = radial_segments
    mesh = Mesh()

    outer_rings, inner_rings = [], []
    for frame in frames:
        outer_rings.append(mesh.add_vertices(
            circle_ring(frame["center"], frame["u_axis"], frame["v_axis"], outer_radius, n)))
        inner_rings.append(mesh.add_vertices(
            circle_ring(frame["center"], frame["u_axis"], frame["v_axis"], inner_radius, n)))

    f0 = mesh.face_count()
    for s in range(len(outer_rings) - 1):
        a, b = outer_rings[s], outer_rings[s + 1]
        for i in range(n):
            j = (i + 1) % n
            mesh.add_quad(a[i], a[j], b[j], b[i])
    f1 = mesh.face_count()
    for s in range(len(inner_rings) - 1):
        a, b = inner_rings[s], inner_rings[s + 1]
        for i in range(n):
            j = (i + 1) % n
            mesh.add_quad(a[j], a[i], b[i], b[j])
    f2 = mesh.face_count()
    for i in range(n):
        j = (i + 1) % n
        mesh.add_quad(outer_rings[0][i], outer_rings[0][j], inner_rings[0][j], inner_rings[0][i])
    f3 = mesh.face_count()
    for i in range(n):
        j = (i + 1) % n
        mesh.add_quad(outer_rings[-1][j], outer_rings[-1][i], inner_rings[-1][i], inner_rings[-1][j])
    f4 = mesh.face_count()

    features = [
        _feature("swept_outer_profile", "swept_outer_profile", outer_rings[0][0], outer_rings[-1][-1], f0, f1,
                 {"radius_mm": outer_radius, "bend_radius_mm": bend_radius, "total_angle_rad": total_angle_rad}),
        _feature("swept_inner_profile_bore", "swept_inner_void", inner_rings[0][0], inner_rings[-1][-1], f1, f2,
                 {"radius_mm": inner_radius}),
        _feature("end_cap_start", "annular_end_cap", outer_rings[0][0], inner_rings[0][-1], f2, f3, {}),
        _feature("end_cap_end", "annular_end_cap", outer_rings[-1][0], inner_rings[-1][-1], f3, f4, {}),
    ]
    return mesh, features


def build_solid_cylinder(radius, length, radial_segments):
    """Prompt 13 Sec.16/18: a solid (non-hollow) cylinder closed with two
    flat end discs - used for the tee run/branch bodies and the cap body
    (a cap is exactly a solid cylinder of the selected length -
    `CapProfileConstructionRule`'s flat-disc closure, Sec.18)."""
    u, v, _axis = straight_axis_frame()
    n = radial_segments
    mesh = Mesh()

    ring_start = mesh.add_vertices(circle_ring((0.0, 0.0, 0.0), u, v, radius, n))
    ring_end = mesh.add_vertices(circle_ring((0.0, 0.0, length), u, v, radius, n))

    f0 = mesh.face_count()
    for i in range(n):
        j = (i + 1) % n
        mesh.add_quad(ring_start[i], ring_start[j], ring_end[j], ring_end[i])
    f1 = mesh.face_count()

    start_center = mesh.add_vertex((0.0, 0.0, 0.0))
    for i in range(n):
        j = (i + 1) % n
        mesh.add_triangle(start_center, ring_start[j], ring_start[i])
    f2 = mesh.face_count()

    end_center = mesh.add_vertex((0.0, 0.0, length))
    for i in range(n):
        j = (i + 1) % n
        mesh.add_triangle(end_center, ring_end[i], ring_end[j])
    f3 = mesh.face_count()

    features = [
        _feature("outer_wall", "swept_outer_profile", ring_start[0], ring_end[-1], f0, f1,
                 {"radius_mm": radius, "length_mm": length}),
        _feature("start_cap", "flat_end_cap", start_center, start_center, f1, f2, {"z_mm": 0.0}),
        _feature("end_cap", "flat_end_cap", end_center, end_center, f2, f3, {"z_mm": length}),
    ]
    return mesh, features


def build_cap_solid(radius, length, radial_segments):
    """Prompt 13 Sec.18-19: a cap fitting - a cylindrical shell OPEN at
    z=0 (the connection port / open end, where the mating pipe inserts)
    and closed with a flat disc at z=length
    (`CapProfileConstructionRule`'s flat-disc closure)."""
    u, v, _axis = straight_axis_frame()
    n = radial_segments
    mesh = Mesh()

    ring_open = mesh.add_vertices(circle_ring((0.0, 0.0, 0.0), u, v, radius, n))
    ring_closed = mesh.add_vertices(circle_ring((0.0, 0.0, length), u, v, radius, n))

    f0 = mesh.face_count()
    for i in range(n):
        j = (i + 1) % n
        mesh.add_quad(ring_open[i], ring_open[j], ring_closed[j], ring_closed[i])
    f1 = mesh.face_count()

    closed_center = mesh.add_vertex((0.0, 0.0, length))
    for i in range(n):
        j = (i + 1) % n
        mesh.add_triangle(closed_center, ring_closed[i], ring_closed[j])
    f2 = mesh.face_count()

    features = [
        _feature("cap_body_wall", "swept_outer_profile", ring_open[0], ring_closed[-1], f0, f1,
                 {"radius_mm": radius, "length_mm": length}),
        _feature("open_end", "open_face", ring_open[0], ring_open[-1], f0, f0, {"z_mm": 0.0}),
        _feature("closed_end_disc", "flat_end_cap", closed_center, closed_center, f1, f2, {"z_mm": length}),
    ]
    return mesh, features


def build_frustum_solid(large_radius, small_radius, length, radial_segments, small_end_offset=(0.0, 0.0)):
    """Prompt 13 Sec.22-25: a solid (external-envelope) reducer body - a
    ruled lateral surface between a large-radius ring at z=0 (centred at
    the origin) and a small-radius ring at z=length (centred at
    `small_end_offset` in the XY plane, per `EccentricReducerOffsetRule` -
    (0,0) for a concentric reducer), closed with two flat end discs.
    `ConcentricReducerTransitionRule`'s linear interpolation is exactly
    this ruled-surface construction (a straight generatrix from each large
    -ring vertex to its corresponding small-ring vertex)."""
    u, v, _axis = straight_axis_frame()
    n = radial_segments
    mesh = Mesh()
    ox, oy = small_end_offset

    large_ring = mesh.add_vertices(circle_ring((0.0, 0.0, 0.0), u, v, large_radius, n))
    small_ring = mesh.add_vertices(circle_ring((ox, oy, length), u, v, small_radius, n))

    f0 = mesh.face_count()
    for i in range(n):
        j = (i + 1) % n
        mesh.add_quad(large_ring[i], large_ring[j], small_ring[j], small_ring[i])
    f1 = mesh.face_count()

    large_center = mesh.add_vertex((0.0, 0.0, 0.0))
    for i in range(n):
        j = (i + 1) % n
        mesh.add_triangle(large_center, large_ring[j], large_ring[i])
    f2 = mesh.face_count()

    small_center = mesh.add_vertex((ox, oy, length))
    for i in range(n):
        j = (i + 1) % n
        mesh.add_triangle(small_center, small_ring[i], small_ring[j])
    f3 = mesh.face_count()

    features = [
        _feature("conical_transition", "ruled_transition_surface", large_ring[0], small_ring[-1], f0, f1,
                 {"large_radius_mm": large_radius, "small_radius_mm": small_radius, "length_mm": length,
                  "small_end_offset_mm": list(small_end_offset)}),
        _feature("large_end_cap", "flat_end_cap", large_center, large_center, f1, f2, {"z_mm": 0.0}),
        _feature("small_end_cap", "flat_end_cap", small_center, small_center, f2, f3, {"z_mm": length}),
    ]
    return mesh, features


def build_hollow_cylinder_with_hub(body_outer_radius, hub_outer_radius, bore_radius,
                                    body_length, hub_length, radial_segments):
    """Prompt 42: a flange body (`build_hollow_cylinder`, body_outer_radius,
    spanning z in [0, body_length]) with a hub - a raised annular cylinder
    of `hub_outer_radius` - stacked immediately after it, spanning z in
    [body_length, body_length+hub_length]. Modeled as a STRAIGHT cylinder,
    not the true ASME B16.5 taper toward the pipe OD at the weld end (no
    consistently-published far-end/point-of-welding diameter across the
    cross-verified sources - a documented simplification, not a
    fabricated dimension; see kgpe.geometry.products.flange's module
    docstring). Body and hub share ONE continuous bore (`bore_radius`)
    throughout - physically correct, since a weld-neck flange is forged
    as a single piece, never two separately-bored parts.

    Like `build_tee_multi_feature`/`build_cross_multi_feature`, this is a
    deterministic multi-feature mesh, NOT a boolean union - the body's
    end-cap-at-z=body_length and the hub's start-cap-at-z=body_length are
    two coincident (touching, non-overlapping-volume) annular disc faces,
    an honest representation of a stacked composite, never fused into a
    single watertight shell."""
    body_mesh, body_features = build_hollow_cylinder(body_outer_radius, bore_radius, body_length, radial_segments)
    hub_mesh, hub_features = build_hollow_cylinder(hub_outer_radius, bore_radius, hub_length, radial_segments)
    for i, v in enumerate(hub_mesh.vertices):
        hub_mesh.vertices[i] = (v[0], v[1], v[2] + body_length)
    body_features = [dict(f, name=f"body_{f['name']}") for f in body_features]
    return _merge_meshes(body_mesh, body_features, hub_mesh, hub_features, "hub_")


def build_solid_cylinder_with_hub(body_outer_radius, hub_outer_radius, body_length, hub_length, radial_segments):
    """Prompt 42: same composite as `build_hollow_cylinder_with_hub` but
    for the no-resolved-bore case (body and hub both solid, external-
    envelope only) - used when hub dimensions ARE available but bore
    isn't (structurally possible even though today's only hub-bearing
    standard, ASME_B16.5, always resolves a bore too via
    FlangeBoreViaPipeScheduleRule when a mating pipe context is supplied;
    this function exists so the hub is never silently dropped just
    because bore context happened not to be supplied for a given call)."""
    body_mesh, body_features = build_solid_cylinder(body_outer_radius, body_length, radial_segments)
    hub_mesh, hub_features = build_solid_cylinder(hub_outer_radius, hub_length, radial_segments)
    for i, v in enumerate(hub_mesh.vertices):
        hub_mesh.vertices[i] = (v[0], v[1], v[2] + body_length)
    body_features = [dict(f, name=f"body_{f['name']}") for f in body_features]
    return _merge_meshes(body_mesh, body_features, hub_mesh, hub_features, "hub_")


def _merge_meshes(mesh_a, features_a, mesh_b, features_b, prefix_b):
    """Deterministically merges mesh_b's vertices/faces onto the end of
    mesh_a (index-offset, append-only - Sec.13: a deterministic
    multi-feature mesh, never a boolean union)."""
    offset = mesh_a.vertex_count()
    for v in mesh_b.vertices:
        mesh_a.add_vertex(v)
    for f in mesh_b.faces:
        mesh_a.add_triangle(f[0] + offset, f[1] + offset, f[2] + offset)
    merged_features = list(features_a)
    face_offset = len(mesh_a.faces) - len(mesh_b.faces)
    for feat in features_b:
        merged_features.append(_feature(
            f"{prefix_b}{feat['name']}", feat["type"],
            feat["vertex_range"][0] + offset, feat["vertex_range"][1] + offset,
            feat["face_range"][0] + face_offset, feat["face_range"][1] + face_offset,
            feat["params"]))
    return mesh_a, merged_features


def build_tee_multi_feature(run_radius, run_half_length, branch_radius, branch_length, radial_segments):
    """Prompt 13 Sec.12-13: deterministic multi-feature tee representation
    - an honest, non-manifold-at-intersection mesh (per
    `TeeBranchBlendingRule` - no fillet/blend surface is constructed).
    Run body: solid cylinder along global +Z, centred at the origin,
    spanning z in [-run_half_length, +run_half_length]. Branch body: solid
    cylinder along global +Y, spanning y in [0, branch_length] (from the
    run centreline outward) - its root end necessarily overlaps the run
    body's volume for y in [0, run_radius]; this overlap is the
    `TeeBranchBlendingRule`'s explicit, documented "raw intersection, no
    blend" representation."""
    run_mesh, run_features = build_solid_cylinder(run_radius, 2.0 * run_half_length, radial_segments)
    for i, v in enumerate(run_mesh.vertices):
        run_mesh.vertices[i] = (v[0], v[1], v[2] - run_half_length)

    branch_mesh, branch_features = build_solid_cylinder(branch_radius, branch_length, radial_segments)
    angle = -math.pi / 2.0  # rotate local +Z onto global +Y
    for i, v in enumerate(branch_mesh.vertices):
        branch_mesh.vertices[i] = rotate_about_axis(v, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), angle)

    run_features = [dict(f, name=f"run_{f['name']}") for f in run_features]
    return _merge_meshes(run_mesh, run_features, branch_mesh, branch_features, "branch_")


def build_two_arm_multi_feature(radius, length_a, length_b, angle_rad, radial_segments):
    """Prompt 15 Sec.13: deterministic multi-feature socket-weld elbow
    representation - two solid cylindrical arms joined at the origin, arm
    A along global +Z spanning [0, length_a], arm B rotated by
    `angle_rad` from +Z about the Y axis (bend plane = X-Z plane, matching
    Prompt 13's buttweld-elbow bend-plane convention) spanning
    [0, length_b] from the origin. Honest non-manifold overlap at the
    joint, exactly like `build_tee_multi_feature` - no fillet/bend
    transition is fabricated. `angle_rad = pi/2` for a 90deg elbow,
    `pi/4` for a 45deg elbow."""
    arm_a_mesh, arm_a_features = build_solid_cylinder(radius, length_a, radial_segments)
    arm_b_mesh, arm_b_features = build_solid_cylinder(radius, length_b, radial_segments)
    for i, v in enumerate(arm_b_mesh.vertices):
        arm_b_mesh.vertices[i] = rotate_about_axis(v, (0.0, 0.0, 0.0), (0.0, 1.0, 0.0), angle_rad)

    arm_a_features = [dict(f, name=f"arm_a_{f['name']}") for f in arm_a_features]
    return _merge_meshes(arm_a_mesh, arm_a_features, arm_b_mesh, arm_b_features, "arm_b_")


def build_cross_multi_feature(radius, run_half_length, branch_a_length, branch_b_length, radial_segments):
    """Prompt 15 Sec.13: deterministic multi-feature socket-weld cross
    representation - a run body (solid cylinder along global +Z, centred
    at the origin, spanning [-run_half_length, +run_half_length]) plus
    TWO branch arms along +Y and -Y (opposite directions), each a solid
    cylinder from the origin outward. Honest non-manifold overlap at the
    intersection, exactly like `build_tee_multi_feature` extended to a
    fourth arm - no fillet/blend surface is fabricated."""
    run_mesh, run_features = build_solid_cylinder(radius, 2.0 * run_half_length, radial_segments)
    for i, v in enumerate(run_mesh.vertices):
        run_mesh.vertices[i] = (v[0], v[1], v[2] - run_half_length)
    run_features = [dict(f, name=f"run_{f['name']}") for f in run_features]

    branch_a_mesh, branch_a_features = build_solid_cylinder(radius, branch_a_length, radial_segments)
    for i, v in enumerate(branch_a_mesh.vertices):
        branch_a_mesh.vertices[i] = rotate_about_axis(v, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), -math.pi / 2.0)

    branch_b_mesh, branch_b_features = build_solid_cylinder(radius, branch_b_length, radial_segments)
    for i, v in enumerate(branch_b_mesh.vertices):
        branch_b_mesh.vertices[i] = rotate_about_axis(v, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), math.pi / 2.0)

    mesh, features = _merge_meshes(run_mesh, run_features, branch_a_mesh, branch_a_features, "branch_a_")
    mesh, features = _merge_meshes(mesh, features, branch_b_mesh, branch_b_features, "branch_b_")
    return mesh, features
