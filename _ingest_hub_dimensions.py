# -*- coding: utf-8 -*-
"""
_ingest_hub_dimensions.py
=============================
Prompt 42: one-off, documented merge script that adds hub geometry data
to the canonical ASME B16.5 flange source JSON - kept in the repo
permanently as the provenance record for how these numbers got there
(same pattern as _ingest_new_flange_types.py from Prompt 41).

WHY: KGPE modeled weld-neck flange bodies as flat plates only (Prompt 14
Sec.21-22, "hub geometry has zero facts for any standard and is never
attempted") - a genuine, previously-documented data gap. This script
closes it for ASME_B16.5 weld_neck flanges (the only standard/subtype
where a verified source was found), and additionally ingests the ASME
B16.5 "Long Weld Neck" (LWN) variant, which is NOT a separately-tabulated
ASME B16.5 flange type - it is a standard weld-neck flange with IDENTICAL
body/hub-diameter dimensions, differing ONLY in length-through-hub (fixed
at 229mm for NPS<=4, 305mm for NPS>4, regardless of pressure class).

SOURCES (two independent, explicitly-labeled, cross-verified):
  1. Texas Flange (texasflange.com) - ANSI B16.5 Class 150/300/400/600/
     900/1500/2500 Forged Flanges pages. Column "X" = diameter of hub at
     base; column "L2" = length through hub (unlabeled by letter on the
     page itself, but numerically identified - see cross-check below).
     Already an established, previously-verified source for this project
     (Prompt 41 used its T/TJ columns).
  2. pipingpipeline.com - ASME B16.5 Welding Neck Flange Class 150/300
     pages, EXPLICITLY labeled: "Y: length through hub; X: diameter of
     hub at base; A: diameter of hub at top welding point."

CROSS-CHECK (0 mismatches, Class 150 NPS 1/2/4 + Class 300 NPS 2/4):
  Class150 NPS1:  pipingpipeline X=49mm,  Y=54mm  | TexasFlange X=1.94in
                  (=49.28mm), L2=2.12in (=53.85mm)  -> MATCH
  Class150 NPS2:  pipingpipeline X=78mm,  Y=62mm  | TexasFlange X=3.06in
                  (=77.72mm), L2=2.44in (=61.98mm)  -> MATCH
  Class150 NPS4:  pipingpipeline X=135mm, Y=75mm  | TexasFlange X=5.31in
                  (=134.87mm), L2=2.94in (=74.68mm) -> MATCH
  Class300 NPS2:  pipingpipeline X=84mm,  Y=68mm  | TexasFlange X=3.31in
                  (=84.07mm), L2=2.69in (=68.33mm)  -> MATCH
  Class300 NPS4:  pipingpipeline X=146mm, Y=84mm  | TexasFlange X=5.75in
                  (=146.05mm), L2=3.32in (=84.33mm) -> MATCH
  This confirms Texas Flange's "X" = hub base diameter and "L2" = length
  through hub (both letters used identically by pipingpipeline.com,
  though Texas Flange's page does not spell out the L2 letter meaning
  itself - the numeric match across both independent sources is the
  actual verification, not the letter label).

Texas Flange's "H" column and pipingpipeline's "A" column both track a
THIRD dimension - hub diameter at the point of welding (roughly the
mating pipe OD) - confirmed equal to each other numerically too, but NOT
ingested here: it is not needed for the straight-cylinder hub
simplification this prompt uses (see kgpe/geometry/products/flange.py's
module docstring for that simplification's rationale).

LONG WELD NECK (LWN) override rule - confirmed via pipingpipeline.com's
own dedicated LWN page (explicit quote: "The LWN flanges shall have
dimensions and tolerances of the standard welding neck flanges of the
same size and class, except that the length through hub shall be 229 mm
(9-inch) for NPS 4 and smaller and 305 mm (12-inch) for larger than NPS
4") and independently corroborated by semetalgroup.com, steeljrv.com,
dynamicforgefittings.com, and piping-designer.com (all stating the same
229mm/305mm rule, unprompted, in the same search pass) - X (hub base
diameter) is explicitly confirmed UNCHANGED between weld_neck and LWN.

Class 900/1500 NPS 1/2-2-1/2 identical-to-Class-1500 rule (already
established in Prompt 41) is preserved here too - those rows literally
reuse Class 1500's own X/Y values, not re-sourced separately.

DISCLOSED CONFLICT (Y only, X unaffected): the KAFCO CRM dashboard's own
pre-existing `HUB_DIM` JS table (KAFCO_CRM_Dashboard.html, a legacy
client-side hub-rendering heuristic, unrelated to this ingestion) and
wermac.org's per-NPS "H" column BOTH report Y values consistently ~0.06in
(~1.5mm) HIGHER than Texas Flange/pipingpipeline for the same NPS/class
(e.g. Class 300 NPS 2: CRM/wermac ~2.75in vs Texas Flange/pipingpipeline
2.69in - a delta matching ASME B16.5's own published raised-face height
for Class 150-600, ~1.6mm). This strongly suggests a real, understood
measurement-convention difference (Y measured to the back of the raised
face vs. to the flat gasket-seating plane beneath it), not a data error
on either side. This script uses Texas Flange/pipingpipeline's values
(the flat-plane convention) because: (1) two independently-labeled
sources agree with each other to sub-mm precision across every
spot-checked NPS/class, vs. one single legacy JS table and one
third-party aggregator; (2) this convention keeps Y measured to the SAME
reference plane as the already-canonical flange_thickness_weld_neck_mm
("T"), which is the geometrically consistent choice for a flat-plate-
plus-hub solid model (Y and T stacking cleanly along the same axis with
no unaccounted RF-height gap). Flagged here rather than silently
resolved, per this project's standing disclosure discipline.
"""
import json

SRC = r"C:\Users\admin\Desktop\Dimensions and Standards\AI-Readable\Flanges\ASME_B16.5_Flanges.json"

IN_TO_MM = 25.4


def mm(inches):
    return round(inches * IN_TO_MM, 2)


# Hub base diameter (X) and length-through-hub (Y), both in INCHES as
# published by Texas Flange, keyed by class -> NPS -> (X_in, Y_in).
# NPS ordering matches each class's existing row order in the source JSON
# exactly (confirmed live before writing this script).
_HUB_IN = {
    "150": {
        "1/2": (1.19, 1.81), "3/4": (1.50, 2.00), "1": (1.94, 2.12), "1-1/4": (2.31, 2.19),
        "1-1/2": (2.56, 2.38), "2": (3.06, 2.44), "2-1/2": (3.56, 2.69), "3": (4.25, 2.69),
        "3-1/2": (4.81, 2.75), "4": (5.31, 2.94), "5": (6.44, 3.44), "6": (7.56, 3.44),
        "8": (9.69, 3.94), "10": (12.00, 3.94), "12": (14.38, 4.44), "14": (15.75, 4.94),
        "16": (18.00, 4.94), "18": (19.88, 5.44), "20": (22.00, 5.62), "24": (26.12, 5.94),
    },
    "300": {
        "1/2": (1.50, 2.00), "3/4": (1.88, 2.19), "1": (2.12, 2.38), "1-1/4": (2.50, 2.50),
        "1-1/2": (2.75, 2.63), "2": (3.31, 2.69), "2-1/2": (3.94, 2.94), "3": (4.62, 3.06),
        "3-1/2": (5.25, 3.13), "4": (5.75, 3.32), "5": (7.00, 3.82), "6": (8.12, 3.82),
        "8": (10.25, 4.32), "10": (12.62, 4.56), "12": (14.75, 5.06), "14": (16.75, 5.56),
        "16": (19.00, 5.69), "18": (21.00, 6.19), "20": (23.12, 6.32), "24": (27.62, 6.56),
    },
    "400": {
        "1/2": (1.5, 2.06), "3/4": (1.88, 2.25), "1": (2.12, 2.44), "1-1/4": (2.5, 2.62),
        "1-1/2": (2.75, 2.75), "2": (3.31, 2.88), "2-1/2": (3.94, 3.12), "3": (4.62, 3.25),
        "3-1/2": (5.25, 3.38), "4": (5.75, 3.5), "5": (7.00, 4.00), "6": (8.12, 4.06),
        "8": (10.25, 4.62), "10": (12.62, 4.88), "12": (14.75, 5.38), "14": (16.75, 5.88),
        "16": (19.00, 6.00), "18": (21.00, 6.50), "20": (23.12, 6.62), "24": (27.62, 6.88),
    },
    "600": {
        "1/2": (1.5, 2.06), "3/4": (1.88, 2.25), "1": (2.12, 2.44), "1-1/4": (2.5, 2.62),
        "1-1/2": (2.75, 2.75), "2": (3.31, 2.88), "2-1/2": (3.94, 3.12), "3": (4.62, 3.25),
        "3-1/2": (5.25, 3.38), "4": (6.00, 4.00), "5": (7.44, 4.50), "6": (8.75, 4.62),
        "8": (10.75, 5.25), "10": (13.5, 6.00), "12": (15.75, 6.12), "14": (17.00, 6.50),
        "16": (19.5, 7.00), "18": (21.5, 7.25), "20": (24.00, 7.50), "24": (28.25, 8.00),
    },
    # NPS 1/2-2-1/2 identical to Class 1500 (established Prompt 41 rule) -
    # own table only starts at NPS 3.
    "900": {
        "3": (5.00, 4.00), "4": (6.25, 4.50), "5": (7.50, 5.00), "6": (9.25, 5.50),
        "8": (11.75, 6.38), "10": (14.50, 7.25), "12": (16.50, 7.88), "14": (17.75, 8.38),
        "16": (20.00, 8.50), "18": (22.25, 9.00), "20": (24.50, 9.75), "24": (29.50, 11.50),
    },
    "1500": {
        "1/2": (1.5, 2.38), "3/4": (1.75, 2.75), "1": (2.06, 2.88), "1-1/4": (2.5, 2.88),
        "1-1/2": (2.75, 3.25), "2": (4.12, 4.00), "2-1/2": (4.88, 4.12), "3": (5.25, 4.62),
        "4": (6.38, 4.88), "5": (7.75, 6.12), "6": (9.00, 6.75), "8": (11.5, 8.38),
        "10": (14.5, 10.00), "12": (17.75, 11.12), "14": (19.5, 11.75), "16": (21.75, 12.25),
        "18": (23.5, 12.88), "20": (25.25, 14.00), "24": (30.00, 16.00),
    },
    "2500": {
        "1/2": (1.69, 2.88), "3/4": (2.00, 3.12), "1": (2.25, 3.5), "1-1/4": (2.88, 3.75),
        "1-1/2": (3.12, 4.38), "2": (3.75, 5.00), "2-1/2": (4.5, 5.62), "3": (5.25, 6.62),
        "4": (6.5, 7.5), "5": (8.00, 9.00), "6": (9.25, 10.75), "8": (12.00, 12.5),
        "10": (14.75, 16.5), "12": (17.38, 18.25),
    },
}
# Class 900 NPS 1/2-2-1/2 == Class 1500's own values (source: Texas
# Flange's explicit "Sizes 1/2 through 2-1/2 are identical to class 1500"
# note on the Class 900 page).
for _nps in ("1/2", "3/4", "1", "1-1/4", "1-1/2", "2", "2-1/2"):
    _HUB_IN["900"][_nps] = _HUB_IN["1500"][_nps]


def lwn_length_through_hub_mm(nps):
    """Sec. LWN override: 229mm (9in) for NPS<=4, 305mm (12in) for
    NPS>4 - independent of pressure class, per pipingpipeline.com's own
    LWN page (cross-corroborated by 4 other independent sources)."""
    _le_4 = {"1/2", "3/4", "1", "1-1/4", "1-1/2", "2", "2-1/2", "3", "3-1/2", "4"}
    return 229.0 if nps in _le_4 else 305.0


def main():
    with open(SRC, "r", encoding="utf-8") as f:
        data = json.load(f)
    counts = {"hub_base_diameter": 0, "length_through_hub_weld_neck": 0,
              "length_through_hub_long_weld_neck": 0}
    for class_key, rows in data["classes"].items():
        table = _HUB_IN.get(class_key, {})
        for row in rows:
            nps = row["NPS"]
            if nps not in table:
                continue
            x_in, y_in = table[nps]
            row["HubBaseDiameter_mm"] = mm(x_in)
            row["LengthThroughHub_WeldNeck_mm"] = mm(y_in)
            row["LengthThroughHub_LongWeldNeck_mm"] = lwn_length_through_hub_mm(nps)
            counts["hub_base_diameter"] += 1
            counts["length_through_hub_weld_neck"] += 1
            counts["length_through_hub_long_weld_neck"] += 1
    with open(SRC, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    print("Merge complete:", counts)


if __name__ == "__main__":
    main()
