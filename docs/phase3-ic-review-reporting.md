# Phase 3 — IC review dependencies and Excel numerical fields

Implements code fixes V04 and V06 from the 31 October 2026 plan verification.
Phases 1 and 2 remain intact. Storage failure receipts and operational activation
remain separate work.

## Decision review basis

The versioned `ic-reviewed-basis-v2` hash includes the reviewed model; portfolio
holdings, prices, cash and concentration; risk limits; factor assignments and their
immutable record/source versions; timing policy and price-history versions;
candidate stop/target inputs; numerical risk/exposure/scenario results;
correlations; and the proposal's sizing result.

A change within the supplied limits can still require review: the reproduced CREDIT
to OIL factor reassignment increases portfolio OIL exposure from approximately
15.42% to 43.45%, leaves the factor cap unbreached, and changes the approval status
from CURRENT to NEEDS_REVIEW. Risk breaches also trigger review. The original user,
decision date/reason, reviewed hash, accepted decision payload and prior snapshot
remain unchanged. Transaction fulfilment stays separate, and no orders are created.

Derived decision rows expose basis_version and model_version `ic-decision-v2`.
A historical approval using the earlier hash contract is not silently migrated or
reapproved. Its old reviewed hash remains recorded and current evaluation requires
review. Use the current decision-basis command and an explicit sourced superseding
user decision to record a fresh review.

Run IDs, upstream run references, input/code hashes and schema stamps are excluded
from the material comparison. Unordered risk inputs/results are canonicalized, so
list reordering, logs, user notes and unchanged reruns do not create false review
changes. Unchanged decision rows retain their original calculation lineage.

## Workbook fields

Forward_Bridge now exports interest income, funding costs, opening/closing equity,
OCI, dividend capacity, book value per share, receivable movement/closing balance,
working-capital movement and depreciation as native numeric money cells. Sustainable
ROE is a native numeric fraction displayed as a percentage. Existing shares, PAT,
EPS, FCFE and other registered fields keep their numerical conversion and formats.
Dates and timezone-bearing timestamps retain their existing behavior.

New exports stamp core document version `investment-workspace-excel-v3`. In addition
to numerical/record parity, validation checks the new fields' actual Excel data types
and semantic formats. A numeric field converted to text or formatted as General is
rejected in a new workbook. Independent tests inspect cells and formats directly;
they do not rely only on the exporter's conversion function.

Historical workbooks are not rewritten. For earlier/unversioned workbooks, the newly
registered fields may retain their historical numeric-text representation, subject
to finite numeric value/parity checks. Wrong values remain invalid. This narrowly
scoped compatibility path preserves historical replay while new exports enforce the
new format.

## Evidence

Tests in tests/test_ic_review_reporting.py cover within-limit factor changes,
breaches, source versions, concentration, correlations, cash, other holdings,
candidate stops, unchanged/reordered inputs, historical review hashes, immutable
history and frozen snapshots, every new numerical bridge field, corrupted cell
values/formats and legacy text compatibility. The original audit probe now observes
the corrected review status and Excel types; see
[probe evidence](phase3-ic-reporting-evidence.json).

The existing historical run 20261031T085618170933Z-fbe64605 replays with integrity and
workbook parity PASS. All experiments use synthetic inputs in temporary repositories.
No accepted workspace data or frozen workbooks are modified by this implementation.
Changes remain local; publication and fresh CI belong to Phase 5.

Final verification: 377 tests passed and one boto3 configuration test was skipped
because the SDK is unavailable in the existing local environment. All 15 new
Phase 3 cases passed, along with Phase 1/2 regressions. Historical replay and the
accepted demo's integrity/workbook parity passed. The dependency lock validated
offline and whitespace checks passed. No new external dependencies were introduced.
