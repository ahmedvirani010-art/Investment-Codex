# Phase 1 data contract

The strict Pydantic contract is in `src/investment_workspace/schemas.py`; the
JSON Schema export is `docs/input-schema.json`. Unknown fields are errors.
Money and quantities are finite Decimal strings, serialized losslessly in JSON.
Only PKR is supported. Timestamps require offsets; effective/session dates are
ISO dates. Missing prices use JSON null, while zero/negative prices are errors.

| Entity | Contract |
| --- | --- |
| Source | Stable unique ID, title, publisher, effective date, evidence label, locator. Imported bytes are SHA-256 content-addressed. Revisions need a new ID. A source label is user-declared; validation does not independently verify a broker or exchange. |
| Security | Unique synthetic or user-provided ticker, sector, PKR currency. No exchange universe membership is inferred. |
| Opening / closing | Offset-aware timestamp, source ID, settled cash, positions with quantity and **total** cost. One row per ticker; zero quantity requires zero cost. |
| Transaction | Stable ID, timestamp, settlement date, kind, source ID; BUY/SELL require quantity and price, cash kinds require amount, SPLIT requires ratio. No unsettled trades or fees silently omitted. |
| Price | Ticker, declared completed-session date, optional close, source ID, `CURRENT_SHARES` basis. Phase 1 cannot verify exchange holidays or adjust historical series. |
| Policy | Calendar-day age limits and Decimal cash/cost/quantity tolerances. Optional max-position limit defaults null. These do not activate sizing. |
| Note override | Immutable ID, ticker, `field=note`, value, author, reason, dates, explicit confirmation, optional supersedes. Narrative history only. |

The ledger window is `(opening.timestamp, closing.timestamp]`; transactions must
also have settled by closing. Deposits and withdrawals reconcile cash but do not
count as investment returns. Realized gain = net sale proceeds minus allocated
weighted-average cost. Confirmed dividend receipts are shown separately as
net cash income; no pending entitlement is inferred. Cash cannot go negative.
Splits retain cost and apply quantity ratios; only the post-action closing price
is supplied. No historical returns, dividend forecasts, tax-law calculations,
FIFO election, short positions, FX conversion, or leverage are implemented.

Canonical portfolio JSON contains structured holdings, accepted ledger history,
reconciliation exceptions, summary, evidence registry, policy assumptions,
coverage, gaps, notes, logs, and usage. Material records carry owning module,
schema version, record/run IDs, effective/cutoff dates, units, code version,
input content hash, sources, assumptions, confidence, and validation status.
`SYNTHETIC` confidence prevents fixture values being presented as sourced facts.
Validation status means schema/arithmetic validation, not independent evidence
verification. Policy IDs resolve to the Assumptions sheet and canonical array.
Each run manifest records the source-code SHA-256 and input policy SHA-256.
The installed Python/dependency versions and dependency-lock hash are also
recorded. Total wall time is recorded after commitment in external publication
logs; workbook usage stores calculation time separately and leaves total time
unknown until that external observation. AI token/cost values remain null.

Holdings are displayed from the declared closing snapshot. Calculated ledger
quantity/cost and cash remain visible beside mismatches. Missing prices prevent
total asset/weight calculation; stale prices may remain displayed with their
original date, a gap, and blocked sizing. Weights are equity and total-sleeve
fractions, not percentages stored as whole numbers. HHI uses equity weights;
effective positions = 1 / HHI. Empty or unpriced denominators yield null.

For no-change runs, financial records and their original run IDs/dates remain
unchanged. For failed imports, last-good holdings/ledger remain; current attempt
errors and blocked readiness are appended. Each accepted transaction ID has one
canonical row across repeated or successive imports. Changing an accepted
transaction is rejected; a controlled supersession ledger is future work.

Evidence blobs and historical run snapshots are append-only through the CLI.
Git is the history mechanism; direct manual changes require explicit review.
The inherited PSX evidence contract was unavailable. This document defines the
implemented baseline and does **not** claim to replace or reproduce that source.

## Phase 2 research contract

Portfolio bundles accept optional `research` under the strict
[research schema](research-schema.json). The [Phase 2 guide](phase2.md) specifies
earnings normalization, explicit sector reference equations, forecast/scenario
bases, signed returns, coverage/universe expiry, immutable supersessions and
verified dividend entitlement. Unknown tax, entitlement and net-return fields
remain null. Sources, record IDs and history are published with the portfolio
and workbook as one revision. See the synthetic `phase2-demo.json` fixture for
an end-to-end example; it is never a source of real holdings or PSX valuations.

## Phase 3 integration contract

The optional `integration` object follows [integration-schema.json](integration-schema.json).
It contains sourced, dated, immutable session/membership/history records; explicit
indicator/calibration/risk policies; macro facts/scenarios/events; economic factors;
catalysts; user-authored candidates; and proposed IC actions. See the exact
[Phase 3 equations, gates and limitations](phase3.md). Decimal values serialize
as strings, unknowns stay null, histories retain superseded payloads and provenance,
and all canonical outputs/workbook tables publish together.

## Completion release extensions

Optional dataset identity, financial facts, migration records, original-document
catalogue and wealth records extend the input contract. Absent additive defaults
are normalized for old evidence-ID comparisons; old snapshots are never rewritten.
See [completion interfaces](completion.md), [wealth schemas](wealth-schema.json),
and [implemented evidence rules](evidence_contract.md). Evaluation date is a run
context separate from observation cutoff. Monetary input precision remains explicit;
model/projection output Decimal strings retain intermediate precision.
