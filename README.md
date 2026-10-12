# Investment Workspace

A private, Git-backed investment research workspace. **Version 0.1 implements
Phase 1 only**, with synthetic offline fixtures. It does not contain Ahmed's
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
run/change logs, and unknown usage telemetry. Later-phase tabs explicitly say
`NOT_IMPLEMENTED`. `SUCCESS` means the **Phase 1 portfolio calculation** ran, not
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
Sizing remains blocked throughout Phase 1; risk limits are never invented.
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

## Remaining implementation

[Migration inventory and blockers](docs/migration.md) lists missing source
workbooks, evidence contracts, model inputs, holdings, feeds, tax/risk settings,
and scheduler details. The supplied [PRD](docs/PRD.md) describes later phases;
these are not implemented by placeholder worksheets. No valid model inputs were
available to migrate Phase 2, so every demo valuation is `BLOCKED_MODEL`; no
fair values, entry levels, Top 10 rankings, or COMPLETE screen are fabricated.

Tests cover hand-calculated cash/cost/returns, splits, duplicate/conflicting
imports, stale/missing data, lineage, failed runs, note import, reproducibility,
concurrent writers, workbook/commit failures, and push failures. CI runs the
same locked offline suite.
