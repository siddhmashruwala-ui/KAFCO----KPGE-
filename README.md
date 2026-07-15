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
