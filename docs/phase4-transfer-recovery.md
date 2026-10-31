# Phase 4 — durable R2 failure receipts and transfer recovery

Implements V05 from the 31 October 2026 plan verification. Phase 1–3 changes remain
intact. All code changes remain local; publication and fresh CI belong to Phase 5,
and live connectivity/private production activation remain Phase 6 requirements.

## Independent outcomes

Standalone CLI transfers, workspace storage requests and optional calculation
archives use one non-publishing transfer-result handler. Their callers publish the
receipt through the existing Git journal. Operational failures return FAILED with
transfer details; a valid storage request is no longer classified INVALID merely
because its object is inaccessible. Malformed/stale requests and conflicting IDs
remain request-validation failures.

A failed workspace transfer writes reports/storage/<request_id>.json together with
its JSON/Markdown request receipt. storage.status can read the failed record. An
optional archive failure records its own FAILED receipt and makes the request
PARTIAL, preserving module outcomes, accepted imports, calculated snapshots and
workbook outputs. A retry uses a new transfer request ID and references the already
committed analytical run; it does not repeat the accepted financial import.

Receipts preserve operation, immutable request hash, source Git head, source run,
publication authority and financial_acceptance: false. This last flag means the
R2 transfer itself does not establish financial acceptance. Accepted input changes
remain identified separately in the workspace calculation receipt.

## Progress and verification

Available per-object progress includes expected/content SHA-256, observed read hash,
known size, bytes read, advertised response size, network attempt/retry/failure
counts, status and verification state. Completed earlier objects remain visible if
a later object fails. The archive manifest has its own progress state, so verified
objects do not imply a completed archive if manifest publication fails. Overall
bytes counts verified data-object bytes, not total network traffic across retries;
per-object bytes_read/observed_sha256 reflect the last observed read attempt.

Interrupted streams record the observed partial-byte hash and close their bodies.
Checksum failures retain the observed hash without issuing a pinned artifact ID.
Partial downloads in ignored staging cannot be imported through a FAILED receipt;
all pinned import, source ownership, licensing and dataset checks remain in force.
Streaming hashes are updated incrementally, avoiding repeated whole-buffer hashing.

HEAD/existence checks now use bounded retries alongside GET and PUT. Missing objects
are recognized explicitly; other service failures use sanitized diagnostics.
The archive manifest retains its original stable object/hash/revision representation;
volatile progress counters stay in transfer receipts, preserving existing immutable
archive keys and manifests. No deletion or unrestricted synchronization is added.

## IDs and recovery

A submitted ID and its content hash remain immutable. Rerunning an existing receipt
returns the original outcome without network calls, including FAILED outcomes.
Submit a new ID for a new transfer attempt. A CLI/workspace ID collision cannot
overwrite the earlier storage receipt. A publication interruption can retry the
same still-unpublished request after the existing journal recovery checks.

If an archive failed after an accepted import, read the request result_run_id and
submit storage.push for that committed run's exact manifest paths. Confirm module
and transfer statuses separately and read the new Git receipt. Do not resubmit the
accepted import as an archive retry. For failed pulls, retry the exact approved keys
and pinned hashes under a new ID; downloading alone never accepts financial data.

## Verification

Tests in tests/test_transfer_failure_receipts.py cover inaccessible objects, partial
multi-object pulls, checksum mismatches, stream interruption, upload/read-back/
manifest failures, HEAD retries, source/run provenance, status queries, immutable-ID
conflicts, missing SDK, dry runs and publication retry. An accepted synthetic price
import survives an archive failure; a later storage-only retry leaves accepted
input bytes, canonical snapshot and workbook unchanged. Existing R2 limits, prefix,
corruption, rehydration and normal-push tests are retained.

The original V05 audit reproduction now returns independent FAILED request/transfer
outcomes and a committed storage receipt. See
[probe evidence](phase4-transfer-receipt-evidence.json). No live R2 calls or financial
production activation were used to establish these results.

Final verification: 391 tests passed and one boto3 configuration test was skipped
because the SDK is unavailable locally. All 14 new Phase 4 cases passed, along
with earlier-phase regressions. Historical replay and accepted-demo integrity and
workbook parity passed. The dependency lock validated offline using a writable
cache directory, and whitespace checks passed. No new dependencies, live R2 calls,
production activation or financial workspace changes were introduced.
