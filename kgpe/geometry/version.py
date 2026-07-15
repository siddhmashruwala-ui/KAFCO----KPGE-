# -*- coding: utf-8 -*-
"""
kgpe.geometry.version
=========================
Prompt 12 Sec.33: explicit, simple, deterministic version identifiers for
the new geometry kernel. Bump deliberately (never silently) when the
corresponding logic changes - each version rides along in every
`GeometryResult` so a previously-generated result can be identified as
possibly stale.

These are INDEPENDENT of kgpe/version.py (the legacy generator's own
versions, Prompt 1-3) - the new kernel is additive, not a replacement,
and must never be confused with the legacy ruleset/mapper versions.
"""

GEOMETRY_RESULT_SCHEMA_VERSION = "geometry-result-schema-2026.07.15"
GEOMETRY_KERNEL_VERSION = "geometry-kernel-2026.07.15"
GENERATION_PARAMETER_SCHEMA_VERSION = "generation-parameters-schema-2026.07.15"

# Individual construction-rule versions live on each rule object itself
# (Sec.12 - "rule identifier; rule version" per rule), not centralized here.
