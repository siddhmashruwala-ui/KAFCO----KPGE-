# -*- coding: utf-8 -*-
"""Buttweld fitting geometry rules: elbow_90, tee, cap.

These produce SIMPLIFIED representative geometry (swept/stub primitives),
not true CAD boolean-intersection solids - adequate for schematic/hologram
visualization (matching the CRM dashboard's existing use case) but not a
substitute for a real CAD model. This limitation is stated in every result's
warnings, not left implicit.
"""
from .. import dimension_library as dl
from ..schema import make_result, make_provenance, incomplete, STATUS_OK, ENGINEERING_STATE_FINISHED
from ..version import RULESET_VERSION, MAPPER_VERSION, DIMENSION_LIBRARY_ADAPTER_VERSION

PRODUCT_TYPE = "buttweld_fitting"
SIMPLIFIED_WARNING = ("Simplified representative geometry (swept/stub primitives), not a true CAD "
                       "boolean-intersection solid - suitable for schematic/hologram visualization only.")


def generate(request):
    fitting = request.get("fitting_type")
    standard = request.get("standard")
    size = request.get("size")
    if not (fitting and standard and size is not None):
        return incomplete("buttweld request requires 'fitting_type', 'standard', and 'size'", PRODUCT_TYPE, request)

    if fitting == "elbow_90":
        return _elbow90(request, standard, size)
    if fitting == "tee":
        return _tee(request, standard, size)
    if fitting == "cap":
        return _cap(request, standard, size)
    return incomplete(f"Unsupported fitting_type '{fitting}' (supported: elbow_90, tee, cap)", PRODUCT_TYPE, request)


def _elbow90(request, standard, size):
    try:
        dims, source = dl.get_buttweld_elbow90(standard, size)
    except dl.DimNotFound as e:
        return incomplete(str(e), PRODUCT_TYPE, request)
    geometry = {
        "type": "elbow_sweep",
        "features": [{"type": "elbow_90_sweep", "od_mm": dims["OD_mm"], "bend_radius_mm": dims["CtoE_mm"],
                      "angle_deg": 90, "wall_thickness_mm": dims.get("WallThickness_mm")}],
    }
    provenance = make_provenance(source, RULESET_VERSION, MAPPER_VERSION, DIMENSION_LIBRARY_ADAPTER_VERSION, request)
    return make_result(STATUS_OK, PRODUCT_TYPE, ENGINEERING_STATE_FINISHED, geometry, provenance, [SIMPLIFIED_WARNING])


def _tee(request, standard, size):
    try:
        dims, source = dl.get_buttweld_tee(standard, size)
    except dl.DimNotFound as e:
        return incomplete(str(e), PRODUCT_TYPE, request)
    geometry = {
        "type": "tee_branch",
        "features": [{"type": "tee_stub_assembly", "od_mm": dims["OD_mm"],
                      "run_ctoe_mm": dims["RunCtoE_mm"], "outlet_ctoe_mm": dims["OutletCtoE_mm"]}],
    }
    provenance = make_provenance(source, RULESET_VERSION, MAPPER_VERSION, DIMENSION_LIBRARY_ADAPTER_VERSION, request)
    return make_result(STATUS_OK, PRODUCT_TYPE, ENGINEERING_STATE_FINISHED, geometry, provenance, [SIMPLIFIED_WARNING])


def _cap(request, standard, size):
    try:
        dims, source = dl.get_buttweld_cap(standard, size)
    except dl.DimNotFound as e:
        return incomplete(str(e), PRODUCT_TYPE, request)
    geometry = {"type": "cap_end", "features": [{"type": "cap_stub", "od_mm": dims["OD_mm"], "length_mm": dims["Length_mm"]}]}
    provenance = make_provenance(source, RULESET_VERSION, MAPPER_VERSION, DIMENSION_LIBRARY_ADAPTER_VERSION, request)
    return make_result(STATUS_OK, PRODUCT_TYPE, ENGINEERING_STATE_FINISHED, geometry, provenance, [SIMPLIFIED_WARNING])
