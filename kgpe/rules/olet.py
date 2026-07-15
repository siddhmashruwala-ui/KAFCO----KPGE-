# -*- coding: utf-8 -*-
"""
Olet (branch outlet fitting) geometry - NOT YET IMPLEMENTED.

Per the architecture spec: "If required geometry information is missing,
ambiguous, or unsupported, KGPE must return a structured result such as
GEOMETRY_DEFINITION_INCOMPLETE... rather than silently creating a plausible
but potentially incorrect shape."

Olet branch-intersection geometry (the saddle/hole cut into the run pipe,
the branch stub, the reinforcement contour) is genuinely more complex than
a flange/pipe/elbow primitive, AND the MSS SP-97 standard itself does not
fully specify body geometry (see Dimension Library notes in
Olets/MSS_SP97_Branch_Outlets.json) - manufacturer body dimensions exist
but a true intersection geometry rule has not been designed yet. Rather
than approximate, this returns INCOMPLETE every time until a real rule
is written and reviewed.
"""
from ..schema import incomplete

PRODUCT_TYPE = "olet"


def generate(request):
    return incomplete(
        "Olet geometry is not yet implemented in KGPE. The MSS SP-97 standard does not fully "
        "specify body/branch-intersection geometry, and no reviewed geometry rule exists yet for "
        "this fitting family. Returning GEOMETRY_DEFINITION_INCOMPLETE rather than guessing.",
        PRODUCT_TYPE, request,
    )
