# -*- coding: utf-8 -*-
"""
Automated tests for KGPE's canonical engineering-data contract (Prompt 4).

Run with:
    cd "Dimensions and Standards/Engine/KGPE"
    python -m unittest discover -s tests -p "test_*.py" -v

or directly:
    python tests/test_canonical_contract.py

Uses only the Python standard library `unittest` - Prompt 1 found neither
pytest nor any test framework installed, and Prompt 4 explicitly says not
to install pytest just for this prompt.
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from kgpe import contract as C
from kgpe.contract.units import Quantity, UnknownUnitError, LENGTH_MM, LENGTH_IN
from kgpe.contract.applicability import Applicability
from kgpe.contract.model import (
    EngineeringFact, EngineeringFactProvenance, ConstructionParameter,
    FactRegistry, canonical_json, DimensionQuarantined, CombinationNotFound,
    MalformedInput,
)
from kgpe.contract import vocabulary as VOC
from kgpe.contract import verification as V
from kgpe.contract.derived_rules import RF_HEIGHT_BY_CLASS, TOLERANCE_BOLT_CIRCLE
from kgpe.generator import generate_geometry  # existing, pre-Prompt-4 entry point


def _prov(**kw):
    return EngineeringFactProvenance(**kw)


class TestValidAuthoritativeRecord(unittest.TestCase):
    def test_create_authoritative_fact_and_query_it(self):
        fact = EngineeringFact(
            dimension_name=VOC.DIM_OUTSIDE_DIAMETER,
            value=Quantity(152.4, LENGTH_MM),
            applicability=Applicability(product_family="flange", standard="ASME_B16.5", class_key="150", nps="2"),
            verification_status=V.VERIFIED_AUTHORITATIVE,
            provenance=_prov(source_name="KGPE ASME B16.5 JSON", source_type="internal_dataset"),
        )
        self.assertEqual(fact.verification_status, V.VERIFIED_AUTHORITATIVE)
        reg = FactRegistry()
        reg.add(fact)
        results = reg.query(VOC.DIM_OUTSIDE_DIAMETER, standard="ASME_B16.5", class_key="150", nps="2")
        self.assertEqual(len(results), 1)
        self.assertIs(results[0], fact)


class TestUnitsPolicy(unittest.TestCase):
    def test_invalid_unit_rejected(self):
        with self.assertRaises(UnknownUnitError):
            Quantity(10.0, "furlongs")

    def test_source_unit_preserved_and_converted(self):
        q = Quantity.from_source(source_value=6.0, source_unit=LENGTH_IN, canonical_unit=LENGTH_MM)
        self.assertAlmostEqual(q.value, 152.4, places=3)
        self.assertEqual(q.source_unit, LENGTH_IN)
        self.assertEqual(q.source_value, 6.0)

    def test_bare_number_requires_explicit_unit(self):
        with self.assertRaises(TypeError):
            Quantity(10.0)  # unit is a required positional arg, never defaulted


class TestQuarantineEnforcement(unittest.TestCase):
    def setUp(self):
        self.reg = FactRegistry()
        # Fixture reproducing Prompt 3's exact quarantined conflict:
        # NPS14/Class150 raised-face diameter, JS=419.1mm vs Texas Flange=412.75mm.
        self.js_value = EngineeringFact(
            dimension_name=VOC.DIM_RAISED_FACE_DIAMETER,
            value=Quantity(419.1, LENGTH_MM),
            applicability=Applicability(standard="ASME_B16.5", class_key="150", nps="14"),
            verification_status=V.QUARANTINED_CONFLICT,
            provenance=_prov(source_name="JS CRM RF_BORE table", source_type="legacy_code"),
            notes="Conflicts with Texas Flange R column (412.75mm) by exactly 6.35mm/0.25in.",
        )
        self.tf_value = EngineeringFact(
            dimension_name=VOC.DIM_RAISED_FACE_DIAMETER,
            value=Quantity(412.75, LENGTH_MM),
            applicability=Applicability(standard="ASME_B16.5", class_key="150", nps="14"),
            verification_status=V.QUARANTINED_CONFLICT,
            provenance=_prov(source_name="Texas Flange dimension table", source_type="supplier_reference"),
        )
        self.reg.add(self.js_value)
        self.reg.add(self.tf_value)

    def test_quarantined_conflict_blocked_from_query(self):
        with self.assertRaises(DimensionQuarantined):
            self.reg.query(VOC.DIM_RAISED_FACE_DIAMETER, standard="ASME_B16.5", class_key="150", nps="14")

    def test_quarantined_conflict_visible_via_explicit_inspector(self):
        quarantined = self.reg.get_quarantined(VOC.DIM_RAISED_FACE_DIAMETER)
        self.assertEqual(len(quarantined), 2)

    def test_unverified_hub_length_class300_fixture(self):
        # Fixture reproducing Prompt 3's Class-300 HUB_DIM Y gap.
        fact = EngineeringFact(
            dimension_name=VOC.DIM_LENGTH_THROUGH_HUB,
            value=Quantity(114.3, LENGTH_MM),
            applicability=Applicability(standard="ASME_B16.5", class_key="300", nps="2"),
            verification_status=V.QUARANTINED_UNVERIFIED,
            provenance=_prov(source_name="JS CRM HUB_DIM table", source_type="legacy_code",
                              notes="~1.5mm gap vs Texas Flange L2 column, unresolved as of Prompt 3."),
        )
        reg = FactRegistry()
        reg.add(fact)
        with self.assertRaises(DimensionQuarantined):
            reg.query(VOC.DIM_LENGTH_THROUGH_HUB, standard="ASME_B16.5", class_key="300", nps="2")


class TestManufacturerSpecificContext(unittest.TestCase):
    def setUp(self):
        self.reg = FactRegistry()
        self.fact = EngineeringFact(
            dimension_name=VOC.DIM_MASS,
            value=Quantity(1.0, "kg"),
            applicability=Applicability(fitting_type="cap", nps="4", manufacturer_profile="Hackney Ladish"),
            verification_status=V.VERIFIED_MANUFACTURER_SPECIFIC,
            provenance=_prov(source_name="Hackney Ladish cap weight table", source_type="internal_dataset"),
        )
        self.reg.add(self.fact)

    def test_manufacturer_specific_blocked_by_default(self):
        with self.assertRaises(DimensionQuarantined):
            self.reg.query(VOC.DIM_MASS, fitting_type="cap", nps="4", manufacturer_profile="Hackney Ladish")

    def test_manufacturer_specific_allowed_with_explicit_opt_in(self):
        results = self.reg.query(VOC.DIM_MASS, allow_manufacturer_specific=True,
                                  fitting_type="cap", nps="4", manufacturer_profile="Hackney Ladish")
        self.assertEqual(len(results), 1)


class TestConstructionParameterDisclaimer(unittest.TestCase):
    def test_disclaimer_required(self):
        with self.assertRaises(MalformedInput):
            ConstructionParameter(
                dimension_name=VOC.DIM_HUB_BASE_DIAMETER,
                value=Quantity(50.0, LENGTH_MM),
                applicability=Applicability(product_family="olet", product_type="nipoflange"),
                provenance=_prov(source_name="JS CRM nipoflange proportional formula", source_type="legacy_code"),
                disclaimer="",
            )

    def test_valid_construction_parameter(self):
        cp = ConstructionParameter(
            dimension_name=VOC.DIM_HUB_BASE_DIAMETER,
            value=Quantity(50.0, LENGTH_MM),
            applicability=Applicability(product_family="olet", product_type="nipoflange"),
            provenance=_prov(source_name="JS CRM nipoflange proportional formula", source_type="legacy_code"),
            disclaimer="Proportional construction estimate, not a standard-tabulated dimension.",
        )
        self.assertEqual(cp.verification_status, V.CONSTRUCTION_PARAMETER)


class TestDeterministicSerialization(unittest.TestCase):
    def test_same_fact_serializes_identically(self):
        def make():
            return EngineeringFact(
                dimension_name=VOC.DIM_BOLT_CIRCLE_DIAMETER,
                value=Quantity(120.65, LENGTH_MM),
                applicability=Applicability(standard="ASME_B16.5", class_key="150", nps="2"),
                verification_status=V.VERIFIED_AUTHORITATIVE,
                provenance=_prov(source_name="KGPE ASME B16.5 JSON"),
            )
        j1 = canonical_json(make())
        j2 = canonical_json(make())
        self.assertEqual(j1, j2)

    def test_derived_rule_evaluation_deterministic(self):
        q1 = RF_HEIGHT_BY_CLASS.evaluate("150")
        q2 = RF_HEIGHT_BY_CLASS.evaluate("150")
        self.assertEqual(q1.value, q2.value)
        self.assertEqual(q1.value, 1.6)
        q3 = RF_HEIGHT_BY_CLASS.evaluate("600")
        self.assertEqual(q3.value, 6.35)

    def test_bolt_circle_tolerance_rule(self):
        q = TOLERANCE_BOLT_CIRCLE.evaluate("2")
        self.assertEqual(q.value, 1.6)


class TestSchemaVersionExposure(unittest.TestCase):
    def test_canonical_schema_version_is_exposed_and_distinct_from_software_version(self):
        from kgpe.version import KGPE_VERSION
        self.assertTrue(hasattr(C, "CANONICAL_SCHEMA_VERSION"))
        self.assertIsInstance(C.CANONICAL_SCHEMA_VERSION, str)
        self.assertNotEqual(C.CANONICAL_SCHEMA_VERSION, KGPE_VERSION)


class TestMissingDataSemantics(unittest.TestCase):
    def test_combination_not_found(self):
        reg = FactRegistry()
        with self.assertRaises(CombinationNotFound):
            reg.query(VOC.DIM_OUTSIDE_DIAMETER, standard="ASME_B16.5", class_key="150", nps="999")


class TestBackwardCompatibility(unittest.TestCase):
    def test_existing_flange_generation_path_unaffected(self):
        # Exact request shape from examples/demo.py, unmodified - proves
        # Prompt 4's new kgpe/contract/ package did not alter
        # generator.py/rules/*.py behaviour at all.
        req = {"product_type": "flange", "standard": "ASME_B16.5", "size": "2",
               "class_key": "150", "pipe_schedule": "Sch40"}
        result = generate_geometry(req)
        self.assertEqual(result["status"], "OK")
        self.assertIn("geometry", result)
        self.assertIn("provenance", result)

    def test_existing_olet_stub_still_fails_closed(self):
        result = generate_geometry({"product_type": "olet", "standard": "MSS_SP97", "size": "2"})
        self.assertEqual(result["status"], "GEOMETRY_DEFINITION_INCOMPLETE")


if __name__ == "__main__":
    unittest.main(verbosity=2)
