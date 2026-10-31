# Phase 3 — integrated offline investment workflows

Version 0.3 adds evidence-gated market histories, timing, macro/news, risk,
watchlists and IC proposals to the same publication/replay protocol as Phases
1–2. Sources remain explicit authorized imports. No live endpoint, scheduler,
legacy workbook mapping, actual holding or investment assumption is invented.
Production activation/parity is **not complete**: the original datastore, source
access and runner configuration have not been supplied.

## Commands and inputs

```bash
uv run --locked python -m investment_workspace import-integration --file inputs/private/integration.json
uv run --locked python -m investment_workspace run daily --offline
uv run --locked python -m investment_workspace run timing --offline
uv run --locked python -m investment_workspace run macro --offline
uv run --locked python -m investment_workspace run watchlist --offline
uv run --locked python -m investment_workspace run ic --offline
uv run --locked python -m investment_workspace analyze APL --offline
uv run --locked python -m investment_workspace run event --ticker APL --source-file inputs/private/event.json --offline
uv run --locked python -m investment_workspace inspect-datastore --workbook /path/to/PSX_Mean_Reversion_DataStore.xlsx
uv run --locked python -m investment_workspace schedule-status
```

`integration` is an optional object in the portfolio bundle. A separate packet
has exactly `sources` and `integration` (the complete active snapshot). See
[integration-schema.json](integration-schema.json) and the complete synthetic
`fixtures/phase3-demo.json`. Sources already accepted need not be redeclared.
All IDs/facts are immutable; revise using a new source/record ID, `supersedes`,
and a nondecreasing effective date. Removing accepted records is rejected.
The source registry binds both active facts and historical superseded facts.
Unknown numerical fields remain null. Raw documents can be reviewed separately;
this release does not pretend to parse PDF announcements into verified facts.

The event command imports the same typed packet, then checks all shared
records and dependencies. `--ticker` records the requested focus; full required
coverage is still checked. `analyze` reports that security's owned timing/news,
watchlist and IC outputs. Research and integration imports preserve each other.
Later portfolio imports must carry their accepted research/integration forward.
An invalid packet publishes a FAILED diagnostic and retains last-good analysis.

For a separate synthetic demo:

```bash
uv run --locked python -m investment_workspace --root /tmp/investment-phase3-demo init --offline --phase3
uv run --locked python -m investment_workspace --root /tmp/investment-phase3-demo validate --run latest
```

The fixture uses deliberately synthetic dates, prices and assumptions. Its
loss-making example has an explicit industrial FCFE model; negative reported
EPS is not replaced with a positive earnings multiple. It demonstrates four
verified fixture histories, bank/industrial/E&P valuations, a requested ADD_ON
candidate, conditional IC review, Pakistan/global observations, and null/disabled
outputs where calibration or migration evidence is absent. No fixture becomes
Ahmed's holdings. Its integrated status remains PARTIAL.

## Verified market history and CSV adapter

A completed-session calendar is imported, with source, cutoff and validity;
the engine never guesses sessions from weekdays. Membership snapshots preserve
effective/expiry dates. Current membership selects the latest effective valid
snapshot; equal-date conflicting snapshots block the universe. Every required
name is accounted for. Holdings, candidates and active membership join valuation
coverage; unknown securities retain missing-metadata/model gaps.

Each history declares SECURITY/BENCHMARK, raw OHLCV, observed traded value,
corporate actions and action coverage through the latest completed session.
OHLC ranges, dates, duplicate sessions/IDs, sources, expiry, missing internal
sessions, benchmark alignment and current-price conflicts are checked. No
calendar hole is converted into a zero return or a shorter lookback. A history
may begin later than the calendar; sufficient synchronized observations are still
required for each calculation. The benchmark has a separate declared role and
is excluded from stock percentile ranks.

Supported actions are SPLIT/BONUS with an explicit new/old share ratio.
For each historical bar, prices divide and volume multiplies by all later
verified action ratios through cutoff. Actual traded value remains unchanged.
Only RAW inputs are accepted, preventing a second adjustment of an already
adjusted series. Cash dividends are excluded from timing/correlation/backtests;
these are explicitly **price-return**, not total-return, series. Complex rights,
mergers, stock entitlements and cash-in-lieu need additional validated adapters.

The CSV adapter accepts exactly:

```text
session_date,open,high,low,close,volume,traded_value
```

It supplies bars to one history in an otherwise complete evidence packet:

```bash
uv run --locked python -m investment_workspace import-history \
  --file inputs/private/history.csv --packet inputs/private/integration.json \
  --history-id HISTORY_RECORD_ID
```

Calendar, membership, source IDs, action coverage and policy must already be
explicit in that packet; CSV data alone cannot certify a history. Blank traded
value remains unknown. The engine never substitutes close × volume for observed
turnover. The accepted JSON extraction is retained as immutable evidence.

## Timing, rank, breadth and mean reversion

The imported TimingPolicy supplies all lookbacks, liquidity floor, minimum rank
universe, SMA slope/extension thresholds and reversion thresholds. There are no
assumed profitable parameters or inherited numerical scores.

- Price return over L completed sessions = P(t)/P(t−L) − 1.
- Relative performance = [P(t)/P(t−L)] / [B(t)/B(t−L)] − 1.
- RS momentum = current relative performance minus the same L-session measure
  lagged by the explicit momentum lag. It is not percentile-rank movement.
- Percentile = 100 × [number strictly below + (tie count−1)/2] / (N−1).
  Ties receive midrank; all-equal scores are 50. Below the policy's minimum
  eligible liquid universe size, percentiles are null.
- Stage 2 requires close > long SMA, short SMA > long SMA, positive relative
  performance and long-SMA slope above the explicit flat threshold. Stage 4 is
  the inverse. Flat slope yields Stage 1 below/equal long SMA or Stage 3 above;
  other cases are TRANSITION. This is **DAILY_SMA_PROXY_V1**, not a claimed
  reproduction of an unrecovered weekly Weinstein model.
- Extension = close / short SMA − 1. Breakout compares close with the highest
  high of the prior window, excluding the current session.
- Reversion z = (latest close − rolling mean) / population standard deviation.
  Zero variance produces null. Provisional calibration retains descriptive z
  but gives UNCALIBRATED rather than a trade signal. Only explicit validated
  calibration permits OVERSOLD/OVERBOUGHT/NEUTRAL classification.

Sector rotation uses equal-weight eligible-name relative performance, Stage-2
price breadth and positive-RS breadth; both the denominator and missing coverage
are shown. It does not imply a market-cap-weighted sector index or infer sector
fundamentals from a price chart.

The MR backtest is a transparent reference long-only simulation: threshold
signal at session close, entry at **next** session open, mean-cross/removed-member
exit at the next open, and explicit costs at entry and exit. Parameters and
membership evidence must be available at the historical decision date;
point-in-time membership must cover all test sessions. Missing membership,
fees, start date or validated calibration blocks the test. Open positions and
pending next-session orders are reported separately, without a fabricated final
fill. Trades and summaries occupy separate workbook tables. Backtests exclude
cash dividends, taxes, slippage, liquidity/market impact and efficacy claims;
production strategy calibration remains a separate dependency.

## Macro, events and owned revisions

Macro observations explicitly separate FACT, INTERPRETATION and SCENARIO, with
domain, units, date, expiry, value (possibly null), narrative and optional imported
regime. Hypothetical bear/base/bull paths are separate; fully supplied probability
sets must sum to one. The software does not manufacture current SBP/IMF/global
stress data or derive a regime from an absent methodology.

Events retain affected tickers, urgency, transmission and optional EPS delta.
A numerical EPS impact needs its period and calculation rationale; qualitative
news has null EPS. An event never adds its delta to owned normalized/forward EPS.
If `requires_model_revision` is true, the affected model is withheld from
Valuation/Top_10 and coverage becomes BLOCKED_EVIDENCE until a new owned model
revision explicitly includes its `covered_event_ids` and a suitable date.
Risk scenarios, sizing, watchlist and IC consume that blocked coverage. Stale or
unverified events cannot satisfy acknowledgement/readiness. Unaffected model and
timing records retain their original lineage. Event_Propagation records the
owners, event revision and acknowledgement rather than claiming an automatic
forecast rewrite.

Pakistan numerical alerts remain disabled until a dated, source-confirmed
methodology with explicit replacement approval is imported. Manual evaluation
then uses **strictly greater than 8.0**, not greater-or-equal. No background alert
or production score methodology is created by this release.

## Risk, watchlist and IC controls

RiskLimits require explicit position, sector and factor maximums; minimum cash;
per-trade risk budget; liquidity participation; correlation lookback/sample;
source dates and `user_confirmed`. No personal limits are defaulted. Conflicting
position limits across the portfolio policy and risk owner block sizing.
Economic factor tags are explicit; overlapping tags are overlapping exposures,
not independent diversification. Concentration uses total-sleeve weights and
retains the earlier equity HHI/effective-position figures separately.

Risk scenarios reuse owned horizon exit prices and horizon dividends (not fair
value as a future exit). All holdings need compatible-horizon scenario coverage;
missing values keep scenario totals unknown and block sizing/readiness. Price,
income and total returns stay separate. Pending/received dividend cash is never
added a second time. Correlation uses synchronized adjusted price returns,
explicit observation counts/lookback and null for insufficient/zero-variance
histories. No correlation is manufactured for missing sessions.

An additional-share research cap is the floored minimum of:

1. Position/explicit target, sector, factor and minimum-cash headroom divided by
   current verified price.
2. Total assets × per-trade risk budget / (price − explicit stop).
3. Observed average traded value × participation limit / price.

Stale/unreconciled holdings, current-price conflicts, missing factors/scenarios,
breached/unconfirmed limits, unverified candidate inputs, absent target weight,
invalid stop or missing liquid history block the cap. Caps exclude transaction
costs/taxes and are **proposals**, never executable quantities. Synthetic caps
are ILLUSTRATIVE_ONLY and never enable real sizing. No accepted position changes.

Watchlist retains author, thesis, invalidation, portfolio-fit rationale, entry,
stop, target, catalysts, review date and requested stage in immutable history.
Held names derive ADD_ON; other names derive NEW_POSITION. READY is possible only
when explicitly requested and evidence, valuation, risk/fit, upcoming catalyst
and nonextended Stage-2 timing gates all pass. Screening never promotes RESEARCH
to READY. Explicit model BLOCKED gates are honored; calculated owning timing/risk
results are shown separately on Entry_Levels. Monitoring state is independent:
TRIGGERED / APPROACHING / WATCHING / STALE. ON_HOLD/REJECTED/ARCHIVED remain user
lifecycle choices.

IC records separate requested action from the resulting gated action and keep
confidence, reason, invalidation, opportunity cost and dependencies. ADD and
ACCUMULATE require READY **and** the explicit price trigger. Missing/blocked
requirements produce REVIEW. Superseded candidate references keep their original
historical decision links and require review. Outputs are PROPOSED and
NOT_EXECUTED; no approved decision or transaction is inferred.

## Publication, parity and remaining deployment dependencies

Canonical `integration.json`, portfolio/research records, timing/IC feeds,
coverage, refresh queue, changes, manifests and the main workbook publish as one
checksummed local revision. New tabs include RS_Trend, Sector_Rotation,
Mean_Reversion, Backtests/Backtest_Trades, Macro/Scenarios, News_Impact,
Portfolio_Risk/Correlations, Watchlist/Catalysts, IC_Actions, Event_Propagation,
Refresh_Queue and Alerts. Excel numerical parity covers these tables. No-change
runs append diagnostics but reuse analytical IDs/dates. Offline replay performs
no retrieval. Interrupted publication uses the existing lock/journal/recovery.
Source updates trigger dependent gate checks; local reference arithmetic is
recalculated deterministically, while unchanged records are reused. Network
incremental fetching is not implemented or claimed.

`inspect-datastore` produces a read-only hash, sheet/header/formula inventory.
The real `PSX_Mean_Reversion_DataStore.xlsx` has not been supplied, so legacy row,
formula and historical parity remains NOT_MIGRATED in Data_Gaps. No independently
editable numerical store or counterfeit compatibility workbook is created.
A future real migration must map that inventory against the canonical timing
records, verify row/totals/history and preserve the original immutable evidence.
Integrated status remains PARTIAL while that deployment gate is unresolved.

`config/schedules.json` is a **disabled plan**, readable with `schedule-status`.
It declares Asia/Karachi, the PRD's weekly times and null/unrecovered times for
other jobs. ATRL/BFAGRO, Western rates and production score monitoring are disabled.
No daemon, cron job, remote push or legacy-job cancellation is performed. Activate
only after supported live-source access, a persistent runner, delayed/completed
session handling, real-data manual parity and legacy-job inventory are available.
