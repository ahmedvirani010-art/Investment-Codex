# Investment Codex - Practical Prompt Catalogue

Implemented Python 0.6.0 checkout; published release e88446f; documentation/preflight through Phase 6. Not a current market assessment.

## Common prompt
Use the latest accepted Investment-Codex state first. Resolve dataset_id and published_run_id from committed data/canonical/portfolio.json. Use <date> explicitly in Asia/Karachi and preserve the original market cutoff. Tell me exactly which fields/sources are missing rather than fabricating them. Use simulation for what-if requests; accept new inputs only when I explicitly ask. Produce a PDF report and link JSON, Markdown and Excel evidence. If execution is disabled, prepare/validate the request and say submitted or blocked, never completed.

## Input packs

### A - Portfolio
Full Bundle JSON for initial import: mode, market_cutoff, sources, securities, opening, closing, transactions, prices; dataset_id and policy as applicable. Snapshot = timezone-bearing timestamp, source_id, cash, positions[{ticker,quantity,cost}], where cost is total position cost. Transactions need immutable ID, timestamp, settlement_date, kind and source_id; BUY/SELL need ticker/quantity/price, cash flows amount, SPLIT ratio. Prices need ticker/session_date/close/source_id. Workspace updates use package.portfolio (complete securities/opening/closing/transactions/prices; optional policy) plus package.sources. See docs/input-schema.json and WorkspacePackage schema.

### B - Research and forecasts
JSON research contains universe/expiry verification, earnings, models, dividends and resolutions. Supply sourced reported PAT/shares/EPS, one-off signed adjustments and tax effects; owned model/method/version, accounting/period/share bases, benchmark/ERP, bear/base/bull drivers and applicable approval. Current real core-sector certification needs numerical sector_forecasts, financials and shared scenario mappings. Source references need locators and confirmed evidence. Unknown required drivers block calculation. See research-schema.json and financial-fact-schema.json.

### C - Integration and history
JSON integration holds calendar, memberships, histories, timing_policy, macro, macro_scenarios, events, risk_limits, factors, catalysts, candidates, proposals and alert_methodology. Records have record_id/ticker/effective_date/valid_until/source_ids; corrections supersede old IDs. Supplied collections are complete owned views, not deletion patches. OHLCV CSV is supported only via import-history with a companion JSON packet. All timing/risk parameters, source provenance and corporate actions must be explicit. See integration-schema.json.

### S / D - Scenarios and decisions
ScenarioProfile supplies version/name/basis/period/horizon, dated sources and numerical assumptions with units. ScenarioLink supplies profile_id/basis/period/horizon, numerical bindings and binding_units; sourced rationale/overrides for domain differences. ICDecision supplies proposal_id, decision, actor/time, reason and reviewed_basis_hash; approved_quantity/transaction_ids only for APPROVE. See scenario-profile-schema.json and ic-decision-schema.json.

### W - Wealth
A sources/wealth JSON packet or package.wealth. Assets need unique asset/economic IDs, kind, balance or accepted portfolio_link, currency, availability and explicit USD FX where needed. Flows specify net amounts, nominal/real basis, destination, frequency, dates and unique benefit claim IDs. Scenarios specify inflation and per-asset return/fee/tax rates; plans specify month-start dates, months, spending and complete withdrawal order. Histories specify ordered quotes, FX and price/total-return basis. See wealth-schema.json and wealth-packet-schema.json.

### E / M / T - Evidence, migration, storage
EvidencePackage 4.0 imports sources, structured owned modules and licensed original descriptors; CLI file paths resolve relative to its package. Workspace originals use verified receipt_id/artifact_id plus EvidenceDocument, never arbitrary paths. Migration requires XLSX plus WorkbookMigration JSON with hash/mappings/approval/permission/tolerances. StorageRequest JSON accepts only pull or push, not shell commands. See evidence-package-schema.json, migration-schema.json and storage-request-schema.json.

## P01 - Check readiness and missing inputs

### Copy-ready prompt
Read the accepted workspace and report what is ready, blocked, stale or missing for portfolio, valuation, timing, macro, IC, retirement and cross-asset workflows. Distinguish software readiness from production readiness. Deliver a downloadable PDF summary and link the native artifacts. Identify missing inputs without guessing.

Inputs: No new financial data. Reuse committed canonical state and configuration; specify the intended assessment date if a new dated calculation is wanted.

Route: CLI: readiness; schedule-status. These read committed status, not a fresh market assessment.

Native outputs: Readiness JSON: per-workflow coverage, compatibility, deployment status, dependency reasons and next actions. Schedule-status JSON.

Effect / limits: Read only. A new date is not silently applied to this read-only command.

Code: readiness.py:committed_report; cli.py

## P02 - Run an isolated complete synthetic demonstration

### Copy-ready prompt
Create a separate empty demo workspace using the completion fixture and demonstrate the implemented scenarios, numerical forecasts, portfolio and wealth modules. Do not replace my accepted workspace. Deliver a downloadable PDF summary and link the native artifacts. Identify missing inputs without guessing.

Inputs: An empty separate directory; supplied completion-demo fixture. No personal balances or secrets.

Route: CLI: --root <empty_demo> init --offline --completion-demo.

Native outputs: Synthetic JSON state, run manifest, coverage/validation/change/usage files and Investment_Workspace.xlsx.

Effect / limits: Creates a DEMO only in the selected empty workspace. Never initializes over accepted data.

Code: cli.py:init; pipeline.py:fixture_bytes

## P03 - Reconcile and review my existing portfolio

### Copy-ready prompt
As of <date>, reconcile accepted holdings, cost and cash; explain realized/unrealized returns, stale prices and exceptions. Keep dividends receivable separate from received cash. Deliver a downloadable PDF summary and link the native artifacts. Identify missing inputs without guessing.

Inputs: Pack A already accepted: opening/closing dated snapshots, ledger, securities, sources and prices; optional declared tolerances/risk policy.

Route: Workspace run with workflows [portfolio], or CLI run portfolio --offline --as-of <date>.

Native outputs: Holdings, Transactions, Cash, Reconciliation and Data_Gaps sheets; canonical snapshot and reports/latest/summary.json.

Effect / limits: Recalculates/publishes derived reports; does not import a new balance package. DEMO portfolio readiness can remain PARTIAL.

Code: portfolio.py:calculate; readiness.py:workflow_status

## P04 - Accept a revised portfolio or price snapshot

### Copy-ready prompt
Validate this approved complete portfolio snapshot first. Then accept the supplied update with new source identities where evidence changed, reconcile it and recalculate portfolio and valuation. Do not alter other module-owned inputs. Deliver a downloadable PDF summary and link the native artifacts. Identify missing inputs without guessing.

Inputs: Pack A as WorkspacePackage.portfolio plus sources. Supply the complete active portfolio view, not one-cell patches. A revised price feed uses appropriate new source IDs; do not modify accepted transaction IDs.

Route: Workspace validate first; explicit accept-and-run/import with package.portfolio. CLI import-portfolio accepts a full Bundle, not the same partial workspace envelope.

Native outputs: Validation/request receipts; accepted canonical state, source history, run manifest, refreshed workbook and scoped request snapshot/workbook.

Effect / limits: Explicit acceptance changes financial inputs only after validation. Initial real dataset activation is P30.

Code: workspace_requests.py:prepare/execute; pipeline.py:run

## P05 - Analyze one already registered security

### Copy-ready prompt
Analyze <ticker> using its accepted earnings, sector model, scenarios, price, timing, events and risk basis. Explain valuation, entry gates, catalysts, invalidation and missing evidence. Deliver a downloadable PDF summary and link the native artifacts. Identify missing inputs without guessing.

Inputs: Ticker must exist in securities. Packs B and C, current price and applicable approvals must already be accepted, or be supplied separately for validation/import.

Route: CLI analyze <ticker> --offline. Alternatively run valuation/timing/ic and present that ticker; the workspace envelope has no ticker-filter field.

Native outputs: Ticker-filtered CLI security JSON plus shared-workspace outputs; Earnings_Bridge, Valuation, Entry_Levels and integration sheets where populated.

Effect / limits: Recalculates shared dependencies/full required coverage; not an isolated ticker-only calculation or automatic company data download.

Code: cli.py:analyze/run; research.py

## P06 - Run the required valuation screen

### Copy-ready prompt
As of <date>, screen the dated required universe and give every ticker a final coverage outcome. Rank only eligible validated base-case valuations, show fewer than ten if necessary, and explain all exclusions. Deliver a downloadable PDF summary and link the native artifacts. Identify missing inputs without guessing.

Inputs: Pack B: verified universe/membership, earnings, models, bear/base/bull assumptions, current prices, sovereign benchmark/ERP, financial facts, scenario mappings and approvals. Pack C supports timing/risk gates.

Route: Workspace run [valuation]; CLI run valuation --as-of <date> --offline --require-full-coverage.

Native outputs: Coverage register, valuation/return/entry tables, eligible Top_10, data gaps, valuation summary JSON and workbook.

Effect / limits: Publishes derived results. Incomplete models produce PARTIAL/BLOCKED outcomes; a full coverage ledger alone is not a complete screen.

Code: research.py:_calculate; models.py:reference_value

## P07 - Import reported and normalized earnings with forecasts

### Copy-ready prompt
Validate the supplied filing-derived earnings bridge and revised owned model for <ticker>. Show reported, normalized and forward PAT/EPS, signed adjustments, taxes, share basis and scenarios before accepting the approved package. Deliver a downloadable PDF summary and link the native artifacts. Identify missing inputs without guessing.

Inputs: Pack B: Earnings and ValuationModel records, source locators, adjustment rationale/tax effect, accounting/period/share bases, typed drivers and version-matched approvals. Supersede existing records explicitly.

Route: Workspace validate/simulate package.research + financials + sources, followed by explicit import/accept-and-run. CLI import-research only accepts sources/research; use import-evidence for a richer combined pack.

Native outputs: Earnings_Bridge, Forward_Bridge, Valuation and coverage diagnostics; validated/accepted input and request receipts.

Effect / limits: No automatic PDF-to-financial-statement parser; the backend consumes controlled structured inputs.

Code: schemas.py:Earnings/ValuationModel; intake.py:EvidencePackage

## P08 - Check a Bank, E&P or Industrial numerical model

### Copy-ready prompt
Validate the supplied <Bank/E&P/Industrial> forecast against its sourced facts. Show intermediate calculations, PAT/EPS, FCFE where applicable, capital/payout constraints, units, share basis and period reconciliation. Deliver a downloadable PDF summary and link the native artifacts. Identify missing inputs without guessing.

Inputs: Pack B engine records; see the engine checklist and required-field appendix. Every required driver must be supplied; bound facts need canonical units, physical denominators and explicit FX as applicable.

Route: Workspace validate or simulate [valuation] with revised research/financials; certification uses the normal valuation engine.

Native outputs: Forward_Bridge numerical intermediates, valuation outputs and specific blocking reasons. Bank has equity/dividend-capacity outputs; FCFE is for E&P/Industrial.

Effect / limits: Validation/simulation does not accept inputs. Other sectors do not have these first-wave typed engines.

Code: sector_engines.py:forecast; forecast_contracts.py; models.py

## P09 - Revise shared scenario assumptions

### Copy-ready prompt
Validate these new versioned bear/base/bull profiles and explicit valuation/macro/wealth mappings. Show which dependent forecasts need revision, and preserve owned EPS until an approved model update is imported. Deliver a downloadable PDF summary and link the native artifacts. Identify missing inputs without guessing.

Inputs: Pack S: profiles with basis, period, horizon, assumptions/units, dates and evidence; mappings with bindings and units; sourced rationale for overrides/domain differences; revised owned records for intentional acceptance.

Route: Workspace validate/simulate package.scenario_profiles plus affected research/integration/wealth. Accept only with explicit import.

Native outputs: Scenario_Profiles, mapped scenario diagnostics, forecast/wealth results and data gaps for stale/mismatched dependencies.

Effect / limits: Profile changes do not automatically rewrite EPS or carry short-term assumptions into retirement horizons.

Code: scenarios.py:prepare/resolve; schemas.py:ScenarioLink

## P10 - Simulate a forecast or portfolio change

### Copy-ready prompt
Simulate <specific supplied changes> as of <date> against accepted inputs. Compare valuation, portfolio risk and/or retirement outcomes, and leave canonical financial inputs unchanged. Deliver a downloadable PDF summary and link the native artifacts. Identify missing inputs without guessing.

Inputs: Only changed owned modules in a complete typed WorkspacePackage; use new IDs/supersession for revised accepted records, explicit assumptions, and expected dataset/run IDs.

Route: Workspace simulate with selected workflows and optional package or verified package_artifact.

Native outputs: reports/requests/<id>/Investment_Workspace.xlsx, snapshot.json, JSON/Markdown receipt, module statuses and missing-input list.

Effect / limits: Isolated calculation; accepted_inputs_changed must be false. There is no arbitrary code/formula execution or generic numerical optimizer.

Code: workspace_requests.py:execute

## P11 - Reconcile dividends and entitlement corrections

### Copy-ready prompt
Update dividends as of <date>. Show historical entitlement, linked receipts, gross/net pending, overdue balances and withholding exceptions. For a correction, preserve old proof and recalculate only from verified revised evidence. Deliver a downloadable PDF summary and link the native artifacts. Identify missing inputs without guessing.

Inputs: Pack B dividends plus Pack A opening snapshot, settled quantity-affecting transactions and accepted DIVIDEND receipt IDs; ex/record/payment dates, DPS, tax policy and sources. Use revision_kind ENTITLEMENT_BASIS or RECEIPT_UPDATE for revisions.

Route: Workspace run [update-dividends] for accepted data; validate/import a revised research/portfolio package when new facts are supplied. CLI update-dividends has no --as-of; use run update-dividends --as-of <date>.

Native outputs: Dividend_Calendar: eligible quantity, immutable entitlement basis, gross/net entitlement/received/pending, overdue/status flags and correction proof; gaps/receipts.

Effect / limits: Receivables never increase brokerage cash. Unknown tax gives null net pending; fees do not create unpaid dividend entitlement.

Code: dividends.py:result; research.py:dividend_result

## P12 - Run RS, trend, sector rotation and mean reversion

### Copy-ready prompt
Using verified completed-session data, identify leaders, laggards, sector rotation, trend stages, extension and mean-reversion conditions. Disclose calibration and backtest limitations. Deliver a downloadable PDF summary and link the native artifacts. Identify missing inputs without guessing.

Inputs: Pack C: calendar, dated membership, benchmark/security OHLCV, corporate actions/action coverage, sector labels and explicit TimingPolicy windows, thresholds and liquidity/calibration parameters.

Route: Workspace run [timing]; CLI run timing. To import CSV: import-history --file <csv> --packet <integration.json> --history-id <id>.

Native outputs: RS_Trend, Sector_Rotation, Mean_Reversion, Backtests/Backtest_Trades and gaps; feeds/latest/timing.json.

Effect / limits: No inferred histories or live-feed discovery. CSV header order is exact; JSON provides provenance, calendar and actions.

Code: timing.py; workflows.py:_calculate; adapters.py:read_history_csv

## P13 - Review macro observations and scenarios

### Copy-ready prompt
Review the accepted Pakistan/global macro observations and bear/base/bull paths as of <date>. Separate facts, interpretations and assumptions, identify conflicts/expiry and flag affected forecasts for owned revision. Deliver a downloadable PDF summary and link the native artifacts. Identify missing inputs without guessing.

Inputs: Pack C macro observations with indicator, value/unit, narrative, dates and sources; macro scenarios and Pack S mappings. Numerical claims require supplied evidence.

Route: Workspace run [macro]; import revised sources/integration separately if requested.

Native outputs: Macro, Scenarios, News_Impact/Event_Propagation where relevant, refresh queue and macro completeness status.

Effect / limits: No autonomous macro feeds or guaranteed economic forecasts. Numerical alert evaluation requires approved methodology and supplied scores.

Code: workflows.py; schemas.py:MacroObservation/MacroScenario/AlertMethodology

## P14 - Import a news or earnings event packet

### Copy-ready prompt
Validate and import this approved event packet. Map the stated transmission to the supplied affected tickers, report urgency, and queue stale owned models rather than silently applying an EPS change. Deliver a downloadable PDF summary and link the native artifacts. Identify missing inputs without guessing.

Inputs: Pack C complete integration update plus new sources; event headline, affected_tickers, transmission, urgency, requires_model_revision. If eps_delta is given, include eps_period and eps_calculation.

Route: Workspace validate then import/accept-and-run [event]; CLI run event --source-file <sources-integration.json> --as-of <date>.

Native outputs: News_Impact, Event_Propagation, Refresh_Queue, changed coverage/readiness, run/request receipts and workbook.

Effect / limits: Acceptance changes the integration inputs. A headline/PDF alone is not a valid event packet; no automatic owned EPS overwrite.

Code: schemas.py:NewsEvent; workflows.py:event propagation; cli.py:run

## P15 - Review portfolio concentration and sizing constraints

### Copy-ready prompt
Review position, sector and economic-factor concentration, cash, correlations, scenario returns and research quantity caps. Explain breached limits and missing inputs. Do not generate orders. Deliver a downloadable PDF summary and link the native artifacts. Identify missing inputs without guessing.

Inputs: Packs A/B/C: reconciled current holdings/prices, supplied user-confirmed RiskLimits, factors, histories/calendar, valid valuations and candidate entry/stop/target assumptions.

Route: Workspace run [ic] and/or [daily]; CLI run ic. Both operate on shared accepted inputs.

Native outputs: Portfolio_Risk, Correlations, IC_Actions sizing details, scenario coverage, proposed/illustrative caps and gap reasons.

Effect / limits: Calculated caps are not trades. DEMO data and incomplete risk/history coverage can keep gates blocked.

Code: workflows.py:risk_outputs; decisions.py:basis

## P16 - Update or review the watchlist

### Copy-ready prompt
Review the watchlist for approaching entries, stale theses, catalysts and invalidation. For the supplied update, validate the revised complete candidate collection before accepting it. Deliver a downloadable PDF summary and link the native artifacts. Identify missing inputs without guessing.

Inputs: Pack C WatchCandidate: author, thesis, invalidation, portfolio_fit, desired_entry, stop_price, approach_fraction, next_review, requested stage/weight and catalyst IDs; Pack A/B/C for derived readiness.

Route: Workspace run [watchlist] for monitoring; validate/import package.integration for changes.

Native outputs: Watchlist, Catalysts, gate/monitoring states, next-review information and IC/risk dependencies.

Effect / limits: No standalone add/remove command. Updates use owned records; omission is not deletion—use supersession and requested archive/reject stages.

Code: schemas.py:WatchCandidate; workflows.py:watchlist

## P17 - Prepare IC proposals

### Copy-ready prompt
Review supplied IC proposals against valuation, timing, candidate readiness, portfolio risk, invalidation and opportunity cost. Clearly distinguish proposals from user decisions. Deliver a downloadable PDF summary and link the native artifacts. Identify missing inputs without guessing.

Inputs: Pack C ICProposal records with action, reason, confidence, invalidation, opportunity_cost and candidate_id where applicable; accepted model/risk/timing/candidate evidence.

Route: Workspace run [ic]; explicit package.integration import only if proposal records are changing.

Native outputs: IC_Actions with proposed/effective research action, readiness reasons, sizing cap and supporting tables.

Effect / limits: Derived proposal actions never constitute user approval, execution or an order.

Code: schemas.py:ICProposal; workflows.py:IC actions

## P18 - Record an explicit IC approval, rejection or deferral

### Copy-ready prompt
Record my explicit <APPROVE/REJECT/DEFER> decision for <proposal_id> with my reason, date and reviewed basis. If I supplied a completion quantity and imported transaction IDs, report factual fulfilment separately. Deliver a downloadable PDF summary and link the native artifacts. Identify missing inputs without guessing.

Inputs: Pack D: ICDecision actor/timezone timestamp, effective/expiry dates, reason, source IDs, proposal ID and exact reviewed_basis_hash from decision-basis. APPROVE may include approved_quantity and valid transaction IDs.

Route: CLI decision-basis to obtain current hashes; workspace operation decision with package.sources and package.decisions. Do not substitute an ICProposal.

Native outputs: IC_Decisions, immutable history, CURRENT/NEEDS_REVIEW and execution-fulfilment statuses; request receipt.

Effect / limits: Changes accepted user decision records, not trades. Material risk/source versions can require review even inside limits.

Code: decisions.py:basis/calculate; schemas.py:ICDecision

## P19 - Project retirement and liquidity

### Copy-ready prompt
Project my supplied plan under bear/base/bull assumptions. Show nominal/real wealth, accessible versus locked assets, spending gaps, benefit timing and depletion dates. State all unknown assumptions. Deliver a downloadable PDF summary and link the native artifacts. Identify missing inputs without guessing.

Inputs: Pack W: dated asset balances and accessibility, currencies/FX, net contribution/benefit/expense flows, inflation and per-asset return/fee/tax policies, month-start plan dates, horizon and withdrawal order; shared long-term mapping for real certification.

Route: Workspace run [retirement] with accepted wealth; CLI import-wealth for an approved sources/wealth packet, or workspace validate/import a wealth package.

Native outputs: Retirement monthly trajectories, Retirement_Summary, Wealth_Assets/Flows and model/data gaps; JSON snapshot and workbook.

Effect / limits: Deterministic scenario projection, not Monte Carlo success probability. Missing PSX inputs need not block independently supplied wealth assets.

Code: wealth.py:project/calculate_wealth; schemas.py:Wealth

## P20 - Compare retirement what-if choices

### Copy-ready prompt
Simulate the supplied contribution/spending/retirement-date alternatives <A and B> against the same accepted base. Compare real balances, funding gaps, accessibility and depletion without accepting either alternative. Deliver a downloadable PDF summary and link the native artifacts. Identify missing inputs without guessing.

Inputs: Pack W for each alternative, including superseding scenario/flow/plan IDs as needed, explicit inflation/returns/tax/fees and complete updated owned collections.

Route: Two workspace simulate requests with unique IDs and workflows [retirement]; or compatible legacy wealth requests. wealth-preflight checks a candidate packet without changing the caller checkout.

Native outputs: Scoped snapshots/workbooks and receipts for each alternative; assistant-produced comparison PDF from those results.

Effect / limits: No built-in contribution search/retirement optimizer. A/B comparison is orchestration of supplied deterministic scenarios.

Code: wealth_requests.py:preflight/sandbox; workspace_requests.py:simulate

## P21 - Compare PSX, gold, USD, funds and optional crypto

### Copy-ready prompt
Compare the supplied asset histories on synchronized common dates and a consistent PKR basis. Show returns, observations and pairwise correlations, with explicit price versus total-return limitations. Deliver a downloadable PDF summary and link the native artifacts. Identify missing inputs without guessing.

Inputs: Pack W assets/histories: asset_key, currency, PRICE/TOTAL_RETURN basis, ordered dates/quotes, dated explicit USD FX and source IDs; minimum observation setting. Crypto requires include_crypto=true.

Route: Workspace run [cross-asset], or simulate a revised supplied wealth package.

Native outputs: Cross_Asset, Asset_Correlations and coverage/insufficient-history diagnostics; JSON and workbook.

Effect / limits: No live quote acquisition or automatic optimized allocations. Price histories must not be silently called total-return histories.

Code: wealth.py:compare_histories; schemas.py:CrossAssetHistory

## P22 - Explain what changed between committed runs

### Copy-ready prompt
Compare the current accepted state with run <run_id>. Explain changes in owned inputs, results, coverage and decisions, distinguishing data changes from unchanged carried calculations. Deliver a downloadable PDF summary and link the native artifacts. Identify missing inputs without guessing.

Inputs: Existing committed historical run ID; no new financial input. Resolve the comparison base explicitly.

Route: CLI changes --since-run <run_id>; inspect committed run manifests/snapshots and changes records.

Native outputs: Comparison JSON plus reports/latest/changes.md and run changes.json where already published; narrative PDF.

Effect / limits: Read only. Do not invent business causes beyond recorded evidence or imply every change has a live-news explanation.

Code: pipeline.py:changes_since

## P23 - Inspect and reconcile the legacy workbook

### Copy-ready prompt
Inspect <workbook.xlsx> read-only, inventory sheets/formulas and prepare the supplied mapping/parity dry run. List missing mappings, ignored-sheet reasons and model conflicts before any acceptance. Deliver a downloadable PDF summary and link the native artifacts. Identify missing inputs without guessing.

Inputs: Pack M: actual XLSX and WorkbookMigration JSON with SHA-256, sheet/column/key mappings, approved_by, reason, store permission, tolerances and methodology-review status.

Route: CLI inspect-datastore --workbook <xlsx>; migrate-workbook --file <xlsx> --mapping <mapping.json> --dry-run. --accept is a separate explicit action.

Native outputs: Sheet/formula inventory JSON, reconciliation differences and migration diagnostics; accepted migration record only after explicit acceptance.

Effect / limits: Inspection is not recovered methodology approval or certified parity. Never execute workbook formulas or manually merge binary workbooks.

Code: adapters.py:inspect_datastore; intake.py:migrate_workbook; migration.py

## P24 - Import approved evidence and original documents

### Copy-ready prompt
Validate this controlled evidence package, retain only licensed-to-store originals, and then accept the explicitly approved records with complete provenance. Identify unsupported or missing extraction fields. Deliver a downloadable PDF summary and link the native artifacts. Identify missing inputs without guessing.

Inputs: Pack E: EvidencePackage schema_version 4.0; sources and optional bundle/research/integration/wealth/financials/profiles/decisions; files with path and EvidenceDocument source/hash/suffix/role/store_permitted. Paths are for CLI operator imports only.

Route: CLI import-evidence --file <package.json> --as-of <date>. Workspace requests instead use package.originals verified transfer references; no arbitrary local paths.

Native outputs: Evidence_Library, content-addressed evidence blobs, source registry, accepted records/workbook and run receipt.

Effect / limits: Raw PDF/XLSX files are stored/referenced, not automatically converted into verified financial facts.

Code: intake.py:EvidencePackage/import_package; schemas.py:EvidenceDocument

## P25 - Fetch and verify an R2 source artifact

### Copy-ready prompt
From investmentcodex, fetch approved/<exact_key> with expected SHA-256 <hash>. Verify bytes, preserve source metadata and stage the artifact. Do not accept it as financial input. Deliver a downloadable PDF summary and link the native artifacts. Identify missing inputs without guessing.

Inputs: Pack T pull: unique request_id, operation pull, objects with exact permitted keys and preferably expected sha256. Active transport and required connection policy must be available.

Route: Workspace storage.pull or CLI storage pull --file <storage.json> [--dry-run]. Interactive Cloudflare plugin is a separate operator route; it is not called by the Python runner.

Native outputs: reports/storage/<id>.json; artifact_id/hash/size/pinned status; ignored .runtime/r2/artifacts staging. Workspace JSON/Markdown receipt.

Effect / limits: Only sources/ and approved/ are configured for pulls. Unpinned or failed/partial receipts cannot feed accepted imports.

Code: object_storage.py:transfer_receipt/artifact; workspace_requests.py

## P26 - Accept a previously verified transferred package

### Copy-ready prompt
Validate the workspace package referenced by receipt <receipt_id> and artifact <artifact_id>. After my explicit approval, import its typed records and recalculate the selected modules. Deliver a downloadable PDF summary and link the native artifacts. Identify missing inputs without guessing.

Inputs: A COMPLETE pinned pull receipt plus matching artifact bytes containing a valid WorkspacePackage; source IDs, dataset/run revision and acceptance authorization.

Route: Workspace validate/simulate first; explicit import or accept-and-run with package_artifact={receipt_id,artifact_id}.

Native outputs: Validation/request receipts and, after acceptance, canonical records, source history, run artifacts and workbook.

Effect / limits: No arbitrary downloaded file is accepted: it must match the package contract. Original PDFs/XLSX use package.originals and EvidenceDocument descriptors instead.

Code: workspace_requests.py:prepare; object_storage.py:artifact

## P27 - Archive a committed analytical run to R2

### Copy-ready prompt
Archive committed run <run_id> to investmentcodex using only these exact manifest paths: <paths>. Verify read-back SHA-256 and write the archive manifest last. Report storage status separately from financial acceptance. Deliver a downloadable PDF summary and link the native artifacts. Identify missing inputs without guessing.

Inputs: Pack T push: unique request_id, operation push, committed run_id, exact paths in its manifest; enabled authenticated runner storage route, prefixes and limits.

Route: Workspace storage.push or CLI storage push --file <storage.json> [--dry-run]. An accepted calculation may request optional archive_paths.

Native outputs: Immutable archives/<run_id>/<sha256>/<filename> objects, verified archive manifest and durable storage receipt.

Effect / limits: No deletion or unrestricted sync. Current public-bucket policy excludes private financial files; binary plugin transfer remains unverified.

Code: object_storage.py:transfer; docs/cloudflare-r2-plugin.md

## P28 - Inspect a failed transfer and retry only storage

### Copy-ready prompt
Read transfer <receipt_id>, explain completed/failed/unattempted objects and available checksum/byte observations. Retry the same approved transfer with a new ID, without repeating any accepted financial import. Deliver a downloadable PDF summary and link the native artifacts. Identify missing inputs without guessing.

Inputs: Prior transfer receipt; for an archive retry use the already committed accepted result_run_id and manifest paths. Correct access/configuration first; do not mutate the old receipt.

Route: Workspace storage.status with transfer_receipt_id, then a new storage.pull/push request; CLI storage status --request-id <id>.

Native outputs: Old immutable receipt plus a new attempt receipt; independent module/transfer outcomes and progress. Existing workbook/input bytes remain unchanged for storage-only retries.

Effect / limits: An existing ID returns its recorded outcome; rerunning FAILED with the same ID is not a new attempt.

Code: object_storage.py:execute/transfer_receipt; tests/test_transfer_failure_receipts.py

## P29 - Validate, export or replay a workbook

### Copy-ready prompt
Validate committed run <latest_or_id>. Export a current workbook if requested, or replay run <run_id> into a separate XLSX output. Confirm record/numerical parity and distinguish replay from current analysis. Deliver a downloadable PDF summary and link the native artifacts. Identify missing inputs without guessing.

Inputs: Committed state/manifests; explicit run ID for replay and operator output path. No new financial facts.

Route: CLI validate --run <latest_or_id>; export-excel --offline; replay --run-id <id> --output <path.xlsx> --offline.

Native outputs: Validation JSON with integrity/parity; export updates the main XLSX/run revision; replay writes the separate requested workbook.

Effect / limits: Validation reads only; export creates derived publication; replay does not change accepted state. PDF presentation requires a separate reporting step.

Code: pipeline.py:validate/replay; excel.py:export_workbook/validate_workbook

## P30 - Activate an explicitly approved real dataset

### Copy-ready prompt
After privacy and validation prerequisites pass, activate this supplied USER_IMPORT bundle as dataset <id>, recording author <name> and reason <reason>. Preserve the prior demo history and never relabel synthetic balances as real. Deliver a downloadable PDF summary and link the native artifacts. Identify missing inputs without guessing.

Inputs: Full approved Pack A Bundle with real sourced records and dataset ID, privacy checks, author/reason and explicit real-data confirmation. Follow-on evidence/legacy/methodology gates remain separate.

Route: CLI activate-dataset --file <bundle.json> --author <name> --reason <reason> --confirm-real-data. No workspace request operation activates a dataset.

Native outputs: Real-dataset canonical snapshot, dataset transition/audit history, new workbook and run artifacts; source/history validation diagnostics.

Effect / limits: GATED. Not currently ready; activation is not permission to publish private files into a public repository/bucket.

Code: cli.py:activate-dataset; pipeline.py:dataset boundary

## P31 - Review or import permitted workbook notes

### Copy-ready prompt
Inspect the supplied Manual_Inputs sheet and import only confirmed permitted notes with author, reason, effective date and expiry. Reject numerical overrides. Deliver a downloadable PDF summary and link the native artifacts. Identify missing inputs without guessing.

Inputs: XLSX containing the exact Manual_Inputs header contract: override_id,ticker,field,value,author,reason,effective_date,expires_at,confirmed,supersedes. The only permitted field value is note. Author/reason, confirmation, effective date and optional expiry/supersession are separate metadata columns.

Route: CLI import-overrides --workbook <xlsx>.

Native outputs: Accepted notes/override lineage, workbook and run diagnostics; invalid fields are rejected.

Effect / limits: Explicit note import; not a route to overwrite accepted prices, balances or models through Excel cells.

Code: excel.py:read_notes; schemas.py:NoteOverride; pipeline.py:import_overrides

## P32 - Run a budgeted refresh or measure caching

### Copy-ready prompt
Refresh <workflow> as of <date> within <work units/seconds>, preserve a deferred-work queue and report actual usage. Separately benchmark unchanged and changed synthetic wealth inputs with parity verification. Deliver a downloadable PDF summary and link the native artifacts. Identify missing inputs without guessing.

Inputs: Accepted input packs for the workflow; explicit budgets. Benchmark needs samples (1..10) and months (1..1200), not personal financial data.

Route: CLI run <workflow> --offline --as-of <date> --max-work-units <n> --max-seconds <n>; benchmark-wealth --samples <n> --months <n>.

Native outputs: Usage/deferred-work JSON and workbook diagnostics; benchmark JSON with timings, code/input hashes, parity, medians and ratios.

Effect / limits: Budgeted run can publish PARTIAL/deferred results. Benchmark is isolated synthetic measurement, not guaranteed speedup or measured AI savings.

Code: runtime.py:RunContext; wealth_benchmark.py:benchmark

## P33 - Recover publication, submit pending requests and publish

### Copy-ready prompt
Inspect pending publication recovery, recover the journal if needed, and process authorized committed requests. Publish to origin/work only after checking the expected remote head; report receipts and publication outcome. Deliver a downloadable PDF summary and link the native artifacts. Identify missing inputs without guessing.

Inputs: Existing journal/request files, authorized publication policy and correct dataset/run IDs; clean checkout, repository access and private Actions context for the guarded scanner.

Route: CLI recover; request --pending --publish for activated private Actions; push --remote origin --branch work. Native push defaults to main, so specify work.

Native outputs: Recovery/run/request receipts, publication status/remote SHA and recovery bundle where configured. JSON/Markdown and workbook links as applicable.

Effect / limits: GATED for production. No force-push or automatic workbook merge. GitHub-plugin publication uses inspected expected-head operations when native transport is unavailable.

Code: storage.py:publish/rollback_pending; workspace_requests.py:pending; cli.py:push

## P34 - Check automation prerequisites without starting schedules

### Copy-ready prompt
Check whether <daily/valuation/ic/macro> can run under the current production policy as of <date>. List exact missing prerequisites and unconfirmed schedules. Do not enable jobs or invent alert methods. Deliver a downloadable PDF summary and link the native artifacts. Identify missing inputs without guessing.

Inputs: Committed production/schedule/source configuration, approved real data, legacy parity, provenance, required macro indicators, methods and manual-run evidence for eventual activation.

Route: CLI automation --workflow <workflow> --as-of <date> --dry-run; schedule-status; readiness.

Native outputs: Policy/readiness JSON with blocked requirements; schedule plan and alert-method status. PDF operational checklist.

Effect / limits: Currently gated/disabled. Monday time and special monitors require confirmation; >8.0 scores need approved methodology. No generic scheduler is created by a status check.

Code: automation.py; readiness.py; config/schedules.json
