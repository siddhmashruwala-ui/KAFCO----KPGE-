# -*- coding: utf-8 -*-
"""
kgpe.contract.adapters._shared
==================================
Small shared utilities reused across Prompt 8's several new adapters
(ASME B16.11, MSS SP-97, JIS x3, EN x3). Per Prompt 8 Sec.23, this is
deliberately a handful of narrow helpers - safe source loading, a
generic positive-numeric-or-null field check, and a generic duplicate-
key check - NOT a generic adapter framework. Every adapter still owns
its own column mapping, fitting-type assignment, and applicability
construction explicitly; nothing here hides source-specific engineering
meaning.
"""
import json
import os

from ..model import SourceValidationError


def load_json_source(dimlib_root, rel_path):
    """Reads and parses a JSON file at dimlib_root/rel_path, raising
    SourceValidationError (not a bare exception) on I/O or parse failure.
    Returns (data, rel_path) - rel_path is handed back so callers can
    stash it directly into EngineeringFactProvenance.source_file without
    reconstructing it."""
    full_path = os.path.join(dimlib_root, rel_path)
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError as e:
        raise SourceValidationError(f"Source file not found at {full_path!r}") from e
    except json.JSONDecodeError as e:
        raise SourceValidationError(f"Source file at {full_path!r} is not valid JSON: {e}") from e
    return data, rel_path


def validate_positive_numeric_or_null(section_label, index, row, field, required=False):
    """Generic check: row[field] must be a positive int/float, OR None if
    not `required`. Returns a list of error strings (empty if OK) - never
    raises directly, so callers can accumulate errors across many fields/
    rows before raising one SourceValidationError with everything found."""
    if field not in row:
        return [f"{section_label} row {index}: missing declared column {field!r}"]
    v = row[field]
    if v is None:
        if required:
            return [f"{section_label} row {index}: {field} is required and must not be null"]
        return []
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return [f"{section_label} row {index}: {field} must be numeric or null, got {v!r}"]
    if v <= 0:
        return [f"{section_label} row {index}: {field} must be positive, got {v!r}"]
    return []


def check_duplicate_key(section_label, rows, key_fn):
    """Generic duplicate-key check: key_fn(row) -> a hashable canonical
    key (e.g. a normalized size string, or a tuple of two). Returns a
    list of error strings for any key seen more than once. Rows whose
    key_fn raises ValueError are silently skipped here (that malformed
    row is expected to already be reported by the caller's own per-row
    validation - this function only checks for duplicates among rows
    that parsed successfully)."""
    seen = {}
    errs = []
    for i, row in enumerate(rows):
        try:
            key = key_fn(row)
        except (ValueError, KeyError, TypeError):
            continue
        if key in seen:
            errs.append(f"{section_label}: duplicate key {key!r} at rows {seen[key]} and {i}")
        else:
            seen[key] = i
    return errs
