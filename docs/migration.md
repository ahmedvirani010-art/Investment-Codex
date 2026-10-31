# Migration inventory — Phases 1–4

Inspected the selected checkout and accessible workspace input/shared folders.
The repository was unborn/empty. Only `Investment_Workspace_PRD.md` was supplied;
its exact content is retained at `docs/PRD.md`. No original workbook, portfolio
export, valuation feed, price history, or inherited source contract was found.
The Git remote read operation succeeded and reported no remote branches.

| Component | Current result | Needed for live migration |
| --- | --- | --- |
| Python/CLI | Implemented and locked; deterministic offline imports | No secrets needed for Phase 1 |
| Holdings/cash/transactions | Synthetic fixtures only; settled weighted-average reconciliation | Dated opening/closing balances and complete settled ledger from designated authoritative source |
| Main workbook | Generated review workbook with synthetic labels | Actual source workbook and real tab/formula/lineage inventory |
| Legacy mean-reversion workbook | Not found; read-only inventory tool implemented; no parity certification or fake compatibility artifact | `PSX_Mean_Reversion_DataStore.xlsx` and its source histories |
| Evidence contract | Baseline implementation contract documented | The three source documents named in PRD section 2 |
| Valuation/earnings | Offline bridges, explicit bank/E&P/industrial reference adapters, coverage and legacy conflict gates implemented; no real inherited models recovered | Recovered model equations, cutoffs, facts, normalization bridges, assumptions; reconcile POL/BAHL/OGDC/INDU/AKBL exceptions |
| Dividends | Offline verified-date/settled-ledger entitlement, tax unknowns and receipt reconciliation implemented | Verified entitlement dates, settlement rules, tax profile, receipts and holdings history |
| Prices/calendar | Local strict JSON/CSV raw OHLCV, completed-session calendar, action adjustment, RS/trend/MR and correlation/backtest reference calculations implemented | Authorized data exports/adapters, PSX sessions/holidays and corporate-action histories |
| Risk/IC/watchlist | Explicit limits/factors, scenario/risk caps, gated lifecycle and PROPOSED IC actions implemented; no execution | Confirmed portfolio limits, liquidity inputs, source-backed models and user theses |
| Automation | Manual integrated runs and disabled Asia/Karachi schedule plan; no production jobs | Persistent scheduler, source access, timing methodology and verified calendars |
| Git | Local durable revisions; explicit push command only | Confirm private destination and authorize each push or an auto-push policy separately |
| AI | No provider calls or SDK; usage null | Optional provider, permitted model IDs, secure credentials and budget |

Phase 2 cannot honestly migrate or reproduce inherited valuations without the
actual model inputs and evidence contract. This baseline does not certify a
complete valuation screen. Supplied fixture names are **not** real PSX tickers,
and fixture quantities/amounts are **not** Ahmed's holdings.

The Phase 1 gates AC01/02/05/10/11/12/13/15 are exercised by the automated suite
within the implemented offline scope. AC12 covers simulated workbook lock,
interrupted commit, concurrent writers, and failed remote push; these are local
protocol tests, not a Windows Excel integration or a deployed scheduler.
AC13 reproduces chosen committed dataset cells/records, not byte-identical ZIPs
or execution of historical Python binaries. AC15 supports narrative notes;
numerical overrides remain deliberately unsupported until field owners exist.
Phase 2 AC03/04/06/07/08 are now exercised within the synthetic/offline scope;
this is not a live-model migration acceptance. Tests include explicit model and
universe gates, signed earnings bridges, unsupported sectors, ex-date and split
boundaries, duplicate cash links, and legacy conflict/reproduction gates. The
separate Phase 2 fixture produces three eligible synthetic models and one
BLOCKED_MODEL. The original accepted Phase 1 demo remains unchanged unless a
research packet is explicitly imported. See [Phase 2 details](phase2.md).
Phase 3 AC09/14/16 are exercised within the synthetic/offline scope: no READY
from screening alone, owned-input reuse/event invalidation, offline replay,
verified split-adjusted returns/rank/correlation and next-session backtests with
point-in-time membership and explicit fees. This does not establish real legacy
row/formula/history parity or authorize deployment. Source endpoints, the real
compatibility workbook, approved production calibration and a persistent runner
remain unavailable. See [Phase 3 details](phase3.md). No duplicate legacy jobs
have been disabled. Phase 4 now has hand-calculated synthetic acceptance tests; this is not a real retirement plan. See [completion status](implementation-status.md) and [source recovery](recovery_inventory.md).
