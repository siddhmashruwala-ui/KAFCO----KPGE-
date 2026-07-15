# -*- coding: utf-8 -*-
"""
kgpe.contract.verification
===========================
The verification-status vocabulary established in KGPE Prompt 3/40 ("11.
Engineering Baseline Decision Register") and the policy for which statuses
may be consumed as authoritative engineering truth.

This is the enforcement point for KGPE's fail-closed rule at the DATA
layer: "Missing or unverified engineering information must never silently
become authoritative geometry" (Prompt 4 Sec. 2).
"""

VERIFIED_AUTHORITATIVE = "VERIFIED_AUTHORITATIVE"
VERIFIED_DERIVED_RULE = "VERIFIED_DERIVED_RULE"
VERIFIED_MANUFACTURER_SPECIFIC = "VERIFIED_MANUFACTURER_SPECIFIC"
CONSTRUCTION_PARAMETER = "CONSTRUCTION_PARAMETER"
VISUAL_ONLY = "VISUAL_ONLY"
QUARANTINED_CONFLICT = "QUARANTINED_CONFLICT"
QUARANTINED_UNVERIFIED = "QUARANTINED_UNVERIFIED"
DEPRECATED_LEGACY = "DEPRECATED_LEGACY"

ALL_STATUSES = frozenset({
    VERIFIED_AUTHORITATIVE, VERIFIED_DERIVED_RULE, VERIFIED_MANUFACTURER_SPECIFIC,
    CONSTRUCTION_PARAMETER, VISUAL_ONLY, QUARANTINED_CONFLICT,
    QUARANTINED_UNVERIFIED, DEPRECATED_LEGACY,
})

# Usable with NO extra context/opt-in required.
ALWAYS_USABLE_STATUSES = frozenset({VERIFIED_AUTHORITATIVE, VERIFIED_DERIVED_RULE})

# Usable ONLY if the caller explicitly opts in / supplies the required
# context (e.g. a manufacturer_profile for VERIFIED_MANUFACTURER_SPECIFIC).
# Prompt 4 Sec. 6 asks us to decide whether CONSTRUCTION_PARAMETER and
# VERIFIED_MANUFACTURER_SPECIFIC require explicit opt-in - decision made
# here: yes, both do, because both are real-but-conditional facts (a
# specific manufacturer's data, or a value that was never standard-
# tabulated but is needed to build a shape) that must never become the
# silent default answer to a generic "give me the standard dimension" query.
CONTEXT_REQUIRED_STATUSES = frozenset({VERIFIED_MANUFACTURER_SPECIFIC, CONSTRUCTION_PARAMETER})

# NEVER usable as authoritative engineering geometry input, no opt-in
# possible. This is a hard rule, not a policy default that can be relaxed.
NEVER_AUTHORITATIVE_STATUSES = frozenset({
    VISUAL_ONLY, QUARANTINED_CONFLICT, QUARANTINED_UNVERIFIED, DEPRECATED_LEGACY,
})

assert ALWAYS_USABLE_STATUSES | CONTEXT_REQUIRED_STATUSES | NEVER_AUTHORITATIVE_STATUSES == ALL_STATUSES
assert not (ALWAYS_USABLE_STATUSES & CONTEXT_REQUIRED_STATUSES & NEVER_AUTHORITATIVE_STATUSES)


class VerificationPolicyError(Exception):
    """Raised when code attempts to use a status in a way the safest-
    reasonable policy forbids (e.g. treating a QUARANTINED_CONFLICT value
    as authoritative, or using VERIFIED_MANUFACTURER_SPECIFIC data without
    a manufacturer_profile context). Deliberately a hard failure, not a
    warning - per KGPE's fail-closed philosophy, a policy violation must
    stop the pipeline, not just log a note."""
    pass


def is_known_status(status):
    return status in ALL_STATUSES


def is_usable_as_authoritative(status, allow_manufacturer_specific=False, allow_construction_parameter=False):
    """Returns True only if `status` may be treated as authoritative
    engineering input under the given opt-ins.

    - VERIFIED_AUTHORITATIVE / VERIFIED_DERIVED_RULE: always True.
    - VERIFIED_MANUFACTURER_SPECIFIC: True only if allow_manufacturer_specific.
    - CONSTRUCTION_PARAMETER: True only if allow_construction_parameter.
    - VISUAL_ONLY / QUARANTINED_CONFLICT / QUARANTINED_UNVERIFIED /
      DEPRECATED_LEGACY: always False. No opt-in flag can change this -
      callers must not be able to accidentally (or even deliberately, via
      this function) treat quarantined or visual-only data as
      authoritative geometry input.
    """
    if not is_known_status(status):
        raise VerificationPolicyError(f"Unknown verification status: {status!r}")
    if status in NEVER_AUTHORITATIVE_STATUSES:
        return False
    if status in ALWAYS_USABLE_STATUSES:
        return True
    if status == VERIFIED_MANUFACTURER_SPECIFIC:
        return bool(allow_manufacturer_specific)
    if status == CONSTRUCTION_PARAMETER:
        return bool(allow_construction_parameter)
    # Unreachable given ALL_STATUSES partition, but fail closed rather than
    # silently returning True for a status this function doesn't recognize.
    return False


def require_usable_as_authoritative(status, allow_manufacturer_specific=False,
                                     allow_construction_parameter=False, context=""):
    """Same check as is_usable_as_authoritative, but raises
    VerificationPolicyError instead of returning False - for call sites
    that should hard-stop rather than branch on a bool."""
    if not is_usable_as_authoritative(status, allow_manufacturer_specific, allow_construction_parameter):
        raise VerificationPolicyError(
            f"Verification status {status!r} cannot be used as authoritative engineering "
            f"input{(' (' + context + ')') if context else ''}. This is a fail-closed rule, "
            f"not a bug - see kgpe/contract/verification.py."
        )
