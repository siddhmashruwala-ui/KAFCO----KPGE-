# -*- coding: utf-8 -*-
"""
kgpe.geometry_spec.fingerprint
==================================
Prompt 11 Sec.17: deterministic geometry-specification fingerprint.

PARTICIPATES in the fingerprint: schema version, engineering object
identity (all populated fields), every included required/optional
dimension's name+value+unit+verification_status, manufacturer context,
the data-layer fingerprint it was compiled against, and the geometry
profile id+version.

EXCLUDED: timestamps, object memory addresses, dict-insertion accidents
(json.dumps(..., sort_keys=True) neutralizes this), non-deterministic
trace ordering (the trace itself never participates at all).

Same resolved spec + same profile -> same fingerprint. A meaningful
dimension change -> a different fingerprint. Reuses the exact SHA-256/
sort_keys discipline already established in kgpe.schema._input_hash and
kgpe.contract.snapshot.registry_fingerprint.
"""
import hashlib
import json

GEOMETRY_SPEC_SCHEMA_VERSION = "geometry-spec-schema-2026.07.15"


def _bundle_payload(bundle):
    if bundle is None:
        return {}
    return {
        name: {"value": d.value, "unit": d.unit, "verification_status": d.verification_status}
        for name, d in bundle.dimensions.items()
    }


def compute_geometry_specification_fingerprint(schema_version, identity, required_bundle, optional_bundle,
                                                data_layer_fingerprint, profile_id, profile_version):
    payload = {
        "schema_version": schema_version,
        "identity": identity.as_dict() if identity else None,
        "required_dimensions": _bundle_payload(required_bundle),
        "optional_dimensions": _bundle_payload(optional_bundle),
        "manufacturer_profile": identity.manufacturer_profile if identity else None,
        "data_layer_fingerprint": data_layer_fingerprint,
        "geometry_profile_id": profile_id,
        "geometry_profile_version": profile_version,
    }
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()
