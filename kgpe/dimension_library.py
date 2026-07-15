# -*- coding: utf-8 -*-
"""
Dimension Library adapter/resolver for KGPE.

Reads the AI-Readable JSON files under 'Dimensions and Standards' (built
separately, standard by standard) and normalizes them into a small set of
canonical field names that the geometry rules (kgpe/rules/*.py) consume.

This module does ONE job: look up rows and translate column names. It does
NOT calculate anything and does NOT invent values that aren't in the source
file - if a field isn't present in the source, the normalized record simply
omits it, and the calling rule is responsible for deciding whether that's
fatal (GEOMETRY_DEFINITION_INCOMPLETE) or just a modeling simplification
(a warning).
"""
import json
import os
from .version import DIMENSION_LIBRARY_ADAPTER_VERSION

# Root of "Dimensions and Standards" - three levels up from this file
# (Engine/KGPE/kgpe/dimension_library.py -> Dimensions and Standards/)
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
DIMLIB_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", "..", "..", "AI-Readable"))

_CACHE = {}


def _load(rel_path):
    if rel_path not in _CACHE:
        full = os.path.join(DIMLIB_ROOT, rel_path)
        with open(full, "r", encoding="utf-8") as f:
            _CACHE[rel_path] = json.load(f)
    return _CACHE[rel_path]


# ---- registry: (standard_family, standard_id) -> relative JSON path ----
FLANGE_FILES = {
    "ASME_B16.5": "Flanges/ASME_B16.5_Flanges.json",
    "JIS_B2220": "Flanges/JIS_B2220_Flanges.json",
    "EN_1092-1": "Flanges/DIN_EN1092_Flanges.json",
}
PIPE_FILES = {
    "ASME_B36": "Pipes/ASME_B36.10M_B36.19M_Pipes.json",
    "JIS_G3452_3454_3459": "Pipes/JIS_G3452_G3454_G3459_Pipes.json",
    "EN_10216_10217": "Pipes/DIN_EN10216_10217_Pipes.json",
}
BUTTWELD_FILES = {
    "ASME_B16.9": "Buttweld/ASME_B16.9_Buttweld_Fittings.json",
    "JIS_B2311_2312": "Buttweld/JIS_B2311_B2312_Buttweld_Fittings.json",
    "EN_10253": "Buttweld/DIN_EN10253_Buttweld_Fittings.json",
}
SOCKETWELD_FILES = {"ASME_B16.11": "Socketweld/ASME_B16.11_Socketweld_Fittings.json"}
OLET_FILES = {"MSS_SP97": "Olets/MSS_SP97_Branch_Outlets.json"}


class DimNotFound(Exception):
    """Raised when a (standard, size, class) combination can't be resolved.
    Callers (rules) MUST turn this into GEOMETRY_DEFINITION_INCOMPLETE -
    never catch-and-guess."""
    pass


def get_flange(standard_id, size, class_key):
    """Returns (normalized_dict, source_info) or raises DimNotFound.
    size: NPS string for ASME (e.g. '2', '1-1/2') or DN/NPS_A number for JIS/EN.
    class_key: e.g. '150' (ASME), '10K' (JIS), 'PN16' (EN).
    """
    if standard_id not in FLANGE_FILES:
        raise DimNotFound(f"Unknown flange standard '{standard_id}'. Known: {list(FLANGE_FILES)}")
    rel = FLANGE_FILES[standard_id]
    data = _load(rel)

    if standard_id == "ASME_B16.5":
        rows = data.get("classes", {}).get(str(class_key))
        if not rows:
            raise DimNotFound(f"ASME_B16.5: class {class_key} not in dimension library")
        row = next((r for r in rows if str(r["NPS"]) == str(size)), None)
        if not row:
            raise DimNotFound(f"ASME_B16.5 class {class_key}: NPS {size} not in dimension library")
        norm = {
            "OD_mm": row["OD_mm"], "BoltCircle_mm": row["BoltCircle_mm"],
            "BoltHoleDia_mm": row["BoltHoleDia_mm"], "NumBolts": row["NumBolts"],
            "BoltSize": row["BoltSize_in"], "Thickness_mm": row["Thickness_WeldNeck_mm"],
            # NOT present in this source file - do not invent:
            "BoreID_mm": None, "RaisedFace_mm": None, "NeckOD_mm": None,
        }
        return norm, {"standard": f"ASME B16.5 Class {class_key}", "source_file": rel, "size_class": f"NPS{size}/{class_key}"}


    if standard_id == "JIS_B2220":
        rows = data.get("classes", {}).get(str(class_key))
        if not rows:
            raise DimNotFound(f"JIS_B2220: class {class_key} not in dimension library")
        row = next((r for r in rows if str(r["NPS_A_mm"]) == str(size)), None)
        if not row:
            raise DimNotFound(f"JIS_B2220 class {class_key}: size {size}A not in dimension library")
        norm = {
            "OD_mm": row["OD_mm"], "BoltCircle_mm": row["BoltCircle_mm"],
            "BoltHoleDia_mm": row["BoltHoleDia_mm"], "NumBolts": row["NumBolts"],
            "BoltSize": row["BoltSize"], "Thickness_mm": row["Thickness_mm"],
            "BoreID_mm": row["BoreID_mm"], "RaisedFace_mm": row["RaisedFace_mm"],
            "NeckOD_mm": row["PipeOD_mm"],
        }
        return norm, {"standard": f"JIS B2220 Class {class_key}", "source_file": rel, "size_class": f"{size}A/{class_key}"}

    if standard_id == "EN_1092-1":
        rows = data.get("pn_classes", {}).get(str(class_key))
        if not rows:
            raise DimNotFound(f"EN_1092-1: {class_key} not in dimension library")
        row = next((r for r in rows if str(r["DN"]) == str(size)), None)
        if not row:
            raise DimNotFound(f"EN_1092-1 {class_key}: DN{size} not in dimension library")
        norm = {
            "OD_mm": row["OD_mm"], "BoltCircle_mm": row["BoltCircle_mm"],
            "BoltHoleDia_mm": row["BoltHoleDia_mm"], "NumBolts": row["NumBolts"],
            "BoltSize": row["BoltSize"], "Thickness_mm": row["Thickness_mm"],
            "BoreID_mm": None, "RaisedFace_mm": None, "NeckOD_mm": None,
        }
        return norm, {"standard": f"EN 1092-1 {class_key}", "source_file": rel, "size_class": f"DN{size}/{class_key}"}

    raise DimNotFound(f"No adapter implemented for flange standard '{standard_id}'")


def get_pipe(standard_id, size, schedule_key):
    """schedule_key e.g. 'Sch40' (ASME/JIS) or 'Series3' (EN)."""
    if standard_id not in PIPE_FILES:
        raise DimNotFound(f"Unknown pipe standard '{standard_id}'. Known: {list(PIPE_FILES)}")
    rel = PIPE_FILES[standard_id]
    data = _load(rel)

    if standard_id == "ASME_B36":
        table = data.get("B36_10M_wall_thickness_mm", []) + data.get("B36_19M_wall_thickness_mm", [])
        row = next((r for r in table if str(r["NPS"]) == str(size)), None)
        if not row:
            raise DimNotFound(f"ASME_B36: NPS {size} not in dimension library")
        wt = row.get(schedule_key)
        if wt is None:
            raise DimNotFound(f"ASME_B36: NPS {size} has no {schedule_key} value (schedule not defined at this size)")
        norm = {"OD_mm": row["OD_mm"], "WallThickness_mm": wt, "BoreID_mm": round(row["OD_mm"] - 2 * wt, 3)}
        return norm, {"standard": f"ASME B36.10M/19M {schedule_key}", "source_file": rel, "size_class": f"NPS{size}/{schedule_key}"}

    if standard_id == "JIS_G3452_3454_3459":
        tables = data.get("tables", {})
        all_rows = []
        for t in tables.values():
            all_rows.extend(t.get("rows", []))
        row = next((r for r in all_rows if str(r.get("A_mm")) == str(size) and schedule_key in r and r[schedule_key] is not None), None)
        if not row:
            raise DimNotFound(f"JIS pipe: {size}A / {schedule_key} not in dimension library")
        wt = row[schedule_key]
        norm = {"OD_mm": row["OD_mm"], "WallThickness_mm": wt, "BoreID_mm": round(row["OD_mm"] - 2 * wt, 3)}
        return norm, {"standard": f"JIS pipe {schedule_key}", "source_file": rel, "size_class": f"{size}A/{schedule_key}"}

    if standard_id == "EN_10216_10217":
        rows = data.get("rows", [])
        row = next((r for r in rows if str(r["DN"]) == str(size)), None)
        if not row:
            raise DimNotFound(f"EN pipe: DN{size} not in dimension library")
        wt = row.get(schedule_key)
        if wt is None:
            raise DimNotFound(f"EN pipe: DN{size} has no {schedule_key} value")
        norm = {"OD_mm": row["OD_mm"], "WallThickness_mm": wt, "BoreID_mm": round(row["OD_mm"] - 2 * wt, 3)}
        return norm, {"standard": f"EN 10216/10217 {schedule_key}", "source_file": rel, "size_class": f"DN{size}/{schedule_key}"}

    raise DimNotFound(f"No adapter implemented for pipe standard '{standard_id}'")


def get_buttweld_elbow90(standard_id, size):
    if standard_id not in BUTTWELD_FILES:
        raise DimNotFound(f"Unknown buttweld standard '{standard_id}'")
    rel = BUTTWELD_FILES[standard_id]
    data = _load(rel)
    if standard_id == "ASME_B16.9":
        row = next((r for r in data["elbows_90_45_LR_3D"]["rows"] if str(r["NPS"]) == str(size)), None)
        if not row or row.get("Elbow90LR_CtoE_mm") is None:
            raise DimNotFound(f"ASME B16.9: 90deg LR elbow NPS{size} not in dimension library")
        norm = {"OD_mm": row["OD_mm"], "CtoE_mm": row["Elbow90LR_CtoE_mm"]}
        return norm, {"standard": "ASME B16.9 90deg LR Elbow", "source_file": rel, "size_class": f"NPS{size}"}
    if standard_id == "JIS_B2311_2312":
        row = next((r for r in data["fittings"]["elbow_90LR_and_45"]["rows"] if str(r["A_mm"]) == str(size)), None)
        if not row:
            raise DimNotFound(f"JIS buttweld: 90deg elbow {size}A not in dimension library")
        norm = {"OD_mm": row["OD_mm"], "CtoE_mm": row["Elbow90LR_CtoE_mm"]}
        return norm, {"standard": "JIS B2311/2312 90deg Elbow", "source_file": rel, "size_class": f"{size}A"}
    if standard_id == "EN_10253":
        row = next((r for r in data["fittings"]["elbow_90_180"]["rows"] if str(r["DN"]) == str(size)), None)
        if not row:
            raise DimNotFound(f"EN 10253: 90deg elbow DN{size} not in dimension library")
        norm = {"OD_mm": row["OD_mm"], "CtoE_mm": row["Elbow90_CtoE_mm"], "WallThickness_mm": row["WallThk_mm"]}
        return norm, {"standard": "EN 10253-2 90deg Elbow", "source_file": rel, "size_class": f"DN{size}"}
    raise DimNotFound(f"No elbow adapter for '{standard_id}'")


def get_buttweld_tee(standard_id, size):
    rel = BUTTWELD_FILES.get(standard_id)
    if not rel:
        raise DimNotFound(f"Unknown buttweld standard '{standard_id}'")
    data = _load(rel)
    if standard_id == "ASME_B16.9":
        row = next((r for r in data["tees_straight_equal"]["rows"] if str(r["NPS"]) == str(size)), None)
        if not row:
            raise DimNotFound(f"ASME B16.9: equal tee NPS{size} not in dimension library")
        norm = {"OD_mm": row["OD_mm"], "RunCtoE_mm": row["Run_CtoE_C_mm"], "OutletCtoE_mm": row["Outlet_CtoE_M_mm"]}
        return norm, {"standard": "ASME B16.9 Equal Tee", "source_file": rel, "size_class": f"NPS{size}"}
    if standard_id == "JIS_B2311_2312":
        row = next((r for r in data["fittings"]["equal_tee"]["rows"] if str(r["A_mm"]) == str(size)), None)
        if not row:
            raise DimNotFound(f"JIS buttweld: equal tee {size}A not in dimension library")
        norm = {"OD_mm": row["OD_mm"], "RunCtoE_mm": row["CtoE_mm"], "OutletCtoE_mm": row["CtoE_mm"]}
        return norm, {"standard": "JIS B2311/2312 Equal Tee", "source_file": rel, "size_class": f"{size}A"}
    if standard_id == "EN_10253":
        row = next((r for r in data["fittings"]["equal_tee"]["rows"] if str(r["DN"]) == str(size)), None)
        if not row:
            raise DimNotFound(f"EN 10253: equal tee DN{size} not in dimension library")
        norm = {"OD_mm": row["OD_mm"], "RunCtoE_mm": row["CtoE_mm"], "OutletCtoE_mm": row["CtoE_mm"], "WallThickness_mm": row["WallThk_mm"]}
        return norm, {"standard": "EN 10253-2 Equal Tee", "source_file": rel, "size_class": f"DN{size}"}
    raise DimNotFound(f"No tee adapter for '{standard_id}'")


def get_buttweld_cap(standard_id, size):
    rel = BUTTWELD_FILES.get(standard_id)
    if not rel:
        raise DimNotFound(f"Unknown buttweld standard '{standard_id}'")
    data = _load(rel)
    if standard_id == "ASME_B16.9":
        row = next((r for r in data["caps"]["rows"] if str(r["NPS"]) == str(size)), None)
        if not row:
            raise DimNotFound(f"ASME B16.9: cap NPS{size} not in dimension library")
        norm = {"OD_mm": row["OD_mm"], "Length_mm": row["Length_H_mm"]}
        return norm, {"standard": "ASME B16.9 Cap", "source_file": rel, "size_class": f"NPS{size}"}
    if standard_id == "JIS_B2311_2312":
        row = next((r for r in data["fittings"]["cap"]["rows"] if str(r["A_mm"]) == str(size)), None)
        if not row:
            raise DimNotFound(f"JIS buttweld: cap {size}A not in dimension library")
        norm = {"OD_mm": row["OD_mm"], "Length_mm": row["EndToEnd_mm"]}
        return norm, {"standard": "JIS B2311/2312 Cap", "source_file": rel, "size_class": f"{size}A"}
    if standard_id == "EN_10253":
        row = next((r for r in data["fittings"]["cap"]["rows"] if str(r["DN"]) == str(size)), None)
        if not row:
            raise DimNotFound(f"EN 10253: cap DN{size} not in dimension library")
        norm = {"OD_mm": row["OD_mm"], "Length_mm": row["Height_mm"]}
        return norm, {"standard": "EN 10253-2 / DIN 2617 Cap", "source_file": rel, "size_class": f"DN{size}"}
    raise DimNotFound(f"No cap adapter for '{standard_id}'")
