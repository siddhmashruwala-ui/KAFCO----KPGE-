# -*- coding: utf-8 -*-
"""
kgpe.contract.units
=====================
Strict units policy for the KGPE canonical engineering-data contract
(Prompt 4 Sec. 8).

Rules enforced here:
  - Canonical internal unit for length is millimetres (mm); mass is
    kilograms (kg); angle is degrees (deg) - matching what KGPE's existing
    Dimension Library JSON files and rules/*.py already use throughout
    (confirmed in Prompts 1-3: every *_mm field in dimension_library.py).
  - A bare number is never accepted as a Quantity - `unit` is a required,
    explicit constructor argument with no default, always.
  - The ORIGINAL source unit (e.g. the JS CRM's inches-based HUB_DIM, FLG,
    BOLT_DIA tables - confirmed in Prompts 2-3) can be preserved alongside
    the canonical value, so provenance never silently loses which unit a
    legacy figure was actually recorded in.
"""

LENGTH_MM = "mm"
LENGTH_IN = "in"
LENGTH_M = "m"
MASS_KG = "kg"
MASS_LB = "lb"
ANGLE_DEG = "deg"
ANGLE_RAD = "rad"
COUNT = "count"                # for num_bolts etc - dimensionless
DESIGNATION = "designation"    # for bolt_size_designation etc - not a physical quantity

CANONICAL_LENGTH_UNIT = LENGTH_MM
CANONICAL_MASS_UNIT = MASS_KG
CANONICAL_ANGLE_UNIT = ANGLE_DEG

_TO_MM = {LENGTH_MM: 1.0, LENGTH_IN: 25.4, LENGTH_M: 1000.0}
_TO_KG = {MASS_KG: 1.0, MASS_LB: 0.45359237}
_TO_DEG = {ANGLE_DEG: 1.0, ANGLE_RAD: 57.29577951308232}

_CONVERSION_TABLES = {"length": _TO_MM, "mass": _TO_KG, "angle": _TO_DEG}

_UNIT_DIMENSION = {}
for _dim, _table in _CONVERSION_TABLES.items():
    for _unit in _table:
        _UNIT_DIMENSION[_unit] = _dim
_UNIT_DIMENSION[COUNT] = "count"
_UNIT_DIMENSION[DESIGNATION] = "designation"

KNOWN_UNITS = frozenset(_UNIT_DIMENSION)


class UnknownUnitError(Exception):
    pass


class IncompatibleUnitError(Exception):
    pass


def _dimension_of(unit):
    if unit not in _UNIT_DIMENSION:
        raise UnknownUnitError(f"Unknown unit {unit!r}. Known units: {sorted(KNOWN_UNITS)}")
    return _UNIT_DIMENSION[unit]


def convert(value, from_unit, to_unit):
    """Explicit, checked unit conversion. Never guesses a unit; raises if
    either unit is unknown or if the two units aren't the same physical
    quantity (e.g. converting 'mm' to 'kg' is a caller bug, not silently 0)."""
    dim_from = _dimension_of(from_unit)
    dim_to = _dimension_of(to_unit)
    if dim_from != dim_to:
        raise IncompatibleUnitError(f"Cannot convert {from_unit!r} ({dim_from}) to {to_unit!r} ({dim_to})")
    if dim_from in ("count", "designation"):
        if from_unit != to_unit:
            raise IncompatibleUnitError(f"{dim_from} values are not convertible between units")
        return value
    table = _CONVERSION_TABLES[dim_from]
    return value * table[from_unit] / table[to_unit]


class Quantity:
    """An explicit (value, unit) pair, optionally remembering the original
    source-recorded value/unit before conversion to canonical form.

    Constructing a Quantity NEVER infers a unit - `unit` is a required
    argument with no default, by design (Prompt 4 Sec. 8: "Never infer
    units from a bare number").
    """
    __slots__ = ("value", "unit", "source_value", "source_unit")

    def __init__(self, value, unit, source_value=None, source_unit=None):
        if unit not in KNOWN_UNITS:
            raise UnknownUnitError(f"Unknown unit {unit!r}. Known units: {sorted(KNOWN_UNITS)}")
        if source_unit is not None and source_unit not in KNOWN_UNITS:
            raise UnknownUnitError(f"Unknown source_unit {source_unit!r}. Known units: {sorted(KNOWN_UNITS)}")
        self.value = value
        self.unit = unit
        self.source_value = source_value
        self.source_unit = source_unit

    @classmethod
    def from_source(cls, source_value, source_unit, canonical_unit):
        """Build a Quantity from a legacy/original-source value, converting
        to the canonical unit while preserving the original for provenance."""
        value = convert(source_value, source_unit, canonical_unit)
        return cls(value=value, unit=canonical_unit, source_value=source_value, source_unit=source_unit)

    def to(self, target_unit):
        return convert(self.value, self.unit, target_unit)

    def to_dict(self):
        d = {"value": self.value, "unit": self.unit}
        if self.source_value is not None:
            d["source_value"] = self.source_value
        if self.source_unit is not None:
            d["source_unit"] = self.source_unit
        return d

    def __eq__(self, other):
        return isinstance(other, Quantity) and self.value == other.value and self.unit == other.unit

    def __repr__(self):
        return f"Quantity({self.value!r}, {self.unit!r})"
