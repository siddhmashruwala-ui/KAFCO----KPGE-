# -*- coding: utf-8 -*-
"""
kgpe.contract.applicability
=============================
Applicability model (Prompt 4 Sec. 9): what a given engineering fact,
derived rule, construction parameter, or rendering parameter APPLIES TO.

Deliberately a flat dataclass of optional fields, not a generic rules
engine - Prompt 4 Sec. 9 explicitly warns against building "an
unnecessarily abstract rules engine." Every field here corresponds to a
combination KGPE's actual datasets are known to use (Prompts 1-3), not a
speculative one.
"""
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass(frozen=True)
class Applicability:
    product_family: Optional[str] = None       # e.g. "flange"
    product_type: Optional[str] = None         # e.g. "weld_neck", "slip_on"
    flange_type: Optional[str] = None          # e.g. "weld_neck" | "other" (Prompt 3 T/TJ split)
    fitting_type: Optional[str] = None         # e.g. "elbow_90", "tee", "cap", "reducer"
    standard: Optional[str] = None             # e.g. "ASME_B16.5"
    standard_edition: Optional[str] = None     # e.g. "2020" - None means unconfirmed, never guessed
    class_key: Optional[str] = None            # e.g. "150" / "PN16" / "10K"
    schedule: Optional[str] = None             # e.g. "Sch40"
    nps: Optional[str] = None
    dn: Optional[str] = None
    jis_size: Optional[str] = None
    reducing_pair: Optional[str] = None        # e.g. "6x4" - display-only; DO NOT query on this, see large_end_nps/small_end_nps
    run_branch_pair: Optional[str] = None      # e.g. "6x2" - reserved for a future reducing-tee source; unused as of Prompt 7
    manufacturer_profile: Optional[str] = None  # e.g. "Hackney Ladish" - required context for VERIFIED_MANUFACTURER_SPECIFIC
    # Prompt 7 additive fields: role-specific NPS identity for two-size
    # fittings (e.g. ASME B16.9 reducers), so a reducer's engineering
    # identity is deterministically queryable by end role rather than only
    # via an opaque display string like "6x4" (Prompt 7 Sec.3/12). Both
    # default to None and are simply absent from single-size facts
    # (flanges, pipes, elbows, tees, caps) - fully backward compatible.
    large_end_nps: Optional[str] = None        # e.g. reducer large-end NPS, normalized via normalize_nps()
    small_end_nps: Optional[str] = None        # e.g. reducer small-end NPS, normalized via normalize_nps()

    # Prompt 8 additive fields. Each is scoped to the ONE size system it
    # names - deliberately NOT a single generic "large_end_size"/
    # "small_end_size" pair, so a reader can tell which size system a
    # fact uses from the field name alone (matching the large_end_nps/
    # small_end_nps precedent from Prompt 7). Only added because a real
    # migrated dataset actually needs each one - not speculative:
    #   - large_end_dn / small_end_dn: EN/DIN reducers (DIN_EN10253
    #     concentric_reducer table gives DN_Large/DN_Small explicitly).
    #   - large_end_jis_size / small_end_jis_size: JIS B2311/2312
    #     concentric-reducer sample (SizeLarge_mm/SizeSmall_mm, JIS
    #     A-size designation, not NPS or DN).
    #   - run_nps / branch_nps: MSS SP-97 branch-outlet fittings, where
    #     "run" and "branch" are genuinely different engineering roles
    #     from a reducer's "large end"/"small end" (Prompt 8 Sec.13 -
    #     do not misuse reducer fields for branch fittings). Both are
    #     NPS-system sizes (MSS SP-97's own tables use NPS), so they
    #     reuse normalize_nps()/nps_sort_key(), just under role-specific
    #     field names distinct from a reducer's large/small end roles.
    large_end_dn: Optional[str] = None
    small_end_dn: Optional[str] = None
    large_end_jis_size: Optional[str] = None
    small_end_jis_size: Optional[str] = None
    run_nps: Optional[str] = None
    branch_nps: Optional[str] = None

    def as_dict(self):
        return {k: v for k, v in asdict(self).items() if v is not None}

    def matches(self, **filters):
        """True if every filter key/value given matches this Applicability's
        corresponding field. Fields not passed in `filters` are ignored -
        this is a simple exact-match filter, not a rules engine."""
        for key, expected in filters.items():
            if not hasattr(self, key):
                raise AttributeError(f"Applicability has no field {key!r}")
            if getattr(self, key) != expected:
                return False
        return True
