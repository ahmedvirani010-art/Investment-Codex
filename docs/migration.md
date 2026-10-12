# Migration inventory — Phase 1

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
| Legacy mean-reversion workbook | Not found; not fabricated | `PSX_Mean_Reversion_DataStore.xlsx` and its source histories |
| Evidence contract | Baseline implementation contract documented | The three source documents named in PRD section 2 |
| Valuation/earnings | BLOCKED_MODEL for every demo ticker | Recovered model equations, cutoffs, facts, normalization bridges, assumptions; reconcile POL/BAHL/OGDC/INDU/AKBL exceptions |
| Dividends | Confirmed synthetic cash receipt arithmetic only | Verified entitlement dates, settlement rules, tax profile, receipts and holdings history |
| Prices/calendar | User-provided current-share prices, calendar-day age gates | Authorized data exports/adapters, PSX sessions/holidays and corporate-action histories |
| Risk/IC/watchlist | Sizing blocked; later-phase sheets are explicit placeholders | Confirmed portfolio limits, liquidity inputs, source-backed models and user theses |
| Automation | Offline CI tests only; no production jobs | Persistent scheduler, source access, timing methodology and verified calendars |
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
Later-phase acceptance gates remain unrun, not passed.
