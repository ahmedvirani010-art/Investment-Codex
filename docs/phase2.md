# Phase 2: offline earnings, valuation and dividends

This release implements the Phase 2 calculation and publication infrastructure.
It does **not** recover absent legacy workbooks or certify Ahmed's investments.
No network retrieval, AI service, schedules or trade execution is introduced.
All supplied examples are synthetic. Inherited equations remain provisional until
recovered inputs reproduce the historical output and evidence is verified.

## Import and run

An accepted portfolio is required. A portfolio bundle now accepts an optional
`research` object; existing Phase 1 bundles remain valid. Alternatively import a
packet containing exactly `sources` (new source declarations) and `research`
(the entire active research snapshot). See `docs/research-schema.json` and
`src/investment_workspace/fixtures/research-demo.json` for the contract/example.
New securities must first be declared in the portfolio bundle. Required names
without sector/financial inputs still receive blocked coverage.

```bash
uv run --locked python -m investment_workspace import-research --file inputs/private/research.json
uv run --locked python -m investment_workspace run valuation --offline --scope required --require-full-coverage
uv run --locked python -m investment_workspace update-dividends
uv run --locked python -m investment_workspace validate --run latest
```

`--require-full-coverage` returns exit code 1 unless the accepted research screen
is COMPLETE; diagnostics and partial coverage are still published. A FAILED
attempt never passes this flag, even when the preceding screen was complete.
Commands read committed snapshots and use the existing writer lock, checksummed
staging, local commit, recovery and replay protocol. No automatic remote push.

For a separate synthetic demo, start in an empty Git repository and import
`fixtures/phase2-demo.json` using `import-portfolio --file ABSOLUTE_PATH`. Do not
replace a real portfolio with fixture data. The fixture produces PARTIAL:
three eligible names and one deliberately unsupported sector, never a fake Top 10.
`research-demo.json` contains only the corresponding research packet; its prices
and financial evidence are valid only in that synthetic bundle.

## Earnings and models

Earnings ownership stays in the earnings module. Reported PAT must reconcile to
reported EPS using the declared weighted-average share count (absolute EPS
rounding tolerance 0.000001). Normalized PAT = reported PAT + signed pretax
adjustments + signed tax effects. Normalized EPS divides this result by the same
share count. Adjustments require a genuine-one-off recurring test, reason,
source and locator. Recurring inventory/treasury economics cannot be classified
as adjustments by this interface. Quality grades are imported assessments with
rationale, not invented scores. Forecast EPS/DPS is a separate sourced model
input with FY/CY/NTM period, accounting basis and dated share basis. No EPS is
silently annualized or adjusted for a different share count.

Implemented reference adapters (not recovered proprietary equations):

- **Bank / BANK_JUSTIFIED_PB**: BVPS × (sustainable ROE − g) / (ke − g).
  Requires treasury, credit-cost, OCI, capital and dividend-capacity driver evidence.
- **E&P / FCFE_DCF**: discounted annual equity cash flows plus an explicitly
  supplied terminal equity value, divided by shares. Requires reserves,
  production, realized prices, collections, depletion, capex, tax and payout
  driver evidence and a separate payout cross-check.
- **Industrial / FCFE_DCF**: the same FCFE arithmetic with operating drivers,
  midcycle margins, capex, working capital and net-debt evidence.

DCF terminal value is an explicit equity value at the end of the final modeled
year. The engine does not assume a perpetual resource life or manufacture a
terminal growth equation. FCFE must already include financing, taxes, capex and
working capital. No separate cash, investment-income or net-debt add-back exists;
those must be reconciled inside the supplied equity cash flows/terminal value.
Both adapters reject g ≥ ke and nonpositive equity value. Other sectors/methods
stay BLOCKED_MODEL; a loss alone is not grounds to discard a valid cash-flow model.

Every model needs bear/base/bull, distinct scenario IDs, source IDs, version,
explicit methodology and rate rationale, expiry, benchmark date, ERP, MOS,
positive horizon and event coverage through the cutoff. Prices must be current
under the portfolio freshness policy. A model and its owned earnings must share
accounting/share bases. VALIDATED is the importer's explicit certification; source
labels and dates are declarations, not an independent filing audit. PROVISIONAL
models cannot enter ranked outputs. Legacy models additionally require a column
map and all three historical fair values reproduced within the declared tolerance.
The tests validate the reference arithmetic, not the economics of a real company.

POL DPS, BAHL EPS, OGDC entitlement, INDU cash-income and AKBL treasury/OCI are
explicit unresolved migration gates for matching tickers. Each needs a dated,
sourced resolution with rationale. A resolution cannot silently revise an old
model; model changes need their own supersession.

## Coverage and returns

Required coverage is the union of imported dated required membership and all
portfolio securities. The importer must include the constituent snapshot,
watchlist and requested names and declare its basis; the software cannot verify
an absent exchange feed. COMPLETE requires verified full membership within its explicit
`universe_date` / `universe_valid_until` window, plus all
non-excluded models passing. Held names cannot be excluded. Every ticker gets a
coverage outcome; missing evidence and unsupported models appear in Data_Gaps.
Coverage is checked on every valuation run; unchanged analytical rows retain
their dates and lineage. This release recalculates local reference equations;
it does not implement selective network retrieval or certify event absence.

Present fair value is separate from the imported horizon exit price. Gross
return = (exit price + horizon dividends − entry price) / entry price. Exit
prices must explicitly use an EX_DISTRIBUTION basis. Horizon distributions have
their own rationale and are never augmented with the dividend-calendar pending
receivables or cash receipts. Sustainable DPS is separate again. MOS = 1 −
price / present fair value. Annualization uses the declared positive horizon.
Net return stays unknown until every tax, transaction-cost and separate liability
input is supplied; taxes apply to positive price gains and to horizon dividends.
This is an explicit scenario convention, not a jurisdictional tax opinion.

Entry ceiling is the minimum of FV × (1 − required MOS) and
(exit price + dividends) / (1 + sovereign benchmark + ERP)^horizon. This is a
**gross research ceiling**. Timing/risk gates default UNKNOWN and block readiness.
Even passed gates produce REVIEW, never a watchlist READY or executable size.
Ranking uses base-case gross horizon return among eligible models only, breaks
ties by ticker and shows at most ten, with no padding. Sizing remains blocked.

## Dividends

Cash dividends carry announcement/type/DPS, ex/record/book-closure/payment dates,
verification, an explicit settlement rule, optional tax and receipt transaction IDs.
The supported imported rule is SETTLED_BEFORE_EX. This is not an assumed PSX rule:
it must be verified by the source. Future/unsupported rules remain pending.
Entitlement requires a reconciled, source-confirmed ledger spanning the ex date.
Opening is strictly before ex date; settled trades/splits before that date adjust
quantity, whereas ex-date buys cannot inherit the dividend. If the window does
not cover ex date, dates/rule are unverified, or evidence expired, quantity and
entitlement stay null with PENDING_CONFIRMATION. Current holdings alone do not
establish historical entitlement. Stock dividends/complex entitlements remain
unsupported; an unrepresentable split/DPS basis needs a controlled import.

Outputs distinguish NOT_ENTITLED, ENTITLED, RECEIVABLE, OVERDUE, RECEIVED,
RECEIPT_EXCEPTION and PENDING_CONFIRMATION. Tax unknown leaves net entitlement
unknown. Receipt IDs must be accepted cash-dividend transactions for the same
security and cannot be linked twice. Gross/tax discrepancies remain exceptions.
Cash receipts already affect portfolio cash and are never added again.

## History and review

Record IDs and source facts are immutable. A revision has a new record/source ID,
explicit `supersedes` to the active same-owner/ticker record, and a nondecreasing
effective date. Omitted accepted records fail; superseded records cannot be
reactivated. Prior model inputs, original provenance and decision revisions are
retained in `research.history` and committed run snapshots. Whole-packet errors
publish diagnostics while retaining the last-good research and original dates.
When importing a later portfolio bundle, carry its accepted research forward;
an omitted research object is rejected rather than silently erasing research.

`data/canonical/research.json` and the portfolio snapshot are published together
with Earnings_Bridge, Valuation, Entry_Levels, Dividend_Calendar and Top_10 tabs.
Python writes all numerical cells; workbook validation checks their parity.
Unsupported later-phase tabs remain explicit placeholders. Replay of older
snapshots tolerates absent Phase 2 fields and reproduces the saved values, not
an execution of a historical Python binary.
