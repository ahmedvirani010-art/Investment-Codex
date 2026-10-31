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
