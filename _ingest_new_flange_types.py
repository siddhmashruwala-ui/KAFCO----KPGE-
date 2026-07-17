# -*- coding: utf-8 -*-
"""
One-off merge script (KGPE Prompt 41): adds Slip-On/Threaded/Socket-Weld/
Lap-Joint/Blind thickness data to the existing ASME B16.5 flange JSON.

Sources:
  - TJ_IN: Texas Flange combined per-class dimension tables
    (texasflange.com/products/flange-dims-weights/ansi-b16-5-forged-flanges/
    class-*), fetched 2026-07-16. TJ = shared Slip-On/Threaded/Socket-Weld/
    Lap-Joint thickness at Class 150/300 (distinct from weld-neck T at
    those two classes only). At Class 400+ ASME B16.5 uses a single T
    shared by weld-neck AND all other non-blind types - confirmed no
    separate TJ column exists there. TJ cross-verified 2026-07-16 against
    Ferrobend's Class 150 Slip-On page - 0 mismatches across 4 spot-checked
    sizes (NPS 1/2, 4, 10, 24).
  - THR_IN: Texas Flange 'Thr' column - a size is treated as offering a
    Threaded variant only where this column has a real value.
  - Socket-Weld capped at NPS 4 and below in every class, per the
    well-established ASME B16.5 convention that socket-weld is a
    small-bore method - applied even where Texas Flange's 'D' (socket
    depth) column showed values beyond NPS 4 at Class 150/300, since that
    continuation could not be independently corroborated and is
    inconsistent with standard socket-weld practice.
  - TYPE_AVAILABLE_BY_CLASS: read directly from the flange-type icon list
    Texas Flange displays per class page (Class 900 omits Socket-Weld;
    Class 2500 omits Slip-On and Socket-Weld; all others list all 6).
  - BLIND_C_MM: htpipe.com's Blind Flange page, explicitly labeled
    "C = Minimum Flange Thickness", citing ASME B16.5-2022 Tables 1.1-1
    through 1.1-7, fetched 2026-07-16. The ONLY source of 4 candidates
    checked (Texas Flange's own 'C' column, Ferrobend, HardHat Engineer,
    htpipe.com) that was internally consistent (thickness plateaus across
    adjacent small sizes before stepping up - the expected real ASME
    B16.5 pattern) and monotonic with pressure class. The other three were
    rejected: Texas Flange's 'C' is IDENTICAL across all 7 classes for a
    given NPS (impossible for a pressure-rated thickness); Ferrobend's
    Class 150 'Blind' page is byte-identical to its own Class 150 Slip-On
    page, and its Class 1500 'Blind' page duplicates weld-neck thickness
    (templating bugs); HardHat Engineer disagrees with htpipe.com by up to
    ~30% at small sizes and shows an implausibly smooth per-size increase.
    Blind flange thickness is therefore SINGLE-SOURCED here (flagged in
    the per-fact verification note) - a documented deviation from the
    project's normal two-source discipline, made after three alternate
    sources were checked and each independently disqualified, per
    explicit user direction ("do what's right").
  - Class 900 NPS 1/2-2-1/2 Threaded values reuse Class 1500's (ASME
    B16.5 states Class 900 at these sizes is dimensionally identical to
    Class 1500).
"""
import json

SRC = r"C:\Users\admin\Desktop\Dimensions and Standards\AI-Readable\Flanges\ASME_B16.5_Flanges.json"

IN2MM = 25.4
def mm(inches):
    return round(inches * IN2MM, 2)

# TJ (inches): shared Slip-On/Threaded/Socket-Weld/Lap-Joint thickness,
# Class 150 and 300 only (Texas Flange 'TJ' column).
TJ_IN = {
    "150": {
        "1/2": 0.44, "3/4": 0.50, "1": 0.56, "1-1/4": 0.62, "1-1/2": 0.69,
        "2": 0.75, "2-1/2": 0.88, "3": 0.94, "3-1/2": 0.94, "4": 0.94,
        "5": 0.94, "6": 1.00, "8": 1.12, "10": 1.19, "12": 1.25,
        "14": 1.38, "16": 1.44, "18": 1.56, "20": 1.69, "24": 1.88,
    },
    "300": {
        "1/2": 0.56, "3/4": 0.62, "1": 0.69, "1-1/4": 0.75, "1-1/2": 0.81,
        "2": 0.88, "2-1/2": 1.00, "3": 1.12, "3-1/2": 1.19, "4": 1.25,
        "5": 1.38, "6": 1.44, "8": 1.62, "10": 1.88, "12": 2.00,
        "14": 2.12, "16": 2.25, "18": 2.38, "20": 2.50, "24": 2.75,
    },
}

# Threaded thickness (inches), Texas Flange 'Thr' column - only where a
# real (non-blank) value is present in the source table for that class/NPS.
THR_IN = {
    "150": {
        "1/2": 0.62, "3/4": 0.62, "1": 0.69, "1-1/4": 0.81, "1-1/2": 0.88,
        "2": 1.00, "2-1/2": 1.12, "3": 1.19, "3-1/2": 1.25, "4": 1.31,
        "5": 1.44, "6": 1.56, "8": 1.75, "10": 1.94, "12": 2.19,
        "14": 2.25, "16": 2.50, "18": 2.69, "20": 2.88, "22": 3.13, "24": 3.25,
    },
    "300": {
        "1/2": 0.62, "3/4": 0.62, "1": 0.69, "1-1/4": 0.81, "1-1/2": 0.88,
        "2": 1.12, "2-1/2": 1.25, "3": 1.25, "3-1/2": 1.44, "4": 1.44,
        "5": 1.69, "6": 1.81, "8": 2.00, "10": 2.19, "12": 2.38,
        "14": 2.50, "16": 2.69, "18": 2.75, "20": 2.88, "22": 3.13, "24": 3.25,
    },
    "400": {
        "1/2": 0.62, "3/4": 0.62, "1": 0.69, "1-1/4": 0.81, "1-1/2": 0.88,
        "2": 1.12, "2-1/2": 1.25, "3": 1.38, "3-1/2": 1.56, "4": 1.44,
        "5": 1.69, "6": 1.81, "8": 2.00, "10": 2.19, "12": 2.38,
        "14": 2.50, "16": 2.69, "18": 2.75, "20": 2.88, "24": 3.25,
    },
    "600": {
        "1/2": 0.62, "3/4": 0.62, "1": 0.69, "1-1/4": 0.81, "1-1/2": 0.88,
        "2": 1.12, "2-1/2": 1.25, "3": 1.38, "3-1/2": 1.56, "4": 1.62,
        "5": 1.88, "6": 2.00, "8": 2.25, "10": 2.56, "12": 2.75,
        "14": 2.88, "16": 3.06, "18": 3.12, "20": 3.25, "24": 3.62,
    },
    "900": {
        "3": 1.62, "4": 1.88, "5": 2.12, "6": 2.25, "8": 2.50, "10": 2.81,
        "12": 3.00, "14": 3.25, "16": 3.38, "18": 3.50, "20": 3.62, "24": 4.00,
        # NPS 1/2-2-1/2 borrowed from Class 1500 (documented "identical" rule)
        "1/2": 0.88, "3/4": 1.00, "1": 1.12, "1-1/4": 1.19, "1-1/2": 1.25, "2": 1.50, "2-1/2": 1.88,
    },
    "1500": {
        "1/2": 0.88, "3/4": 1.00, "1": 1.12, "1-1/4": 1.19, "1-1/2": 1.25, "2": 1.50, "2-1/2": 1.88,
    },
    "2500": {
        "1/2": 1.12, "3/4": 1.25, "1": 1.38, "1-1/4": 1.50, "1-1/2": 1.75, "2": 2.00, "2-1/2": 2.25,
    },
}

# Socket-Weld thickness (inches), Texas Flange 'D' column, capped at NPS 4.
SW_IN = {
    "150": {
        "1/2": 0.38, "3/4": 0.44, "1": 0.50, "1-1/4": 0.56, "1-1/2": 0.62,
        "2": 0.69, "2-1/2": 0.75, "3": 0.81, "3-1/2": 0.88, "4": 0.94,
    },
    "300": {
        "1/2": 0.38, "3/4": 0.44, "1": 0.50, "1-1/4": 0.56, "1-1/2": 0.62,
        "2": 0.69, "2-1/2": 0.75, "3": 0.81,
    },
    "400": {
        "1/2": 0.38, "3/4": 0.44, "1": 0.50, "1-1/4": 0.56, "1-1/2": 0.62,
        "2": 0.69, "2-1/2": 0.75,
    },
    "600": {
        "1/2": 0.38, "3/4": 0.44, "1": 0.50, "1-1/4": 0.56, "1-1/2": 0.62,
        "2": 0.69, "2-1/2": 0.75,
    },
    "1500": {
        "1/2": 0.38, "3/4": 0.44, "1": 0.50, "1-1/4": 0.56, "1-1/2": 0.62,
        "2": 0.69, "2-1/2": 0.75,
    },
}

# Blind flange minimum thickness "C" (mm, direct - htpipe.com already
# publishes in mm, no inch conversion needed/wanted here).
BLIND_C_MM = {
    "150": {
        "1/2": 9.6, "3/4": 9.6, "1": 9.6, "1-1/4": 9.6, "1-1/2": 9.6,
        "2": 12.7, "2-1/2": 12.7, "3": 12.7, "3-1/2": 12.7, "4": 12.7,
        "5": 12.7, "6": 12.7, "8": 14.3, "10": 17.5, "12": 17.5,
        "14": 20.6, "16": 20.6, "18": 20.6, "20": 20.6, "24": 20.6,
    },
    "300": {
        "1/2": 9.6, "3/4": 9.6, "1": 9.6, "1-1/4": 9.6, "1-1/2": 12.7,
        "2": 12.7, "2-1/2": 12.7, "3": 12.7, "3-1/2": 14.3, "4": 14.3,
        "5": 17.5, "6": 17.5, "8": 20.6, "10": 22.3, "12": 22.3,
        "14": 25.4, "16": 28.6, "18": 31.8, "20": 31.8, "24": 38.1,
    },
    "400": {
        "1/2": 9.6, "3/4": 9.6, "1": 9.6, "1-1/4": 9.6, "1-1/2": 12.7,
        "2": 12.7, "2-1/2": 12.7, "3": 12.7, "3-1/2": 14.3, "4": 14.3,
        "5": 17.5, "6": 17.5, "8": 20.6, "10": 22.3, "12": 22.3,
        "14": 25.4, "16": 28.6, "18": 31.8, "20": 31.8, "24": 38.1,
    },
    "600": {
        "1/2": 9.6, "3/4": 12.7, "1": 12.7, "1-1/4": 12.7, "1-1/2": 12.7,
        "2": 12.7, "2-1/2": 14.3, "3": 14.3, "3-1/2": 17.5, "4": 17.5,
        "5": 20.6, "6": 22.3, "8": 25.4, "10": 28.6, "12": 28.6,
        "14": 31.8, "16": 34.9, "18": 41.3, "20": 41.3, "24": 47.7,
    },
    "900": {
        "1/2": 12.7, "3/4": 12.7, "1": 12.7, "1-1/4": 12.7, "1-1/2": 12.7,
        "2": 14.3, "2-1/2": 17.5, "3": 17.5, "4": 31.8, "5": 34.9,
        "6": 34.9, "8": 41.3, "10": 47.7, "12": 50.8, "14": 50.8,
        "16": 53.2, "18": 60.3, "20": 66.7, "24": 79.4,
    },
    "1500": {
        "1/2": 12.7, "3/4": 12.7, "1": 12.7, "1-1/4": 12.7, "1-1/2": 12.7,
        "2": 14.3, "2-1/2": 17.5, "3": 22.3, "4": 28.6, "5": 34.9,
        "6": 41.3, "8": 47.7, "10": 57.2, "12": 63.5, "14": 66.7,
        "16": 73.2, "18": 79.4, "20": 85.8, "24": 98.5,
    },
    "2500": {
        "1/2": 17.5, "3/4": 17.5, "1": 20.6, "1-1/4": 20.6, "1-1/2": 22.3,
        "2": 22.3, "2-1/2": 25.4, "3": 28.6, "4": 34.9, "5": 41.3,
        "6": 47.7, "8": 53.2, "10": 66.7, "12": 76.2,
    },
}

# Class 900 explicitly omits Socket-Weld (no icon on the source page);
# Class 2500 omits both Slip-On and Socket-Weld.
SLIP_ON_AVAILABLE_CLASSES = {"150", "300", "400", "600", "900", "1500"}
LAP_JOINT_AVAILABLE_CLASSES = {"150", "300", "400", "600", "900", "1500", "2500"}

def shared_thickness_mm(class_key, nps, wn_mm):
    """Slip-On/Threaded/Socket-Weld/Lap-Joint thickness: the distinct TJ
    value at Class 150/300, else identical to weld-neck's own T (no
    separate column exists at Class 400+)."""
    tj = TJ_IN.get(class_key, {}).get(nps)
    return mm(tj) if tj is not None else wn_mm


def main():
    with open(SRC, "r", encoding="utf-8") as f:
        data = json.load(f)

    counts = {"slip_on": 0, "lap_joint": 0, "threaded": 0, "socket_weld": 0, "blind": 0}
    for class_key, rows in data["classes"].items():
        for row in rows:
            nps = row["NPS"]
            wn_mm = row["Thickness_WeldNeck_mm"]
            shared = shared_thickness_mm(class_key, nps, wn_mm)

            if class_key in SLIP_ON_AVAILABLE_CLASSES:
                row["Thickness_SlipOn_mm"] = shared
                counts["slip_on"] += 1
            if class_key in LAP_JOINT_AVAILABLE_CLASSES:
                row["Thickness_LapJoint_mm"] = shared
                counts["lap_joint"] += 1
            if nps in THR_IN.get(class_key, {}):
                row["Thickness_Threaded_mm"] = shared
                counts["threaded"] += 1
            if nps in SW_IN.get(class_key, {}):
                row["Thickness_SocketWeld_mm"] = shared
                counts["socket_weld"] += 1
            if nps in BLIND_C_MM.get(class_key, {}):
                row["Thickness_Blind_mm"] = BLIND_C_MM[class_key][nps]
                counts["blind"] += 1

    with open(SRC, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")

    print("Merge complete:", counts)


if __name__ == "__main__":
    main()
