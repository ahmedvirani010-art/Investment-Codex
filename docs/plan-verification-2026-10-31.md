# Implementation plan verification — 31 October 2026

**Verdict: the plan is not implemented in full.** Its main features exist, but six
reproducible code gaps remain, alongside the explicitly unfulfilled deployment and
real-data acceptance gates. The previous release summary established feature
presence and passing tests; it did not establish complete satisfaction of every
requirement.

Reviewed published `work` commit `060d93280fed9222284ce6d9bf22d434af822abb`.
The six application files cited below have identical Git blob hashes locally and
at that published commit. GitHub still reports the repository as public, with
`work` as its default branch. No application code, accepted financial data,
workbooks, secrets or production settings were changed during this verification.
All new experiments used synthetic fixtures in temporary repositories and a fake
R2 client; no live storage calls were made.

[Full CI run 41186986205](https://github.com/ahmedvirani010-art/Investment-Codex/actions/runs/41186986205)
passed 255 tests, installation, dependency compatibility, build and version checks.
The existing accepted demo again passed integrity and workbook parity. These results
are valid, but the additional probes below expose cases absent from that suite.
Raw observations are in [the evidence JSON](plan-verification-evidence-2026-10-31.json).

| Plan area | Assessment |
| --- | --- |
| 1. Dividends and catalyst dates | Entitlement persistence, tax/null/pending arithmetic, receipt exceptions and assessment-date catalyst boundaries exist. Corrected entitlement bases remain incomplete: V01. |
| 2. Shared scenarios and first-wave forecasting | Versioned profiles, sourced mappings/overrides, approval gates and all three numerical engines exist. Numerical unit and multi-year period validation remain incomplete: V02–V03. |
| 3. IC decisions and reporting | Append-only decisions, transaction linkage, carried code lineage and workbook date/parity support exist. Material risk dependency invalidation and new numerical field formatting remain incomplete: V04 and V06. |
| 4. R2 operations | Pinned SDK, SigV4/auto, prefix restrictions, limits, staging, checksum verification and immutable archives exist. Failed workspace transfers do not persist the independent transfer record: V05. Live R2 configuration/connectivity remains unverified. |
| 5. Unified ChatGPT requests | Typed envelope, eleven workflows, nine operations, legacy entry points, scanner, journaled publication and temporary-remote tests exist. Transfer failure statuses remain incomplete: V05. The public synthetic helper proves a subset of routing; the guarded private production queue has not been demonstrated end to end. |
| Compatibility and rollout | Original fixtures/tests and historical snapshots are preserved; branch configuration is aligned to work and processing is disabled. Real-source/methodology/legacy-workbook/manual-production evidence and schedule confirmation remain open. |
| Verification and acceptance | The 192-test baseline is retained and 63 cases were added. Existing CI and synthetic routing passed. Six reproduced gaps require new regressions, fixes and another full CI run before full acceptance. |

## Confirmed code gaps

**V01 — P1: explicit correction of the entitlement basis reuses the old quantity.**
The plan requires explicit supersession for corrected announcements or entitlement
bases, recalculation when historical evidence exists, and review when it does not.
[dividends.py:14](../src/investment_workspace/dividends.py#L14) reuses a superseded
basis whenever ex-date, record date and DPS match, without comparing the corrected
opening snapshot or supporting transaction basis. This prevents the later
recalculation branch from running.

A temporary-repository pipeline test first accepted 100 eligible shares and PKR 250
gross entitlement. It then supplied new source IDs, corrected reconciled opening
and closing snapshots, and a superseding dividend record with unchanged dates/DPS.
The corrected evidence establishes 150 eligible shares and PKR 375 gross, but the
published result retains 100 shares, PKR 250 and the old basis. There are no ledger
reconciliation exceptions. Required closure: distinguish a receipt-only update
from a corrected entitlement basis, recalculate from available historical evidence,
and otherwise preserve the historical result with an explicit review flag.

**V02 — P1: incompatible numerical fact units can pass valuation validation.**
The plan requires physical quantities/rates and explicit conversions, with conflicting
units rejected. [sector_engines.py:27](../src/investment_workspace/sector_engines.py#L27)
checks units for a subset of input names, but omits realized commodity prices and
several monetary/rate fields. A whole-Bundle-validated E&P forecast bound
`commodities.0.realized_price` to a FinancialFact whose unit is `SHARES`.
`reference_value` accepted it and returned a valuation of 6.818181818… . Required
closure: validate dimensions, currencies and conversion bases for every supported
numerical binding, and reject unsupported/mismatched bindings.

**V03 — P1: forecast period labels do not control cash-flow discount timing.**
The plan requires reconciliation to valuation share/period bases.
[models.py:79](../src/investment_workspace/models.py#L79) checks only the first
forecast period; [models.py:101](../src/investment_workspace/models.py#L101)
discounts later cash flows by list position. With the first forecast at FY27,
changing the second forecast from FY28 to FY37 is accepted and returns exactly
the same valuation, 13.0165289256… . Both probes retained an explicit payout
cross-check tolerance, relaxed equally to isolate time validation. Required closure:
validate ordered, contiguous annual periods and the applicable horizon, or calculate
time offsets from explicit periods and reject unsupported period mappings.

**V04 — P1: a material factor-risk change can leave an IC approval CURRENT.**
The plan requires review when material decision dependencies change.
[decisions.py:14](../src/investment_workspace/decisions.py#L14) hashes summary
risk flags, but excludes factor assignments/exposure rows and other numerical risk
basis. In a complete pipeline test, a sourced superseding factor record moved the
approved bank from CREDIT to OIL. Portfolio OIL exposure rose from about 15.42%
to 43.45% while staying within the supplied limit. The decision hash did not change
and the approval stayed CURRENT. Required closure: include the material reviewed
risk inputs/results and source versions in the decision basis; test changes that
remain inside limits as well as breaches.

**V05 — P2: failed workspace R2 transfers have no independent durable transfer receipt.**
The plan requires independent module/transfer statuses, durable transfer records and
transfer-only recovery. [workspace_requests.py:147](../src/investment_workspace/workspace_requests.py#L147)
creates the storage receipt only after a successful transfer. Its outer exception
handler at [line 188](../src/investment_workspace/workspace_requests.py#L188)
clears payloads and marks the request INVALID. An inaccessible approved-prefix
object reproduced `status: INVALID`, no `transfer` status and no
`reports/storage/<request_id>.json`. A later storage.status operation therefore has
no transfer receipt to report. Required closure: persist a FAILED transfer receipt
with request/run/revision provenance and per-object progress where available, while
preserving independent request/module outcomes. Standalone CLI failure receipts
already exist; the workspace path needs equivalent behavior.

**V06 — P2: new bank bridge money/rate fields are exported as unformatted text.**
The plan requires consistent Excel money and fraction formatting.
[excel.py:22](../src/investment_workspace/excel.py#L22) omits several fields added
by the new numerical engines. In a generated Forward_Bridge sheet, interest income,
funding costs, opening/closing equity, dividend capacity and sustainable ROE have
Excel data type `s` and format `General`. PAT is correctly numeric/formatted.
Required closure: register all new numerical money, quantity and fraction fields,
including sustainable ROE as a percentage, and assert both Excel types and formats.
Current parity checks compare against the same conversion function, so they do not
expose these omissions.

## Operational acceptance still open

The repository is public and production/storage/request policies are disabled.
A fixed synthetic helper on a development branch successfully ran a simulation and
published a receipt/workbook, but it uses `local_demo=True` in a temporary seed and
does not exercise the guarded private production queue or live R2. Keep that
successful demonstration, and complete the actual private runner flow separately.

Still required: private-repository verification; GitHub Actions endpoint/bucket and
bucket-scoped credentials; live R2 connectivity and synthetic pull/push validation;
real-source imports; reconciliation of the actual legacy workbook; sourced,
version-matched methodology validation; manual production runs; and explicit Monday
macro and special-monitor timings/methodologies. Do not enable schedules to close
a documentation checklist.

The remaining engines — OMC, refining, IPP, holding companies, auto, cement,
textile, chemical, pharma, consumer, insurance and shipping — were explicitly
deferred by this plan. Their documented backlog satisfies the planned deferral;
full PRD numerical sector coverage remains open.

Reproduce the additional checks from the repository root using the existing Python
environment: `python docs/plan-verification-probes/numerical-and-transfer.py`,
`python docs/plan-verification-probes/dividend-correction.py`, and
`python docs/plan-verification-probes/ic-and-excel.py`. The scripts print synthetic
observations and write their raw JSON under `/tmp`; they leave accepted workspace
files unchanged. No fixes were made as part of this verification.
