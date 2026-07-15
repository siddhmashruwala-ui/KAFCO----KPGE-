# -*- coding: utf-8 -*-
"""Pipe geometry rule - a plain annular cylinder. Pipe length is a cut-to-
order commercial parameter, not an engineering dimension in the standard,
so it is never invented as if it were real - if not supplied, a clearly
labeled visualization-only placeholder length is used."""
from .. import dimension_library as dl
from ..schema import make_result, make_provenance, incomplete, STATUS_OK, ENGINEERING_STATE_FINISHED
from ..version import RULESET_VERSION, MAPPER_VERSION, DIMENSION_LIBRARY_ADAPTER_VERSION

PRODUCT_TYPE = "pipe"


def generate(request):
    standard = request.get("standard")
    size = request.get("size")
    schedule = request.get("schedule")
    length_mm = request.get("length_mm")

    if not (standard and size is not None and schedule):
        return incomplete("pipe request requires 'standard', 'size', and 'schedule'", PRODUCT_TYPE, request)
    try:
        dims, source = dl.get_pipe(standard, size, schedule)
    except dl.DimNotFound as e:
        return incomplete(str(e), PRODUCT_TYPE, request)

    warnings = []
    if length_mm is None:
        length_mm = round(max(500.0, dims["OD_mm"] * 5), 1)
        warnings.append(f"No 'length_mm' given - using a VISUALIZATION-ONLY placeholder length of "
                         f"{length_mm}mm. This is not a real cut length; pass length_mm explicitly for a real order.")

    geometry = {
        "type": "annular_cylinder",
        "outside_dia_mm": dims["OD_mm"], "inside_dia_mm": dims["BoreID_mm"],
        "wall_thickness_mm": dims["WallThickness_mm"], "length_mm": length_mm,
    }
    provenance = make_provenance(source, RULESET_VERSION, MAPPER_VERSION, DIMENSION_LIBRARY_ADAPTER_VERSION, request)
    return make_result(STATUS_OK, PRODUCT_TYPE, ENGINEERING_STATE_FINISHED, geometry, provenance, warnings)
