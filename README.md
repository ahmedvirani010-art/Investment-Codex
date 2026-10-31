# Investment Workspace

A private, Git-backed investment research workspace. **Version 0.3 implements
Phases 1–3 offline**, with synthetic fixtures and evidence-gated research imports. It does not contain Ahmed's
holdings, live PSX prices, validated valuations, or trading instructions.

## Quick start

Requires Python 3.12+, Git, and `uv` (validated with 0.12.23).

```bash
uv sync --locked
uv run --locked pytest
uv run --locked python -m investment_workspace init --offline
uv run --locked python -m investment_workspace validate --run latest
```

The included repository already has a published demo. `init` refuses to replace
accepted data. For another demo attempt, use:

```bash
uv run --locked python -m investment_workspace run portfolio --offline
```

The main review artifact is
[`workbooks/Investment_Workspace.xlsx`](workbooks/Investment_Workspace.xlsx).
Dashboard cells are computed in Python and readable without Excel recalculation.
Unknown values display as `UNKNOWN`, never zero. The workbook contains holdings,
transactions, cash, reconciliation, sources, assumptions, coverage, gaps, notes,
run/change logs, and unknown usage telemetry. Phase 4 tabs explicitly say
`NOT_IMPLEMENTED`; Phase 2–3 tabs populate from accepted evidence. `SUCCESS` means the **Phase 1 portfolio calculation** ran, not
that a valuation screen is complete or live investment decisions are ready.

## Import your own data

Phase 1 accepts a **JSON bundle**, not an ambiguous flat holdings CSV. Copy
`src/investment_workspace/fixtures/demo.json` to the ignored `inputs/private/`
directory outside your reviewable source changes. Replace all synthetic data,
set `mode` to `USER_IMPORT`, and supply opening/closing snapshots, the complete
settled ledger between them, current-share prices, and declared sources.

```bash
mkdir -p inputs/private
# Supply a validated bundle at inputs/private/portfolio.json, then:
uv run --locked python -m investment_workspace import-portfolio \
  --file inputs/private/portfolio.json
uv run --locked python -m investment_workspace run daily --offline
```

Read [the data contract](docs/data_dictionary.md) and
[generated input schema](docs/input-schema.json). No broker identifiers or
credentials are accepted. **Accepted input data, evidence, and workbooks are
committed locally**: use only a private repository for real financial records.
The input directory is ignored; it is not a promise that published holdings are
excluded from Git. There are no network calls during import, run, or replay.

Opening costs are total weighted-average acquisition costs in PKR; BUY fees and
taxes increase cost, and SELL fees/taxes reduce proceeds. DIVIDEND is a confirmed
cash receipt, not an entitlement forecast. SPLIT changes quantity at constant
total cost. Realized gains and received income cover the explicit opening-to-
closing window, not lifetime return. Pricing uses imported current-share prices;
historical OHLCV adjustments and cash-in-lieu are not implemented.
`unrealized_return_on_cost` measures current appreciation against acquisition
cost including entry charges; it is not a historical total-return series.

Duplicate transaction IDs with identical facts are ignored; conflicting IDs fail.
Source IDs bind their referenced facts as well as their descriptive metadata;
updated prices or snapshots require a new dated/revision source ID.
An accepted transaction cannot be changed or omitted from an overlapping ledger
window. New, non-overlapping windows retain prior accepted transaction history.
Corrections to financial facts need a separate controlled correction workflow;
this baseline intentionally refuses silent rewrites.

An unreconciled quantity/cost/cash, stale input, missing price, or unverified
source appears as a gap. Missing aggregate market values remain unknown.
Phase 3 sizing remains a research cap under explicit confirmed limits; risk limits are never invented.
Calendar-day freshness limits are operational input policy, not a verified PSX
session calendar. No market session is inferred from today's weekday.

## Notes and workbook overrides

Review/edit a **copy outside the checkout**. Add rows to `Manual_Inputs` with the
existing headers. Supported `field` is `note`; `confirmed` must be `TRUE` or
`YES`. Supply an immutable override ID, known ticker, author, reason, and
effective date. To correct a note, use a new ID and `supersedes`. Financial
fields are rejected. Only the designated sheet is read; changing Holdings or
Valuation in Excel cannot alter canonical values.

```bash
uv run --locked python -m investment_workspace import-overrides \
  --workbook /tmp/Investment_Review.xlsx
uv run --locked python -m investment_workspace export-excel --offline
```

Accepted notes remain in the `Notes` history sheet across exports, including
supersession and expiry dates. Notes are narrative history, never calculation
inputs; expiry does not grant or remove numerical permissions. Imported workbook
bytes are retained as immutable evidence. Formula-like text is exported literally.
Unimported manual cells are not preserved when rebuilding a review copy.

## Validation, replay, and recovery

```bash
uv run --locked python -m investment_workspace validate --run latest
uv run --locked python -m investment_workspace replay \
  --run-id RUN_ID --offline --output /tmp/replayed-workspace.xlsx
uv run --locked python -m investment_workspace recover
```

Replay validates the selected committed output set and rebuilds that snapshot's
workbook; it does not re-fetch evidence, mutate accepted records, or rerun a
historical code version. Numerical workbook parity allows 1e-8 absolute / 1e-12
relative float round-trip error; canonical Decimal strings retain exact values.
XLSX byte identity is not required. Replay refuses to overwrite an existing file.

Every calculation attempt gets a unique run ID. FAILED attempts publish
diagnostics and retain last-good holdings/transactions with their original dates.
Repeated unchanged imports publish `NO_MATERIAL_CHANGE`, retaining analytical
IDs while appending a diagnostic log. Runtime/token/cost telemetry is not invented.

A kernel single-writer lock, staged outputs, content hashes, rollback journal,
and local Git commit define publication. **Committed data is authoritative**;
partially replaced working-tree files are not. Close Excel before running. If
Excel is locked or a commit is interrupted, the CLI exits with an error, retains
the staged candidate, and does not claim publication. Run `recover` after
removing the lock. Pending failures are added to the next successfully published
Run_Log; a locked workbook cannot be updated in place. Concurrent rejected jobs
likewise queue diagnostics without racing the active writer.

The working tree must be clean before publication. Commit or preserve source
edits and never edit the generated workbook directly. Recovery refuses to
overwrite new manual edits or an unexpected HEAD change. See
[publication details](docs/publication.md).

## Remote publication

Every run makes a local commit of only its staged, generated outputs. Auto-push
is disabled. No remote was changed during implementation. When you explicitly
intend to publish the workspace to its private remote:

```bash
uv run --locked python -m investment_workspace push --remote origin --branch main
```

This command performs a normal push and verifies the remote SHA. It never
force-pushes. Failed pushes retain the local revision and an external retry log;
they do not recalculate or repeat ingestion. On divergence, fetch and inspect
the current canonical state before regenerating; do not merge binary workbooks.

## Phase 2 research

[Phase 2 guide](docs/phase2.md) documents the JSON evidence packet, reference
model equations, evidence gates, dividend rules, migration limits and fixtures.

```bash
uv run --locked python -m investment_workspace import-research --file inputs/private/research.json
uv run --locked python -m investment_workspace run valuation --offline --scope required --require-full-coverage
uv run --locked python -m investment_workspace update-dividends
```

For an isolated synthetic demonstration (never overwrite real accepted data):

```bash
mkdir -p /tmp/investment-phase2-demo
uv run --locked python -m investment_workspace --root /tmp/investment-phase2-demo init --offline --phase2
uv run --locked python -m investment_workspace --root /tmp/investment-phase2-demo validate --run latest
```

Earnings_Bridge, Valuation, Entry_Levels, Dividend_Calendar and Top_10 are computed
and checked against canonical records. Bank justified P/B and E&P/industrial
FCFE DCF reference adapters use explicit sourced inputs. Reported, normalized
and forward EPS stay separate. Gross/net horizon returns, MOS and entry ceilings
remain separate. Tax unknowns remain null. Dividend entitlement uses verified
dates/rules and the historical settled ledger; linked receipts are never added
to cash twice. Model revisions require new IDs and explicit supersession.

The Phase 2 fixture deliberately produces PARTIAL: three eligible synthetic
models and one unsupported sector. Real legacy inputs and model equations were
not supplied, so no actual PSX valuation has been migrated or certified.
A complete coverage ledger with blocked names is never a COMPLETE screen.
A strict valuation command exits 1 while coverage is incomplete, after publishing
the coverage and gaps. Screening does not enable sizing or watchlist readiness.

## Phase 3 integrated workflows

[Phase 3 guide](docs/phase3.md) documents raw OHLCV/JSON imports, verified session
and corporate-action gates, relative performance/rank/momentum, trend and mean
reversion, point-in-time backtests, macro/news propagation, risk caps, watchlist
readiness, and proposed IC decisions.

```bash
uv run --locked python -m investment_workspace import-integration --file inputs/private/integration.json
uv run --locked python -m investment_workspace run daily --offline
uv run --locked python -m investment_workspace run ic --offline
uv run --locked python -m investment_workspace analyze APL --offline
```

For an isolated synthetic demo, use `init --offline --phase3` with a new `--root`.
Its source data and limits are illustrative. Events cannot silently rewrite EPS;
screening cannot create READY; a proposed action cannot create a transaction.
The real legacy datastore and production source/runner setup remain missing,
so integrated deployment parity is PARTIAL and schedules stay disabled.

## Remaining implementation

[Migration inventory and blockers](docs/migration.md) lists the missing source
workbooks, original evidence contract, model feeds, holdings, prices, tax/risk
settings and scheduler details. Remaining sectors need validated adapters;
legacy models need exact column maps and reproducible historical outputs.
Phase 3 live-source access, real legacy-datastore migration/parity and production
scheduling remain blocked. Phase 4 wealth planning remains unimplemented.

Tests cover hand-calculated cash/cost/returns, signed earnings bridges, bank/DCF
values, coverage gates, revision history, dividend ex-date/split boundaries,
receipt reconciliation, workbook parity/replay and interrupted publication.
