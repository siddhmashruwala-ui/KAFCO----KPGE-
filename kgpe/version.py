# -*- coding: utf-8 -*-
"""
Version identifiers for KGPE (KAFCO Geometry & Parametric Engine).

Every geometry result KGPE produces carries these versions in its
provenance block. Per the architecture spec: "The same input dimensions,
geometry ruleset version, product mapper version, and configuration
version must always generate the same geometric definition."

Bump these deliberately (not silently) whenever the corresponding logic
changes, so downstream consumers (CAD/3D/ERP/MES) can detect when a
previously-generated geometry may need to be regenerated.
"""

KGPE_VERSION = "0.1.0"

# Bumps when a geometry rule (flange.py, pipe.py, buttweld.py, olet.py) changes
RULESET_VERSION = "ruleset-2026.07.14"

# Bumps when the mapping from a Dimension Library row -> rule input fields changes
MAPPER_VERSION = "mapper-2026.07.14"

# Bumps when dimension_library.py's file layout/loading logic changes
DIMENSION_LIBRARY_ADAPTER_VERSION = "dimlib-adapter-2026.07.14"
