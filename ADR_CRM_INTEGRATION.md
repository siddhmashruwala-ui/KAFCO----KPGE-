# ADR-01: KGPE Integration with the KAFCO Sales CRM

**Status:** Accepted (Phase 1 implemented). **Author:** Jarvis (Lead Architect directive, 2026-07-16).

## Context

The KGPE engineering kernel (Prompts 1-15) is complete: a deterministic
pipeline `EngineeringRequest -> EngineeringResolver -> GeometrySpecification
-> GeometryKernel -> GeometryResult`, covering flanges, buttweld fittings,
pipe, socketweld fittings, and olets, with full provenance/fingerprint/
manufacturer-context honesty.

Before designing the CRM integration, the existing CRM stack
(`C:\Users\admin\Desktop\Sales and CRM`) was inspected end-to-end. This
surfaced a critical fact that changes the integration shape: **the
dashboard already contains a complete, production-quality 3D hologram
viewer**, built directly into `KAFCO_CRM_Dashboard.html` ("KAFCO HOLO-CAD
v2"):

- `mosParse()` / `holoSpecFor()` - regex-parses a line item's free-text
  description into an approximate geometry spec (type, NPS, schedule,
  class, length), then looks dimensions up against small embedded JS
  tables (`stdPipeOD`, `stdPipeWT`, `stdFlg`).
- `holoBuildModel()` - constructs the actual Three.js parametric geometry
  per part type (flange, elbow, tee, reducer, nipple, cap, pipe, bar,
  nipoflange, blind, spectacle, generic buttweld).
- `holoMat()` - a custom multi-hue Fresnel/scanline shader that IS the
  "hologram" visual language already established across the dashboard.
- `holoDim` / `holoLeader` / `holoDimCircle` / `holoTolGlow*` - a full
  CAD-style dimension-annotation system with tolerance-glow halos.
- `holoOpen()` - the full-screen viewer: OrbitControls + WASD fly camera,
  section/clipping view, quantity HUD strip, material spec-sheet side
  panel (`mosGrade`/`MATPROPS` - composition + mechanical properties for
  ~18 alloy grades), all styled to the dashboard's dark/cyan/gold theme.
- `mhhHoloBuild` / `mesHoloBuild` - mini/embedded preview variants used
  in the Order Command board and MES Workspace hero tiles.

This viewer already **is** the "Jarvis-style engineering hologram
experience" the production-integration directive asks for. What it does
**not** have is engineering authority: `mosParse`'s regex guesses at
dimensions from free text, and `holoSpecFor`'s lookup tables are a small
hand-maintained subset of the full canonical data KGPE already carries
(ASME B16.5/B16.9/B16.11/B36.10M/MSS SP-97, with tolerances, manufacturer
context, and construction-rule provenance).

Line items themselves (`KAFCO_Orders.json`) carry only free-text
`desc`/`qty` - no structured product-family/standard/subtype/size field
exists yet to hand KGPE a clean identity.

`kafco_server.py` is a small, dependency-free `http.server` process
(no framework) serving static files and a handful of JSON endpoints
(`/data`, `/orders`, `/suppliers`, save endpoints, folder/quote helpers).

## Decision

**Do not build a new viewer.** Integrate KGPE as an additive,
independently-failing **data backend** behind the existing hologram
system, in two layers:

**1. Backend bridge (implemented this session).**
`kgpe_bridge.py` (new file, `Sales and CRM/`) is a pure adapter: it adds
the KGPE checkout to `sys.path`, builds one `CanonicalReader` +
`EngineeringResolver` at process start (expensive - built once, reused
per request, never rebuilt per-call), and exposes three functions:
`status()`, `discovery_query(payload)` (wraps
`kgpe.geometry_spec.discovery.progressive_discovery`), and
`resolve_geometry(payload)` (wraps `kgpe.geometry.pipeline.run_pipeline`
end-to-end: resolve -> compile -> generate, returning the full
`PipelineResult.to_dict()` - every stage's honest status, never
collapsed to one ok/fail flag). Every function catches broadly and
returns a structured `{"ok": false, ...}` envelope on any failure - a
KGPE problem can never crash the CRM server.

`kafco_server.py` gained exactly three additive routes (no existing
route touched): `GET /kgpe/status`, `GET /kgpe/discovery`,
`POST /kgpe/geometry`. The import itself is wrapped in `try/except` so a
missing/broken KGPE checkout degrades only the new routes, never the
existing dashboard/Excel-sync/orders/suppliers functionality.

Verified live (real HTTP, real KGPE checkout, real canonical data):
`/kgpe/discovery` returns real product families
(`flange, buttweld_fitting, socketweld_fitting, olet, pipe`) and the full
cascading standard/subtype/size/rating/dimension chain; `/kgpe/geometry`
returns `GEOMETRY_GENERATED` with a full mesh/features/ports/fingerprint
payload for a real request (ASME B16.5 6" 150# weld-neck flange); a
malformed request returns a clean `invalid_request` error, never a stack
trace; the pre-existing `/data` endpoint was confirmed unaffected.

**2. Frontend wiring (next phase - not yet implemented).** Add a
**Part Configurator**: a small additive UI (modal or side-panel) on each
Order Command line item where a user can optionally pick
family/standard/subtype/size/rating from live `/kgpe/discovery`-backed
dropdowns. When a line item has a saved KGPE identity, `holoSpecFor(it)`
tries a `/kgpe/geometry` call first and adapts the returned
`geometry_payload` into `holoBuildModel`'s existing input shape; when it
doesn't (the overwhelming majority of historical line items), it falls
back to today's `mosParse`-based heuristic spec exactly as now. Nothing
about `holoOpen`/`holoBuildModel`/`holoMat`/the dimension system changes
structurally - KGPE only gets to supply *better dimensions*, honestly
labeled as verified-vs-estimated in the side panel.

## Consequences

- Zero risk to the existing CRM: every change so far is additive files
  or additive routes; the dashboard HTML has not been touched at all.
- KGPE's authority is used where it already has real coverage (flange,
  buttweld, socketweld, olet families per ASME/MSS) and the existing
  heuristic viewer remains the fallback everywhere else (pipe/bar cut
  lists, reducers, nipples, spectacle blinds, arbitrary free-text
  descriptions) - so every line item still gets *a* hologram, just not
  always a KGPE-verified one yet.
- The canonical reader/resolver singleton in `kgpe_bridge.py` is built
  once per server process start; a canonical-data change requires a
  dashboard server restart to pick up (documented limitation, not a bug -
  matches the existing Excel-cache-by-mtime pattern already in
  `kafco_server.py`).
- The Part Configurator (not yet built) is the only new *manual* step in
  the workflow - unavoidable, since free-text descriptions cannot be
  reliably and deterministically mapped to a canonical engineering
  identity without guessing, which KGPE's whole design forbids.

## Next steps

1. Part Configurator UI (dropdowns backed by `/kgpe/discovery`, saved
   per line item in `KAFCO_Orders.json` under a new optional field e.g.
   `it.kgpe_identity` - additive, does not alter existing item shape).
2. `holoSpecFor()` KGPE-first / heuristic-fallback wiring, with a visible
   "KGPE VERIFIED" vs "ESTIMATED" badge in the hologram side panel.
3. Regression pass + updated docs + commit/push (both repos).


## Update — 2026-07-16, Phase 2 complete

Both "Next steps" items from the original decision are now implemented and
live:

1. **Part Configurator** — every Order Command line item has an
   "Engineering ID" button opening a modal with cascading dropdowns
   (family -> standard -> subtype -> size -> rating -> manufacturer
   profile), all populated live from `/kgpe/discovery`. RESOLVE calls
   `/kgpe/geometry` and shows the honest outcome; SAVE only enables once
   KGPE returns `GEOMETRY_GENERATED`. Saved as
   `it.kgpe_identity = {request, verified, fingerprint, saved_at}` on the
   line item in `KAFCO_Orders.json` (additive field, defaulted to `null`
   for every existing item via `ogNorm()`).

2. **`holoSpecFor()` KGPE-first wiring** — when an item has a saved,
   verified `kgpe_identity`, `holoSpecFor()` now overlays specific
   KGPE-authoritative values on top of its normal heuristic spec:
   `outside_diameter_mm` -> `spec._od`, any `wall_thickness*` measurement
   -> `spec._wt`, and (for flanges) the `bolt_pattern` feature's bolt
   circle/count combined with a `flange_thickness*` measurement ->
   `spec._flg` (converted to the inches-based 4-tuple `holoBuildModel`
   already expects, so the existing Three.js construction code for the
   flange family needed zero changes). Every other field - and every item
   without a saved identity - is completely untouched; the merge only
   ever overlays fields KGPE actually returned, never invents or
   approximates on KGPE's behalf.

   The KGPE fetch itself never blocks rendering: `holoSpecFor()` always
   produces the normal heuristic spec first, then kicks off a
   fire-and-forget `/kgpe/geometry` call (cached per item + request) that
   silently upgrades the already-visible hologram (mini preview, MES hero,
   or the full viewer if still open) once it resolves. A side-panel badge
   (`kgpeBadgeHtml()`) shows KGPE VERIFIED / RESOLVING / NOT YET READY /
   UNAVAILABLE so the distinction is never hidden from the user.

Verified: `node --check` clean on the full extracted script; all new
function/variable names confirmed present in the live-served HTML;
`/data`, `/orders`, `/version` unaffected; full KGPE suite still 748/748
after both sessions. Both repos committed and pushed.

### Known limitation carried forward

Only flange-family items get a `_flg` override today (the only family
whose `holoBuildModel` "authoritative override" shape was mapped this
session). Buttweld/socketweld/olet items with a saved, verified identity
still get the OD/WT overlay but keep their existing heuristic shape
construction otherwise - extending per-family overrides to the other
product types is straightforward (same pattern, different
`geometry_payload.features`/`measurements` keys) but not yet done.

### Next recommended milestone

Extend the verified-dimension overlay to buttweld/socketweld/olet
families (map their `geometry_payload` shapes the same way the flange
family was mapped this session), and consider exposing KGPE's raw mesh
(`geometry_payload.mesh`) as an optional "true canonical geometry" render
mode for users who want the exact standard-published solid rather than
the parametric approximation - a larger undertaking requiring a
BufferGeometry adapter and is out of scope for the current additive-only
integration style.
