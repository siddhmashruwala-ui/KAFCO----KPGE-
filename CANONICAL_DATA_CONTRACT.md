# KGPE Canonical Engineering-Data Contract (Prompt 4 / Phase 2)

This documents the `kgpe/contract/` package: the canonical schema,
verification-status model, provenance model, units policy, applicability
model, and quarantine mechanism that KGPE's Phase 2-4 work will build on.

It is purely additive. Nothing in `kgpe/schema.py`, `kgpe/generator.py`,
`kgpe/dimension_library.py`, or `kgpe/rules/*.py` was changed or now
depends on this package - see "Relationship to existing code" below.

## Why this exists

Prompts 1-3 found real engineering data (verified in Prompt 3) sitting
inside the JS CRM dashboard with no formal representation of: where a
number came from, how sure we are it's right, whether it's a standard
fact, a derived rule, a construction estimate, or a rendering-only value.
That ambiguity is exactly what produced the Prompt 2/3 "flange thickness
conflict" investigation (which turned out not to be a conflict at all -
two genuinely different ASME B16.5 figures with no field distinguishing
them). `kgpe/contract/` gives every future engineering value a place to
carry that context explicitly, so this kind of multi-prompt investigation
doesn't have to happen again for the same reason.

## The four record types

| Type | Module | Represents | Default status |
|---|---|---|---|
| `EngineeringFact` | `model.py` | A value tied to a standard/applicability | any of the 8 statuses |
| `DerivedRule` | `model.py` | A verified deterministic rule, not a bare value | `VERIFIED_DERIVED_RULE` |
| `ConstructionParameter` | `model.py` | A value needed to build geometry but never standard-tabulated | `CONSTRUCTION_PARAMETER` |
| `RenderingParameter` | `model.py` | A visual-only value (color, easing curve, etc) | `VISUAL_ONLY` |

These are four flat dataclasses, not a class hierarchy - each maps 1:1 to
one of the four kinds of engineering claim Prompt 4 Sec.3 required KGPE to
keep separate.

## Verification statuses (`verification.py`)

The 8 statuses from Prompt 3: `VERIFIED_AUTHORITATIVE`,
`VERIFIED_DERIVED_RULE`, `VERIFIED_MANUFACTURER_SPECIFIC`,
`CONSTRUCTION_PARAMETER`, `VISUAL_ONLY`, `QUARANTINED_CONFLICT`,
`QUARANTINED_UNVERIFIED`, `DEPRECATED_LEGACY`.

Policy implemented in `is_usable_as_authoritative()`:
- `VERIFIED_AUTHORITATIVE` / `VERIFIED_DERIVED_RULE` - always usable.
- `VERIFIED_MANUFACTURER_SPECIFIC` / `CONSTRUCTION_PARAMETER` - usable only
  with an explicit opt-in flag (`allow_manufacturer_specific=True` /
  `allow_construction_parameter=True`).
- `VISUAL_ONLY` / `QUARANTINED_CONFLICT` / `QUARANTINED_UNVERIFIED` /
  `DEPRECATED_LEGACY` - never usable as authoritative, no opt-in can
  change this.

## Provenance (`model.py` - `EngineeringFactProvenance`)

Records source name/type, standard designation, standard edition (only if
genuinely known - never fabricated), source file/URL, original field
name, transcription/verification method, verification sources, and notes.
Distinct from `kgpe/schema.py`'s `make_provenance()`, which stamps a
*generated geometry result* with ruleset/mapper/dimlib version + an input
hash - that is provenance of a computation, not of a raw engineering fact.
Both are legitimately "provenance"; they answer different questions and
are kept as two separate structures on purpose.

## Units policy (`units.py`)

Canonical units: millimetres for length, kilograms for mass, degrees for
angle - matching every existing `*_mm` field already in the Dimension
Library. `Quantity(value, unit, ...)` requires `unit` explicitly - there
is no default, so a bare number can never be constructed. `Quantity.
from_source(source_value, source_unit, canonical_unit)` converts while
preserving the original source value/unit for provenance (built for the
JS CRM's inches-based tables, which this prompt does NOT migrate).

## Applicability (`applicability.py`)

A flat dataclass (`product_family`, `product_type`, `flange_type`,
`fitting_type`, `standard`, `standard_edition`, `class_key`, `schedule`,
`nps`, `dn`, `jis_size`, `reducing_pair`, `run_branch_pair`,
`manufacturer_profile`) with a simple exact-match `.matches(**filters)` -
deliberately not a rules engine.

## Missing-data / error semantics (`model.py`)

Six distinct exception classes under `KGPEDataError`, each with a stable
`.code`: `DimensionNotApplicable`, `DimensionUnavailable`,
`DimensionQuarantined`, `CombinationNotFound`, `UnsupportedProductFamily`,
`MalformedInput`. `CombinationNotFound` is the canonical-layer equivalent
of `dimension_library.py`'s existing `DimNotFound` (not a replacement for
it - `DimNotFound` still handles that case for the live lookups
unchanged).

## Quarantine mechanism (`model.py` - `FactRegistry`)

`FactRegistry.query()` raises `CombinationNotFound` if nothing matches at
all, and `DimensionQuarantined` if matches exist but none are usable
under the given opt-ins. Quarantined/visual/deprecated records are only
reachable via the separately-named `get_quarantined()` inspector, so a
caller can never stumble into them through the normal lookup path. Proven
in `tests/test_canonical_contract.py` against the two real items Prompt 3
quarantined: the NPS14/Class150 raised-face-diameter conflict (JS
419.1mm vs Texas Flange 412.75mm) and the Class-300 hub-length gap.

## Manufacturer-specific data

`VERIFIED_MANUFACTURER_SPECIFIC` facts (e.g. the Hackney-Ladish cap-weight
data found in the JS CRM) are excluded from a standard-only `query()`
unless the caller passes `allow_manufacturer_specific=True` - a generic
"give me the standard dimension" request never silently receives one
manufacturer's numbers as if they were the standard.

## Derived rules (`derived_rules.py`)

Two of Prompt 3's fully-verified rules are implemented as `DerivedRule`
instances to prove the interface: raised-face height by pressure class,
and the (unconditional / single-band) outside-diameter and bolt-circle
general tolerances. The other 6 tolerance families are deliberately left
unported - they involve asymmetric +/- bands, and re-typing all 8 from
memory in this prompt risked the exact transcription error this project
exists to prevent.

## Schema versioning

`kgpe.contract.CANONICAL_SCHEMA_VERSION` versions the shape of this
contract itself, kept separate from `kgpe.version.KGPE_VERSION` (overall
software version) and `RULESET_VERSION` / `MAPPER_VERSION` /
`DIMENSION_LIBRARY_ADAPTER_VERSION` (which version geometry-generation
logic, not this data contract). Individual dataset versions and standard
editions are NOT currently tracked in the AI-Readable JSON files - this
is a real, honestly-reported gap (see Prompt 4 report), not fabricated
here.

## Relationship to existing code

`kgpe/contract/` is a new subpackage. It does not import from, get
imported by, or change the behaviour of `kgpe/schema.py`,
`kgpe/generator.py`, `kgpe/dimension_library.py`, `kgpe/cli.py`, or any
`kgpe/rules/*.py` file. The one place it reads existing code is
`vocabulary.known_dimensional_standards()`, which reads (never writes)
`dimension_library.py`'s own standard-ID registries so the vocabulary list
can't silently drift out of sync with what's actually implemented.

No dataset was migrated into this contract in Prompt 4 beyond the
quarantine/manufacturer/construction-parameter fixtures used in the test
suite - see the Prompt 4 report's "Exact Recommended Scope for Prompt 5"
for what's next.

## Prompt 5: production ingestion (ASME B16.5 reference adapter)

### Source-adapter architecture

`kgpe/contract/adapters/` holds source-format-specific adapters. Each one
follows: **Source JSON -> adapter -> `EngineeringFact` records ->
`FactRegistry`**. `FactRegistry` has zero knowledge of any source's JSON
shape; an adapter has zero knowledge of `FactRegistry`'s internals beyond
`add()`/`add_checked()`. Future adapters (ASME B36.10/19, B16.9, JIS, EN,
MSS) can be added as new modules in this package without touching
`FactRegistry` or any existing adapter.

`adapters/asme_b16_5_flanges.py` is the reference implementation:
`_load_source()` re-uses `dimension_library.DIMLIB_ROOT` +
`FLANGE_FILES["ASME_B16.5"]` (the exact path the live lookups already
use), `_validate_top_level()`/`_validate_row()` check structure before
anything is ingested (collecting ALL problems, not failing at the first),
and `ingest_asme_b16_5_flanges(registry=None)` builds 6 `EngineeringFact`
records per source row (outside diameter, weld-neck thickness, bolt
circle, bolt-hole diameter, bolt count, bolt-size designation) and loads
them via `add_checked()`.

`adapters/legacy_crm_quarantine_fixture.py` is explicitly NOT a source
adapter - it has no JSON to read. It hand-builds 3 `EngineeringFact`
records from Prompt 3's own audit findings (the NPS14/Class150
raised-face conflict, the Class-300 hub-length gap) so the quarantine
mechanism can be proven against real historical data without touching
the CRM JavaScript or fabricating a fake ASME source.

### Canonical identity and duplicate/conflict handling

`EngineeringFact.identity_key()` returns a deterministic tuple
(dimension name + every applicability field) - never a random UUID, never
dependent on object identity or dict ordering. `identity_hash()` is a
short SHA-256 digest of that tuple for indexing convenience; the tuple
itself remains the inspectable source of truth.

`FactRegistry.add_checked(fact)` uses this identity for duplicate
detection: an exact duplicate (same identity, same value + status) is a
silent no-op returning the existing record; a **conflicting** duplicate
(same identity, different value) raises `ConflictingDuplicateFact` -
never silently overwritten. The quarantine fixture deliberately bypasses
this via plain `add()`, because it *wants* two already-known-conflicting
historical values stored side by side.

### NPS and pressure-class normalization

`kgpe/contract/normalization.py` (new module, no Prompt 4 dataclass
changed): `normalize_nps()` accepts source variants ("1 1/2", "1-1/2")
and always emits one canonical dash/slash string; `nps_sort_key()` returns
a `fractions.Fraction` (exact rational, never float) for deterministic
sorting only - the canonical *identity* stays the string.
`normalize_pressure_class()` collapses "150"/150/"Class 150"/"CL150" into
one canonical string per rating system (ASME class, PN, JIS K).

### Registry indexing

`FactRegistry` now keeps a `dimension_name -> [facts]` dict so `query()`
filters only within one dimension's bucket instead of the whole registry.
At current scale (792 facts from the full ASME B16.5 ingestion) this is
sufficient - a full secondary index by standard/class/NPS was evaluated
and rejected as premature (Prompt 5 Sec. 18: "do not prematurely build a
database").

### Verified result

Ingesting the full ASME B16.5 JSON produces 132 (class, NPS) combinations
x 6 facts = 792 `EngineeringFact` records, cross-checked field-by-field
against the existing live `dimension_library.get_flange()` lookup: 792/792
exact matches, 0 mismatches, 0 not-comparable. See
`tests/test_asme_b16_5_ingestion.py`.

## Prompt 6: ASME pipe ingestion (B36.10M/19M) - schedule-based resolution

### Actual source structure (inspected, not assumed)

One JSON file (`Pipes/ASME_B36.10M_B36.19M_Pipes.json`) covers BOTH
standards as two separate top-level arrays - `B36_10M_wall_thickness_mm`
(36 rows, NPS 1/8-48, 14 schedule columns) and `B36_19M_wall_thickness_mm`
(18 rows, NPS 1/8-12, 4 S-suffix schedule columns). The file's own
`"standards"` dict names them `"ASME_B36.10M"` / `"ASME_B36.19M"`
explicitly - used verbatim as this adapter's `standard` identity. Unlike
the flange source, this file has no top-level `"units"` key.

### Standard identity: never merged

`kgpe/contract/adapters/asme_b36_pipes.py` tags every fact's
`Applicability.standard` with `"ASME_B36.10M"` or `"ASME_B36.19M"` -
never a combined `"ASME pipe"` identity. This is deliberately different
from `dimension_library.py`'s `PIPE_FILES["ASME_B36"]` key, which only
selects which JSON file to load for the existing combined live lookup
and was left untouched. `normalization.normalize_asme_pipe_standard()`
collapses source variants (`"ASME B36.10M"`, `"B36.10M"`, `"ASME_B36.10"`)
into one of these two canonical forms only.

### Schedule normalization (`normalization.normalize_schedule()`)

Canonical forms: `"SCH40"`, `"SCH40S"`, `"STD"`, `"XS"`, `"XXS"`, etc.
Accepts `"40"`, `"Sch40"`, `"SCH 40"`, `"SCH-40"` as equivalent inputs,
but **never** merges a numeric schedule with its S-suffix counterpart,
and never aliases `STD`/`XS`/`XXS` to a numeric schedule (the source's
own notes explicitly flag `Sch40`/`SchSTD` as distinct, diverging
columns for NPS>=12).

### Schedule identity vs. dimensional equality

Proven with real source values, not a fixture: `SCH40` and `SCH40S` are
numerically equal at NPS6 (7.11mm both) but diverge at NPS12 (10.31mm vs
9.53mm); `SCH80`/`SCH80S` diverge starting at NPS10 (15.09mm vs 12.7mm).
Both schedules remain separate canonical identities throughout - equality
at one size is never used to justify aliasing.

### Missing-cell semantics

A `null` schedule cell (e.g. B36.10M NPS22/Sch40) produces **no**
`EngineeringFact` - not a zero-thickness fact, not a quarantined one. A
query for that exact combination correctly raises `CombinationNotFound`
(proven by test against the real null cell).

### Cross-standard overlap: proven, not assumed

NPS 1/8-12 appear in both tables with **identical** OD at every single
overlapping size - two separate `EngineeringFact` OD records are created
(one per standard), which is legitimate overlap, not a duplicate: their
`identity_key()` tuples differ because `standard` differs, so
`add_checked()` never raises `ConflictingDuplicateFact` for them.

### Known limitation surfaced in the live lookup (not fixed here)

`dimension_library.get_pipe()` concatenates the B36.10M rows before the
B36.19M rows and returns the first NPS match - for every NPS in 1/8-12
that is always the B36.10M row, which has no S-suffix columns. This means
the live lookup can **never** resolve an S-suffix schedule (confirmed by
direct testing: `dl.get_pipe("ASME_B36", "6", "Sch40S")` raises
`DimNotFound` even though the value exists). This pre-existing behaviour
was left untouched (`dimension_library.py` was not modified) - it is the
reason all 69 S-suffix wall-thickness facts fall into "not comparable" in
the Prompt 6 cross-check, each with this exact explanation attached.

### Verified result

409 facts ingested (54 OD + 355 wall-thickness). Cross-check against the
live `dimension_library.py`: OD 54/54 exact matches, wall thickness
286/355 comparable (69 explained not-comparable per above) with 286/286
exact matches, 0 unexplained mismatches anywhere. See
`tests/test_asme_pipe_ingestion.py`.

## Prompt 7: ASME B16.9 buttweld fittings - multi-size product identity

### Actual source structure (inspected, not assumed)

`Buttweld/ASME_B16.9_Buttweld_Fittings.json` has no edition year in its
top-level `"standard"` string (unlike the flange source) - `standard_edition`
stays `None` throughout, never guessed. Five product sections, each with
its own `"rows"` list: `elbows_90_45_LR_3D` (bundles FOUR elbow subtypes
as columns on one row - 90LR/45LR/90-3D/45-3D), `elbows_90_SR` (a FIFTH
elbow subtype, narrower NPS range: 1-24 only), `tees_straight_equal`
(only equal tees exist in this source - no reducing-tee table, so no
`tee_reducing` fitting-type identifier was invented), `caps` (THREE
dimensional columns: `Length_H_mm` always present, `Length_H1_mm`/
`WT_threshold_mm` present together or null together), and
`reducers_concentric_eccentric` (rows keyed by a `"LARGE - SMALL"` display
string; the section's own note states the same OD/length table applies
to both concentric and eccentric reducers - this source does not
distinguish them dimensionally at all).

### Fitting-type vocabulary (`vocabulary.py`)

Nine canonical fitting-type identifiers: five elbow subtypes
(`elbow_90_lr`, `elbow_45_lr`, `elbow_90_3d`, `elbow_45_3d`, `elbow_90_sr`
- angle x radius-type are both engineering-significant, never collapsed),
one tee subtype (`tee_equal` - matching what the source actually
contains), two reducer subtypes (`reducer_concentric`,
`reducer_eccentric` - kept as distinct identities even though this source
tabulates identical values for both), and `cap`.

### Multi-size applicability model

`Applicability` gained two additive fields: `large_end_nps` and
`small_end_nps` (both default `None`, so every pre-Prompt-7 fact is
unaffected). A reducer's engineering identity is queryable by explicit
end role (`large_end_nps="6", small_end_nps="4"`) rather than only via
the opaque display string `reducing_pair` (kept for display only, never
used for identity/query distinctness). `EngineeringFact.identity_key()`
appends these two fields at the end of its tuple (not inserted), so
Prompt 5/6 identity comparisons are unaffected.

### Elbow / tee / reducer / cap dimension mapping

`DIM_CENTRE_TO_END` (already existed) is reused as-is for all five elbow
subtypes - the dimension's meaning doesn't change between subtypes, only
its value and `fitting_type` applicability. `DIM_END_TO_END` (already
existed) is reused as-is for a reducer's overall face-to-face length.
Tees needed two NEW distinct dimension names -
`DIM_TEE_RUN_CENTRE_TO_END` / `DIM_TEE_BRANCH_CENTRE_TO_END` - because
both measurements coexist simultaneously on the same fitting and
genuinely diverge at large NPS (confirmed: NPS42 Run=762mm vs
Outlet=711mm). Caps needed two NEW distinct dimension names -
`DIM_CAP_LENGTH_STANDARD_WALL` (source `Length_H_mm`) and
`DIM_CAP_LENGTH_HEAVY_WALL` (source `Length_H1_mm`), plus
`DIM_CAP_WALL_THICKNESS_THRESHOLD` (source `WT_threshold_mm`) - these are
genuinely different engineering facts selected by which side of a
wall-thickness threshold the pipe being capped falls on, not duplicates.

### Reducer pair parsing and validation

`_parse_reducer_pair()` splits the source's `"LARGE - SMALL"` string on
the space-hyphen-space separator (safe because an individual NPS's own
internal hyphen, e.g. `"1-1/4"`, never has surrounding spaces).
`_validate_reducer_row()` requires the large-end sort key to be strictly
greater than the small-end sort key (via `nps_sort_key()`, exact
`Fraction` comparison, never float) - a reversed or equal pair is
rejected at source-validation time, never silently swapped or corrected.

### KNOWN FINDING: real cross-section OD inconsistency (NPS8, NPS12)

Every product section repeats `OD_mm` for a given NPS, and this adapter
deliberately gives OD a **shared identity with no `fitting_type`** across
all five sections - so `add_checked()` acts as a free, structural
cross-section consistency check, not merely an assertion in a comment.
This caught a real, previously-unknown inconsistency in the "approved"
source file during this prompt's ingestion (not a hand-built fixture):

- **NPS12**: `323.8mm` in `elbows_90_45_LR_3D` / `elbows_90_SR` /
  `tees_straight_equal` / `caps`, but `323.9mm` in every
  `reducers_concentric_eccentric` row referencing NPS12 (as either the
  large or small end).
- **NPS8**: `219.1mm` everywhere except one reducer row (`"16 - 8"`),
  where `OD_Small_D1_mm` is `219.0mm`.

Neither value is silently picked, averaged, or dropped, and the source
JSON was **not** edited. Both NPS's OD facts are ingested as
`QUARANTINED_CONFLICT` (via `_collect_od_observations()` /
`_find_od_conflicts()`, run once before any fact is built, so the
affected NPS values are known in advance rather than discovered mid-crash)
- both disagreeing values are retained side by side, reachable only via
`get_quarantined()`, never via the normal `query()` path. Every other NPS
proceeds as ordinary `VERIFIED_AUTHORITATIVE`. As weak supporting
context only (not used to silently resolve the conflict): Prompt 6's
independently-ingested ASME B36.10M/19M pipe data gives NPS12 OD =
323.9mm in both pipe tables.

### Duplicate/conflict handling detail: `_add_fact()` dispatcher

A small dispatcher routes every fact through the right registry method:
`VERIFIED_AUTHORITATIVE` facts go through `add_checked()` as in Prompts
5-6; `QUARANTINED_CONFLICT` facts go through plain `add()` (matching the
`legacy_crm_quarantine_fixture.py` precedent of deliberately storing
known-conflicting values side by side) but with its own explicit
exact-duplicate check first (same `identity_key()`, same value, same
status), so re-ingesting into the same registry stays idempotent - `add()`
alone has no identity index, and without this check re-running ingestion
would silently double every conflicted record on each pass. This was
caught and fixed during this prompt's own test suite (a real bug, not a
hypothetical).

### Same-value-different-subtype: proven non-conflict

Reducer `Length_H_mm` is ingested once for `reducer_concentric` and once
for `reducer_eccentric` per source row, with the identical tabulated
value - proving dimensional equality never collapses two genuinely
distinct product identities into a false conflict (their `identity_key()`
tuples differ on `fitting_type`).

### Exhaustive comparison against `dimension_library.py`, by subtype

`dimension_library.py` only ever implemented three buttweld lookups:
`get_buttweld_elbow90()` (90LR only), `get_buttweld_tee()`, and
`get_buttweld_cap()` (H only, no H1/threshold) - confirmed by direct
inspection, not assumed. Cross-checked exactly against each:

| Subtype | Rows checked | Mismatches |
|---|---|---|
| Elbow 90 LR | 33 | 0 |
| Tee (run + outlet) | 33 | 0 |
| Cap (`Length_H`) | 33 | 0 |

The remaining subtypes have **no** existing `dimension_library.py`
equivalent at all - this is new canonical-only coverage, not a gap being
hidden: elbow 45LR (33 facts), elbow 90-3D (32), elbow 45-3D (32), elbow
90SR (19), reducer concentric (114) + reducer eccentric (114, matching
the source's 114 reducer rows exactly), cap `Length_H1`/`WT_threshold`
(21 each, matching the NPS 1/2-24 range where both are non-null).

### Existing geometry-generation compatibility

`kgpe/rules/buttweld.py` supports exactly `elbow_90` (routed to
`get_buttweld_elbow90`, i.e. 90LR only), `tee`, and `cap` - no 45deg, 3D,
SR, or reducer geometry exists yet in the generator. All three existing
request shapes in `examples/demo.py` still return `STATUS: OK` with
unchanged geometry after this prompt (verified by re-running the demo).

### Verified result

864 facts built; 840 `VERIFIED_AUTHORITATIVE` + 24 fact-build events
flagged `QUARANTINED_CONFLICT` (the NPS8/NPS12 OD finding above, one
build event per section/reducer-row occurrence that references those
NPS values); 573 total records held in a fresh registry after
`add_checked()`/`add()` dedup - of which exactly **4** are unique
`QUARANTINED_CONFLICT` records once the Prompt-8-verified `_add_fact()`
exact-duplicate guard collapses repeated identical (NPS8: 219.1mm and
219.0mm; NPS12: 323.8mm and 323.9mm) observations across sections (see
Prompt 8's registry-statistics cross-check, which confirmed this exact
count programmatically against the live registry rather than by
re-reading this paragraph). Elbow-90LR/tee/cap: 33/33/33 exact matches
against `dimension_library.py`, 0 mismatches. Reducer fact count (228)
equals 2 x 114 source rows exactly (concentric + eccentric). See
`tests/test_asme_b16_9_ingestion.py`.

## Prompt 8: completing migration of all remaining structured datasets

### Complete dataset inventory (11 files total, matching the Prompt 1-3 estimate exactly)

| Family | File | Adapter | Status |
|---|---|---|---|
| Flange | ASME_B16.5 | `asme_b16_5_flanges.py` | Migrated (Prompt 5) |
| Flange | JIS_B2220 | `jis_b2220_flanges.py` | Migrated (Prompt 8) |
| Flange | EN_1092-1 | `en_1092_flanges.py` | Migrated (Prompt 8) |
| Pipe | ASME_B36.10M/19M | `asme_b36_pipes.py` | Migrated (Prompt 6) |
| Pipe | JIS_G3452/3454/3459 | `jis_pipes.py` | Migrated (Prompt 8) |
| Pipe | EN_10216/10217 | `en_pipes.py` | Migrated (Prompt 8) |
| Buttweld | ASME_B16.9 | `asme_b16_9_buttweld.py` | Migrated (Prompt 7) |
| Buttweld | JIS_B2311/2312 | `jis_buttweld.py` | Migrated (Prompt 8) |
| Buttweld | EN_10253 | `en_buttweld.py` | Migrated (Prompt 8) |
| Socketweld | ASME_B16.11 | `asme_b16_11_socketweld.py` | Migrated (Prompt 8) |
| Olet | MSS_SP97 | `mss_sp97_olets.py` | Migrated (Prompt 8) |

Every approved structured dataset now has a production adapter - none
remain classified as "not yet migratable."

### Size systems supported

`NPS` (ASME, exact-`Fraction` sort key, never float identity), `DN`
(EN/DIN, `normalize_dn()` -> "DN50"), `JIS A-size` (`normalize_jis_size()`
-> "50A") - three textually-distinct systems that never collide even at
identical numeric values, because `standard` is always part of
`identity_key()` regardless. None is ever silently converted to another.

### Rating systems supported

ASME pressure class (`normalize_pressure_class(..., RATING_SYSTEM_ASME_CLASS)`
- reused as-is for ASME B16.11's Class 3000/6000, since B16.11 is itself
an ASME standard using the identical designation convention, not a
cross-standard force-fit), ASME schedule (`normalize_schedule()`), PN
(`normalize_pressure_class(..., RATING_SYSTEM_PN)`), JIS K rating
(`normalize_pressure_class(..., RATING_SYSTEM_JIS_K)` - already declared
in Prompt 4, first actually exercised by `jis_b2220_flanges.py` in this
prompt), and a new EN/DIN wall-thickness-band designation
(`normalize_wall_designation()` -> "EN_SERIES1".."EN_SERIES5", stored in
`Applicability.schedule` but always `EN_`-prefixed so it can never be
mistaken for an ASME schedule).

### Multi-size identity extensions

Six new `Applicability` fields (all additive, default `None`):
`large_end_dn`/`small_end_dn` (EN reducers), `large_end_jis_size`/
`small_end_jis_size` (JIS reducers), `run_nps`/`branch_nps` (MSS SP-97
branch outlets - a genuinely different engineering role from a
reducer's large/small end, so deliberately NOT reusing the Prompt 7
reducer fields). All six participate in `identity_key()`.

### Newly discovered data conflicts (Prompt 8)

Two real, previously-unknown cross-section inconsistencies were found
by this prompt's ingestion (both via the same structural-quarantine
mechanism Prompt 7 used for ASME B16.9's NPS8/NPS12 finding - a
pre-scan before any fact is built, routing affected values to
`QUARANTINED_CONFLICT` rather than crashing or silently picking one):

- **EN 10253 buttweld OD**: DN450 is 457.2mm in `elbow_90_180` but
  457.0mm in `equal_tee`/`concentric_reducer`/`cap`; DN600 is 610.0mm in
  `elbow_90_180`/`equal_tee`/`cap` but 609.6mm in `concentric_reducer`.
- **EN 10253 buttweld wall thickness**: DN200 is 6.3mm in
  `elbow_90_180`/`equal_tee`/`concentric_reducer(large)` but 5.9mm in
  `concentric_reducer(small)`; DN450/DN500/DN600 are 10.0/11.0/12.7mm in
  `elbow_90_180` (and reducer where present) but a flat 9.52mm in
  `equal_tee` at all three sizes - the repeated identical 9.52mm value
  at three different DNs (where wall thickness should scale with size)
  suggests a placeholder/copy-paste error in the tee table's source,
  not a genuine engineering difference, but this is not resolved here -
  quarantined per policy, not fixed by inference.

Both remain `QUARANTINED_CONFLICT` (16 total quarantined facts in the
full combined registry: 4 from ASME B16.9's Prompt 7 finding, 12 from
these two new EN 10253 findings), reachable only via
`get_quarantined()`. The source JSON was not edited.

### Canonical-only coverage (dimensions the old live lookup never exposed)

`dimension_library.py` has NO live-lookup function at all for: ASME
B16.11 socketweld fittings, MSS SP-97 olets, JIS pipe/buttweld beyond
their existing flange/elbow/tee/cap functions, or any EN pipe/buttweld
dimension beyond OD/WT/elbow/tee/cap. Every fact from `asme_b16_11_
socketweld.py`, `mss_sp97_olets.py`, and every JIS/EN reducer fact is
therefore new canonical-only coverage - not an error, simply data this
project never had a resolution path for before. All of it is either
`VERIFIED_AUTHORITATIVE` (official/standard-sourced) or
`VERIFIED_MANUFACTURER_SPECIFIC` (MSS body-dims, explicitly Bonney
Forge catalog data per the source's own text) - ready for a future
geometry-generation prompt to consume via `FactRegistry.query()`, not
yet wired into `kgpe/rules/*.py` or `kgpe/generator.py`.

### Excluded, non-fabricated columns (documented, not silently dropped)

- JIS B2220 flange `PipeOD_mm`: redundant with the JIS pipe adapter's
  own OD facts for the same JIS A-size (source's own notes confirm they
  match) - not re-ingested under a second, confusingly-named identity.
- EN 10253 buttweld `Elbow45_CtoE_derived_mm`: the source's own notes
  call this "a GEOMETRIC DERIVATION... not a standard-published value" -
  not ingested as any kind of canonical fact.
- EN 10253 buttweld `WallThk_options_mm`: a slash-separated multi-value
  string, not one deterministic dimension - not ingested.
- EN 10216/10217 pipe `Sch40_equiv_mm`/`Sch80_equiv_mm`: the source's
  own notes call these "a rough ASME-comparison aid only" - not ingested
  as authoritative EN wall-thickness facts.
- JIS B2311/2312 buttweld reducer: only 7 sampled pairs exist in the
  source ("representative sample... not the full matrix" per its own
  notes) - ingested exactly as-is, no interpolation of the rest.

### Complete canonical registry build

`kgpe/contract/registry_builder.py` - `build_canonical_registry()` loads
all 11 adapters in a fixed, explicit order (not filesystem enumeration)
into one shared `FactRegistry` and returns `(registry, per_adapter_
counts)`. `registry_statistics(registry)` derives every count in the
Prompt 8 report directly from the built registry - nothing is hand-
estimated. Does not read any CRM/JS/HTML file, has no network
dependency, and does not replace `kgpe/generator.py` - Prompt 9 will
decide if/when the resolution engine begins consuming this registry as
its primary source.


## Prompt 9: canonical data-layer closure and freeze

Formal audit/closure prompt - no new dataset migration. Confirms the
Prompt 8 baseline programmatically, closes the dataset-to-adapter mapping,
builds a stable read boundary, and freezes the data layer for Prompt 10.

### Dataset-to-adapter closure (Sec.3)

`kgpe/contract/data_layer_audit.py`'s `dataset_inventory()` cross-checks
three independent sources of truth against each other every time it
runs (not just once, by hand): `dimension_library.py`'s file registries
(FLANGE_FILES/PIPE_FILES/BUTTWELD_FILES/SOCKETWELD_FILES/OLET_FILES),
`registry_builder.py`'s fixed `_ADAPTERS` tuple, and a declared 11-row
dataset table. Any drift between them raises `ClosureAuditError` rather
than silently passing. Result: exactly 11 datasets, each with exactly one
adapter, each wired into `build_canonical_registry()` exactly once.

`kgpe/contract/adapters/legacy_crm_quarantine_fixture.py` is confirmed
NOT one of the 11 (it is a Prompt-3-findings quarantine-mechanism test
fixture, never loaded by `registry_builder._ADAPTERS`) - its exclusion is
intentional and now positively tested, not merely asserted.

### Canonical coverage matrix (Sec.4) and gap classification (Sec.5)

`data_layer_audit.coverage_matrix(registry)` reports DATA coverage only,
per standard: product families/subtypes, dimension names, class/schedule
values, size ranges per size-system, represented-combination count, and
verification-status distribution. `coverage_vs_geometry_matrix(registry)`
keeps this strictly separate from LEGACY_RESOLUTION_COVERAGE
(`dimension_library.py`) and LEGACY_GEOMETRY_COVERAGE (`generator.py`/
`rules/*.py`), computed by introspecting the live modules (`hasattr`,
`_DISPATCH` keys), never a hand-duplicated belief.

Key finding: `dimension_library.py` has NO `get_socketweld()`/`get_olet()`
function at all (confirmed via `hasattr`), even though `SOCKETWELD_FILES`/
`OLET_FILES` are registered - so all 750 ASME B16.11 facts and all 223
MSS SP-97 facts are `CANONICAL_DATA_AVAILABLE_NO_LEGACY_LOOKUP`. Separately,
`generator.py` has no `"socketweld_fitting"` entry in `_DISPATCH` at all,
and `rules/olet.py` unconditionally returns `GEOMETRY_DEFINITION_INCOMPLETE`
- both `CANONICAL_DATA_AVAILABLE_NO_GEOMETRY`, not missing engineering data.

`classify_gaps(registry)` uses exactly 7 classifications (`NOT_IN_SOURCE`,
`SOURCE_PARTIAL`, `QUARANTINED_CONFLICT`, `MANUFACTURER_SPECIFIC_ONLY`,
`CANONICAL_DATA_AVAILABLE_NO_LEGACY_LOOKUP`, `CANONICAL_DATA_AVAILABLE_
NO_GEOMETRY`, `UNSUPPORTED_BY_CURRENT_KGPE_SCOPE`) - 79 gap records in the
current registry, none invented to pad the list, none hidden to look
more finished than the data actually is.

### Unresolved-conflict register (Sec.6) and conflict integrity (Sec.7)

`data_layer_audit.conflict_register(registry)` produces one machine-
readable record per conflict GROUP (same dimension+standard+size+subtype),
each listing every individual conflicting fact with its own provenance.
Current register: **8 groups / 16 facts** - 2 groups/4 facts from ASME
B16.9 (NPS8 OD 219.1 vs 219.0mm; NPS12 OD 323.8 vs 323.9mm), 6 groups/12
facts from EN 10253 (DN450 OD 457.2 vs 457.0mm; DN600 OD 610.0 vs
609.6mm; DN200 WT 6.3 vs 5.9mm; DN450/500/600 WT 10.0/11.0/12.7mm vs a
flat, likely-placeholder 9.52mm repeated in the `equal_tee` table). None
resolved by inference; source JSON untouched. Verified this prompt:
quarantined facts remain blocked from `query()`/`CanonicalReader.read()`,
remain inspectable via `get_quarantined()`, survive repeated ingestion
without growing, and do NOT affect nearby valid sizes or unrelated
dimensions at the same size (e.g. NPS8's `centre_to_end_mm` still
resolves normally even though its `outside_diameter_mm` is quarantined).

### Hidden identity-collision / cross-standard / isolation audits (Sec.8-11)

`find_identity_collisions(registry)` confirms every multi-fact identity in
the complete 4,824-fact registry is the ONE sanctioned pattern
(`QUARANTINED_CONFLICT`, exactly the 8 known groups) - zero unsanctioned
hidden collisions. Cross-standard equality (JIS STPG vs SUS Sch40, ASME
vs JIS vs EN flange OD at "matching" sizes) confirmed to remain distinct
identities despite equal values. `size_system_isolation_report()` and
`rating_system_isolation_report()` confirm zero textual overlap between
NPS/DN/JIS-size and between ASME Class/PN/JIS K/Schedule/EN wall-
designation, scanning the live data rather than assuming isolation.

### Manufacturer-specific / verification-status / provenance audits (Sec.12-14)

145 `VERIFIED_MANUFACTURER_SPECIFIC` facts confirmed, all `manufacturer_
profile="Bonney Forge"`, all `olet`/`MSS_SP97`; confirmed unreachable via
plain `query()`/`CanonicalReader.read()` without explicit opt-in. Exactly
3 verification statuses are present in the complete registry
(`VERIFIED_AUTHORITATIVE`, `VERIFIED_MANUFACTURER_SPECIFIC`,
`QUARANTINED_CONFLICT`) - the other 5 (`VERIFIED_DERIVED_RULE`,
`CONSTRUCTION_PARAMETER`, `VISUAL_ONLY`, `QUARANTINED_UNVERIFIED`,
`DEPRECATED_LEGACY`) are simply absent, which Sec.13 confirms is not an
error. Provenance completeness: `source_name`/`source_type`/`standard_
designation`/`source_file`/`original_field`/`transcription_method` are
100% populated across all 4,824 facts. `standard_edition` is populated
only for ASME B16.5 (792/4824, 16.4%) and `verification_date` is 0% -
both legitimately unknown (never fabricated, per this project's own
standing rule), not accidental omissions. `verification_method` is
inconsistently populated across adapters (100% for 7 of 11 datasets, 0%
for ASME B16.11, partial for ASME B16.9/B36/MSS SP-97) - a real narrative-
completeness gap, but non-blocking: it never participates in
`identity_key()`, fail-closed behaviour, or the registry fingerprint, and
touching 5 already-tested production adapters purely to backfill a prose
field was judged higher regression risk than value this prompt - flagged
as a remaining limitation, not fixed here.

### Canonical read interface (Sec.15-18)

`kgpe/contract/canonical_reader.py`'s `CanonicalReader` is the ONE stable
boundary a future resolution engine (Prompt 10+) should import - it never
needs source JSON structure, individual adapters, filesystem paths, or
adapter load order. `build_canonical_reader()` builds the complete
registry and wraps it in one call.

`reader.read(dimension_name, **criteria)` never raises for an expected
engineering outcome; it always returns a `CanonicalReadResult` with one
of 8 outcome codes: `EXACT_MATCH`, `NO_MATCH`, `QUARANTINED_MATCH`,
`AMBIGUOUS_MATCH`, `MANUFACTURER_CONTEXT_REQUIRED`,
`CONSTRUCTION_CONTEXT_REQUIRED`, `UNSUPPORTED_CRITERIA`,
`MALFORMED_CRITERIA`. Ambiguity NEVER resolves to a first/default pick -
if more than one authoritative fact matches, the outcome is
`AMBIGUOUS_MATCH` with every candidate listed, and the caller must supply
more criteria. Manufacturer-specific data is a distinct outcome from
generic quarantine (`MANUFACTURER_CONTEXT_REQUIRED`, with the available
profiles listed), never silently returned as the standard-default answer.

Discovery/coverage methods (`discover()`, `available_dimensions()`,
`available_manufacturer_profiles()`, `available_reducing_pairs()`,
`available_run_branch_pairs()`) are all computed live from `registry.
all_facts()` - never a hard-coded option list that could drift from the
actual ingested data.

### Data-layer snapshot and fingerprint (Sec.19-20)

`kgpe/contract/snapshot.py`'s `build_data_layer_snapshot()` returns a
machine-readable manifest (schema version, registry build version,
adapter list, dataset inventory, total/by-status/by-standard/by-family
counts, unresolved-conflict count and IDs, fingerprint). `registry_
fingerprint()` is a SHA-256 over each fact's `(identity_key(), value,
unit, verification_status, source_file, standard_designation,
original_field, standard_edition)`, sorted before hashing (so adapter/
insertion order never affects it) - documented exhaustively in the
module docstring, including exactly what is excluded (narrative
provenance fields, notes, timestamps, object identity, filesystem order).
Verified: two independent fresh builds produce the identical fingerprint;
mutating any one fact's value changes it.

**Current fingerprint (this Prompt 9 build):**
`9238ab3cb896101c545450df6f0ff070301b4ba68117771b4105e87606c2c873`

### Data-layer freeze

**`DATA_LAYER_READY_FOR_RESOLUTION_ENGINE`** - see the Prompt 9 implementation
report for the full evidence trail. All 16 quarantined facts (8 conflict
groups) remain safely isolated (scoped exactly to their own identity, not
blocking neighbouring sizes/dimensions) and do not block this decision.


## Prompt 10: engineering specification-resolution engine (Phase 3)

Additive resolution layer built entirely on the frozen Prompt 9 canonical
read boundary (`CanonicalReader`/`build_canonical_reader()`). Lives in the
new `kgpe/resolver/` package - does not modify `kgpe/contract/*`,
`dimension_library.py`, `generator.py`, or any `rules/*.py` file.

**Architecture:** `EngineeringRequest` -> alias normalization -> product-
family/subtype/standard/size/rating resolution -> `CanonicalReader` ->
`ResolvedEngineeringSpecification`. Deterministic Python only - no LLM,
no network, no fuzzy/edit-distance matching.

**Request model** (`resolver/request.py`): `EngineeringRequest` - a flat,
separate dataclass from `EngineeringFact`. Raw, unnormalized, optional
fields: `product_family`, `subtype`, `standard`, `size_system`,
`primary_size`/`large_end_size`/`small_end_size`/`run_size`/`branch_size`,
five SEPARATE rating fields (`pressure_class`, `schedule`, `pn`, `jis_k`,
`wall_designation` - so the caller must say which rating SYSTEM a bare
number belongs to, never guessed), `manufacturer_profile`,
`allow_manufacturer_specific`, `dimensions` (explicit list, or empty for
"what's available" discovery mode).

**Resolved specification** (`resolver/spec.py`): `ResolvedEngineeringSpecification`
carries `status`, resolved identity (`product_family`/`subtype`/`standard`/
`size_system`/`sizes`/`rating_system`/`rating_value`/`manufacturer_profile`),
`resolved_dimensions` (value/unit/status/source per requested dimension),
`available_dimensions`, progressive-resolution fields (`missing_criteria`,
`available_options`, `ambiguous_candidates`, `unsupported_reason`),
`quarantine_details`, `available_manufacturer_profiles`, a deterministic
`trace` (no timestamps), `warnings`, and `data_layer_fingerprint` (bound
live from `kgpe.contract.snapshot.registry_fingerprint()`, never hard-coded).

**Resolution-status vocabulary** (`ResolutionStatus`, exactly 7, no generic
`FAILED`): `RESOLVED`, `INCOMPLETE_REQUEST`, `AMBIGUOUS_REQUEST`,
`UNSUPPORTED_REQUEST`, `MALFORMED_REQUEST`, `QUARANTINED_ENGINEERING_DATA`,
`MANUFACTURER_CONTEXT_REQUIRED`. Design rule distinguishing INCOMPLETE from
AMBIGUOUS: when a requested dimension's candidates differ only by a
rating field (class/schedule/PN/K/wall-designation), that's INCOMPLETE
(the object identity is already coherent, one more criterion is needed);
any other differing field (standard/subtype/manufacturer_profile/size
role) is a genuine AMBIGUOUS_REQUEST - a different engineering object.

**Alias layer** (`resolver/aliases.py`): small, explicit, inspectable
dicts (`PRODUCT_FAMILY_ALIASES`, `STANDARD_ALIASES`, per-family subtype
alias tables) - not fuzzy matching, not hundreds of speculative variants.
An input that isn't a key (after simple case/whitespace normalization)
fails explicitly as `UNSUPPORTED_REQUEST`, never guessed.

**Standard/size/rating resolution** (Sec.12-14): standard is normalized
+ validated against live `reader.discover("standard", ...)` coverage if
supplied; if omitted, inferred only when exactly one candidate remains
(else `AMBIGUOUS_REQUEST` listing every candidate - never defaults to
ASME). Size system (NPS/DN/JIS-size) is inferred the same way, per role
(single/large-small/run-branch), reusing `normalize_nps`/`normalize_dn`/
`normalize_jis_size` - never cross-converted. Rating is resolved from a
small explicit `STANDARD_RATING_SYSTEM` map (which rating system applies
to which of the 14 standards), cross-checked against live discovery, not
hard-coded blindly.

**Multi-size roles** (Sec.15): reducer `large_end_size`/`small_end_size`
and branch-outlet `run_size`/`branch_size` are normalized independently
and never encoded as an opaque string. A reversed reducer pair (large <
small after normalization) is rejected as `MALFORMED_REQUEST` before any
canonical query - `6x4` is never silently read as `4x6`.

**Required-criteria / object vs. dimension completeness** (Sec.16-18):
derived live from canonical coverage, never hard-coded per product. A
per-dimension query's `AMBIGUOUS_MATCH` outcome is diffed field-by-field
(`_diff_fields`) to distinguish "missing rating criterion" (INCOMPLETE,
with real available options from discovery) from "genuinely different
object" (AMBIGUOUS). This is exactly how pipe OD (no schedule needed) and
pipe wall thickness (schedule required) are told apart automatically from
the data, with zero per-product hard-coding.

**Shared cross-subtype identity fallback:** ASME B16.9/EN 10253 OD and
wall-thickness facts deliberately have no `fitting_type` (Prompt 7-9's
cross-section consistency-check pattern). If a subtype-scoped dimension
query finds nothing, the resolver retries once with the subtype filter
relaxed - this never arbitrates between ambiguous/quarantined candidates,
it only recognizes the canonical data's own identity shape.

**Quarantine/manufacturer behaviour** (Sec.21-23): quarantined dimensions
surface as `QUARANTINED_ENGINEERING_DATA` with `conflict_id`s matching
Prompt 9's register format exactly; unrelated dimensions explicitly
requested alongside stay resolved. Manufacturer-specific data always
requires `MANUFACTURER_CONTEXT_REQUIRED` -> explicit `manufacturer_profile`
before it can resolve; an unrecognized profile never falls back to
Bonney Forge.

**Public interface:** `resolve_engineering_request(request, resolver=None)`
and `EngineeringResolver(reader, fingerprint).resolve(request)`. The
caller never constructs a registry, imports an adapter, or catches a raw
exception - every outcome is a structured `ResolvedEngineeringSpecification`.

**Verified this prompt:** all 20 Sec.29 representative scenarios pass;
315 total tests (233 Prompt 4-9 + 82 new) pass; demo unchanged; resolver
package contains zero adapter/`dimension_library`/JSON-path imports; no
source engineering file or CRM/JS/HTML/KFEE file modified; fingerprint
unchanged at `9238ab3cb896101c545450df6f0ff070301b4ba68117771b4105e87606c2c873`.


## Prompt 11 (Phase 3 completion): Engineering Specification Orchestration and Geometry Handoff

New package `kgpe/geometry_spec/` completes Phase 3, built strictly ON TOP
of the frozen canonical data layer (Prompt 9) and the resolver (Prompt
10) - neither was modified. It defines the stable boundary:

```
EngineeringRequest -> EngineeringResolver -> ResolvedEngineeringSpecification
    -> GeometrySpecificationCompiler -> GeometrySpecification -> (future Geometry Kernel)
```

This prompt stops at `GeometrySpecification`. No geometry is generated;
`kgpe/generator.py` and `kgpe/rules/*.py` are untouched.

**First-class discovery** (`geometry_spec/discovery.py`): completes
Prompt 10's own named limitation - subtype discovery now works
independently of any dimension request, alongside families/standards/
sizes/ratings/manufacturer profiles/dimensions/reducer pairs/run-branch
pairs, all computed live from `CanonicalReader`'s existing query surface.
No second manually-maintained catalogue.

**`EngineeringObjectIdentity`** (`identity.py`): immutable, only-
applicable-fields-populated identity built from a RESOLVED spec via
`from_resolved_spec()`; raises `IdentityConstructionError` otherwise. A
`display_label` property is a derived convenience, never the identity.

**`EngineeringDimensionBundle`/`ResolvedDimension`** (`dimension_bundle.py`):
every dimension retains name/value/unit/verification_status/source_file -
never reduced to a bare dict of floats. `.numeric_values()` is an
explicit convenience accessor alongside the traceable form.


**`GeometrySpecification`** (`spec.py`): stable, serializable geometry-
INPUT contract - schema version, engineering object identity, required/
optional dimensions, data-layer fingerprint, deterministic own fingerprint,
source-verification summary, compilation trace, warnings, readiness
status. Never contains mesh vertices/triangles/CAD solids/rendering
colours/camera/lighting.

**Geometry readiness vocabulary** (`readiness.py`, 7 statuses):
`GEOMETRY_READY`, `ENGINEERING_SPEC_INCOMPLETE`, `ENGINEERING_SPEC_AMBIGUOUS`,
`ENGINEERING_DATA_QUARANTINED`, `MANUFACTURER_CONTEXT_REQUIRED`,
`GEOMETRY_PROFILE_UNAVAILABLE`, `UNSUPPORTED_GEOMETRY_REQUEST`. Every
non-RESOLVED `ResolutionStatus` maps to a SPECIFIC readiness status, never
one generic failure.

**Geometry profiles** (`profile.py`, 10 profiles): declarative
required/optional/construction-derivable dimension sets per product
family/subtype-group, built from LIVE inspection of the canonical
registry and existing `rules/*.py`/`dimension_library.py` during this
prompt - not invented. Key real findings baked into the profiles:
pipe's `bore_diameter_mm` has zero canonical facts anywhere (legacy
`OD-2*WT` heuristic only); ASME_B16.5/EN_1092-1 flanges have no
authoritative bore at all (JIS_B2220 only) while
`hub_base_diameter_mm`/`length_through_hub_mm` have zero facts for any
flange standard; a buttweld reducer's per-end OD is not resolvable via
the resolver's own reducer-role criteria (`large_end_nps`/`small_end_nps`)
since OD is a shared, plain-`nps`-keyed cross-subtype identity; ASME
B16.11 socket-weld elbow/tee/cross publish no body OD at all (a curated
Prompt 9 source gap - the mating pipe's OD is the correct source);
socket-weld caps ARE fully data-ready (their own `cap_body_diameter_mm`);
olet body dims (weldolet/sockolet/threadolet) exist ONLY as
`VERIFIED_MANUFACTURER_SPECIFIC` (Bonney Forge); the MSS SP-97 official
`branch_outlet_height_mm` is authoritative but alone insufficient for a
full olet body. Profiles never read source JSON, import adapters, call
`dimension_library.py`, or normalize raw input.


**`GeometrySpecificationCompiler`/`compile_geometry_specification()`**
(`compiler.py`): accepts RESOLVED engineering output only, verifies
resolution status, selects the profile, checks manufacturer-context
requirements, defensively re-checks required-dimension presence (fail-
closed even against a manually-built spec), binds the data-layer
fingerprint, and produces the deterministic geometry-specification
fingerprint. Never generates geometry; never imports adapters or
`dimension_library.py`; never reads source JSON.

**Orchestration** (`orchestration.py`): `prepare_geometry_specification(request)`
performs TWO resolver calls (never one opaque merged step) - an identity
resolution (to select a profile), then a dimension resolution scoped to
the profile's required dimensions plus any optional dimensions the
caller explicitly requested. A documented **rating-relaxation fallback**
(`_attempt_rating_relaxation`, orchestration-level, never touching
`kgpe.resolver.engine`) recovers dimensions that are genuinely
rating-independent (e.g. a pipe's OD does not vary by schedule) when the
resolver's own single shared `base_criteria` would otherwise over-scope
them with an inapplicable rating filter - mirroring the resolver's own
established shared-cross-subtype-identity fallback, just applied to the
rating field and implemented in this package instead. It can only ever
recover a dimension the resolver would already resolve EXACT under
relaxed criteria - never arbitrates ambiguity/quarantine differently.

Both resolutions and a `failed_stage` (`ENGINEERING_RESOLUTION` /
`PROFILE_SELECTION` / `DIMENSION_RESOLUTION` / `GEOMETRY_COMPILATION`)
are preserved on the returned `GeometryPreparationResult`.

**Batch semantics** (`prepare_geometry_specifications_batch`): ordered,
independent per-item resolution; one item's failure (or even an
unexpected exception) never corrupts another's result; aggregate status
is one of `ALL_READY`/`PARTIALLY_READY`/`NONE_READY`.

**Deterministic fingerprint** (`fingerprint.py`): SHA-256 over schema
version + identity + included dimension name/value/unit/status +
manufacturer context + data-layer fingerprint + profile id/version,
`json.dumps(..., sort_keys=True)` - excludes timestamps, trace order,
memory addresses. Same resolved spec + profile -> same fingerprint; a
meaningful dimension change -> a different one.

**Geometry profile coverage matrix / construction-rule register /
existing-geometry compatibility mapping** (`coverage.py`): live-computed
`PROFILE_READY`/`PROFILE_BLOCKED_MISSING_AUTHORITATIVE_DIMENSIONS`/
`PROFILE_BLOCKED_QUARANTINED_DIMENSION`/`PROFILE_BLOCKED_CONSTRUCTION_RULE_REQUIRED`/
`PROFILE_NOT_YET_DEFINED` rows per (family, subtype), plus a curated
construction-rule requirement register (5 entries) and existing-geometry
compatibility mapping (6 entries) - both built from direct code
inspection this prompt, following the exact documentation style Prompt
9 established for `data_layer_audit._CURATED_SOURCE_GAPS`.

**Verified this prompt:** all 20 Sec.25 representative scenarios pass;
405 total tests (315 Prompt 4-10 + 90 new) pass; demo unchanged; no
geometry generated; `generator.py`/`rules/*.py` untouched; no source
engineering file or CRM/JS/HTML/KFEE file modified; data-layer fingerprint
unchanged at `9238ab3cb896101c545450df6f0ff070301b4ba68117771b4105e87606c2c873`.


## Prompt 12 addendum (Phase 4 - Parametric Geometry Kernel and Deterministic Construction Rules)

**Internal representation:** a deterministic indexed triangle mesh
(`kgpe.geometry.mesh.Mesh` - vertices as `(x,y,z)` float tuples, faces as
`(i,j,k)` index tuples), chosen over a BRep/CAD kernel since it needs no
new dependency, supports future visualization/export/dimensional
validation directly, and keeps every existing kgpe module's stdlib-only
style (confirmed live: numpy is present in this environment but
scipy/trimesh/open3d are not - numpy was deliberately NOT adopted merely
because it happened to be available).

**Coordinate/unit/numerical policy** (`kgpe.geometry.policy`, the ONE
place every other module imports these from): right-handed system,
primary product axis +Z, origin at the start-face centreline, X/Y span
the start-face cross-section; all internal lengths in mm (matching
`kgpe.contract.units.CANONICAL_LENGTH_UNIT`, so no conversion is ever
needed against the canonical engineering layer); internal angles in
radians, degrees only at doc/API boundaries; centralized tolerances
(`LINEAR_TOLERANCE_MM=1e-6`, `NEAR_ZERO_MM=1e-9`,
`ANGULAR_TOLERANCE_RAD=1e-9`, `DEGENERATE_AREA_THRESHOLD_MM2=1e-9`,
`FINGERPRINT_ROUNDING_DECIMALS=6`).

**Reference Product A - pipe** (`products/pipe.py`): consumes a
GEOMETRY_READY `pipe` `GeometrySpecification` (`outside_diameter_mm`,
`wall_thickness_mm`), derives bore via `PipeBoreConstructionRule`
(`bore = OD - 2*WT`, fully validated: positive OD/WT, `2*WT < OD`,
positive bore, mm-only, finite-numeric-only; tagged
`DERIVED_CONSTRUCTION_VALUE`, never written back to the canonical
registry), builds a hollow cylindrical solid via
`build_hollow_cylinder()`. Segment length is a separate, explicitly
labeled `GenerationParameters.pipe_segment_length_mm`
(`DEFAULT_PIPE_SEGMENT_LENGTH_MM=300.0`,
`PIPE_SEGMENT_LENGTH_LABEL="GEOMETRY_DISPLAY_PARAMETER_NOT_AUTHORITATIVE"`)
- never conflated with engineering truth, never entering the geometry
fingerprint as an engineering dimension (though it IS reflected in the
geometry fingerprint, since it changes the actual generated mesh - Sec.19/27).

**Reference Product B - ASME B16.9 90-degree long-radius elbow**
(`products/buttweld_elbow.py`, geometry profile `buttweld_elbow` from
Prompt 11): selected over tee/cap/JIS-flange because its required
dimensions (`outside_diameter_mm`, `centre_to_end_mm`) are already fully
authoritative with zero cross-family/construction-rule gap (Prompt 11's
own construction-rule register lists reducer/socketweld/flange-bore as
blocked, not elbow), and because it exercises the arc-sweep/revolution
primitive with the highest future reuse value (tee/reducer/other elbow
angles). Geometric mapping (no construction rule needed): for a 90-degree
LR elbow, `centre_to_end_mm` IS the bend radius by the standard's own
definition - consumed directly. No bore is modeled (wall_thickness is not
part of this profile's required/default-included dimension set -
documented honestly, not fabricated).

**Arc-sweep primitive** (`primitives.arc_sweep_frames`): closed-form,
deterministic frames for a circular arc in the XZ plane, pivot implicitly
at `(bend_radius, 0, 0)`: `center(theta) = (R-R*cos(theta), 0, R*sin(theta))`,
`tangent(theta) = (sin(theta), 0, cos(theta))`, `v_axis` always global
+Y, `u_axis = tangent x v_axis` - verified analytically (theta=0 enters
+Z, theta=90 degrees leaves +X, pivot-to-center distance is exactly R at
every theta). Deterministic seam placement is guaranteed throughout
(`circle_ring()`/`arc_sweep_frames()` always start from the same fixed
basis vector, never a random angle) per the tessellation policy
(`MIN_RADIAL_SEGMENTS=8`, `MIN_SWEEP_SEGMENTS=2`,
`DEFAULT_RADIAL_SEGMENTS=32`, `DEFAULT_SWEEP_SEGMENTS=16`).

**Construction-rule framework** (`construction_rules.py`):
`ConstructionRule` base + `ConstructionRuleStatus` vocabulary
(`RULE_APPLIED`/`RULE_NOT_APPLICABLE`/`RULE_INPUT_MISSING`/
`RULE_BLOCKED_QUARANTINE`/`RULE_UNSUPPORTED`), with exactly one
implementation this prompt (`PipeBoreConstructionRule`).

**Cross-family dependency framework** (`cross_family.py`): base class
`CrossFamilyDependencyRule` plus exactly one proof-of-concept rule,
`FlangeBoreViaPipeScheduleRule` (derives a flange's bore from an
explicitly-supplied mating pipe standard+schedule, via the resolver's
public interface only - never an implicit NPS/DN/JIS conversion). This
rule issues TWO separate `resolver.resolve()` calls (one for
`outside_diameter_mm` with no schedule, one for `wall_thickness_mm` with
schedule) rather than one shared-criteria call for both dimensions - a
real bug was found and fixed here during this prompt's own testing: a
single combined call reproduces the exact same rating-criteria-mixing
resolver limitation Prompt 11 documented for `EngineeringResolver`
(`base_criteria` applies the rating filter to every requested dimension
uniformly, even a rating-independent one like pipe OD), which made the
rule's own textbook demonstration case fail until split into two calls -
mirroring, at the rule level, the same fix pattern Prompt 11 already
applied at the orchestration level (`_attempt_rating_relaxation`). This
rule is NOT wired into the kernel's product dispatch (`_PRODUCT_DISPATCH`
contains only `pipe`/`buttweld_elbow`) - proven standalone via its own
dedicated tests only, per Sec.16's instruction to build the framework but
implement/wire only one low-risk proof rule.

**Geometry-generation status vocabulary** (`result.py`):
`GEOMETRY_GENERATED`/`GEOMETRY_SPEC_NOT_READY`/`UNSUPPORTED_GEOMETRY_PROFILE`/
`CONSTRUCTION_RULE_UNAVAILABLE`/`INVALID_ENGINEERING_DIMENSIONS`/
`GEOMETRY_VALIDATION_FAILED`/`GEOMETRY_GENERATION_FAILED`. The kernel's
public boundary (`GeometryKernel.generate()`/`generate_geometry()`) never
raises - every outcome, including an unexpected internal exception, is
converted to a structured `GeometryResult` (verified by a dedicated test
that monkeypatches a product builder to raise `RuntimeError` and confirms
`GEOMETRY_GENERATION_FAILED` is returned, not an exception).

**Structural + dimensional validation** (`validation.py`,
`measurement.py`): `validate_mesh_structure()` checks finite coordinates,
valid/non-duplicate face indices, no degenerate faces, non-empty
topology, and expected feature count; `validate_dimensions()` compares
MEASURED values (via `measure_radial_distance`/`measure_axial_length`/
`measure_bend_radius`, computed directly off the generated mesh's actual
vertex data) against the intended engineering dimensions within
`LINEAR_TOLERANCE_MM` - a result is never assumed correct merely because
generation didn't raise.

**Geometry fingerprint** (`fingerprint.py`): SHA-256 over
`json.dumps(payload, sort_keys=True, default=str)` where payload =
units + coordinate convention + kernel version + generation parameters +
rounded (6-decimal) vertex coordinates + face index tuples. Excludes
timestamps and object identity (verified: identical inputs computed 10ms
apart produce identical fingerprints). Verified sensitive to: kernel
version, generation parameters (segment length, tessellation), and any
mesh/vertex mutation - while the geometry-SPECIFICATION fingerprint
(Prompt 11, engineering-identity-only) stays unchanged when only
generation parameters change, proving the fingerprint hierarchy correctly
separates "same engineering object" from "same generated mesh."

**End-to-end pipeline** (`pipeline.py`, `run_pipeline()`):
`EngineeringRequest -> prepare_geometry_specification() (Prompt 11) ->
GeometryKernel.generate() (Prompt 12) -> GeometryResult` in one call,
preserving every stage result and fingerprint simultaneously (engineering
resolution status, geometry-specification readiness, geometry generation
status, data-layer fingerprint, geometry-specification fingerprint,
geometry fingerprint) - an early-stage failure (engineering resolution /
profile selection / dimension resolution / geometry compilation) is
never masked as, or attempted to reach, geometry generation
(`PipelineResult.failed_stage` always names the exact failing stage;
`PipelineStage.GEOMETRY_GENERATION` extends, never redefines, Prompt 11's
own `OrchestrationStage` vocabulary).

**Verified this prompt (25 representative scenarios, Sec.35):** ASME/JIS/
EN pipe generation (all three standard families); pipe bore derivation
via `PipeBoreConstructionRule`; invalid pipe dimensions
(`2*WT >= OD`) correctly rejected as `CONSTRUCTION_RULE_UNAVAILABLE`;
default vs. caller-supplied segment length (fingerprint-sensitive);
generation-parameter fingerprint sensitivity (tessellation, segment
length) without engineering-identity (geometry-specification fingerprint)
change; repeated-request determinism (identical fingerprint across
independent calls); ASME B16.9 90-degree LR elbow generation +
dimensional validation + fingerprint; not-ready geometry specification ->
`GEOMETRY_SPEC_NOT_READY` (generation never attempted); unsupported
profile (`flange_weld_neck`) -> `UNSUPPORTED_GEOMETRY_PROFILE`; missing
required dimensions -> `INVALID_ENGINEERING_DIMENSIONS`; invalid
primitive input (negative radius, zero segments, non-positive sweep
angle) rejected by `InvalidPrimitiveInputError`; degenerate geometry
(zero-area triangle) detected by `validate_mesh_structure()`;
validation-failure structured result path; demo (`examples/demo.py`)
unchanged/PASS; full end-to-end pipeline via `run_pipeline()`; fingerprint
preservation (data-layer + geometry-specification + geometry, all three
simultaneously) end-to-end; dimension-mutation fingerprint sensitivity
(6" vs 8" pipe -> different geometry-specification AND geometry
fingerprints); tessellation-only mutation fingerprint sensitivity without
engineering-identity change; kernel never raises on an unexpected
internal exception (`GEOMETRY_GENERATION_FAILED`); cross-family
proof-of-concept rule (`FlangeBoreViaPipeScheduleRule`) applies
correctly and is confirmed NOT wired into kernel dispatch.

**Full regression:** 495 total tests (405 Prompt 4-11 + 90 new) pass; a
real bug found and fixed during this prompt's own testing
(`cross_family.py`'s single combined resolver call for OD+WT, described
above) - the only code defect discovered this prompt; demo unchanged;
`git status` confirms only new, additive files
(`kgpe/geometry/*`, `tests/test_prompt12_geometry_kernel.py`) - zero
modifications to `generator.py`, `rules/*.py`, `schema.py`,
`dimension_library.py`, `kgpe/resolver/*`, `kgpe/geometry_spec/*`, or any
canonical data-layer file; data-layer fingerprint unchanged at
`9238ab3cb896101c545450df6f0ff070301b4ba68117771b4105e87606c2c873`.


## Prompt 13 addendum (Phase 4 - core ASME B16.9 buttweld geometry expansion)

**Coordinate conventions (Sec.4):** Prompt 12's global convention (+Z axis,
right-handed, mm units) is preserved unchanged. Per-subtype conventions are
now explicit: elbow - inlet centreline along +Z at origin, bend plane is
the X-Z plane, outlet direction determined by subtype bend angle; equal tee
- run axis along Z centred at origin, branch axis along +Y, branch always
outward from run centreline; reducer - large end centred at z=0, axis +Z,
small end at z=length (+ eccentric XY offset for eccentric reducers); cap -
open-end face at z=0, cap axis +Z, dome/flat profile extends to +z.

**Connection ports (Sec.5-8):** `ConnectionPort` carries port id, position,
outward direction (normalized), nominal-size role, and opening diameter
with explicit provenance (`OPENING_DIAMETER_KNOWN` vs.
`OPENING_DIAMETER_CONSTRUCTION_DERIVED` - never presented as authoritative
if it isn't). Role identity is preserved per product: elbow inlet/outlet;
tee run_inlet/run_outlet/branch; reducer large_end/small_end; cap
open_end. `validate_port(s)` enforces finite position, unit-normalized
direction, positive opening diameter where declared known.

**Wall/bore policy (Sec.7-9):** Hollow buttweld geometry requires an
explicit `WallContext` (pipe_standard + exactly one of pipe_schedule /
pipe_wall_designation) supplied by the caller - never inferred from
nominal size, never defaulted to Sch40. `ButtweldWallViaPipeScheduleRule`
(cross-family, same pattern as Prompt 12's `FlangeBoreViaPipeScheduleRule`)
resolves wall thickness only when this context is present; absent context
means the elbow is generated as `SOLID_EXTERNAL_ENVELOPE` (external-only,
honestly declared, never fabricated as hollow).

**Reducer per-end OD dependency (Sec.20-23):** `ReducerPerEndOutsideDiameterRule`
resolves large-end and small-end OD as two independent per-role queries
against the SAME buttweld_fitting/ASME_B16.9 identity space (intra-family,
not `CrossFamilyDependencyRule`). Quarantined NPS8/NPS12 OD conflicts block
generation whenever they affect either end, tested independently for large
role and small role. Ends are never swapped, never shared as one value.

**Tee, cap, reducer construction rules (Sec.14-27):** All represented
honestly rather than as fabricated watertight solids: tee is a
`DETERMINISTIC_MULTI_FEATURE_MESH_NON_MANIFOLD_AT_INTERSECTION` (two
independent solid cylinders, rigidly placed, no boolean union -
`TeeBranchBlendingRule` documents this explicitly and is versioned); cap
length selection (`CapLengthSelectionRule`, H vs. H1) fails closed when
wall context is ambiguous or missing, never infers wall from nominal size
alone; cap dome profile (`CapProfileConstructionRule`) is explicitly
construction-derived, never claimed as a standard-published contour;
concentric/eccentric reducers use a linear-conical
`ConcentricReducerTransitionRule` and `EccentricReducerOffsetRule`
(flat-on-bottom is the canonical kernel default orientation, documented -
never silently rotated between runs; orientation is a generation
parameter, not an engineering-identity field).

**Topology honesty (Sec.31):** every buttweld product self-reports exactly
one `TopologyRepresentation` value - `HOLLOW_SWEPT_SOLID` (elbow with wall
context), `SOLID_EXTERNAL_ENVELOPE` (elbow without wall context, cap,
concentric/eccentric reducer), or
`DETERMINISTIC_MULTI_FEATURE_MESH_NON_MANIFOLD_AT_INTERSECTION` (tee).
"Watertight" and "hollow" are never claimed unless actually validated.

**One frozen-file exception (documented):** `geometry_spec/profile.py`'s
`PROFILE_BUTTWELD_REDUCER` bumped v1->v2 (removed `outside_diameter_mm`
from `required_dimensions`, retained in `construction_derivable_dimensions`)
- a genuine blocking defect (made `GEOMETRY_READY` structurally
unreachable for every reducer), not a redesign. `geometry_spec/coverage.py`'s
reducer register entry and 5 tests in
`tests/test_prompt11_geometry_handoff.py` were corrected to match the
now-correct behavior; all 90 Prompt 11 tests still pass.

**Verified this prompt (40 representative scenarios, Sec.37):** existing
elbow generation unchanged; hollow elbow with valid wall context; 45LR/
90-3D/45-3D/90SR elbow generation; elbow dimensional/port validation;
quarantined NPS8 blocks elbow OD, non-quarantined neighbor unaffected;
tee generation + run/branch CTE validation + 3-port role validation; cap
generation + standard/heavy-wall length selection + missing-wall-context
handled safely; concentric reducer generation + OD/length validation;
eccentric reducer generation + offset validation + orientation
determinism; reducer port-role validation; reducer involving quarantined
NPS8/NPS12 blocked, unaffected pair (6"x3") generates normally; repeated-
input determinism; construction-rule version participates in
reproducibility; tessellation-only change alters fingerprint without
changing engineering identity; end-to-end elbow/tee/cap/concentric/
eccentric-reducer pipelines; unsupported buttweld subtype remains
structured unsupported; Prompt 12 pipe pipeline unchanged; demo unchanged.

**Full regression:** 575 total tests (405 Prompt 4-11 + 90 Prompt 12 +
80 new) pass; `git status` confirms only the expected additive/modified
geometry files changed (see README Prompt 13 addendum for the full list)
- zero modifications to `generator.py`, `rules/*.py`, `schema.py`,
`dimension_library.py`, `kgpe/resolver/*`, or any canonical data-layer
file; data-layer fingerprint unchanged at
`9238ab3cb896101c545450df6f0ff070301b4ba68117771b4105e87606c2c873`.
