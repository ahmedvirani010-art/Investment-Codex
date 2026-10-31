# Controlled-import completion release

Version 0.4 implements the remaining offline application capabilities and gated
production-runner support. It does not claim migration of unavailable source files,
verified real holdings, live acquisition, an activated scheduler or an AI service.
The original PRD remains unchanged. Its implementation/deployment requirements are
tracked separately in the readiness report.

## Evaluate and review

```bash
uv run --locked python -m investment_workspace readiness
uv run --locked python -m investment_workspace run daily --as-of 2026-10-26 --offline
uv run --locked python -m investment_workspace run timing --require-full-coverage --offline
uv run --locked python -m investment_workspace changes --since-run RUN_ID
```

The evaluation date defaults to the supplied observation cutoff for backward-
compatible offline calculations. An explicit `--as-of` must be on or after that
cutoff. It advances freshness/expiry assessment without relabelling the market
cutoff, completed sessions, balance timestamps or financial periods. Scheduled
runs always pass the current Asia/Karachi evaluation date. Missing calendar
coverage blocks timing rather than inventing market sessions.

`--require-full-coverage` checks the selected workflow: valuation, dividends,
timing, macro, watchlist, IC, retirement, cross-asset or the integrated daily run.
A valid Stage 4/blocked purchase signal is distinct from missing calculation data.
Legacy compatibility and production readiness remain separate. A synthetic demo
can demonstrate complete arithmetic; it cannot activate production.

## Dataset boundary

Each accepted workspace has an immutable dataset ID and mode. Older datasets
without explicit IDs read as `legacy.demo` or `legacy.user`. A normal import cannot
switch them or mix demo transactions into real history.

For the one explicitly supported transition from an existing demo to verified real
inputs, supply a complete real bundle with a distinct `dataset_id`:

```bash
uv run --locked python -m investment_workspace activate-dataset \
  --file inputs/private/real-bundle.json --author YOUR_NAME \
  --reason 'Initialize reconciled production exports' --confirm-real-data
```

The command archives the prior dataset snapshot, including notes and source/decision
history, before publishing the new active dataset. Existing run snapshots/logs remain
readable. Obvious DEMO/synthetic source markers cannot be promoted. Confirmation is
an importer assertion; it does not prove that arbitrary supplied numbers are real.
Other dataset switches require a fresh data workspace; they are not silent resets.

## Evidence packages

`import-evidence --file PACKAGE.json [--as-of DATE]` accepts a strict package with
optional full `bundle`, new `sources`, module replacements (`research`, `integration`,
`financials`, `wealth`), optional updated observation `market_cutoff`, and `files`.
A module replacement is the full active snapshot, preserving accepted IDs or using
explicit supersession. Existing specialized import commands remain supported.

Each file has `path` and `document`: source ID, SHA-256, suffix, role and explicit
`store_permitted: true`. Relative paths resolve against the package directory.
The original hash must match; source document hash, if declared, must agree.
Permitted suffixes are PDF, XLSX, JSON, CSV, Markdown and text. Supported roles are
SOURCE_DOCUMENT, EVIDENCE_CONTRACT, REPLACEMENT_PROMPTS and VALUATION_RERUN.
Original bytes survive publication interruption/recovery. Failed package parsing
publishes diagnostics and retains last-good analysis.

See [the implemented evidence contract](evidence_contract.md). The missing original
contracts remain required recovery evidence; this implementation document does not
pretend to be one of them.

## Workbook migration and compatibility

```bash
uv run --locked python -m investment_workspace migrate-workbook \
  --file /path/original.xlsx --mapping inputs/private/mapping.json --dry-run
uv run --locked python -m investment_workspace migrate-workbook \
  --file /path/original.xlsx --mapping inputs/private/mapping.json --accept
```

The mapping file has exactly `sources` and `migration`. The typed migration includes
record metadata, kind LEGACY_DATASTORE/MODEL_WORKBOOK, original workbook hash,
approver/reason, storage permission and sheet mappings. A mapping declares sheet,
header row, canonical collection, canonical-to-legacy columns and key fields.
Every other labelled legacy column needs an explicit ignored-column reason.
Duplicate rows/headers, mismatched keys, absent formula caches and numeric
mismatches block acceptance. Formulas are inventoried and retained, never executed.

Collections are `timing`, `mean_reversion`, `valuations`, `earnings` and `history`.
History is flattened by ticker/session from imported security histories. Its
`price_basis` is explicitly RAW (default) or SPLIT_ADJUSTED. Historical dates and
current numerical outputs are reconciled with exact row coverage, per-field
comparisons and totals; tolerances default to 1e-8 absolute/1e-12 relative.

A few current cells are only PARTIAL_MAPPING. LEGACY_DATASTORE becomes VERIFIED
only with a historical price mapping (ticker/session/close), signal mapping,
complete mapped-or-explained headers, passing numerical parity and explicit
`methodology_reviewed: true`. That last flag is a dated human review assertion,
not automatic equation discovery. Review the real original equations and lineage
before asserting it. Missing originals remain blockers.

Accepted evidence and baseline checks are immutable. A revised migration appends
a new record/source with `supersedes`; historical proofs remain retained. Only
active verified proofs clear compatibility gates and generate
`workbooks/PSX_Mean_Reversion_DataStore.xlsx` from canonical values. It is a derived
review artifact, never an independently edited numerical store. Blocked current
fields export UNKNOWN; historical parity proof does not relabel today's data fresh.

## Sector models and financial bridges

`models.REGISTRY` contains versioned reference contracts for banks, E&P, industrials,
OMC, refining, finite-life IPPs, holding-company SOTP, autos, cement, textiles,
chemicals, pharma, consumer, insurance and shipping. Existing v0.3 inputs keep their
reference semantics. New sector/method replacements need a version-matched sourced
approval in addition to `certification: VALIDATED`. Provisional replacements do not
enter certified rankings. These formulas are not claimed recovered equations.

- FCFE DCF discounts equity cash flows plus explicit terminal equity value per share.
  Finite-life IPPs require all contract years and zero terminal perpetuity.
- SOTP sums component equity values times ownership, subtracts explicit parent-only
  net debt/liabilities/minorities and divides by shares. Components are flat, uniquely
  identified values; no circular look-through calculation is guessed.
- ROE/book uses BVPS × (ROE − g)/(ke − g) with sector-specific driver evidence.
- An approved normalized multiple uses positive normalized operating EPS × a supplied
  multiple. It is not a generic low-P/E screening rule.

Separate surplus cash requires explicit exclusion of its income from operating
valuation. Numerical forecasts flag included cash income and prevent that add-back;
parent net cash cannot be added twice in SOTP. Optional payout cross-check tolerance
turns the disclosed cross-check into an enforced reconciliation.

FinancialFact imports carry period, accounting basis, line item, amount/units and
locator, with the shared source/history contract. An OperatingForecast references a
confirmed same-basis REVENUE fact and supplies growth, EBITDA margin, depreciation,
interest, other income, **explicit tax charge**, capex, working-capital increase,
net borrowing and shares. Each forecast row uses its cited base independently:

```text
Revenue = cited revenue × (1 + supplied growth relative to that cited base)
PAT = Revenue × EBITDA margin − depreciation − net interest + other income − tax charge
EPS = PAT / shares
FCFE = PAT + depreciation − capex − working-capital increase + net borrowing
```

Forward EPS, cash-flow amounts, period and share count must reconcile to the
valuation's supplied inputs. Tax-loss benefits are never inferred. The Forward_Bridge
and Financial_Facts tables expose these calculations and their evidence IDs.

## Incremental work and budgets

Pure valuation, timing and retirement units cache their deterministic outputs in
committed canonical snapshots. Fingerprints include relevant inputs and code/schema
versions. Ownership/evidence/expiry/coverage gates run on every attempt. Weekly
valuation explicitly reproduces cached arithmetic; a mismatch fails closed.
Unchanged derived records keep original lineage. Phase runtimes, actual work units,
cache hits and deferred units are measured separately from unknown AI usage.

`run --max-work-units N --max-seconds S` bounds calculation work. An exhausted unit
is queued, excluded from complete coverage and published as PARTIAL. Completed
units are retained for the next run; a single interrupted unit restarts from its
beginning. Raising/removing the limit resumes the remaining work without duplicate
financial imports. Dependency and deferred-work records are retained per run.
Large list changes use count/hash summaries and a committed snapshot pointer in
Excel, avoiding truncated Change_Log cells. The CLI can compare committed runs.

## GitHub Actions operation

The private Actions workflow supports manual dispatch (dry run by default) and
scheduled triggers. The production policy ships **disabled**; scheduled invocations stop at its
policy check before installing dependencies or calculating results. It reads accepted exports only; it cannot acquire current market data.
A weekday trigger is a polling opportunity, not an assertion that a session closed.
The imported calendar determines eligibility. Unrecovered Monday macro timing stays
manual; weekly valuation and IC use the PRD's Asia/Karachi times.

Activation requires explicit private-repository confirmation, real dataset identity,
manual parity, original document roles, full provenance, validated calibration,
complete required coverage, explicit budgets and normal-push authorization. Required
macro indicator identifiers are listed in the production policy and must match the
controlled exports. No setting creates or changes personal investment limits.

The job has one publication concurrency group and never cancels an active writer.
It verifies branch and remote HEAD before calculation, uses today's Karachi date,
publishes diagnostics even for incomplete refreshes under the explicit policy,
and verifies a normal push. Divergence stops for a fresh canonical checkout; there
is no force-push, binary merge or silent re-ingestion. Push failures retain local
results. Production execution is restricted to the configured Actions environment.
No remote push, timer activation or legacy-job cancellation was performed here.

## Final integrity rules

A valuation requires event review through the assessment date; an unchanged input
cutoff cannot stand in for a current review. Future event review dates are rejected.
Macro selection uses the latest effective observation per domain/indicator;
conflicting same-date facts block that indicator while historical rows remain visible.
Workbook mappings must cover or explicitly ignore every sheet and column with a
reason. Generated compatibility exports carry a provenance sheet; losing verified
parity replaces old numerical exports with a blocked provenance-only workbook.

## Release validation

The full offline suite passes: **168 tests**, including historical snapshot parity,
immutable evidence, budget recovery, sector arithmetic, locked assets, withholding,
FX, migration reconciliation and local-remote publication failures. Both the prior
repository workbook and a separately initialized Phase 4 synthetic demo pass
committed integrity and workbook parity checks. Production dry runs remain blocked
without mutation. No real remote was pushed.

Validation used the preinstalled locked environment (`uv run --locked --no-sync
pytest`). A fresh offline `uv sync --locked` could not obtain the pinned setuptools
build dependency from the local cache; clean dependency installation on the future
runner remains an activation check.

## Phase 4 chat interface (0.5)

The manual wealth request workflow is implemented separately from PSX production
activation. See [the ChatGPT operator guide](chatgpt-wealth.md) for the request
contract, privacy prerequisite, queue processing, simulation isolation, accepted
updates, committed results and journal recovery. Cross-asset pairs now share the
retirement cache/budget mechanisms, and their returns disclose common endpoints.

Release validation includes a real local runner against a temporary bare Git remote,
with successful normal pushes, remote divergence, push failures and last-good data
retention. These are local integration tests, not verification of deployed GitHub
Actions. A separate synthetic chat-request workbook is generated for review.

Deployment remains disabled: on 2026-10-27 the configured GitHub CLI's visibility
PATCH returned `Forbidden`; the repository could not be made private through this
session. No application code or financial request was pushed. The owner must set
repository visibility to private in GitHub Settings before remote deployment.
An isolated clean dependency installation with scoped network access also failed
because the proxy blocked a PyPI wheel download. Installed dependency compatibility
and locked resolution pass; fresh build/installation are still CI prerequisites.

The final 0.5 offline release suite passes **192 tests**. All six prior committed
revisions pass integrity and workbook parity. The request and packet JSON schemas
match their implementation. Installed third-party dependencies pass `uv pip check`,
and the lockfile passes offline resolution. The separate 360-month/3-sample synthetic
benchmark passes full/incremental analytical parity; measured results are retained
at `reports/benchmarks/phase4-synthetic-360-month.json` without a speedup claim.
