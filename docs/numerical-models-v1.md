# Shared scenarios, first-wave numerical forecasts and IC decisions

These are **new reference methodologies**, not recovered private equations or
certification of actual companies. Explicit version-matched approval and confirmed
source references are required. No user positions, tax law or regulatory ratios
are supplied by the application.

## Compatibility and certification

Existing snapshots and original fixtures are unchanged. Their reference adapters
remain parseable/replayable, and demo rows are labelled LEGACY_REFERENCE. Current
real-data valuation certification requires linked shared scenarios and a numerical
engine for banks, E&P and industrials. Unknown numerical drivers are nullable and
block the affected model; they are never replaced with zero. New records, source
IDs and explicit supersession are required when migrating accepted inputs.

`init --offline --completion-demo` uses a separately versioned synthetic fixture;
it does not overwrite the accepted workspace. Source/record/transaction identities
are distinct from earlier fixtures. All examples are synthetic.

## Shared assumptions

`Bundle.scenario_profiles` contains one active versioned profile per bear/base/bull
name. Revisions supersede prior IDs, retaining immutable history. A profile declares
financial basis, period, horizon, dated evidence and numerical assumptions with units.
Valuation, macro and wealth scenarios contain optional `profile` mappings; mapping
is required for current real-data certification.

A mapping identifies the profile, the actual domain basis/period/horizon, consumed
assumption bindings and their units. Paths bind only numerical fields in the typed
scenario; they are not executable expressions. Different domain bases/horizons need
an explicit rationale and confirmed sources. Wealth mappings use NOMINAL_PKR and
must cover the plan's horizon. Named overrides require matching units, rationale,
sources and consumption by a numerical binding. Rate fields must use FRACTION.
Expired/missing profiles and mismatched assumptions block affected outputs. They
never silently revise forward EPS. Review/revise the owned model and source IDs.

The synthetic fixture binds `discount_rate` directly in valuation, in macro `paths`,
and maps `annual_inflation` into the longer wealth horizon. Individual domain fields
not consumed by a profile remain explicit owned assumptions, not inferred macro effects.

## Numerical engines

`Scenario.sector_forecasts` is a typed list of Bank, E&P or Industrial forecasts.
It is mutually exclusive with the earlier generic operating forecasts. The engine
must match the security sector. Forecasts cite confirmed current financial facts
through `fact_ids` and `fact_bindings`; bound input values and units reconcile to
those facts. Shares and first forward period reconcile to the valuation model.
All rates, costs, tax charges, working-capital movements and borrowing are supplied.

- **Bank:** interest income = sum(average earning balance × supplied annual yield);
  funding cost = sum(average funding balance × supplied rate). Pretax income adds
  fees and supplied treasury income, then subtracts operating costs and credit
  charges. PAT subtracts the explicit tax charge. OCI changes equity separately,
  never PAT. Closing equity = opening equity + PAT + OCI + capital movements −
  proposed dividends. ROE uses average opening/closing equity. Dividend capacity is
  the nonnegative minimum of supplied distributable reserves, available cash, and
  eligible capital after PAT/eligible OCI/capital movements less RWA × supplied
  minimum capital ratio. Proposed dividends exceeding capacity block valuation.
  BVPS, ROE and DPS must reconcile to the valuation's corresponding inputs.
- **E&P:** revenue sums sold volume × realized price × explicit FX per commodity.
  PKR prices require unit FX. Production cannot exceed reserves plus additions;
  sales cannot exceed production plus declared inventory release. Cash operating
  costs, royalties, depletion, interest, other income and explicit tax produce PAT.
  Receivable increase = revenue − collections; collections cannot exceed opening
  receivables plus revenue. FCFE = PAT + depletion − capex − receivable increase −
  other working-capital increase + net borrowing. Other working capital must
  explicitly exclude receivables. Payout cross-checks have an enforced tolerance.
- **Industrial:** revenue = sum(volume × net price); variable cost = sum(volume ×
  variable unit cost). Fixed costs yield EBITDA, then depreciation, interest, other
  income and explicit tax yield PAT. Working-capital increase = receivables increase
  + inventory increase − payables increase. FCFE = PAT + depreciation − capex −
  working-capital increase + net borrowing. Mid-cycle assumptions require rationale.

The output exposes intermediate values in Forward_Bridge. Physical fact units
include BBL/MCF/MMBTU/TONNES/UNITS; no calorific or commodity conversion is guessed.
No tax benefits, regulatory capital ratios or expected growth are inferred.

Deferred numerical engines: OMC, refining, IPP, holding companies, auto, cement,
textile, chemical, pharma, consumer, insurance and shipping. Existing approved
reference-method support is not advertised as completed numerical forecasting for
these sectors. Real-data/source methodology validation remains separate.

## IC decision records

`Bundle.decisions` adds sourced append-only APPROVE, REJECT or DEFER records linked
to a proposal. Records include actor, timezone-bearing decision time, reason and
`reviewed_basis_hash`. `decision-basis` shows hashes for current proposals. The basis
covers model inputs, holdings/price basis, coverage, timing and risk constraints.
Changed dependencies or an expired decision produce NEEDS_REVIEW while retaining
the historical decision. Proposal actions are not automatically user decisions.

Optional transaction IDs must resolve to the same ticker and appropriate BUY/SELL
direction, occur after approval and not be linked to multiple active decisions.
Without an explicit quantity completion basis, linked transactions are reported as
LINKED_TRANSACTIONS. With a quantity, the result distinguishes PARTIALLY_EXECUTED,
EXECUTED and EXECUTION_EXCEPTION for excess quantity. Imported transactions remain
facts; an exception does not create or reverse a trade. Only approvals may link
transactions or approve quantities. Corrections use superseding decisions.

No order execution is implemented. IC_Decisions shows approval, review and
fulfilment independently from IC_Actions' proposed recommendation.
