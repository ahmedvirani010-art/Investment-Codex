# Phase 1 implementation — dividend basis corrections

Closes code finding V01 in the 31 October 2026 plan verification. The original
audit and evidence remain preserved; findings V02–V06 belong to later phases.

A superseding dividend with unchanged dates and DPS no longer automatically reuses
its predecessor's basis. The calculator compares the opening snapshot and settled
quantity-affecting transactions, recalculates verified changed evidence, and retains
both immutable basis records. Receipt-only updates carry unchanged historical proof.
Explicit basis corrections with unavailable evidence preserve the verified result
under CORRECTION_PENDING, including subsequent evaluations of the same pending record.

The optional revision_kind contract distinguishes ENTITLEMENT_BASIS and RECEIPT_UPDATE.
Absent fields normalize out of legacy identity comparisons; dated fixtures, accepted
source IDs and historical workbooks are not rewritten. Public input, evidence,
research and workspace schemas include the new field.

Regression coverage is in tests/test_dividend_corrections.py. It covers corrected
opening quantities, corrected settlement evidence, unchanged basis IDs, unavailable
windows, unverified/unreconciled evidence, repeated pending corrections, later
receipts after review/window expiry, and contradictory receipt updates. The original
audit reproduction now returns 150 eligible shares and PKR 375 gross entitlement,
matching corrected evidence, with no reconciliation exceptions. Partial receipt
reconciliation leaves PKR 100 net pending and preserves brokerage cash.

All new pipeline experiments use isolated synthetic repositories. Live processing,
R2 and schedule activation remain governed by the existing disabled policies.

Verification: 264 tests passed and one boto3 configuration test was skipped because
boto3 is absent from the local environment. The ten new dividend correction tests
all passed. Fresh locked installation was attempted but the managed network could
not reach PyPI; the lock check passed offline. Historical run
20261031T085618170933Z-fbe64605 replayed successfully with integrity and workbook
parity PASS. The five public schemas containing Dividend match the new optional
field contract. Git diff whitespace checks passed. Changes are local; publication
and fresh CI remain part of Phase 5.
