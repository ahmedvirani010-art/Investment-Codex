# Phase 5 — release verification and publication

This release closes the six code findings from the plan verification at published
revision 060d93280fed9222284ce6d9bf22d434af822abb. That original dated audit remains
preserved. The phase documents and regression tests provide the closure evidence.

| Finding | Fix and evidence |
| --- | --- |
| V01 | Corrected dividend basis recalculation, pending proof retention and receipt-only updates; tests/test_dividend_corrections.py; phase1-dividend-corrections.md |
| V02 | Closed driver dimension registry, physical price denominators and explicit FX units; tests/test_forecast_contracts.py; phase2-forecast-validation.md |
| V03 | Ordered contiguous annual forecast periods, explicit NTM restriction and hand-calculated discounting; tests/test_forecast_contracts.py |
| V04 | Versioned reviewed basis including factor assignments, numerical portfolio risk and sizing; tests/test_ic_review_reporting.py; phase3-ic-review-reporting.md |
| V05 | Durable failed transfer receipts, independent outcomes and transfer-only recovery; tests/test_transfer_failure_receipts.py; phase4-transfer-recovery.md |
| V06 | Native numerical bridge money/rate cells, semantic formats and historical workbook compatibility; tests/test_ic_review_reporting.py |

The full local suite passed 391 tests with one SDK-only skip. The release inventory
contains 392 tests, retaining the original 192. It includes all eleven module
requests, all nine request operations published to temporary Git remotes, numerical
hand fixtures, financial correction/review invariants, failed-transfer recovery,
normal push/divergence, and historical workbook integrity/parity. No original fixture
or frozen historical workbook was rewritten.

The existing Offline baseline workflow verifies clean locked installation,
dependency compatibility, wheel/source builds, installed package version and the
full suite including the installed boto3 configuration test. Publication is accepted
only after that workflow passes on the published work revision. The repository's
[Actions record](https://github.com/ahmedvirani010-art/Investment-Codex/actions)
is the durable CI evidence; the operator reports the exact successful run at release.
No benchmark speedup is inferred; the previous dated synthetic benchmark remains
an observation with its original workload and limitations.

Publication uses GitHub Git-data operations with an expected-head check and normal
fast-forward because native Git transport is unavailable in this environment.
Remote-only synthetic request proof is preserved by overlaying changed paths onto
the inspected remote tree. Local Git commit IDs and imported GitHub commit IDs can
differ; imported source commits retain local provenance. No force-push or workbook
merge is used. Source and regenerated accepted-demo exports are locally committed,
and generated records/workbook are published together.

Phase 1–4 reports described local implementation at the time they were written;
this Phase 5 publication record supersedes their pending-publication status once
CI passes. The first-wave release still does not claim numerical engines for the
other twelve sectors, real-source certification or complete real legacy parity.

Cloudflare plugin authentication and a 133-byte synthetic text-object round trip
were verified separately for investmentcodex with SHA-256 PASS. The user chose to
leave public r2.dev access enabled. No private financial upload or processing is
activated by this release. Binary plugin transport, automated runner credentials
and the guarded private production flow remain unverified Phase 6 work. Production,
storage and request policies and analytical schedules remain disabled. Monday macro
and special-monitor timings/methodologies still require explicit confirmation.
