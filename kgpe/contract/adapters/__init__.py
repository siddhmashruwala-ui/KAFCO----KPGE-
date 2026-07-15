# -*- coding: utf-8 -*-
"""
kgpe.contract.adapters
=========================
Source adapters: Source JSON -> canonical EngineeringFact records ->
FactRegistry (Prompt 5 Sec.7). Each adapter is source-format-specific and
knows nothing about FactRegistry's internals beyond its public `add()` /
`add_checked()` methods - FactRegistry, in turn, knows nothing about any
particular source's JSON structure. This separation lets future adapters
(ASME B36.10/19, ASME B16.9, JIS, EN, MSS) be added without modifying
FactRegistry or any other existing adapter.

Modules:
  asme_b16_5_flanges.py            - the Prompt 5 reference adapter
  legacy_crm_quarantine_fixture.py - NOT a source adapter; a small fixture
                                     proving the quarantine mechanism works
                                     in the production registry (Prompt 5
                                     Sec.18), built from Prompt 3 audit
                                     findings, not from any JSON file.
"""
