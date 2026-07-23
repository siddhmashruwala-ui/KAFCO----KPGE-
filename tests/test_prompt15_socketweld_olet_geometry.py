# -*- coding: utf-8 -*-
"""
tests/test_prompt15_socketweld_olet_geometry.py
====================================================
Prompt 15: automated tests for ASME B16.11 socket-weld and MSS SP-97
branch-outlet geometry built on top of the Prompt 12-14 kernel.
Standard-library `unittest` only.
"""
import math
import unittest

from kgpe.contract.canonical_reader import build_canonical_reader
from kgpe.contract.snapshot import registry_fingerprint
from kgpe.contract import vocabulary as VOC
from kgpe.resolver import EngineeringRequest, EngineeringResolver, ResolutionStatus
from kgpe.geometry_spec import prepare_geometry_specification, find_profile, GeometryReadinessStatus

from kgpe.geometry.cross_family import SocketweldBodyOutsideDiameterViaPipeRule
from kgpe.geometry.construction_rules import ConstructionRuleStatus, OletReinforcementEnvelopeConstructionRule
from kgpe.geometry.socket_geometry import (
    build_socket_geometry, validate_socket_geometry, SocketGeometryError,
    SOCKET_STATUS_AUTHORITATIVE, SOCKET_STATUS_UNAVAILABLE, SOCKET_STATUS_CONSTRUCTION_DERIVED,
)
from kgpe.geometry.outlet_geometry import (
    build_outlet_geometry, validate_outlet_geometry, OutletGeometryError,
    OUTLET_STATUS_AUTHORITATIVE, OUTLET_STATUS_CONSTRUCTION_DERIVED, OUTLET_STATUS_UNAVAILABLE,
)
from kgpe.geometry.result import GeometryGenerationStatus, TopologyRepresentation
from kgpe.geometry.kernel import generate_geometry
from kgpe.geometry.ports import OPENING_DIAMETER_PROVENANCE_NOT_MODELED

_READER, _ = build_canonical_reader()
_FINGERPRINT = registry_fingerprint(_READER.registry)
_RESOLVER = EngineeringResolver(_READER, _FINGERPRINT)
_DATA_LAYER_FINGERPRINT = "f291f02e63b591de449502dcbb2980b7729e2cdbdd928765f6a847e13083d748"  # post-Prompt-9: shifted again by the KAFCO_Nipoflange 12th-dataset addition


def _prep(**kwargs):
    return prepare_geometry_specification(EngineeringRequest(**kwargs), resolver=_RESOLVER)


def _sw_spec(subtype, size, extra_dims=None):
    kwargs = dict(product_family="socketweld_fitting", subtype=subtype, standard="ASME_B16.11",
                  primary_size=size, pressure_class="3000")
    if extra_dims:
        kwargs["dimensions"] = extra_dims
    r = _prep(**kwargs)
    assert r.is_ready(), (subtype, size, r.geometry_specification.warnings if r.geometry_specification else r.warnings)
    return r.geometry_specification


def _olet_spec(subtype, branch_size, run_size=None):
    kwargs = dict(product_family="olet", subtype=subtype, standard="MSS_SP97",
                  branch_size=branch_size, manufacturer_profile="Bonney Forge")
    if run_size:
        kwargs["run_size"] = run_size
    r = _prep(**kwargs)
    assert r.is_ready(), (subtype, branch_size, r.geometry_specification.warnings if r.geometry_specification else r.warnings)
    return r.geometry_specification


def _body_od(size, pipe_standard="ASME_B36.10M"):
    outcome = SocketweldBodyOutsideDiameterViaPipeRule().resolve(
        _RESOLVER, target_standard="ASME_B16.11", target_size_system="nps", target_size=size,
        pipe_standard=pipe_standard)
    assert outcome.is_applied(), outcome.detail
    return outcome.value


class TestDataLayerFingerprintUnchanged(unittest.TestCase):
    def test_fingerprint_matches_prior_prompts(self):
        self.assertEqual(_FINGERPRINT, _DATA_LAYER_FINGERPRINT)


# ---------------------------------------------------------------------------
# Sec.2/5: canonical coverage inspection, confirmed live against the
# registry - never assumed.
# ---------------------------------------------------------------------------
class TestSocketweldCoverageInspection(unittest.TestCase):
    def test_elbow_tee_cross_dimensions(self):
        for ft in (VOC.FITTING_TYPE_ELBOW_90_SW, VOC.FITTING_TYPE_ELBOW_45_SW,
                   VOC.FITTING_TYPE_TEE_SW, VOC.FITTING_TYPE_CROSS_SW):
            dims = _READER.available_dimensions(product_family=VOC.PRODUCT_FAMILY_SOCKETWELD_FITTING,
                                                  standard="ASME_B16.11", fitting_type=ft)
            for d in ("centre_to_end_mm", "fitting_body_wall_thickness_mm", "socket_bore_diameter_min_mm",
                      "socket_bore_diameter_max_mm", "socket_bore_depth_min_mm", "socket_bore_depth_max_mm",
                      "socket_wall_thickness_min_mm", "socket_wall_thickness_max_mm"):
                self.assertIn(d, dims, f"{ft} missing {d}")
            self.assertNotIn("outside_diameter_mm", dims)
            self.assertNotIn("socket_wall_min_at_bottom_mm", dims)

    def test_coupling_half_coupling_dimensions(self):
        for ft in (VOC.FITTING_TYPE_COUPLING_SW, VOC.FITTING_TYPE_HALF_COUPLING_SW):
            dims = _READER.available_dimensions(product_family=VOC.PRODUCT_FAMILY_SOCKETWELD_FITTING,
                                                  standard="ASME_B16.11", fitting_type=ft)
            for d in ("end_to_end_mm", "socket_bore_diameter_min_mm", "socket_bore_depth_min_mm"):
                self.assertIn(d, dims)
            self.assertNotIn("outside_diameter_mm", dims)
            self.assertNotIn("fitting_body_wall_thickness_mm", dims)

    def test_cap_dimensions_no_socket_diameter(self):
        dims = _READER.available_dimensions(product_family=VOC.PRODUCT_FAMILY_SOCKETWELD_FITTING,
                                              standard="ASME_B16.11", fitting_type=VOC.FITTING_TYPE_CAP_SW)
        for d in ("cap_body_diameter_mm", "cap_socket_length_mm", "socket_bore_depth_min_mm"):
            self.assertIn(d, dims)
        self.assertNotIn("socket_bore_diameter_min_mm", dims)
        self.assertNotIn("outside_diameter_mm", dims)

    def test_no_outside_diameter_anywhere_in_socketweld_family(self):
        dims = _READER.available_dimensions(product_family=VOC.PRODUCT_FAMILY_SOCKETWELD_FITTING,
                                              standard="ASME_B16.11")
        self.assertNotIn("outside_diameter_mm", dims)


class TestOletCoverageInspection(unittest.TestCase):
    def test_weldolet_sockolet_threadolet_dimensions(self):
        for ft, extra in ((VOC.FITTING_TYPE_WELDOLET, ()), (VOC.FITTING_TYPE_THREADOLET, ()),
                           (VOC.FITTING_TYPE_SOCKOLET, ("olet_socket_diameter_mm",))):
            dims = _READER.available_dimensions(product_family=VOC.PRODUCT_FAMILY_OLET,
                                                  standard="MSS_SP97", fitting_type=ft)
            for d in ("olet_base_outside_diameter_mm", "olet_bore_diameter_mm", "olet_face_to_face_mm",
                      "olet_height_mm") + extra:
                self.assertIn(d, dims, f"{ft} missing {d}")

    def test_official_height_table_dimensions(self):
        for ft in (VOC.FITTING_TYPE_WELDOLET_FULL, VOC.FITTING_TYPE_WELDOLET_REDUCING):
            dims = _READER.available_dimensions(product_family=VOC.PRODUCT_FAMILY_OLET,
                                                  standard="MSS_SP97", fitting_type=ft)
            self.assertEqual(set(dims), {"branch_outlet_height_mm"})

    def test_elbolet_latrolet_sweepolet_nippolet_unsupported_by_canonical_data(self):
        # Sec.1: only implement if actual canonical coverage exists -
        # confirmed live: none of these fitting_type identities are even
        # defined in the vocabulary, let alone populated with facts.
        self.assertNotIn("elbolet", VOC.OLET_FITTING_TYPES)
        self.assertNotIn("latrolet", VOC.OLET_FITTING_TYPES)
        self.assertNotIn("sweepolet", VOC.OLET_FITTING_TYPES)
        self.assertNotIn("nippolet", VOC.OLET_FITTING_TYPES)


# ---------------------------------------------------------------------------
# Sec.3/4: subtype support matrices.
# ---------------------------------------------------------------------------
class TestSocketweldSubtypeSupportMatrix(unittest.TestCase):
    def test_elbow_tee_cross_share_one_profile(self):
        for ft in (VOC.FITTING_TYPE_ELBOW_90_SW, VOC.FITTING_TYPE_ELBOW_45_SW,
                   VOC.FITTING_TYPE_TEE_SW, VOC.FITTING_TYPE_CROSS_SW):
            profile = find_profile(VOC.PRODUCT_FAMILY_SOCKETWELD_FITTING, ft)
            self.assertIsNotNone(profile)
            self.assertEqual(profile.profile_id, "socketweld_elbow_tee")
            self.assertEqual(profile.version, "2")

    def test_coupling_half_coupling_share_new_profile(self):
        for ft in (VOC.FITTING_TYPE_COUPLING_SW, VOC.FITTING_TYPE_HALF_COUPLING_SW):
            profile = find_profile(VOC.PRODUCT_FAMILY_SOCKETWELD_FITTING, ft)
            self.assertIsNotNone(profile)
            self.assertEqual(profile.profile_id, "socketweld_coupling")

    def test_cap_has_its_own_profile(self):
        profile = find_profile(VOC.PRODUCT_FAMILY_SOCKETWELD_FITTING, VOC.FITTING_TYPE_CAP_SW)
        self.assertIsNotNone(profile)
        self.assertEqual(profile.profile_id, "socketweld_cap")

    def test_outside_diameter_only_construction_derivable_not_required(self):
        profile = find_profile(VOC.PRODUCT_FAMILY_SOCKETWELD_FITTING, VOC.FITTING_TYPE_ELBOW_90_SW)
        self.assertNotIn("outside_diameter_mm", profile.required_dimensions)
        self.assertIn("outside_diameter_mm", profile.construction_derivable_dimensions)


class TestOletSubtypeSupportMatrix(unittest.TestCase):
    def test_weldolet_sockolet_threadolet_share_olet_body_profile(self):
        for ft in (VOC.FITTING_TYPE_WELDOLET, VOC.FITTING_TYPE_SOCKOLET, VOC.FITTING_TYPE_THREADOLET):
            profile = find_profile(VOC.PRODUCT_FAMILY_OLET, ft)
            self.assertIsNotNone(profile)
            self.assertEqual(profile.profile_id, "olet_body")
            self.assertEqual(profile.manufacturer_specific, "REQUIRED")

    def test_official_height_table_has_separate_thin_profile(self):
        for ft in (VOC.FITTING_TYPE_WELDOLET_FULL, VOC.FITTING_TYPE_WELDOLET_REDUCING):
            profile = find_profile(VOC.PRODUCT_FAMILY_OLET, ft)
            self.assertIsNotNone(profile)
            self.assertEqual(profile.profile_id, "olet_outlet_height")

    def test_unrecognized_olet_subtypes_have_no_profile(self):
        for ft in ("elbolet", "latrolet", "sweepolet", "nippolet"):
            self.assertIsNone(find_profile(VOC.PRODUCT_FAMILY_OLET, ft))


# ---------------------------------------------------------------------------
# Manufacturer-specific isolation (Sec.10, preserves Prompt 9/10 model).
# ---------------------------------------------------------------------------
class TestManufacturerIsolation(unittest.TestCase):
    def test_weldolet_without_manufacturer_context_blocked(self):
        r = _prep(product_family="olet", subtype="weldolet", standard="MSS_SP97",
                   run_size="2", branch_size="2")
        self.assertEqual(r.geometry_specification.readiness_status,
                          GeometryReadinessStatus.MANUFACTURER_CONTEXT_REQUIRED)

    def test_weldolet_with_bonney_forge_context_ready(self):
        r = _prep(product_family="olet", subtype="weldolet", standard="MSS_SP97",
                   run_size="2", branch_size="2", manufacturer_profile="Bonney Forge")
        self.assertTrue(r.is_ready())
        self.assertEqual(r.geometry_specification.engineering_object_identity["manufacturer_profile"],
                          "Bonney Forge")

    def test_no_silent_default_manufacturer(self):
        # A request with NO manufacturer_profile never silently resolves
        # as if Bonney Forge had been supplied.
        r = _prep(product_family="olet", subtype="sockolet", standard="MSS_SP97", branch_size="3")
        self.assertNotEqual(r.geometry_specification.readiness_status, GeometryReadinessStatus.GEOMETRY_READY)

    def test_official_height_table_never_requires_manufacturer_context(self):
        profile = find_profile(VOC.PRODUCT_FAMILY_OLET, VOC.FITTING_TYPE_WELDOLET_FULL)
        self.assertEqual(profile.manufacturer_specific, "NOT_APPLICABLE")


# ---------------------------------------------------------------------------
# Sec.5/8/11: SocketGeometry model.
# ---------------------------------------------------------------------------
class TestSocketGeometryModel(unittest.TestCase):
    def test_full_socket_authoritative_fields(self):
        sg = build_socket_geometry("p1", 20.0, 20.5, 12.0, 13.0, 3.0, 3.5, body_wall_thickness=5.0)
        self.assertEqual(sg.diameter.status, SOCKET_STATUS_AUTHORITATIVE)
        self.assertEqual(sg.depth.status, SOCKET_STATUS_AUTHORITATIVE)
        self.assertEqual(sg.wall_thickness.status, SOCKET_STATUS_AUTHORITATIVE)
        self.assertEqual(sg.transition.status, SOCKET_STATUS_CONSTRUCTION_DERIVED)
        validate_socket_geometry(sg)

    def test_shoulder_and_stop_always_unavailable(self):
        sg = build_socket_geometry("p1", 20.0, 20.5, 12.0, 13.0)
        self.assertEqual(sg.shoulder.status, SOCKET_STATUS_UNAVAILABLE)
        self.assertEqual(sg.stop.status, SOCKET_STATUS_UNAVAILABLE)

    def test_transition_unavailable_without_body_wall(self):
        sg = build_socket_geometry("p1", 20.0, 20.5, 12.0, 13.0)
        self.assertEqual(sg.transition.status, SOCKET_STATUS_UNAVAILABLE)

    def test_cap_socket_diameter_unavailable(self):
        sg = build_socket_geometry("cap", None, None, 12.0, 13.0)
        self.assertEqual(sg.diameter.status, SOCKET_STATUS_UNAVAILABLE)
        self.assertEqual(sg.bore.status, SOCKET_STATUS_UNAVAILABLE)
        self.assertEqual(sg.opening.status, SOCKET_STATUS_UNAVAILABLE)
        self.assertEqual(sg.depth.status, SOCKET_STATUS_AUTHORITATIVE)
        validate_socket_geometry(sg)

    def test_negative_diameter_rejected(self):
        sg = build_socket_geometry("bad", -1.0, None, 12.0, None)
        with self.assertRaises(SocketGeometryError):
            validate_socket_geometry(sg)

    def test_min_greater_than_max_rejected(self):
        sg = build_socket_geometry("bad", 20.0, 15.0, 12.0, 13.0)
        with self.assertRaises(SocketGeometryError):
            validate_socket_geometry(sg)

    def test_to_dict_serializable(self):
        sg = build_socket_geometry("p1", 20.0, 20.5, 12.0, 13.0)
        d = sg.to_dict()
        for key in ("port_id", "depth", "diameter", "bore", "wall_thickness", "shoulder", "stop",
                    "transition", "opening"):
            self.assertIn(key, d)


# ---------------------------------------------------------------------------
# Sec.6/9/12: OutletGeometry model.
# ---------------------------------------------------------------------------
class TestOutletGeometryModel(unittest.TestCase):
    def test_authoritative_and_derived_statuses(self):
        og = build_outlet_geometry(65.08, 52.5, 38.1)
        self.assertEqual(og.run_interface.status, OUTLET_STATUS_AUTHORITATIVE)
        self.assertEqual(og.branch_interface.status, OUTLET_STATUS_AUTHORITATIVE)
        self.assertEqual(og.reinforcement_body.status, OUTLET_STATUS_CONSTRUCTION_DERIVED)
        self.assertEqual(og.blend_region.status, OUTLET_STATUS_UNAVAILABLE)
        validate_outlet_geometry(og)

    def test_axis_default_is_z(self):
        og = build_outlet_geometry(65.08, 52.5, 38.1)
        self.assertEqual(og.outlet_axis, (0.0, 0.0, 1.0))

    def test_branch_exceeding_run_rejected(self):
        og = build_outlet_geometry(10.0, 50.0, 20.0)
        with self.assertRaises(OutletGeometryError):
            validate_outlet_geometry(og)

    def test_non_positive_rejected(self):
        og = build_outlet_geometry(0.0, 5.0, 20.0)
        with self.assertRaises(OutletGeometryError):
            validate_outlet_geometry(og)


# ---------------------------------------------------------------------------
# Sec.15: SocketweldBodyOutsideDiameterViaPipeRule.
# ---------------------------------------------------------------------------
class TestSocketweldBodyODRule(unittest.TestCase):
    def test_applies_with_explicit_pipe_standard(self):
        cv = _body_od("2")
        self.assertAlmostEqual(cv.value, 60.3, places=1)
        self.assertEqual(cv.rule_id, "socketweld_body_od_via_pipe_reference")

    def test_missing_pipe_standard_fails_closed(self):
        outcome = SocketweldBodyOutsideDiameterViaPipeRule().resolve(
            _RESOLVER, target_standard="ASME_B16.11", target_size_system="nps", target_size="2",
            pipe_standard=None)
        self.assertEqual(outcome.status, ConstructionRuleStatus.RULE_INPUT_MISSING)

    def test_non_nps_size_system_not_applicable(self):
        outcome = SocketweldBodyOutsideDiameterViaPipeRule().resolve(
            _RESOLVER, target_standard="ASME_B16.11", target_size_system="dn", target_size="50",
            pipe_standard="ASME_B36.10M")
        self.assertEqual(outcome.status, ConstructionRuleStatus.RULE_NOT_APPLICABLE)

    def test_never_writes_to_registry(self):
        before = len(_READER.registry.all_facts()) if hasattr(_READER.registry, "all_facts") else None
        _body_od("2")
        if before is not None:
            after = len(_READER.registry.all_facts())
            self.assertEqual(before, after)


# ---------------------------------------------------------------------------
# Sec.9: OletReinforcementEnvelopeConstructionRule.
# ---------------------------------------------------------------------------
class TestOletReinforcementRule(unittest.TestCase):
    def test_applies_for_valid_inputs(self):
        outcome = OletReinforcementEnvelopeConstructionRule().apply(
            base_od_value=65.08, branch_opening_value=52.5, height_value=38.1)
        self.assertEqual(outcome.status, ConstructionRuleStatus.RULE_APPLIED)

    def test_branch_exceeding_base_od_rejected(self):
        outcome = OletReinforcementEnvelopeConstructionRule().apply(
            base_od_value=10.0, branch_opening_value=50.0, height_value=20.0)
        self.assertEqual(outcome.status, ConstructionRuleStatus.RULE_UNSUPPORTED)

    def test_missing_input_rejected(self):
        outcome = OletReinforcementEnvelopeConstructionRule().apply(
            base_od_value=None, branch_opening_value=50.0, height_value=20.0)
        self.assertEqual(outcome.status, ConstructionRuleStatus.RULE_INPUT_MISSING)


# ---------------------------------------------------------------------------
# Sec.18: representative scenarios - actual geometry generation.
# ---------------------------------------------------------------------------
class TestSocketweldElbow(unittest.TestCase):
    def test_elbow_90_generates(self):
        spec = _sw_spec("elbow_90_sw", "2")
        result = generate_geometry(spec, product_kwargs={"body_od_value": _body_od("2")})
        self.assertTrue(result.is_generated())
        self.assertEqual(result.topology_representation,
                          TopologyRepresentation.MULTI_FEATURE_MESH_WITH_SOCKET_METADATA_NO_BOOLEAN_CUT)
        self.assertEqual({p["port_id"] for p in result.connection_ports}, {"inlet_socket", "outlet_socket"})

    def test_elbow_45_generates(self):
        spec = _sw_spec("elbow_45_sw", "2")
        result = generate_geometry(spec, product_kwargs={"body_od_value": _body_od("2")})
        self.assertTrue(result.is_generated())

    def test_elbow_without_body_od_fails_closed(self):
        spec = _sw_spec("elbow_90_sw", "2")
        result = generate_geometry(spec, product_kwargs={})
        self.assertEqual(result.generation_status, GeometryGenerationStatus.CONSTRUCTION_RULE_UNAVAILABLE)

    def test_elbow_repeatable_fingerprint(self):
        spec = _sw_spec("elbow_90_sw", "2")
        kwargs = {"body_od_value": _body_od("2")}
        r1 = generate_geometry(spec, product_kwargs=kwargs)
        r2 = generate_geometry(spec, product_kwargs=kwargs)
        self.assertEqual(r1.geometry_fingerprint, r2.geometry_fingerprint)

    def test_90_and_45_have_different_fingerprints(self):
        r90 = generate_geometry(_sw_spec("elbow_90_sw", "2"), product_kwargs={"body_od_value": _body_od("2")})
        r45 = generate_geometry(_sw_spec("elbow_45_sw", "2"), product_kwargs={"body_od_value": _body_od("2")})
        self.assertNotEqual(r90.geometry_fingerprint, r45.geometry_fingerprint)


class TestSocketweldTee(unittest.TestCase):
    def test_tee_generates_three_ports(self):
        spec = _sw_spec("tee_sw", "2")
        result = generate_geometry(spec, product_kwargs={"body_od_value": _body_od("2")})
        self.assertTrue(result.is_generated())
        self.assertEqual({p["port_id"] for p in result.connection_ports},
                          {"run_inlet_socket", "run_outlet_socket", "branch_socket"})


class TestSocketweldCross(unittest.TestCase):
    def test_cross_generates_four_ports(self):
        spec = _sw_spec("cross_sw", "2")
        result = generate_geometry(spec, product_kwargs={"body_od_value": _body_od("2")})
        self.assertTrue(result.is_generated())
        self.assertEqual({p["port_id"] for p in result.connection_ports},
                          {"run_inlet_socket", "run_outlet_socket", "branch_a_socket", "branch_b_socket"})


class TestSocketweldCoupling(unittest.TestCase):
    def test_coupling_two_open_sockets(self):
        spec = _sw_spec("coupling_sw", "2")
        result = generate_geometry(spec, product_kwargs={"body_od_value": _body_od("2")})
        self.assertTrue(result.is_generated())
        ports = {p["port_id"]: p for p in result.connection_ports}
        self.assertEqual(set(ports), {"socket_a", "socket_b"})
        for p in ports.values():
            self.assertIsNotNone(p["opening_diameter_mm"])

    def test_half_coupling_one_socket_one_closed(self):
        spec = _sw_spec("half_coupling_sw", "2")
        result = generate_geometry(spec, product_kwargs={"body_od_value": _body_od("2")})
        self.assertTrue(result.is_generated())
        ports = {p["port_id"]: p for p in result.connection_ports}
        self.assertEqual(set(ports), {"pipe_side", "closed_side"})
        self.assertIsNotNone(ports["pipe_side"]["opening_diameter_mm"])
        self.assertIsNone(ports["closed_side"]["opening_diameter_mm"])
        self.assertEqual(ports["closed_side"]["opening_diameter_provenance"],
                          OPENING_DIAMETER_PROVENANCE_NOT_MODELED)

    def test_coupling_and_half_coupling_use_own_end_to_end(self):
        c_spec = _sw_spec("coupling_sw", "2")
        h_spec = _sw_spec("half_coupling_sw", "2")
        c_len = c_spec.required_dimensions["end_to_end_mm"]["value"]
        h_len = h_spec.required_dimensions["end_to_end_mm"]["value"]
        self.assertNotEqual(c_len, h_len)


class TestSocketweldCap(unittest.TestCase):
    def test_cap_generates_no_cross_family_rule_needed(self):
        spec = _sw_spec("cap_sw", "2")
        result = generate_geometry(spec, product_kwargs={})
        self.assertTrue(result.is_generated())
        self.assertEqual(result.topology_representation,
                          TopologyRepresentation.SOLID_EXTERNAL_ENVELOPE_WITH_SOCKET_METADATA_NO_BOOLEAN_CUT)
        self.assertEqual([p["port_id"] for p in result.connection_ports], ["socket_opening"])
        self.assertIsNone(result.connection_ports[0]["opening_diameter_mm"])


class TestOletGeneration(unittest.TestCase):
    def test_weldolet_generates(self):
        spec = _olet_spec("weldolet", "2", run_size="2")
        result = generate_geometry(spec)
        self.assertTrue(result.is_generated())
        self.assertEqual(result.topology_representation,
                          TopologyRepresentation.CONSTRUCTION_DERIVED_ENVELOPE_WITH_INTERFACE_METADATA_NO_BOOLEAN_CUT)
        self.assertEqual({p["port_id"] for p in result.connection_ports}, {"run_connection", "branch_connection"})

    def test_sockolet_generates(self):
        spec = _olet_spec("sockolet", "2")
        result = generate_geometry(spec)
        self.assertTrue(result.is_generated())

    def test_threadolet_generates(self):
        spec = _olet_spec("threadolet", "2")
        result = generate_geometry(spec)
        self.assertTrue(result.is_generated())

    def test_sockolet_socket_diameter_exposed_as_metadata(self):
        r = _prep(product_family="olet", subtype="sockolet", standard="MSS_SP97", branch_size="2",
                   manufacturer_profile="Bonney Forge", dimensions=["olet_socket_diameter_mm"])
        self.assertTrue(r.is_ready())
        spec = r.geometry_specification
        result = generate_geometry(spec)
        feature_names = result.topology_summary["feature_names"]
        self.assertIn("branch_socket_diameter", feature_names)

    def test_different_subtypes_different_fingerprints(self):
        r_weld = generate_geometry(_olet_spec("weldolet", "2", run_size="2"))
        r_sock = generate_geometry(_olet_spec("sockolet", "2"))
        self.assertNotEqual(r_weld.geometry_fingerprint, r_sock.geometry_fingerprint)

    def test_repeatable_fingerprint(self):
        spec = _olet_spec("weldolet", "3", run_size="3")
        r1 = generate_geometry(spec)
        r2 = generate_geometry(spec)
        self.assertEqual(r1.geometry_fingerprint, r2.geometry_fingerprint)

    def test_different_sizes_different_fingerprints(self):
        r2in = generate_geometry(_olet_spec("weldolet", "2", run_size="2"))
        r4in = generate_geometry(_olet_spec("weldolet", "4", run_size="4"))
        self.assertNotEqual(r2in.geometry_fingerprint, r4in.geometry_fingerprint)


# ---------------------------------------------------------------------------
# Sec.17: dispatch expansion.
# ---------------------------------------------------------------------------
class TestDispatchExpansion(unittest.TestCase):
    def test_new_profiles_registered(self):
        from kgpe.geometry.kernel import _PRODUCT_DISPATCH
        for profile_id in ("socketweld_elbow_tee", "socketweld_coupling", "socketweld_cap", "olet_body"):
            self.assertIn(profile_id, _PRODUCT_DISPATCH)

    def test_olet_outlet_height_still_unwired(self):
        from kgpe.geometry.kernel import _PRODUCT_DISPATCH
        self.assertNotIn("olet_outlet_height", _PRODUCT_DISPATCH)

    def test_unsupported_olet_subtype_structured(self):
        from kgpe.geometry_spec.spec import GeometrySpecification
        spec = GeometrySpecification(readiness_status=GeometryReadinessStatus.GEOMETRY_READY,
                                      geometry_profile_id="olet_outlet_height")
        result = generate_geometry(spec)
        self.assertEqual(result.generation_status, GeometryGenerationStatus.UNSUPPORTED_GEOMETRY_PROFILE)


# ---------------------------------------------------------------------------
# Sec.14: geometry sanity/dimensional validation.
# ---------------------------------------------------------------------------
class TestGeometricSanity(unittest.TestCase):
    def test_socket_diameter_must_be_less_than_body_od(self):
        from kgpe.geometry.products import socketweld_elbow_tee as builder
        from kgpe.geometry.product_api import GeometryInputError
        spec = _sw_spec("elbow_90_sw", "2")
        # Body OD deliberately smaller than the socket bore diameter.
        bad_od = type(_body_od("2"))(
            name="outside_diameter_mm", value=1.0, unit="mm", rule_id="test", rule_version="0")
        with self.assertRaises(GeometryInputError):
            builder.build(spec, __import__("kgpe.geometry.parameters", fromlist=["GenerationParameters"])
                          .GenerationParameters(), body_od_value=bad_od)

    def test_olet_bore_must_be_less_than_base_od(self):
        from kgpe.geometry.products import olet as olet_builder
        from kgpe.geometry.product_api import GeometryInputError
        from kgpe.geometry.parameters import GenerationParameters
        spec = _olet_spec("weldolet", "2", run_size="2")
        # Corrupt the resolved dims to violate bore < base_od.
        corrupted = dict(spec.required_dimensions)
        corrupted["olet_bore_diameter_mm"] = dict(corrupted["olet_bore_diameter_mm"])
        corrupted["olet_bore_diameter_mm"]["value"] = 9999.0
        import dataclasses
        bad_spec = dataclasses.replace(spec, required_dimensions=corrupted)
        with self.assertRaises(GeometryInputError):
            olet_builder.build(bad_spec, GenerationParameters())


# ---------------------------------------------------------------------------
# Full Prompt 4-14 regression + demo (lightweight import/execution smoke -
# the authoritative full run is `python -m unittest discover -s tests`).
# ---------------------------------------------------------------------------
class TestRegressionSmoke(unittest.TestCase):
    def test_prior_prompt_modules_importable(self):
        import tests.test_prompt12_geometry_kernel  # noqa: F401
        import tests.test_prompt13_buttweld_geometry  # noqa: F401
        import tests.test_prompt14_flange_geometry  # noqa: F401

    def test_flange_pipeline_still_generates(self):
        from kgpe.geometry.cross_family import FlangeBoreViaPipeScheduleRule
        r = _prep(product_family="flange", subtype="weld_neck", standard="ASME_B16.5",
                   primary_size="2", pressure_class="150")
        self.assertTrue(r.is_ready())
        bore = FlangeBoreViaPipeScheduleRule().resolve(
            _RESOLVER, target_standard="ASME_B16.5", target_size_system="nps", target_size="2",
            pipe_standard="ASME_B36.10M", pipe_schedule="Sch40")
        result = generate_geometry(r.geometry_specification, product_kwargs={"bore_value": bore.value})
        self.assertTrue(result.is_generated())

    def test_buttweld_elbow_still_generates(self):
        r = _prep(product_family="buttweld_fitting", subtype="elbow_90_lr", standard="ASME_B16.9",
                   primary_size="6")
        self.assertTrue(r.is_ready())
        result = generate_geometry(r.geometry_specification)
        self.assertTrue(result.is_generated())

    def test_pipe_still_generates(self):
        r = _prep(product_family="pipe", standard="ASME_B36.10M", primary_size="6", schedule="Sch40")
        self.assertTrue(r.is_ready())
        result = generate_geometry(r.geometry_specification)
        self.assertTrue(result.is_generated())


if __name__ == "__main__":
    unittest.main()
