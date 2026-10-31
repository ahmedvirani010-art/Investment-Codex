# PRD completion release — 0.6

This release implements the code changes selected from the 31 October PRD audit.
It does not claim full numerical coverage of every sector or certification of
unavailable real sources. All operational policies remain disabled by default.

| Finding | Code delivery | Remaining dependency |
| --- | --- | --- |
| F01 | Immutable historical dividend basis, roll-forward and correction review | Actual dated entitlement/receipt evidence |
| F02 | Net pending, partial receipts, separate fees and withholding exceptions | Declared tax/withholding policy |
| F03 | Assessment-date countdowns, 30/90-day buckets and expiry checks | Current sourced catalyst records |
| F04 | Versioned common profiles, explicit bindings, units and domain overrides | Reviewed mappings and real assumptions |
| F05 | Typed Bank/E&P/Industrial PAT/EPS/FCFE/capital bridges with approvals and reconciled facts | Methodology/source approval; remaining twelve sector engines deferred |
| F06 | Append-only IC approval/rejection/deferral, dependency hashes and transaction fulfilment | Explicit user decisions and actual imported trades; no orders |
| F07 | Common published code version/hash with original carried lineage | Historical rows resolve through their original manifests |
| F08 | Semantic money/rate/rank/correlation/date/confidence/status formatting and old/new parity | User review of presentation with actual data |

## Interfaces

Read [workspace requests](workspace-requests.md), [numerical contracts](numerical-models-v1.md),
and [dividend continuity](dividend-continuity.md). Current JSON schemas are generated
for workspace/wealth/storage requests, packages, shared profiles, IC decisions and
all existing input modules. The original fixtures and frozen snapshots are unchanged.
`completion-demo.json` has separate synthetic identities for the new contracts.

One typed scanner handles the old wealth and new workspace request folders. It
supports every existing analytical workflow, isolated simulation, explicit accepted
input packages, user IC decisions, pinned transfer references and R2 operations.
Input packages cannot select arbitrary filesystem paths or execute shell code.
Portfolio updates preserve other owned modules. Calculation and transfer results
are independent, and optional archive failures preserve valid accepted calculations.

R2 uses a pinned boto3 SDK with Signature V4/auto region, exact prefix-restricted
keys, streaming size/deadline checks, bounded retries, SHA-256 verification and
immutable archive keys. Its receipts are Git publication records; an R2 object does
not itself establish financial acceptance. Pinned pulls can be rehydrated by later
ephemeral runners. There is no object deletion, unrestricted sync, public bucket
requirement, live feed acquisition, Monte Carlo or trade execution.

## Verification scope and rollout

Tests cover original financial/workbook invariants and the new defect regressions,
shared assumptions, numerical hand values and failure gates, decision basis changes,
partial/full/excess fills, all-module requests, transfer pinning/limits/corruption,
interruption/retries and normal Git publication. A real SDK client-configuration test
runs when boto3 is installed; the offline pre-existing local environment lacks it.
The dependency lock is resolved by GitHub Actions, not fabricated from package names.

Before activation: verify private repository access, configure GitHub R2 variables
and bucket-scoped secrets, verify live connectivity, run a synthetic private request
through the actual GitHub-plugin → Actions → receipt flow, then import/approve real
data and demonstrate manual parity. The current public repository and restricted
local network do not satisfy these gates. Do not enable policies merely because
unit tests pass. Original documents, real legacy datastore migration and live
schedules remain pending; the Monday macro time and special monitors are not guessed.

## Recorded verification — 31 October 2026

The fixed synthetic GitHub submission passed [Actions run 41186668176](https://github.com/ahmedvirani010-art/Investment-Codex/actions/runs/41186668176).
The plugin created request commit `00906027ce6194fe7d56452e362775870760e8a8`;
Actions published proof commit `9ce264025d06550b933f8dfda7aae10741d428b9`.
The [receipt](https://github.com/ahmedvirani010-art/Investment-Codex/blob/codex/prd-completion-v06/reports/smoke/verify-v06/receipt.json)
reports valuation, retirement and cross-asset COMPLETE, `synthetic_only: true`,
`canonical_unchanged: true`, and `accepted_inputs_changed: false`.
Its workbook and snapshot are stored beside it. This public synthetic route proves
submission → calculation → committed receipt, and does not prove private production
or live R2 access.

That CI run completed a clean locked installation, dependency compatibility check,
wheel/source build, installed-version check and all 244 then-present tests, including
the real boto3 client-configuration test without external service calls. The final
inventory contains 255 tests: the original 192 and 63 added cases. The additional
11 boundary/operation cases passed locally and are included in full CI. The offline
local full run had 243 passes and one SDK-only skip before those additions.

| Evidence | Relevant regression tests in `tests/test_prd_completion_v6.py` |
| --- | --- |
| F01–F02 | `test_dividend_roll_preserves_verified_entitlement_and_cash`, `test_partial_receipts_and_unknown_tax_do_not_invent_pending`, `test_correction_outside_window_keeps_previous_proof`, `test_expired_historical_entitlement_late_partial_and_excess_receipts` |
| F03 | `test_catalyst_uses_assessment_not_old_cutoff`, `test_catalyst_bucket_boundaries_keep_market_cutoff` (past, today, 30, 31, 90, 91 days) |
| F04 | `test_shared_profile_overrides_units_expiry_and_dependency`, `test_shared_assumption_revision_blocks_owned_forecast_not_mutates_eps` |
| F05 | `test_first_wave_engines_hand_calculated` (PAT/EPS: 50/5, 100/10, 70/7; FCFE: 75/54), missing-driver, capital, collections, share-basis, duplicate-period and payout guards |
| F06 | Decision basis/history, transaction lifecycle, no-double-link and request-review-status tests |
| F07–F08 | Uniform-lineage, native-date/status formatting, original historical workbook/integrity/parity tests |
| R2 | Pinned pulls, immutable archives, hash/limit/path restrictions, interrupted/retried reads, corrupted content and ephemeral rehydration tests |
| Requests | All eleven workflow simulations; every nine operation types published against a temporary bare Git remote; normal push/divergence and optional archive-failure tests |

The refreshed accepted demo export `20261031T085618170933Z-fbe64605` passed
integrity and numerical/record workbook parity with NO_MATERIAL_CHANGE. Historical
analysis lineage is preserved. Original fixtures and frozen historical workbooks
remain unchanged.

The [synthetic benchmark](../reports/benchmarks/v0.6-synthetic-360-months.json)
used three samples per case over 360 months, with parity PASS. Median full/cached
wall times were 12.085/11.273 seconds for unchanged inputs and 10.455/8.217 seconds
for one changed assumption. These include clone, calculation, workbook, commit and
validation, ran alongside tests, and are observations rather than a production
speed guarantee. No measured AI usage or cost saving is asserted.

Open acceptance evidence remains: private repository verification; GitHub runner R2
configuration, credentials and actual connectivity; a private synthetic financial
request; sourced real imports and legacy-workbook reconciliation; version-matched
methodology approval; manual production demonstrations; and explicit Monday macro
and special-monitor timings/methodologies. Remaining numerical sectors are OMC,
refining, IPP, holding companies, auto, cement, textile, chemical, pharma, consumer,
insurance and shipping. Policies and schedules remain disabled.
