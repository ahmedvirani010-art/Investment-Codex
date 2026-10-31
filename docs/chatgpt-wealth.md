# Phase 4 through the ChatGPT GitHub plugin

The calculator already supports retirement, PF/VPS/gratuity, cash, gold and optional
crypto. This interface lets ChatGPT prepare typed requests and read durable results.
GitHub Actions runs Python; ChatGPT interprets the evidence and results. There is no
LLM API, broker integration, or live data acquisition in the runner.

## Deployment prerequisites

1. The repository owner must change Investment-Codex to **private** in GitHub settings.
   Verify `visibility: private` with the GitHub plugin before uploading financial data.
   The connector has no repository-settings mutation tool; this change is an owner
   setting, not something a request can bypass. Privatizing does not retract copies
   of anything previously published; no real financial inputs belong in public history.
2. Reconcile the local implementation with the remote default branch (`work` when
   inspected). Publish with a normal push, without force-pushing or workbook merges.
3. Run CI: locked installation, wheel/source build, dependency check, installed
   version check and full tests. The current offline environment cannot supply all
   packages for a fresh installation; this runner check remains required.
4. In `config/wealth-requests.json`, set `enabled` and `auto_push` to true and
   `authorized_by` to the approving owner. Keep repository identity and explicit
   work/time/size limits. This is independent of PSX production and schedule policies.
5. Submit a synthetic request first and inspect its receipt/workbook through the
   plugin. Confirm that a simulated change leaves canonical balances untouched.
   Only then import real, dated records through existing dataset activation/import
   commands. A wealth request cannot promote demo assets into real holdings.

The workflow runs only in a private repository on its actual default branch.
It has no timer. Its publication concurrency group is shared with other writers.
Policy-disabled invocations stop before installing dependencies. Changing repository
visibility or policy is never implicit in a financial request.

## ChatGPT operating instructions

Examples: “Run my retirement and gold/cash comparisons”, “What if I contribute PKR
X monthly?”, “Save this dated PF balance and rerun retirement.”

1. Verify private repository metadata. Read `docs/wealth-request-schema.json`,
   `config/wealth-requests.json`, and the committed `data/canonical/portfolio.json`.
   Record `dataset.dataset_id`, `published_run_id`, and the current accepted inputs
   from `runs/<analysis_run_id>/input.json`. Read existing wealth assumptions before
   asking for facts that are already recorded.
2. Translate the instruction into **validate**, **simulate**, or **accept-and-run**.
   Use simulate for a what-if. Use accept-and-run only when the user's instruction
   explicitly requests saving/updating financial inputs. Do not ask for redundant
   confirmation of an explicit save instruction. If intent is ambiguous, simulate.
3. Collect missing dated balances, retirement/spending dates, contributions,
   inflation, asset returns, fees/taxes, withdrawal order and benefit claims. Preserve
   unknowns as null; never substitute zero, invent a source, or mark an estimate as a
   verified fact. Crypto requires explicit opt-in. Returns are supplied assumptions,
   not promises. Existing immutable record IDs/source IDs cannot be edited: revise
   a record with a new ID and `supersedes`, and cite a new source ID for revised facts.
4. Create a new `requests/wealth/<request_id>.json` using the plugin's create-file
   operation. Use a unique ID, exact accepted run ID, dataset and assessment date.
   An optional package is a complete `wealth` collection plus new `sources`; partial
   field patches are not supported. Unchanged records remain present. Supply
   `package.market_cutoff` explicitly when importing newer dated observations;
   advancing the cutoff does not refresh old PSX prices or evidence.
5. Read `reports/requests/<request_id>.json`. A missing receipt means pending, disabled,
   or failed before publication; never claim completion from file creation alone.
   Check its request hash against the submitted file. Read the accompanying Markdown
   report and link the workbook; use the returned publication commit or the file's
   Git commit metadata to pin the result. The receipt includes base revision, result
   run, module statuses, assumptions, evidence IDs, missing inputs and deferred work.
6. Explain each module separately. COMPLETE means calculable, not that retirement
   is funded. FUNDING_SHORTFALL is a calculated outcome; PARTIAL means missing/stale
   evidence or deferred work. Comparisons cover declared histories/assets only.
   Explain common-period returns; individual history returns may span different dates.

The available plugin cannot directly dispatch a workflow. Creating the request file
emits a normal push event. Results are committed UTF-8 JSON/Markdown and binary Excel;
ChatGPT can fetch the former and link the latter. Re-running or repeatedly reading
a request cannot duplicate balances. Corrections must have a new request ID.

## Minimal run request

```json
{
  "schema_version": "1.0",
  "request_id": "wealth-20261027-001",
  "operation": "simulate",
  "dataset_id": "REPLACE_WITH_ACCEPTED_DATASET",
  "expected_run_id": "REPLACE_WITH_PUBLISHED_RUN",
  "as_of": "2026-10-27",
  "modules": ["retirement", "cross-asset"],
  "instruction": "Run both modules with the accepted assumptions",
  "authorized_by": "REPLACE_WITH_REQUESTING_USER"
}
```

The date above is illustrative, not evidence of fresh inputs. Omit `package` to
reuse accepted inputs. For new inputs, start with `docs/templates/wealth-packet.json`.
It intentionally contains empty collections and is **not importable until completed**.
Use `docs/wealth-packet-schema.json` and `docs/wealth-schema.json` for field details;
`fixtures/phase4-demo.json` contains a fully synthetic worked example.

## Local checks and recovery

```bash
investment-workspace wealth-preflight --file inputs/private/wealth-packet.json
investment-workspace benchmark-wealth --samples 3 --months 360
investment-workspace wealth-request --file requests/wealth/example.json --local-demo
```

Preflight uses an isolated checkout; it leaves canonical files and Git HEAD intact.
It checks the same schema, immutable evidence and arithmetic gates as publication.
Local-demo processing rejects real dataset modes and sources without synthetic/demo
identifiers. Production processing requires Actions-provided privacy/repository
context and the explicit policy; request fields cannot change that context.

All requests are scanned in filename order whenever the workflow runs. No FIFO
assumption is made; simultaneous accepted updates use the expected-run guard, so
only the first can accept a shared base revision. Later stale requests receive
INVALID receipts and need a new request based on current accepted state. Historical
request receipts stay immutable. An altered request is rejected without overwriting
its original receipt. Workflow dispatch provides manual queue recovery without
changing or duplicating requests. Interrupted local publication uses `recover`,
then `wealth-request --pending`; the existing journal protects manual edits.

Accepted changes, reports and workbooks publish in one journaled commit. Simulations
publish scoped snapshots/workbooks but leave canonical inputs and totals unchanged.
Rejected/invalid requests publish diagnostics only. A normal push failure retains
local commits; inspect remote HEAD and use a fresh checkout or retry the normal push.
Never force-push, reset user edits, or merge conflicting XLSX files.

## Measurement and limitations

`benchmark-wealth` creates a synthetic 3-scenario workload in a temporary repository.
For unchanged and one-assumption-changed cases it compares full cache verification
with normal incremental evaluation, alternates execution order and reports medians,
work units, cache hits and phase timings. Both paths check the full required valuation
coverage, write the workbook and validate parity. A mismatch invalidates the benchmark.
Clone/commit/workbook overhead is included in end-to-end measurements. A ratio below
one is reported honestly; no performance threshold or AI saving is claimed. Unknown
AI costs remain null. Real-workload benchmarks require representative supplied data.

Release-check measurement on a synthetic 360-month workload (3 samples, this shared
execution environment): full/cached median end-to-end seconds were 4.76/4.91 for
unchanged inputs and 6.03/7.24 for one changed assumption. All pairs passed output
parity. These observations show no end-to-end speedup for this workload; workbook,
Git and copying overhead are included and results are environment dependent.

Deployment check on 2026-10-27: GitHub CLI visibility mutation returned `Forbidden`.
The owner must apply **Settings → General → Danger Zone → Change repository
visibility → Make private**, then verify metadata through the plugin. This release
keeps `enabled: false` and `auto_push: false` until that prerequisite and the clean
runner checks succeed. No source or financial request has been pushed by this release.

## Unified interface in 0.6

The compatible wealth commands remain available. New deployments use
[workspace requests](workspace-requests.md), `config/workspace-requests.json`, and
`request --pending`, scanning both request folders under the same writer group.
R2 transfers and explicit portfolio/IC imports use that typed interface.
