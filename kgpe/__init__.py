# -*- coding: utf-8 -*-
"""KGPE - KAFCO Geometry & Parametric Engine.

Headless. Converts validated Dimension Library data into deterministic
parametric geometry. Does not perform forging engineering calculations
(that is KFEE's job, a separate system) and does not invent dimensions
that aren't in the Dimension Library.
"""
from .generator import generate_geometry
from .version import KGPE_VERSION

__all__ = ["generate_geometry", "KGPE_VERSION"]
__version__ = KGPE_VERSION
