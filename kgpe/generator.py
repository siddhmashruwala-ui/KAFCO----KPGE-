# -*- coding: utf-8 -*-
"""
KGPE main entry point. This is the one function external callers (CLI,
future REST API, a KFEE hand-off, the CRM dashboard's renderer) should use.

    from kgpe.generator import generate_geometry
    result = generate_geometry({"product_type": "flange", "standard": "ASME_B16.5",
                                 "size": "2", "class_key": "150", "pipe_schedule": "Sch40"})

`result["status"]` is always one of OK / GEOMETRY_DEFINITION_INCOMPLETE /
ENGINEERING_REVIEW_REQUIRED - callers must check it before touching
`result["geometry"]`.
"""
from .schema import incomplete
from .rules import flange, pipe, buttweld, olet

_DISPATCH = {
    "flange": flange.generate,
    "pipe": pipe.generate,
    "buttweld_fitting": buttweld.generate,
    "olet": olet.generate,
}


def generate_geometry(request: dict) -> dict:
    product_type = request.get("product_type")
    if product_type not in _DISPATCH:
        return incomplete(
            f"Unknown or missing 'product_type': {product_type!r}. Supported: {list(_DISPATCH)}",
            product_type, request,
        )
    return _DISPATCH[product_type](request)
