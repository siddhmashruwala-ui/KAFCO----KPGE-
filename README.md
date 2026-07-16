# KGPE - KAFCO Geometry & Parametric Engine

Headless engine that converts validated Dimension Library data into
deterministic parametric geometry. Built to the architecture spec provided
2026-07-14 (see "Critical architectural separation" below - this is not
paraphrased, it's the actual contract this code follows).

## What KGPE is NOT

- Not KFEE (KAFCO Forging Engineering Engine - a separate system, being
  built independently, responsible for machining stock, target forging
  geometry, billet/starting-stock requirements, weights, mass balance).
- Not a renderer or CAD kernel. It outputs structured JSON (profiles +
  features); a 3D viewer / CAD adapter / ERP consumes that JSON.
- Not a source of engineering truth for dimensions it doesn't have. If a
  dimension is missing or ambiguous, KGPE returns `GEOMETRY_DEFINITION_INCOMPLETE`
  or `ENGINEERING_REVIEW_REQUIRED` instead of guessing.

## Folder layout

```
Engine/KGPE/
  kgpe/
    version.py           - RULESET_VERSION, MAPPER_VERSION, etc (bump on change)
    schema.py             - result/provenance helpers, status constants
    dimension_library.py  - reads AI-Readable/*.json, normalizes column names
    generator.py           - generate_geometry(request) - THE entry point
    cli.py                 - `python -m kgpe.cli --json '{...}'`
    rules/
      flange.py            - body + bore + bolt circle + (optional) RF marker
      pipe.py               - annular cylinder
      buttweld.py           - elbow_90 / tee / cap (simplified stub/sweep primitives)
      olet.py               - STUB: always returns INCOMPLETE (see below)
    contract/               - canonical engineering-data contract (Prompt 4,
                              Phase 2). Additive only - not yet used by any
                              of the modules above. See CANONICAL_DATA_CONTRACT.md.
      adapters/              - source adapters (Prompt 5-8): JSON -> EngineeringFact ->
                              FactRegistry. All 11 approved structured datasets are now migrated:
                              asme_b16_5_flanges.py, asme_b36_pipes.py, asme_b16_9_buttweld.py,
                              asme_b16_11_socketweld.py, mss_sp97_olets.py, jis_b2220_flanges.py,
                              jis_pipes.py, jis_buttweld.py, en_1092_flanges.py, en_pipes.py,
                              en_buttweld.py. _shared.py holds small reused utilities (safe source
                              loading, generic field/duplicate validation) - not a generic framework.
      registry_builder.py    - build_canonical_registry() (Prompt 8): loads all 11 adapters in
                              deterministic order into one FactRegistry. Not yet wired into
                              generator.py - see CANONICAL_DATA_CONTRACT.md's Prompt 8 section.
      data_layer_audit.py    - (Prompt 9) dataset-to-adapter closure inventory, coverage matrix,
                              gap classification, unresolved-conflict register, identity-collision/
                              size/rating isolation audits - all computed live from the registry.
      canonical_reader.py    - (Prompt 9) CanonicalReader: the stable read boundary for Prompt 10+.
                              Structured outcomes (EXACT_MATCH/NO_MATCH/QUARANTINED_MATCH/
                              AMBIGUOUS_MATCH/MANUFACTURER_CONTEXT_REQUIRED/etc), fail-closed
                              ambiguity handling, data-driven coverage/option discovery.
      snapshot.py            - (Prompt 9) deterministic registry fingerprint + machine-readable
                              data-layer snapshot/manifest.
  examples/demo.py         - smoke test, run after any change
  tests/test_canonical_contract.py    - automated tests for kgpe/contract/
  tests/test_asme_b16_5_ingestion.py  - automated tests for the ASME B16.5 ingestion pipeline
  tests/test_asme_pipe_ingestion.py   - automated tests for the ASME B36.10M/19M ingestion pipeline
  tests/test_asme_b16_9_ingestion.py  - automated tests for the ASME B16.9 buttweld ingestion pipeline
  tests/test_prompt8_migration.py     - automated tests for all Prompt 8 datasets + the complete registry build
  tests/test_prompt9_data_layer_closure.py - automated tests for the Prompt 9 data-layer closure/audit/freeze
  tests/test_prompt10_resolution_engine.py - automated tests for the Prompt 10 resolution engine (Phase 3)
                              (run: python -m unittest discover -s tests -v)
    resolver/               - (Prompt 10, Phase 3) Engineering Specification Resolution. Built ONLY on
                              kgpe.contract.canonical_reader/snapshot - no adapter/dimension_library import.
      request.py            - EngineeringRequest (raw external-request model, separate from EngineeringFact)
      spec.py                - ResolvedEngineeringSpecification + the 7-status ResolutionStatus vocabulary
      aliases.py             - small explicit deterministic nomenclature alias tables (no fuzzy matching)
      engine.py              - EngineeringResolver / resolve_engineering_request() - the one public entry point
```

See `CANONICAL_DATA_CONTRACT.md` for the canonical data contract
(verification statuses, provenance, units policy, quarantine behaviour,
manufacturer-specific data, schema versioning) established in Prompt 4.

## Quick start

```
cd "Dimensions and Standards/Engine/KGPE"
python examples/demo.py
python -m kgpe.cli --json "{\"product_type\":\"flange\",\"standard\":\"ASME_B16.5\",\"size\":\"2\",\"class_key\":\"150\",\"pipe_schedule\":\"Sch40\"}"
```

## Request format

```json
{"product_type": "flange", "standard": "ASME_B16.5", "size": "2", "class_key": "150", "pipe_schedule": "Sch40"}
{"product_type": "flange", "standard": "JIS_B2220", "size": 50, "class_key": "10K"}
{"product_type": "flange", "standard": "EN_1092-1", "size": 50, "class_key": "PN16", "pipe_schedule": "Series3"}
{"product_type": "pipe", "standard": "ASME_B36", "size": "6", "schedule": "Sch40", "length_mm": 6000}
{"product_type": "buttweld_fitting", "fitting_type": "elbow_90", "standard": "ASME_B16.9", "size": "6"}
{"product_type": "buttweld_fitting", "fitting_type": "tee", "standard": "ASME_B16.9", "size": "4"}
{"product_type": "buttweld_fitting", "fitting_type": "cap", "standard": "ASME_B16.9", "size": "4"}
```

Every result has `status` (`OK` / `GEOMETRY_DEFINITION_INCOMPLETE` /
`ENGINEERING_REVIEW_REQUIRED`), `geometry` (null unless OK), `provenance`
(source standard/file, dimension library version, ruleset/mapper version,
a deterministic `input_hash`), and `warnings` (always check these even on OK).


## Contract with KFEE (for whoever/whichever session is building it)

Per the architecture doc, the pipeline is:

```
Dimension Library -> KFEE dimension adapter/resolver -> KFEE engineering
calculations -> structured geometry states -> KGPE parametric geometry
generation -> CAD/3D/ERP/MES/visualization
```

KGPE v1 (this build) only implements `ENGINEERING_STATE_FINISHED` (the
"FINISHED_MACHINED_COMPONENT" state), generated directly from the
Dimension Library - it does not yet consume anything from KFEE, because
KFEE's output schema didn't exist yet when this was built.

`kgpe/schema.py` already defines the other 3 state constants KFEE will
eventually drive:
- `ENGINEERING_STATE_MACHINING_ENVELOPE` (MINIMUM_MACHINING_STOCK_ENVELOPE)
- `ENGINEERING_STATE_TARGET_FORGING` (TARGET_MANUFACTURING_FORGING_GEOMETRY)
- `ENGINEERING_STATE_STARTING_STOCK` (STARTING_STOCK_CUT_PIECE)

**Proposed hand-off contract** (not yet implemented - flag if KFEE's real
output differs): KFEE should call KGPE (or be called by a shared
orchestrator) with a request shaped like the ones above PLUS an
`engineering_state` key and a `state_dimensions` override block, e.g.:

```json
{"product_type": "flange", "standard": "ASME_B16.5", "size": "2", "class_key": "150",
 "engineering_state": "TARGET_MANUFACTURING_FORGING_GEOMETRY",
 "state_dimensions": {"outside_dia_mm": 168.0, "thickness_mm": 22.0, "bore_dia_mm": 40.0},
 "kfee_provenance": {"kfee_version": "...", "calculation_id": "..."}}
```

i.e. KFEE supplies the VALUES for that state (it owns the engineering
calculation), KGPE only turns `state_dimensions` into the same kind of
geometry/feature output it already produces for the finished state - it
must never calculate machining stock or forging losses itself. This isn't
wired up yet (no `state_dimensions` handling in `rules/*.py` today) -
whoever finishes the integration should extend each rule's `generate()`
to accept and geometrize a `state_dimensions` override, and add
`kfee_provenance` into the output's `provenance` block so a generated
shape is always traceable back to which KFEE calculation produced it.

## Known v1 gaps (deliberate, not oversights)

- Flange hub/neck taper is not modeled - the Dimension Library doesn't yet
  carry hub diameter for any of the 3 flange standards. Body is a flat
  plate + bore + bolt pattern (+ RF diameter marker where available).
- Raised-face **height** is never modeled, only diameter (where the source
  standard publishes it - ASME B16.5's JSON file doesn't).
- Buttweld tee/elbow/cap use simplified stub/sweep primitives, not true
  boolean-intersection solids.
- Olets return `GEOMETRY_DEFINITION_INCOMPLETE` unconditionally - no
  geometry rule has been designed for branch-intersection shapes yet.
- Reducers are not wired into `generator.py` yet (dimension_library.py has
  no `get_buttweld_reducer()` adapter yet either) - next thing to add.
- Facing types other than RF (FF, RTJ, lap-joint) are accepted as a
  request field but not yet differentiated in geometry.

## Versioning discipline

Bump `RULESET_VERSION` in `version.py` whenever a `rules/*.py` file's logic
changes, `MAPPER_VERSION` whenever `dimension_library.py`'s field mapping
changes, and `DIMENSION_LIBRARY_ADAPTER_VERSION` whenever the JSON file
layout it reads changes. All three ride along in every result's
`provenance` block specifically so a downstream consumer can tell whether
a previously-generated geometry is still valid or needs regenerating.


## Prompt 11 addendum (Phase 3 completion - geometry handoff)

```
    geometry_spec/          - (Prompt 11, Phase 3 completion) Engineering Specification
                              Orchestration and Geometry Handoff. Built ONLY on kgpe.resolver/
                              kgpe.contract - no adapter/dimension_library import, no geometry generated.
      identity.py            - EngineeringObjectIdentity (immutable, only-applicable-fields)
      dimension_bundle.py     - ResolvedDimension / EngineeringDimensionBundle (traceable, not bare floats)
      readiness.py            - GeometryReadinessStatus (7-status vocabulary)
      profile.py               - GeometryProfile + PROFILE_REGISTRY (10 profiles, built from live inspection)
      spec.py                  - GeometrySpecification (the geometry-INPUT contract)
      fingerprint.py            - deterministic geometry-specification fingerprint (SHA-256)
      compiler.py                - GeometrySpecificationCompiler / compile_geometry_specification()
      orchestration.py            - prepare_geometry_specification() / batch semantics / BatchStatus
      discovery.py                 - completed first-class discovery (families/standards/subtypes/
                                     sizes/ratings/manufacturer profiles/dimensions/pairs)
      coverage.py                   - geometry profile coverage matrix, construction-rule requirement
                                     register, existing-geometry compatibility mapping
  tests/test_prompt11_geometry_handoff.py - automated tests for kgpe/geometry_spec/ (90 tests,
                              covers all 20 Sec.25 representative scenarios)
```

This completes the Phase 3 architecture:
`EngineeringRequest -> EngineeringResolver -> ResolvedEngineeringSpecification`
`-> GeometrySpecificationCompiler -> GeometrySpecification -> (future Geometry Kernel)`

See `CANONICAL_DATA_CONTRACT.md`'s Prompt 11 section for the full design
notes, including the real gaps this prompt's live inspection found
(pipe bore, ASME/EN flange bore, buttweld reducer per-end OD, socket-weld
body OD, olet manufacturer-only body dims) - all registered, none solved
here. Prompt 12 begins the parametric geometry kernel.


## Prompt 12 addendum (Phase 4 - parametric geometry kernel)

```
    geometry/                - (Prompt 12, Phase 4) Parametric Geometry Kernel and
                              Deterministic Construction Rules. Consumes ONLY a compiled
                              GeometrySpecification (kgpe.geometry_spec) - never a raw
                              request, never source JSON, never dimension_library.py.
                              Strictly additive - never touches generator.py/rules/*.py.
      version.py              - GEOMETRY_KERNEL_VERSION and related schema version constants
      policy.py                - coordinate convention (+Z axis, right-handed, mm units),
                                 centralized numerical tolerances
      primitives.py              - pure-stdlib math primitives (vectors, circle_ring,
                                 arc_sweep_frames, rotate_about_axis) - no numpy/CAD dependency
      mesh.py                      - Mesh: deterministic indexed triangle mesh representation
      builders.py                  - build_hollow_cylinder() (pipe), build_arc_swept_solid()
                                 (elbow) - feature-tagged (Sec.11) mesh construction
      construction_value.py         - ConstructionValue (DERIVED_CONSTRUCTION_VALUE provenance)
      construction_rules.py          - ConstructionRule framework + PipeBoreConstructionRule
                                 (bore = OD - 2*WT, fully validated, versioned)
      cross_family.py                 - CrossFamilyDependencyRule framework + one proof-of-
                                 concept rule (FlangeBoreViaPipeScheduleRule) - not wired
                                 into kernel dispatch this prompt
      tessellation.py                  - deterministic segment-count policy/validation
      parameters.py                     - GenerationParameters (display-only, never engineering
                                 truth - e.g. DEFAULT_PIPE_SEGMENT_LENGTH_MM)
      validation.py                      - validate_mesh_structure() / validate_dimensions()
      measurement.py                      - measure_radial_distance/axial_length/bend_radius -
                                 measures the ACTUAL generated mesh, never assumed correct
      fingerprint.py                       - compute_geometry_fingerprint() - SHA-256 over
                                 rounded vertices/faces + units + convention + kernel version
                                 + generation parameters (excludes timestamps/object identity)
      result.py                             - GeometryResult + 7-status GeometryGenerationStatus
      product_api.py                         - GeometryInputError / ConstructionRuleUnavailableError
                                 / ProductGeometryBuild (kernel<->product contract)
      products/pipe.py                        - Reference Product A: hollow cylindrical pipe segment
      products/buttweld_elbow.py                - Reference Product B: ASME B16.9 90-deg LR elbow
                                 (arc-sweep primitive proof)
      kernel.py                                  - GeometryKernel.generate() / generate_geometry() -
                                 the ONE public entry point; never raises (Sec.5)
      pipeline.py                                 - run_pipeline(): EngineeringRequest ->
                                 prepare_geometry_specification() -> GeometryKernel.generate()
                                 in one call, preserving every stage result/fingerprint
  tests/test_prompt12_geometry_kernel.py - automated tests for kgpe/geometry/ (90 tests,
                              covers the 25 representative scenarios)
```

This completes the Phase 4 kernel foundation:
`GeometrySpecification -> GeometryKernel.generate() -> GeometryResult`

Reference Product A (pipe) proves the straight-extrusion/hollow-cylinder
path and the `PipeBoreConstructionRule`; Reference Product B (ASME B16.9
90-degree long-radius elbow) proves the arc-sweep/revolution path with no
construction rule needed (`centre_to_end_mm` IS the bend radius by the
standard's own definition). Both are demonstrated end-to-end across all
three standard families the canonical data layer covers (ASME, JIS, EN).

**Verified this prompt:** all 25 representative scenarios pass; 495 total
tests (405 Prompt 4-11 + 90 new) pass; demo unchanged; no geometry-spec/
resolver/canonical-data-layer file modified; `generator.py`/`rules/*.py`
untouched; data-layer fingerprint unchanged at
`9238ab3cb896101c545450df6f0ff070301b4ba68117771b4105e87606c2c873`.


## Prompt 13 addendum (Phase 4 - core ASME B16.9 buttweld geometry expansion)

```
    geometry/ports.py            - ConnectionPort model (position, outward direction,
                              nominal size role, opening-diameter provenance) + validate_port(s)
    geometry/wall_context.py       - WallContext (pipe_standard + exactly one of
                              pipe_schedule/pipe_wall_designation) - additive, carries wall
                              context to buttweld builders WITHOUT touching frozen models
    geometry/reducer_rules.py       - ReducerPerEndOutsideDiameterRule: resolves large-end
                              and small-end OD independently (intra-family, per-role, never
                              cross-family) - preserves quarantine per end, never swaps ends
    geometry/transition_rules.py      - TeeBranchBlendingRule, CapProfileConstructionRule,
                              ConcentricReducerTransitionRule, EccentricReducerOffsetRule -
                              all versioned, all explicitly construction-derived (never
                              claimed as standard-authoritative contours)
    geometry/cross_family.py (+)       - appended ButtweldWallViaPipeScheduleRule (same
                              pattern as Prompt 12's FlangeBoreViaPipeScheduleRule)
    geometry/construction_rules.py (+)   - appended CapLengthSelectionRule (H vs H1,
                              fails closed when wall context ambiguous/missing)
    geometry/builders.py (+)              - build_arc_swept_hollow_solid, build_solid_cylinder,
                              build_cap_solid, build_frustum_solid, build_tee_multi_feature
                              (deterministic multi-feature mesh, NO boolean union - honestly
                              declared non-manifold at the run/branch intersection)
    geometry/products/buttweld_elbow.py (rewritten) - generalized across 90LR/45LR/90-3D/
                              45-3D/90SR via subtype-driven bend-angle/radius lookup (not
                              copy-pasted); added hollow mode (annular sweep) when wall
                              context supplied; preserves quarantine blocking on OD
    geometry/products/tee.py                - equal tee: run + branch as independent solid
                              cylinders, rigidly placed, 3 ports (run inlet/run outlet/branch)
    geometry/products/cap.py                 - cap: H/H1 length selection + constructed
                              dome profile, 1 open-end port
    geometry/products/reducer.py              - concentric + eccentric reducer: per-end OD
                              dependency, linear-conical transition, eccentric flat-on-bottom
                              default orientation (documented, never silently rotated)
    geometry/result.py (+)                     - TopologyRepresentation vocabulary
                              (HOLLOW_SWEPT_SOLID / SOLID_EXTERNAL_ENVELOPE /
                              DETERMINISTIC_MULTI_FEATURE_MESH_NON_MANIFOLD_AT_INTERSECTION)
                              + GeometryResult.connection_ports
    geometry/kernel.py (+)                       - product_kwargs param (resolver-dependent
                              construction values must be resolved by the CALLER, never
                              by the kernel itself - preserves Prompt 12's architectural rule)
  tests/test_prompt13_buttweld_geometry.py - 80 tests (wall context, per-end OD rule,
                              ports, transition rules, elbow generalization/hollow/quarantine,
                              tee/cap/reducer geometry, dispatch, end-to-end pipelines,
                              topology honesty, fingerprint/rule-version reproducibility,
                              Prompt 12 backward compatibility, full regression + demo)
```

**One frozen-file exception (documented):** `geometry_spec/profile.py`'s
`PROFILE_BUTTWELD_REDUCER` was bumped v1->v2 - `outside_diameter_mm` removed
from `required_dimensions` (kept in `construction_derivable_dimensions`),
because requiring it made `GEOMETRY_READY` structurally unreachable for
every reducer request. This was a genuine blocking defect in Prompt 11,
not a redesign. `geometry_spec/coverage.py`'s reducer register entry and
5 tests in `test_prompt11_geometry_handoff.py` were corrected to match.

**Verified this prompt:** all 40 representative scenarios pass; 575 total
tests (405 Prompt 4-11 + 90 Prompt 12 + 80 new) pass; demo unchanged;
no engineering-source/CRM/JS/HTML file, `generator.py`, or `rules/*.py`
file modified; data-layer fingerprint unchanged at
`9238ab3cb896101c545450df6f0ff070301b4ba68117771b4105e87606c2c873`.
Flange, socketweld, olet geometry and the hologram viewer remain
out of scope - deferred to later prompts per the 20-prompt plan.


## Prompt 14 addendum (Phase 4 - ASME B16.5 / JIS B2220 / EN 1092-1 flange geometry expansion)

```
    geometry/bolt_pattern.py           - BoltPattern model (bolt-circle diameter,
                              hole diameter, count, centre, axis, deterministic angular-zero
                              + equal spacing, ordered hole centres) + build_bolt_pattern()/
                              validate_bolt_pattern() - deterministic, serializable, never an
                              unstructured coordinate list
    geometry/mating_interface.py         - MatingInterface metadata model (face centre/
                              normal, OD, bolt-circle, bolt-hole count/diameter, face type)
                              + FACE_TYPE_NOT_TRACKED/RAISED_FACE/FLAT_FACE vocabulary -
                              metadata only, no assembly logic
    geometry/products/flange.py           - weld-neck flange builder: hollow annular body
                              when bore known, solid external envelope when not; bolt
                              holes represented as feature metadata only (never boolean-cut
                              into the mesh); bore via direct optional dimension (JIS) or
                              externally-resolved FlangeBoreViaPipeScheduleRule construction
                              value (ASME, passed in via product_kwargs) or unavailable (EN);
                              raised-face and hub exposed as honest partial/unavailable
                              metadata features, never fabricated
    geometry/cross_family.py (docstring only) - FlangeBoreViaPipeScheduleRule inspected
                              and confirmed already production-ready (explicit context
                              required, fails closed, no registry write); deliberately NOT
                              extended to DN/EN_1092-1 this prompt (anti-scope-creep)
    geometry/result.py (+)                    - two new TopologyRepresentation values:
                              HOLLOW_ANNULAR_BODY_WITH_BOLT_HOLE_METADATA_NO_BOOLEAN_CUT,
                              SOLID_EXTERNAL_ENVELOPE_WITH_BOLT_HOLE_METADATA_NO_BOOLEAN_CUT
    geometry/kernel.py (+)                     - "flange_weld_neck" wired into
                              _PRODUCT_DISPATCH
    geometry/__init__.py (+)                    - bolt_pattern/mating_interface/
                              product_flange exports; package schema version bumped to
                              "geometry-kernel-package-2026.07.16"
  tests/test_prompt14_flange_geometry.py - 107 tests (coverage inspection, subtype
                              matrix, cross-standard isolation, bolt-pattern model/
                              placement/validation/fingerprint-sensitivity, bore policy
                              incl. FlangeBoreViaPipeScheduleRule, raised-face/hub honesty,
                              blind-flange non-support, topology honesty, dispatch, all 50
                              scenarios, full Prompt 4-13 regression, demo unchanged)
```

**One frozen-file exception (documented, same pattern as Prompt 13's
reducer fix):** `geometry_spec/profile.py`'s `PROFILE_FLANGE_WELD_NECK`
bumped v1->v2 - `bore_diameter_mm` removed from `required_dimensions`
(kept in `optional_dimensions` and `construction_derivable_dimensions`),
because requiring a dimension that is genuinely unresolvable for 2 of 3
standards (ASME without cross-family context, EN entirely) made
`GEOMETRY_READY` structurally unreachable for those standards. This is a
genuine blocking defect, not a redesign. `geometry_spec/coverage.py`'s
flange-bore register entry and 7 tests in
`test_prompt11_geometry_handoff.py` were corrected to match; all 92
Prompt 11 tests still pass.

**Honest coverage findings:** only the weld-neck subtype has ever been
recorded in canonical data for any of the 3 standards - blind, slip-on,
and other flange_type values return no canonical facts and no geometry
profile (`find_profile("flange", "blind")` is `None`); a blind-subtype
request fails at `ENGINEERING_RESOLUTION`/`UNSUPPORTED_REQUEST`, before
geometry is ever attempted. Raised-face diameter is known only for JIS
(and only when explicitly requested); RF height has zero facts for any
standard, so RF geometry is never generated - only metadata is exposed.
Hub/neck dimensions have zero facts for any standard - hub geometry is
never attempted.

**Verified this prompt:** all 50 representative scenarios pass; 684 total
tests (575 Prompt 4-13 + 107 new + 2 Prompt 12/13 tests updated to use a
still-genuinely-unwired profile id now that flange dispatch is wired)
pass; demo unchanged; no engineering-source/CRM/JS/HTML/KFEE file,
`generator.py`, or `rules/*.py` file modified; data-layer fingerprint
unchanged at
`9238ab3cb896101c545450df6f0ff070301b4ba68117771b4105e87606c2c873`.
Blind/slip-on flange geometry, socketweld, olets, and the hologram viewer
remain out of scope - deferred to later prompts per the 20-prompt plan.


## Prompt 15 addendum (Phase 4 - ASME B16.11 socket-weld and MSS SP-97 branch-outlet geometry, final product family)

```
    geometry/socket_geometry.py         - SocketGeometry model (depth, diameter, bore, wall
                              thickness, shoulder, stop, transition, opening) - each feature
                              explicitly AUTHORITATIVE/CONSTRUCTION_DERIVED/UNAVAILABLE;
                              shoulder/stop ALWAYS unavailable (J_mm/socket_wall_min_at_
                              bottom_mm has zero ingested facts anywhere); metadata only,
                              never boolean-cut into a mesh
    geometry/outlet_geometry.py          - OutletGeometry model (run interface, branch
                              interface, outlet axis, outlet opening, reinforcement body,
                              blend region) for MSS SP-97 weldolet/sockolet/threadolet;
                              blend_region always unavailable (no fillet data published)
    geometry/cross_family.py (+)          - appended SocketweldBodyOutsideDiameterViaPipeRule
                              (same od_req pattern as FlangeBoreViaPipeScheduleRule) - ASME
                              B16.11 publishes no fitting-body OD at all; resolved from the
                              mating pipe's own OD via an explicit pipe_standard
    geometry/construction_rules.py (+)      - appended OletReinforcementEnvelopeConstructionRule
                              (frustum envelope base_OD -> branch bore over height -
                              explicitly construction-derived, never MSS-published)
    geometry/builders.py (+)                 - build_two_arm_multi_feature (socket-weld
                              elbow, angled arms), build_cross_multi_feature (socket-weld
                              cross, 4 arms)
    geometry/products/socketweld_elbow_tee.py - 90/45deg elbow, tee, cross (one profile,
                              internally subtype-dispatched); external body envelope via
                              cross-family pipe OD, socket cavities as feature metadata only
    geometry/products/socketweld_coupling.py   - coupling (2 open sockets) / half-coupling
                              (1 socket + 1 documented closed_side port, no opening -
                              mirrors Prompt 14's blind-flange precedent)
    geometry/products/socketweld_cap.py         - cap: own authoritative body OD
                              (cap_body_diameter_mm), no cross-family rule needed; socket
                              diameter genuinely UNAVAILABLE (no such column in the source)
    geometry/products/olet.py                    - weldolet/sockolet/threadolet: frustum
                              envelope via OletReinforcementEnvelopeConstructionRule;
                              manufacturer-gated (Bonney Forge, MANUFACTURER_CONTEXT_REQUIRED
                              if absent); sockolet's extra socket-diameter fact exposed as
                              metadata only, never used as the frustum's small-end radius
    geometry/result.py (+)                        - 3 new TopologyRepresentation values:
                              SOLID_EXTERNAL_ENVELOPE_WITH_SOCKET_METADATA_NO_BOOLEAN_CUT,
                              MULTI_FEATURE_MESH_WITH_SOCKET_METADATA_NO_BOOLEAN_CUT,
                              CONSTRUCTION_DERIVED_ENVELOPE_WITH_INTERFACE_METADATA_NO_BOOLEAN_CUT
    geometry/kernel.py (+)                         - 4 new dispatch entries: socketweld_elbow_tee,
                              socketweld_coupling, socketweld_cap, olet_body
  tests/test_prompt15_socketweld_olet_geometry.py - 64 tests (coverage inspection,
                              subtype matrices, manufacturer isolation, SocketGeometry/
                              OutletGeometry model, cross-family OD rule, olet reinforcement
                              rule, all representative scenarios, dispatch, geometric sanity,
                              full Prompt 4-14 regression, demo unchanged)
```

**Two frozen-file exceptions (documented, same pattern as Prompts 13/14):**
`geometry_spec/profile.py`'s `PROFILE_SOCKETWELD_ELBOW_TEE` bumped v1->v2
(`outside_diameter_mm` removed from `required_dimensions`, retained in
`construction_derivable_dimensions` only) - ASME B16.11 has zero
`outside_diameter_mm` facts anywhere under `product_family=
'socketweld_fitting'`, so requiring it made `GEOMETRY_READY` structurally
unreachable for every elbow/tee/cross request - the identical defect
shape as the Prompt 13 reducer and Prompt 14 flange-bore fixes. A NEW
profile, `PROFILE_SOCKETWELD_COUPLING`, was added for coupling_sw/
half_coupling_sw (no Prompt 11 profile ever covered this subtype pair).
`geometry_spec/coverage.py`'s socketweld construction-rule register entry
was updated (`blocks_geometry_generation_now: True -> False`, `resolved_
in` added) and 3 tests in `test_prompt11_geometry_handoff.py` were
corrected to match (all 95 Prompt 11 tests still pass).

**Verified this prompt:** all 18 representative scenarios (socket elbow/
tee/cross/coupling/half-coupling/cap, weldolet/sockolet/threadolet,
manufacturer-context-required, unsupported olet subtypes, missing-pipe-
context fails closed, deterministic fingerprints) pass; 748 total tests
(684 Prompt 4-14 + 64 new) pass; demo unchanged; no engineering-source/
CRM/JS/HTML/KFEE file, `generator.py`, or `rules/*.py` file modified;
data-layer fingerprint unchanged at
`9238ab3cb896101c545450df6f0ff070301b4ba68117771b4105e87606c2c873`.
elbolet/latrolet/sweepolet/nippolet remain UNSUPPORTED_BY_CANONICAL_DATA
(zero canonical coverage, confirmed live - never fabricated). With this
prompt, every structured engineering dataset already present in KGPE has
a corresponding deterministic geometry implementation - the hologram
viewer, export formats, and assemblies remain out of scope, deferred to
later prompts per the 20-prompt plan.
