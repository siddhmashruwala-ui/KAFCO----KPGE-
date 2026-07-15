# -*- coding: utf-8 -*-
"""
kgpe.contract.normalization
==============================
Deterministic normalization for NPS and pressure-class identity (Prompt 5
Sec.12-13). Exists so that "150", "Class 150", "CL150", and 150 can never
silently become four different canonical identities, and so fractional
NPS ("1-1/2", "3/4") never has to be compared as binary floating point.

No Prompt 4 dataclass shape changed to support this - Applicability.nps
and .class_key already accept plain strings. The improvement here is
discipline (always pass values through these functions before they reach
an Applicability), not a schema redesign.
"""
import re
from fractions import Fraction

from .vocabulary import (
    RATING_SYSTEM_ASME_CLASS, RATING_SYSTEM_PN, RATING_SYSTEM_JIS_K,
)

_WHOLE_FRAC_RE = re.compile(r"^(\d+)-(\d+)/(\d+)$")
_FRAC_RE = re.compile(r"^(\d+)/(\d+)$")
_WHOLE_RE = re.compile(r"^(\d+)$")
_SPACED_WHOLE_FRAC_RE = re.compile(r"^(\d+)\s+(\d+)\s*/\s*(\d+)$")


def normalize_nps(raw):
    """Canonical NPS string, e.g. "1-1/2", "3/4", "2". Never uses float for
    identity - fractional sizes are validated by regex and re-emitted as
    an integer-only dash/slash string. Raises ValueError on anything that
    doesn't match a known NPS shape, rather than guessing."""
    s = str(raw).strip()
    s = _SPACED_WHOLE_FRAC_RE.sub(r"\1-\2/\3", s)  # "1 1/2" -> "1-1/2"
    s = s.replace(" ", "")

    m = _WHOLE_FRAC_RE.match(s)
    if m:
        whole, num, den = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if den == 0:
            raise ValueError(f"Invalid NPS fraction denominator in {raw!r}")
        return f"{whole}-{num}/{den}"

    m = _FRAC_RE.match(s)
    if m:
        num, den = int(m.group(1)), int(m.group(2))
        if den == 0:
            raise ValueError(f"Invalid NPS fraction denominator in {raw!r}")
        return f"{num}/{den}"

    m = _WHOLE_RE.match(s)
    if m:
        return str(int(m.group(1)))

    raise ValueError(f"Cannot normalize NPS value {raw!r} - unrecognized format")


def nps_sort_key(canonical_nps):
    """Exact rational sort key (stdlib `fractions.Fraction`, never float)
    for a canonical NPS string produced by normalize_nps(). This is a SORT
    key only - the canonical IDENTITY of an NPS remains the string, not
    this Fraction (Prompt 5 Sec.13: "Do not use binary floating-point as
    the canonical identity for fractional NPS")."""
    s = canonical_nps.strip()
    if "-" in s:
        whole_part, frac_part = s.split("-", 1)
        num, den = frac_part.split("/")
        return Fraction(int(whole_part)) + Fraction(int(num), int(den))
    if "/" in s:
        num, den = s.split("/")
        return Fraction(int(num), int(den))
    return Fraction(int(s))


_CLASS_PREFIX_RE = re.compile(r"^\s*(?:class|cl)?\s*0*(\d+)\s*(?:lb|#)?\s*$", re.IGNORECASE)


def normalize_pressure_class(raw, rating_system=RATING_SYSTEM_ASME_CLASS):
    """Canonical rating-identity string for a given rating system. Accepts
    common source variants ("150", 150, "Class 150", "CL150") and always
    emits one deterministic form, so the same engineering rating can never
    silently split into multiple canonical identities."""
    if rating_system == RATING_SYSTEM_ASME_CLASS:
        m = _CLASS_PREFIX_RE.match(str(raw).strip())
        if not m:
            raise ValueError(f"Cannot normalize ASME pressure class {raw!r}")
        return str(int(m.group(1)))

    if rating_system == RATING_SYSTEM_PN:
        s = str(raw).strip().upper().replace(" ", "")
        if not s.startswith("PN"):
            s = "PN" + s
        digits = s[2:]
        if not digits.isdigit():
            raise ValueError(f"Cannot normalize PN class {raw!r}")
        return f"PN{int(digits)}"

    if rating_system == RATING_SYSTEM_JIS_K:
        s = str(raw).strip().upper().replace(" ", "")
        if not s.endswith("K"):
            s = s + "K"
        digits = s[:-1]
        if not digits.isdigit():
            raise ValueError(f"Cannot normalize JIS K class {raw!r}")
        return f"{int(digits)}K"

    raise ValueError(f"Unsupported rating_system for pressure-class normalization: {rating_system!r}")


# ---------------------------------------------------------------------------
# Schedule normalization (Prompt 6 Sec.5-6). Broadly reusable across any
# future ASME/JIS pipe adapter, so it lives here rather than inside one
# adapter (Prompt 6 Sec.11).
#
# CRITICAL: "40" and "40S" (and "80"/"80S") are DIFFERENT schedule
# identities and must NEVER be collapsed, even though they happen to
# produce the same wall thickness at some NPS values (e.g. ASME B36.10M
# vs B36.19M both give 7.11mm at NPS6/Sch40 vs Sch40S) - dimensional
# equality at a size is not the same thing as designation identity
# (Prompt 6 Sec.6). Likewise STD/XS/XXS are their own designations, never
# aliased to a numeric schedule unless the source explicitly says so - it
# doesn't (the ASME B36.10M source notes explicitly flag Sch40 and SchSTD
# as "now separate columns... diverge for NPS>=12").
# ---------------------------------------------------------------------------
_SCHEDULE_NUMERIC_RE = re.compile(r"^(\d+)(S)?$")


def normalize_schedule(raw):
    """Canonical schedule-designation string, e.g. "SCH40", "SCH40S",
    "STD", "XS", "XXS". Accepts source variants ("40", "Sch40", "SCH 40",
    "SCH-40") but "SCH40" and "SCH40S" always remain distinct outputs -
    this function never merges a numeric schedule with its S-suffix
    counterpart, and never aliases STD/XS/XXS to a numeric schedule."""
    s = str(raw).strip().upper()
    s = re.sub(r"^SCHEDULE\s*", "", s)
    s = re.sub(r"^SCH\.?\s*", "", s)
    s = s.replace(" ", "").replace("-", "").replace("_", "")

    if s in ("STD", "STANDARD"):
        return "STD"
    if s == "XXS":
        return "XXS"
    if s == "XS":
        return "XS"

    m = _SCHEDULE_NUMERIC_RE.match(s)
    if not m:
        raise ValueError(f"Cannot normalize schedule designation {raw!r} - unrecognized format")
    digits, s_suffix = m.group(1), m.group(2)
    return f"SCH{digits}S" if s_suffix else f"SCH{digits}"


# ---------------------------------------------------------------------------
# ASME pipe standard-identity normalization (Prompt 6 Sec.3/12).
#
# Deliberately produces TWO distinct canonical identifiers -
# "ASME_B36.10M" and "ASME_B36.19M" - matching the actual source file's
# own top-level "standards" dict keys (read directly from
# Pipes/ASME_B36.10M_B36.19M_Pipes.json, not invented). This is NOT the
# same as dimension_library.py's PIPE_FILES registry key "ASME_B36" -
# that key is a FILE-SELECTION identifier (which JSON file to load for
# the existing combined live lookup) and is left completely unchanged;
# this function produces the actual GOVERNING-STANDARD identity used in
# the new canonical contract's Applicability.standard field, which must
# stay sensitive to the B36.10M vs B36.19M distinction (Prompt 6 Sec.3).
# ---------------------------------------------------------------------------
ASME_B36_10M = "ASME_B36.10M"
ASME_B36_19M = "ASME_B36.19M"

_PIPE_STANDARD_ALIASES = {
    "ASME_B36.10M": ASME_B36_10M, "ASME B36.10M": ASME_B36_10M, "ASME_B36.10": ASME_B36_10M,
    "B36.10M": ASME_B36_10M, "B36.10": ASME_B36_10M,
    "ASME_B36.19M": ASME_B36_19M, "ASME B36.19M": ASME_B36_19M, "ASME_B36.19": ASME_B36_19M,
    "B36.19M": ASME_B36_19M, "B36.19": ASME_B36_19M,
}


def normalize_asme_pipe_standard(raw):
    """Canonical ASME pipe standard identifier - always
    "ASME_B36.10M" or "ASME_B36.19M", never a merged/ambiguous
    "ASME pipe" identity (Prompt 6 Sec.3)."""
    s = str(raw).strip()
    if s in _PIPE_STANDARD_ALIASES:
        return _PIPE_STANDARD_ALIASES[s]
    s2 = s.upper().replace("ASME", "").replace(" ", "").replace("_", "").strip()
    if s2 in ("B36.10M", "B36.10"):
        return ASME_B36_10M
    if s2 in ("B36.19M", "B36.19"):
        return ASME_B36_19M
    raise ValueError(f"Cannot normalize ASME pipe standard identifier {raw!r}")


# ---------------------------------------------------------------------------
# DN normalization (Prompt 8 Sec.6). EN/DIN datasets identify size by DN
# (nominal diameter, a plain integer-valued designation - DN50, DN100,
# etc - NOT the same engineering identity as ASME NPS, even where the
# numeric progression happens to look similar). Never silently converted
# to/from NPS anywhere in this codebase - Applicability keeps `dn` and
# `nps` as separate fields (Prompt 4), and this function only normalizes
# DN's own textual variants ("50", 50, "DN50", "DN 50") into one
# canonical form.
# ---------------------------------------------------------------------------
_DN_RE = re.compile(r"^(?:DN)?\s*0*(\d+)$", re.IGNORECASE)


def normalize_dn(raw):
    """Canonical DN string, e.g. "DN50". Accepts "50", 50, "DN50", "DN 50".
    Never accepts a fractional/dashed value (DN is always a plain integer
    designation in every source this project has ingested) - raises
    ValueError rather than guessing if the input doesn't match that shape."""
    s = str(raw).strip()
    m = _DN_RE.match(s)
    if not m:
        raise ValueError(f"Cannot normalize DN value {raw!r} - unrecognized format")
    return f"DN{int(m.group(1))}"


def dn_sort_key(canonical_dn):
    """Sort key only (never identity) for a canonical "DN<n>" string -
    a plain int is exact and sufficient since DN is never fractional."""
    return int(canonical_dn[2:])


# ---------------------------------------------------------------------------
# JIS size normalization (Prompt 8 Sec.5). JIS flange/pipe/buttweld
# sources identify size by a nominal-diameter-in-mm designation commonly
# written "A" in JIS nomenclature (e.g. "50A") - this project's existing
# AI-Readable JSON files store it as a bare integer column (e.g.
# NPS_A_mm=50, A_mm=50). This is its OWN engineering identity, never
# forced into ASME NPS or EN DN even though the numeric progression
# (15,20,25,32,40,50...) happens to match DN's - see Prompt 8 Sec.4.
# ---------------------------------------------------------------------------
_JIS_SIZE_RE = re.compile(r"^0*(\d+)\s*A?$", re.IGNORECASE)


def normalize_jis_size(raw):
    """Canonical JIS A-size string, e.g. "50A". Accepts "50", 50, "50A",
    "50 A". Never accepts a fractional/dashed value - JIS A-size sources
    ingested in this project are always plain integers."""
    s = str(raw).strip()
    m = _JIS_SIZE_RE.match(s)
    if not m:
        raise ValueError(f"Cannot normalize JIS size value {raw!r} - unrecognized format")
    return f"{int(m.group(1))}A"


def jis_size_sort_key(canonical_jis_size):
    """Sort key only (never identity) for a canonical "<n>A" JIS-size
    string - a plain int is exact and sufficient since JIS A-size is
    never fractional."""
    return int(canonical_jis_size[:-1])


# ---------------------------------------------------------------------------
# Wall-designation normalization (Prompt 8 Sec.7/11). The EN/DIN pipe
# source (DIN_EN10216_10217_Pipes.json) selects wall thickness by a
# "Series1".."Series5" designation - a genuinely different rating concept
# from ASME schedule (RATING_SYSTEM_WALL_DESIGNATION, already declared in
# vocabulary.py but previously unused). Stored in Applicability.schedule
# (the field is a generic size-selector slot, not an ASME-only field) but
# ALWAYS with an "EN_" prefix so it can never be confused with or collide
# with an ASME "SCH.." value even if compared carelessly.
# ---------------------------------------------------------------------------
_WALL_DESIGNATION_RE = re.compile(r"^SERIES\s*0*(\d+)$", re.IGNORECASE)


def normalize_wall_designation(raw):
    """Canonical EN/DIN wall-designation string, e.g. "EN_SERIES3".
    Accepts "Series3", "series 3", "SERIES3". Never aliased to or
    confusable with an ASME schedule designation."""
    s = str(raw).strip().upper().replace(" ", "")
    m = _WALL_DESIGNATION_RE.match(s)
    if not m:
        raise ValueError(f"Cannot normalize EN/DIN wall designation {raw!r} - unrecognized format")
    return f"EN_SERIES{int(m.group(1))}"
