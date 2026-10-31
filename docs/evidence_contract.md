# Implemented evidence and ownership contract

This document specifies the application's implemented rules. It is not a recovered
copy of `PSX_Research_Evidence_and_Assumption_Contract.md` and does not replace an
unavailable original. See `docs/recovery_inventory.md` for the recovery result.

## Evidence

Sources declare stable IDs, publisher/title, effective date, evidence label and
locator. Optional URL, publication/access timestamps with timezone, ownership,
observed coverage-through date and original-document SHA-256 support production
provenance. Observed coverage cannot extend beyond the imported observation cutoff.
A CONFIRMED label is an explicit importer assertion, not an automated source audit.
Forecast assumptions are not converted into observed facts by a source label.

Original files enter only through controlled packages with a declared hash and
`store_permitted: true`. Use redacted exports without credentials or broker account
identifiers. Content-addressed originals and canonical input facts are committed
with outputs; local input directories being ignored does not hide accepted records.
The importer never follows source URLs, executes spreadsheet formulas or parses a
PDF into accepted financial facts. Unknown values remain null.

Source IDs bind referenced facts, not just descriptions. A source declared without
facts may be bound on first use; after binding, revised facts need a new source ID.
Research, financial and wealth record IDs are immutable. Revisions require a new
ID, explicit same-owner supersession, evidence and a nondecreasing effective date.
Accepted records cannot disappear from overlapping history. Dataset activation is
a separately confirmed lineage boundary, never transaction-ID reassignment.

## Ownership

- Portfolio owns accepted holdings, cash and transactions; discrepancies block sizing.
- Financial facts and earnings own reported/normalized bridges. Model forecasts
  reference those facts without rewriting them.
- Valuation owns assumptions, numerical forecasts, model versions and fair values.
- Price history owns corporate-action adjustment, timing, relative performance,
  percentile rank and mean reversion.
- Macro/news owns observations, hypothetical paths and proposed EPS transmission.
  Events may invalidate a model; they cannot change its EPS directly.
- Risk owns confirmed limits and proposed caps. Watchlist owns user-authored thesis,
  lifecycle and entry discipline. IC proposals never become executed transactions.
- Wealth owns external assets, benefits and retirement assumptions. Existing portfolio
  balances are linked once, never copied and added again.

## Dates and readiness

Imported observation cutoff, completed price session, financial period, assumption
validity and evaluation date remain distinct. `run --as-of` advances assessment,
not source dates. It cannot precede the imported cutoff. Replay uses the original
committed records and context without retrieval. Evaluation can block an unchanged
old export even when its arithmetic has not changed.

Calculation coverage, signal/readiness gates, historical compatibility and deployment
are separate dimensions. COMPLETE for a retirement calculation is not a declaration
that the PSX screen or production deployment is complete. Replacement models require
source-backed version-matched methodology approval, current evidence and arithmetic
validation before ranking. Provisional calibration is not a profitable trading signal.

Original PRD contracts, prompts and rerun evidence are catalogued by role. Production
activation also needs confirmed real data, complete provenance, validated methodology,
legacy historical parity, private-repository confirmation and explicit publication
policy. No generated document or fixture silently satisfies those conditions.
