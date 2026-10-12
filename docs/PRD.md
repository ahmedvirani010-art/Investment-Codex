# Ahmed's Investment Workspace — Codex Implementation PRD

Version 1.0 | 12 October 2026 | Status: implementation specification, not deployed software

## 1. Product objective

Build a private Git-backed investment research workspace operated through Codex and Python. Consolidate PSX research, portfolio monitoring, valuation, earnings, macro scenarios, relative strength, mean reversion, watchlists, dividends and Investment Committee reviews into one reproducible system. Keep the investment Excel workbook inside the repository and update it after every run. Preserve historical decisions, evidence, assumptions and calculation lineage.

Ahmed should be able to request “run the value screen”, “review my portfolio”, “analyze APL”, “update dividends”, or “what changed?” and receive calculated, evidence-linked outputs using shared state rather than repeatedly reconstructing the workspace from chat history.

Success means reliable research and reviewable portfolio decisions. Trade execution is outside scope.

## 2. Basis and scope

Read source documents for this specification:

- PSX_Research_Evidence_and_Assumption_Contract.md, effective 28 August 2026.
- PSX_Integrated_Research_Workflow_Replacement_Prompts.md, 28 August 2026.
- PSX_Valuation_Rerun_and_Token_Comparison_2026-10-10.md.

Additional requirements come from the visible investment-workspace history: full valuation coverage, normalized earnings for every covered stock, pending dividends, explicit entry levels, sector analysis, macro and global stress monitoring, retirement scenarios, optional gold/crypto diversification, and measured research costs.

These sources establish workflow requirements, not today's positions or validated model inputs. The latest holdings, source workbook, feeds and schedules must be inventoried during migration. The PRD does not claim those have already been migrated or reconciled.

### Included modules

| Module | Required capability | Delivery |
|---|---|---|
| Portfolio | Holdings, transactions, cash, cost, realized/unrealized returns, reconciliation | Phase 1 |
| Evidence and assumptions | Source registry, freshness, conflicts, lineage, common scenarios | Phase 1 |
| Earnings | Reported/normalized/forward bridge, quality assessment, event revisions | Phase 2 |
| Valuation | Complete coverage register, sector models, bear/base/bull, entry levels | Phase 2 |
| Dividends | Announcement, entitlement, receivable, payment, tax, sustainable forecasts | Phase 2 |
| Macro/news | Pakistan regime, global stress, EPS transmission, affected tickers | Phase 3 |
| RS/trend/mean reversion | Verified histories, corporate actions, ranks, breadth, timing | Phase 3 |
| Portfolio risk/IC | Concentration, scenario losses, liquidity, actions, sizing constraints | Phase 3 |
| Watchlist | Candidate lifecycle, triggers, gates, add-on distinction | Phase 3 |
| Cross-asset/retirement | Cash, gold, VPS/PF, optional crypto; retirement simulations | Phase 4 |
| Automation/usage | Scheduled jobs, durable commits, run logs, token/cost observations | All phases |

## 3. Core design decisions

1. **Git is the durable workspace.** Code, configuration, structured research records, reports, run manifests and Excel are versioned together in a private repository.
2. **Excel is the main review interface.** `workbooks/Investment_Workspace.xlsx` is generated from validated structured records. CSV/JSON/YAML records provide readable diffs and rebuildability. Excel and data must represent the same published revision.
3. **One owner per analytical field.** Holdings, normalized earnings, forward forecasts, timing, risk and watchlist readiness have explicit owners.
4. **Python calculates; AI interprets evidence.** AI may propose extraction, normalization and assumptions. Python validates schema, performs arithmetic and reproduces models. Unsupported facts remain null or unverified.
5. **Incremental runs by default.** Fetch only missing, stale, conflicting or post-cutoff inputs; revalue affected names. Every weekly run still checks every required valuation record.
6. **A failed run remains visible.** Update the workbook's Run_Log and Data_Gaps after every attempt; retain last-good analytical values with their original dates. Never relabel failed refreshes as fresh.
7. **No silent trading or position changes.** Research actions are recommendations. Transactions enter through confirmed imports or explicit user records.

## 4. Ownership and reconciliation

| Domain | Authoritative input/owner | Rule |
|---|---|---|
| Holdings and cash | Latest verified Portfolio360 snapshot where accessible | Import/reconcile; do not assume connector availability in standalone Codex |
| Alternative position source | Dated broker export or user-confirmed ledger | Use only as explicitly designated fallback; record source change |
| Reported and normalized earnings | Earnings module backed by filings | Downstream consumers import without independently changing the bridge |
| Forward EPS/DPS, fair value, assumptions | Valuation module | Common scenario IDs; revisions require reason and evidence |
| Macro observations/regime | Macro module | Separate observed values from scenario paths |
| RS/trend/timing | Price-history module | No numerical score without verified history |
| Thesis, risk, portfolio constraints | IC/risk module | Preserve user notes and invalidation rules |
| Candidate lifecycle and entry gates | Watchlist module | Screening never automatically creates READY |

If a snapshot and transaction ledger disagree, generate a reconciliation exception with quantity, cost, cash and timestamp differences. Block executable sizing until reconciled. Historical chat trades are migration leads, not current holdings. Specifically reconcile GCIL additions, ATRL exit, ICL reductions, MCBIM sale and PNSC sale; do not infer remaining quantities from incomplete history.

## 5. Repository layout

```text
investment-workspace/
  AGENTS.md
  README.md
  pyproject.toml
  dependency-lock-file
  .env.example
  .gitignore
  docs/PRD.md
  docs/evidence_contract.md
  docs/data_dictionary.md
  config/{workspace,universe,valuation,thresholds,schedules,sources}.yaml
  inputs/{holdings,transactions,manual_overrides}/
  data/canonical/{securities,prices,financials,normalizations,forecasts}/
  data/canonical/{assumptions,valuations,dividends,macro,watchlist,risk}/
  data/evidence/{sources,conflicts,coverage}/
  data/history/
  feeds/latest/
  reports/latest/
  reports/archive/
  runs/<run_id>/{manifest,coverage,validation,changes,usage}.json
  workbooks/Investment_Workspace.xlsx
  workbooks/PSX_Mean_Reversion_DataStore.xlsx
  src/investment_workspace/
    cli.py
    pipeline.py
    storage.py
    schemas.py
    sources/
    modules/
    models/
    excel/
    validation/
  tests/{unit,integration,fixtures}/
  scripts/
  .github/workflows/
```

The layout is a specification, not files created by this PRD. Choose supported Python dependencies at implementation time and lock versions. Suggested categories: dataframe processing, schema validation, Excel writing, HTTP retrieval, YAML, CLI and testing. Do not require an LLM SDK for offline calculations.

Keep credentials, broker account identifiers, caches, temporary workbooks and bulk raw downloads out of Git. Retain source URLs, hashes, extracted evidence and licensed-to-store source documents. Large historical market data can use partitioned files and, if necessary, Git LFS after confirming all runners support it. Keep ordinary XLSX tracking for the initial small workspace; never merge binary workbooks manually.

## 6. Data contract

Every published analytical record carries `schema_version`, stable record ID, `run_id`, ticker/security ID, owning module, value/basis/units, effective date, market cutoff, financial period where relevant, source IDs, assumption IDs, upstream run IDs, confidence, freshness and validation status. Unknown values are null, never zero. PKR amounts and percentages have explicit units; fiscal-year and calendar-year estimates cannot be compared silently.

Evidence labels: CONFIRMED, DERIVED, ESTIMATE, ASSUMPTION, STALE, UNVERIFIED. These are distinct from validation states and run statuses.

### Required entities

| Entity | Minimum fields beyond shared metadata |
|---|---|
| Security | Ticker, exchange, segment, sector, currency, share count/date, corporate-action history |
| Transaction | Unique ID, trade/settlement date, type, quantity, price, fees, taxes, currency, source |
| Holdings snapshot | Timestamp, quantity, cost, cash, source, reconciliation state |
| Price | Session date, OHLCV, traded value, adjustment basis, source, calendar status |
| Financial fact | Period start/end, standalone/consolidated basis, line item, amount, units, filing locator |
| Normalization | Reported PAT/EPS, adjustment amount/sign, tax effect, rationale, recurring test, normalized result |
| Forecast | FY/CY/NTM basis, drivers, scenarios, EPS/DPS, share basis, model version |
| Valuation | Method, inputs, scenarios, present fair value, separate horizon exit value, uncertainty and gates |
| Source | URL, title, publisher, publication/access time, content hash, page/table/excerpt locator |
| Dividend | Announcement, type, DPS, verified ex/record/book-closure/payment dates, eligible quantity, tax, receipt |
| Watchlist | NEW_POSITION/ADD_ON, thesis, triggers, gates, status, next review, unresolved question |
| Catalyst | Event, window, probability basis, status, affected tickers, old/new decision effect |
| Assumption | Stable ID, scope, scenario, value, unit, valid dates, author, source/rationale |
| Override | Field, previous/new value, owner, reason, evidence, expiry, explicit user confirmation if required |
| Run | Scope, cutoffs, input/output hashes, code/config revisions, coverage, failures, usage, publication state |

History is append-only; corrections supersede records with an explicit link. Latest views select accepted records by effective date and ownership, not filename ordering.

## 7. Research and valuation requirements

### Evidence retrieval

Read saved evidence first. Prepare a missing/stale/conflicting/post-cutoff queue before network retrieval. Prefer PSX filings, statutory statements and regulators; then investor relations; then grounded secondary research. Cache retrieved content by hash, record failures, respect source access conditions and use bounded retries. If a source is unavailable, expose the gap rather than substitute a fabricated value.

Standalone Codex must use configured source adapters or authorized imports. ChatGPT connectors and web-search tools are not presumed to exist in its Python runtime. No plan depends on an undocumented connector API. First delivery must work offline with fixtures and supplied exports.

### Complete weekly coverage

Required universe = dated KSE-100 constituents plus current holdings, active watchlist and explicitly requested names; additional liquid-market discovery is configurable. Preserve membership snapshots to avoid survivorship bias.

Every required ticker receives one final coverage outcome: VERIFIED_CURRENT, VERIFIED_CARRIED_FORWARD, REVALUED, BLOCKED_EVIDENCE, BLOCKED_MODEL or EXCLUDED_WITH_REASON. Carried models must have their arithmetic reproduced, inputs checked against expiry rules and event coverage recorded. Silence or failure to find news is not proof of no event.

“Leave no valuation unchecked” means every required ticker is assessed and accounted for. A complete coverage ledger with unresolved models is not a completed valuation screen. Publish COMPLETE only when all eligible required models satisfy evidence and model checks; otherwise publish PARTIAL with exact counts and gaps. Attempt resolution of every required blocked record within the configured runtime budget; unfinished records remain queued and flagged.

Do not rank an incomplete/provisional model alongside certified candidates. Produce Top 10 only from eligible records; show fewer than ten if fewer pass.

### Earnings and sector models

Maintain reported -> normalized -> forward earnings separately for every modeled security. Genuine one-offs require signed adjustment, tax treatment and source locator. Do not remove recurring inventory effects, cyclicality or volatile treasury economics merely to improve quality scores.

Sector adapters:

- Banks: sustainable ROE/book or residual income; treasury gains, recurring income, credit costs, OCI, capital and dividend capacity.
- E&P: reserves/production, realized commodity prices, receivable collection, depletion, capex, taxes and payout; DCF plus payout cross-check.
- OMC/refining: volumes, margins, inventory gains/losses, working-capital finance, circular debt and upgrade capex.
- IPPs/holding companies: contract life, collections, project/SOTP value, debt, guarantees, minority interests and capital allocation.
- Industrials/autos/cement/textiles/chemicals: operating drivers, mid-cycle margins, capex, working capital and net debt; DCF and suitable multiples.
- Pharma/consumer: volume/price, FX/import costs, margins, working capital, regulation and sustainable growth.
- Insurance/shipping: underwriting/reserve quality/investment income, or freight/route/fleet cycle and renewal capex.

Unsupported sectors are BLOCKED_MODEL until an adapter is validated; a generic low-P/E rule is insufficient. Bear/base/bull outputs must be reproducible, terminal growth must remain below the applicable discount rate, and surplus cash/investment income must not be counted twice.

The latest rerun identifies migration checks: POL legacy bull DPS versus scoped inputs; BAHL legacy EPS versus actual model; OGDC historical dividend versus current entitlement; INDU operating earnings versus cash-income double counting; unresolved AKBL treasury/OCI bridge. Import these as exceptions requiring reconciliation, not as current accepted valuations.

### Return and entry calculations

For a declared horizon H: gross expected total return = (scenario exit price at H + dividends receivable during H - entry price) / entry price. Net return subtracts applicable taxes, transaction costs and separately modeled liabilities. Present fair value is not automatically an exit price. Keep margin of safety = 1 - price/present fair value separate from expected return. Guard zero/negative denominators.

Entry levels require a verified valuation, explicit margin-of-safety/hurdle assumptions and timing/risk gates. Annualized return is calculated only for a defined positive horizon. Default hurdle is the dated relevant sovereign benchmark plus disclosed ERP; company discount rates require their own derivation. Tax assumptions are configurable and must be checked before actual net-return planning.

## 8. Dividends, portfolio and risk

Distinguish declared, entitled, receivable, received, overdue and unverified dividends. Determine entitlement from verified exchange dates, settlement rules and holdings; a current holding is not automatically entitled. Where dates/rules are unverified, retain PENDING_CONFIRMATION. Buying after ex-date cannot inherit earlier entitlement.

Do not add a pending dividend twice through fair value and return calculations. Reconcile cash receipts and withholding. Sustainable forward DPS, trailing declared DPS and pending receivables are separate fields.

Portfolio diagnostics: equity and total-sleeve weights, brokerage cash, realized/unrealized gains, top holdings, sectors, economic factors, HHI, effective positions, liquidity and downside scenarios. Separate price return, income return and total return. Corporate actions must adjust share quantities/cost and historical comparison basis.

Correlation requires synchronized histories, a declared return basis, horizon and observation count. Missing prices are not zero returns. No implied portfolio diversification claim from insufficient samples. Portfolio sizing is blocked when holdings, prices or risk constraints are stale/unreconciled. Maximum position/sector/factor limits remain unconfigured until confirmed; do not invent Ahmed's limits.

IC outputs: ADD, ACCUMULATE, HOLD, TRIM, EXIT or REVIEW, with reason, evidence, confidence and dependencies. Distinguish proposed action from user-approved decision and executed transaction. Preserve 30/90-day catalysts, invalidation and opportunity cost.

## 9. Timing, watchlist and macro

RS/trend must distinguish relative return, percentile rank and RS momentum; publish lookbacks, eligible universe, ties, adjustment method and coverage. Mean reversion uses explicit formulas and calibrated thresholds, not an assumed profitable strategy. Backtests need point-in-time membership, corporate actions, fees and no look-ahead.

Retain the existing PSX_Mean_Reversion_DataStore.xlsx as a compatibility artifact during migration. Inspect its real tabs, formulas and lineage before mapping. Adopt one canonical structured record set; both workbooks derive from it. Do not introduce a second independently edited numerical RS store.

Watchlist stages: RESEARCH, ON_HOLD, PRICE_WATCH, READY, REJECTED, ARCHIVED; monitoring state separately tracks APPROACHING/TRIGGERED/WATCHING/STALE. READY requires evidence, valuation, portfolio fit/risk, catalyst and timing gates. Attractive held names become ADD_ON candidates; non-held names become NEW_POSITION candidates. Preserve user-authored thesis and entry discipline.

Macro covers SBP rates/yields, inflation, FX, reserves/external finance, IMF/fiscal risks, commodity/energy inputs and scenarios. Global stress monitoring includes oil/energy security, Western rates, sovereign spreads/French carry unwind, AI-linked credit stress and commercial-property/consumer signals. Distinguish facts, interpretations and hypothetical scenarios. News maps only evidence-supported transmission to tickers and EPS; otherwise use qualitative impact.

Carry the requested Pakistan bull/bear alert threshold strictly above 8.0, but do not activate numerical alerts until the inherited score methodology is recovered or a replacement explicitly approved. ATRL/BFAGRO weekday monitoring and Western rate-cut alerts need verified source adapters and schedules.

## 10. Excel specification

| Worksheet | Contents |
|---|---|
| Dashboard | Run status, all cutoffs, portfolio totals, key changes, unresolved gates |
| Holdings | Reconciled positions, costs, prices, gains, weights, source dates |
| Transactions / Cash | Append-only trades, fees, receipts and cash reconciliation |
| Dividend_Calendar | Dates, entitlement, gross/net pending and received amounts |
| Valuation | All required names, EPS basis, methods, scenarios, returns, confidence |
| Earnings_Bridge | Reported/normalized/forward results with adjustments |
| Entry_Levels | Proposed ranges, MOS, hurdle, timing and risk gates |
| Watchlist / Catalysts | Lifecycle, triggers, 30/90-day events and unresolved questions |
| RS_Trend / Sector_Rotation | Verified ranks, stages, history eligibility and breadth |
| Mean_Reversion | Signals, inputs, formula/model version and limitations |
| Macro / Scenarios | Dated observations and common bear/base/bull assumptions |
| Portfolio_Risk / IC_Actions | Concentration, stress losses and review decisions |
| Assumptions / Sources | Stable IDs, ownership, URLs, dates and locators |
| Coverage / Data_Gaps | Every required ticker, blocked fields, owner and next action |
| Run_Log / Change_Log | Every attempt, upstream IDs, old/new values and publication state |
| Usage | Measured tokens/cost/runtime; missing telemetry remains unknown |
| Manual_Inputs | Controlled overrides imported through a separate validation command |
| Retirement / Cross_Asset | Phase 4 scenarios, kept outside PSX position totals |

Use filterable tables, frozen headings, consistent PKR/%/date formats, source links, confidence/freshness formatting and explicit null display. Dashboard status remains readable without Excel recalculation. Python writes computed results; optional Excel formulas are cross-checks, not the sole calculations. Never depend solely on uncalculated formula caches.

Workbook export writes a temporary file, validates it, closes it and atomically replaces the prior workbook under a single-writer lock. If Excel has locked the file, record PUBLICATION_FAILED, retain a recovery candidate and retry when unlocked; do not claim an update succeeded.

Manual workbook edits are not silently ingested. An import command reads only the designated Manual_Inputs table, validates it and stores overrides with provenance. Export preserves accepted notes/overrides from canonical data. Users should close Excel before refresh or review a separate copy.

## 11. Run lifecycle and Git publication

1. Acquire repository/run lock; read latest published revision and ensure a clean or explicitly isolated worktree.
2. Resolve scope, universe and completed-session calendar; create unique run ID and explicit cutoffs.
3. Import/reconcile inputs; build freshness/conflict queue; fetch only justified gaps.
4. Validate source facts; recompute affected models and required coverage checks.
5. Generate structured feeds, delta report, workbook and validation results in staging.
6. Validate workbook-to-record parity, schema, totals, lineage and coverage; never overwrite manual work.
7. Publish accepted updates and run diagnostics as one local revision. PARTIAL may publish valid unaffected records and explicitly blocked areas; FAILED updates diagnostics only.
8. Commit only generated/authorized paths using a message such as `research: valuation <run_id> [PARTIAL]`.
9. Push the committed revision to the private remote when configured and authorized by workspace setup. Verify remote revision; otherwise report PUSH_FAILED/LOCAL_ONLY and preserve local commit for retry.

Atomic file replacement alone is not a multi-file transaction. Use a staged output set, a checksummed manifest and Git commit as the durable publication boundary. Recover abandoned staging on startup; published readers resolve the last committed manifest. Store content hashes in the manifest; record its commit SHA in external publication logs to avoid self-referential hashing.

Every run, including NO_MATERIAL_CHANGE and FAILED, appends a diagnostic entry and updates the workbook log if publication succeeds. No-change analytical values retain original run IDs/dates. Idempotency means repeat upstream ingestion creates no duplicate financial/transaction records; a repeated attempt may have a new diagnostic run ID.

Serialize all workbook writers. On non-fast-forward push, stop publication, fetch latest state and rerun the affected export from current canonical data; never force-push or merge XLSX binaries. A push failure does not cause recalculation or repeated trade ingestion. Rollback uses an explicit revert and records corrected lineage.

## 12. Commands and schedules

Proposed CLI contract; commands do not exist yet:

```bash
python -m investment_workspace init --offline
python -m investment_workspace import-portfolio --file inputs/holdings/latest.csv
python -m investment_workspace run daily
python -m investment_workspace run valuation --scope required --require-full-coverage
python -m investment_workspace run ic
python -m investment_workspace analyze APL
python -m investment_workspace run event --ticker PPL --source-file inputs/event.pdf
python -m investment_workspace update-dividends
python -m investment_workspace import-overrides --workbook workbooks/Investment_Workspace.xlsx
python -m investment_workspace validate --run latest
python -m investment_workspace export-excel
python -m investment_workspace replay --run-id EXAMPLE --offline
```

| Workflow | Target schedule in Asia/Karachi | Scope |
|---|---|---|
| Daily prices/RS/news/watchlist | Weekdays after verified completed PSX session | Incremental |
| Weekly valuation | Saturday 10:00 | Every required valuation checked |
| Integrated risk/IC/watchlist | Sunday 19:00 | Reuse latest valid feeds |
| Macro brief | Monday; exact time to recover/confirm | Common observations/scenarios |
| Earnings/notice event | On verified event or manual request | Affected tickers and dependents |
| Special monitors | Existing schedule to recover; configurable | ATRL/BFAGRO, stress, rates, score |

No schedules are created by this document. Scheduler must run on a persistent machine or hosted runner with repository and data access; an interactive Codex session alone is not a scheduler. Store timezone explicitly, resolve UTC conversions in scheduler config, accommodate holidays and delayed job starts, and use actual market sessions rather than guessed exchange closing times. Disable overlapping legacy jobs only after parity tests and replacement activation.

## 13. AI, cost and operational controls

Start with a single deterministic Python pipeline and optional AI enrichment. Codex writes/refines scripts and diagnoses failures; it need not reread the entire historical dataset each run. Pass compact evidence packets with source locators and calculation inputs. Cache extraction by document hash; invalidate when evidence/model/schema changes. Batch independent source retrieval, but serialize accepted state mutation.

Optional delegation follows the user's existing intent: planner, retrieval/extraction workers and independent validator. Provider/model names are configurable; do not hard-code a ChatGPT model label as a deployable API ID. AI service access and credentials are setup dependencies, not assumed available. Validate critical calculations independently in Python regardless of provider. AI output never bypasses schemas, evidence gates or human-authored records.

Log actual input, cached input, output and reasoning tokens where telemetry exposes them, tool charges, runtime, retries and coverage. Unknown usage is null. Rough text-size estimates must be labeled separately; never claim measured savings from character counts. Equivalent-scope cost comparisons must include delegation overhead and failed retries. Configure spend/runtime caps with explicit incomplete coverage when reached.

## 14. Acceptance criteria

| ID | Required test/outcome |
|---|---|
| AC01 | One offline fixture run generates a usable workbook and matching structured records |
| AC02 | Every run attempt appears in Run_Log; failures retain last-good values and original dates |
| AC03 | All eligible required tickers have reproducible validated valuations before COMPLETE |
| AC04 | Missing model/source produces explicit blocked coverage; no fabricated FV/Top 10 |
| AC05 | Repeat transaction/upstream ingestion creates no duplicates or false analytical changes |
| AC06 | Reported/normalized/forward EPS and fiscal bases stay separate; signed bridges reconcile |
| AC07 | Corporate actions and dividend entitlement prevent quantity, return and payout double counting |
| AC08 | Conflicting POL/BAHL/OGDC legacy inputs cannot silently overwrite accepted models |
| AC09 | Downstream IC/watchlist reuse owned inputs; no READY from screening alone |
| AC10 | Stale/unreconciled holdings block sizing; current cash/positions reconcile to source |
| AC11 | Every material output traces to sources, assumptions, code/model versions and upstream IDs |
| AC12 | Locked Excel, interrupted publication, push failure and concurrent jobs recover safely |
| AC13 | Rebuild workbook from a chosen committed dataset reproduces values/records within declared precision |
| AC14 | Offline replay performs no network requests; missing telemetry is reported unknown |
| AC15 | Changes to notes/overrides survive export and require explicit import validation |
| AC16 | Price adjustment, returns, ranks, correlation and backtests pass hand-calculated fixtures |

Tests should cover decisions and failure modes, not merely mirror code. Required fixtures: one bank, one E&P, one industrial, loss-making security, missing filing, split/bonus, ex-dividend boundary, stale price, changed assumption, duplicate import and publication interruption. Byte-identical XLSX is not required; normalized workbook values/tables and content hashes of canonical records are the reproducibility standard.

## 15. Implementation and migration plan

### Phase 1 — Durable baseline

Inventory source workbook(s), feeds, research files, holdings source and automations. Materialize/import accessible files once; retain immutable migration copies and checksums. Create package, CLI, schemas, contracts, run manifest, Excel export and Git publication. Deliver offline portfolio dashboard, reconciliation, sources, gaps and logs. Gate: AC01/02/05/10/11/12/13/15.

### Phase 2 — Earnings, valuation and dividends

Migrate the latest assumption/valuation feeds and model equations; map legacy workbook columns explicitly. Recover each model's exact inputs and reproduce historical outputs before changing methodology. Resolve known conflicts. Implement sector adapters incrementally, complete coverage tracking, return bridges and entitlement. Gate: AC03/04/06/07/08 with inherited models labeled provisional until evidence is verified.

### Phase 3 — Integrated investment workflows

Add verified data adapters, daily market history, macro/news, RS/mean reversion, risk, watchlist and IC. Reconcile legacy datastore totals/rows and history; demonstrate incremental event propagation and no-change reruns. Activate schedules after successful manual runs. Gate: AC09/14/16 plus operational parity; disable duplicate legacy tasks only afterward.

### Phase 4 — Broader wealth planning and optimization

Add gold/cash/crypto comparisons and retirement/PF/VPS/gratuity scenarios with dated user inputs, inflation, contributions, tax and withdrawal assumptions. Keep nominal and real values separate. Do not seed previously discussed retirement balances as current confirmed assets. Measure equivalent-scope cost/runtime and optimize evidence packets and retrieval without reducing required valuation checks.

No fixed completion estimate is promised before source access and model inventory; price-history coverage and filing extraction are likely dependencies.

## 16. Setup decisions and defaults

Proceed with private Git, Asia/Karachi schedules, PKR reporting, offline fixtures, ordinary XLSX tracking and manual position import as safe implementation defaults. Recover source files before asking for uploads.

Required before live operation: repository destination/access; actual source workbook; latest verified holdings/cash; supported data access; scheduler host; confirmed portfolio risk limits; tax/account settings; authorized Git auto-push policy. Required only for optional AI calls: provider, permitted model IDs, credentials and budget. These do not block designing or implementing the offline baseline.

## 17. Copy-ready Codex implementation instruction

> Implement the attached Investment_Workspace_PRD.md in this private repository. Read AGENTS.md and the existing repository first. Start with Phase 1 only: package/CLI, typed schemas, offline sample data, immutable source/provenance records, portfolio reconciliation, run logs, canonical readable files, and Investment_Workspace.xlsx. Keep the workbook tracked in Git and regenerate it after every attempted run, exposing failures while preserving last-good analysis. Implement staged publication, a single-writer lock and recovery. Add meaningful fixture tests and document how to run them. Do not invent current holdings, models, data APIs, financial facts or risk limits. Keep secrets out of Git. Do not depend on ChatGPT-only connectors. Preserve user-authored notes and import Excel overrides explicitly. Provide an offline demo and a clear list of remaining live-data dependencies. After the baseline passes, implement Phase 2 using recovered model inputs and the evidence contract; account for every required valuation and withhold COMPLETE until eligible models pass. Report exactly what was built, tested and remains blocked.

