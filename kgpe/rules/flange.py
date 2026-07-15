# -*- coding: utf-8 -*-
"""
Flange geometry rule - the worked example from the KGPE architecture spec:
  "Create the flange body. Create the central bore. Create the hub.
   Create the neck. Create the taper/transition. Create the raised face.
   Create the bolt circle. Pattern the bolt holes."

v1 SCOPE (deliberately, not by oversight): the Dimension Library does not
currently carry hub diameter / neck taper geometry for any of the 3 flange
standards (ASME B16.5, JIS B2220, EN 1092-1) - those columns were dropped
during data-building because the source PDFs' hub/taper figures were
ambiguous. Per the architecture rule "KGPE must never infer an unknown
engineering dimension merely because a visually plausible model can be
generated", this rule models the flange as a flat-plate body + bore +
optional raised-face diameter + bolt-hole pattern, and explicitly warns
that the hub/neck taper is NOT modeled until that dimension data exists.
"""
from .. import dimension_library as dl
from ..schema import make_result, make_provenance, incomplete, STATUS_OK, ENGINEERING_STATE_FINISHED
from ..version import RULESET_VERSION, MAPPER_VERSION, DIMENSION_LIBRARY_ADAPTER_VERSION

PRODUCT_TYPE = "flange"


def generate(request):
    standard = request.get("standard")
    size = request.get("size")
    class_key = request.get("class_key")
    facing = request.get("facing", "RF")
    pipe_schedule = request.get("pipe_schedule")
    pipe_standard = request.get("pipe_standard")

    if not (standard and size is not None and class_key):
        return incomplete("flange request requires 'standard', 'size', and 'class_key'", PRODUCT_TYPE, request)

    try:
        dims, source = dl.get_flange(standard, size, class_key)
    except dl.DimNotFound as e:
        return incomplete(str(e), PRODUCT_TYPE, request)

    warnings = []
    bore_mm = dims.get("BoreID_mm")
    pipe_source = None
    if bore_mm is None:
        if not pipe_schedule:
            return incomplete(
                f"{standard} does not publish per-class bore diameter; "
                f"'pipe_schedule' (e.g. 'Sch40') is required to resolve bore for this flange, "
                f"but none was given in the request.", PRODUCT_TYPE, request)
        pstd = pipe_standard or _default_pipe_standard(standard)
        try:
            pipe_dims, pipe_source = dl.get_pipe(pstd, size, pipe_schedule)
        except dl.DimNotFound as e:
            return incomplete(f"Could not resolve bore via pipe schedule: {e}", PRODUCT_TYPE, request)
        bore_mm = pipe_dims["BoreID_mm"]
        if dims.get("NeckOD_mm") is None:
            dims["NeckOD_mm"] = pipe_dims["OD_mm"]

    return _build(request, dims, source, bore_mm, pipe_source, warnings)


def _default_pipe_standard(flange_standard):
    return {"ASME_B16.5": "ASME_B36", "JIS_B2220": "JIS_G3452_3454_3459", "EN_1092-1": "EN_10216_10217"}.get(flange_standard)


def _build(request, dims, source, bore_mm, pipe_source, warnings):
    od = dims["OD_mm"]
    thk = dims["Thickness_mm"]
    rf = dims.get("RaisedFace_mm")

    features = [
        {"type": "body_disc", "outside_dia_mm": od, "thickness_mm": thk, "bore_dia_mm": bore_mm},
        {"type": "bore_through_hole", "diameter_mm": bore_mm},
        {"type": "bolt_circle_pattern", "bolt_circle_dia_mm": dims["BoltCircle_mm"],
         "hole_dia_mm": dims["BoltHoleDia_mm"], "num_holes": dims["NumBolts"], "bolt_size": dims["BoltSize"]},
    ]
    if rf is not None:
        features.append({"type": "raised_face_diameter_marker", "diameter_mm": rf,
                          "height_mm": None, "note": "RF height not in dimension library - diameter only"})
    else:
        warnings.append("Raised face diameter not available in dimension library for this standard/class - "
                         "RF feature omitted; face modeled flat.")
    warnings.append("Hub/neck taper NOT modeled in KGPE v1 - hub diameter data is not yet in the Dimension "
                     "Library for any flange standard. Body is modeled as a flat plate of uniform thickness.")

    # Simplified axisymmetric half-profile (r, z) mm: flat plate + through bore.
    # z=0 is the back face, z=thk is the front (raised-face-bearing) face.
    profile_2d = [
        {"r": od / 2, "z": 0}, {"r": od / 2, "z": thk},
        {"r": bore_mm / 2, "z": thk}, {"r": bore_mm / 2, "z": 0},
    ]

    geometry = {
        "type": "revolve_profile_plus_features",
        "profile_2d_mm": profile_2d,
        "features": features,
    }
    prov_extra = {}
    if pipe_source:
        prov_extra["bore_source"] = pipe_source
    provenance = make_provenance(source, RULESET_VERSION, MAPPER_VERSION, DIMENSION_LIBRARY_ADAPTER_VERSION,
                                  request, extra=prov_extra)
    return make_result(STATUS_OK, PRODUCT_TYPE, ENGINEERING_STATE_FINISHED, geometry, provenance, warnings)
