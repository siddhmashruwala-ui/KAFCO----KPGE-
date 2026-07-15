# -*- coding: utf-8 -*-
"""Smoke-test / demo for KGPE - run this after any change to verify nothing broke."""
import sys, os, json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from kgpe.generator import generate_geometry

REQUESTS = [
 {"product_type": "flange", "standard": "ASME_B16.5", "size": "2", "class_key": "150", "pipe_schedule": "Sch40"},
 {"product_type": "flange", "standard": "JIS_B2220", "size": 50, "class_key": "10K"},
 {"product_type": "flange", "standard": "EN_1092-1", "size": 50, "class_key": "PN16"},
 {"product_type": "flange", "standard": "ASME_B16.5", "size": "2", "class_key": "150"},  # missing pipe_schedule -> INCOMPLETE
 {"product_type": "pipe", "standard": "ASME_B36", "size": "6", "schedule": "Sch40"},
 {"product_type": "buttweld_fitting", "fitting_type": "elbow_90", "standard": "ASME_B16.9", "size": "6"},
 {"product_type": "buttweld_fitting", "fitting_type": "tee", "standard": "ASME_B16.9", "size": "4"},
 {"product_type": "buttweld_fitting", "fitting_type": "cap", "standard": "ASME_B16.9", "size": "4"},
 {"product_type": "olet", "standard": "MSS_SP97", "size": "2"},  # -> INCOMPLETE by design
]

for req in REQUESTS:
    r = generate_geometry(req)
    print("-" * 70)
    print("REQUEST:", req)
    print("STATUS: ", r["status"])
    if r["status"] == "OK":
        print("GEOMETRY:", json.dumps(r["geometry"], indent=None))
        print("PROVENANCE hash:", r["provenance"]["input_hash"])
    else:
        print("REASON:  ", r["error"])

# determinism check
r1 = generate_geometry(REQUESTS[0])
r2 = generate_geometry(REQUESTS[0])
same = r1["provenance"]["input_hash"] == r2["provenance"]["input_hash"] and r1["geometry"] == r2["geometry"]
print("=" * 70)
print("DETERMINISM CHECK (same input twice -> identical geometry+hash):", "PASS" if same else "FAIL")
