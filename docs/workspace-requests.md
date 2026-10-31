# ChatGPT workspace requests — version 0.6

The GitHub plugin writes structured requests; GitHub Actions runs the existing
Python calculators and publishes a JSON/Markdown receipt and workbook links.
There is no new Cloudflare plugin or LLM API. Both application and R2 processing
ship disabled. Existing wealth requests and CLI commands remain supported.

## Setup

1. Verify the repository is private before real financial requests. Configure the
   actual default branch (`work` in this workspace); never force-push or merge XLSX.
2. Enable `config/workspace-requests.json` only after private-repository and synthetic
   checks. Set repository identity, approving user, auto-push authorization and the
   explicit byte/work/time limits. The wealth policy remains a compatible fallback.
3. Configure R2 independently in `config/storage.json`: enable only after verifying
   access, mark private financial storage verification, and review prefixes/limits.
   Defaults are 50 objects, 100 MiB per object, 500 MiB total, 300 seconds and three
   bounded attempts. R2 is not required for ordinary offline calculations.
4. In GitHub Actions variables set `R2_ENDPOINT_URL` to the account's HTTPS
   `*.r2.cloudflarestorage.com` endpoint and `R2_BUCKET` to the private bucket.
   In Actions secrets set `R2_ACCESS_KEY_ID` and `R2_SECRET_ACCESS_KEY` using a
   bucket-scoped token. Session environment variables are separate; they do not
   configure GitHub Actions. Never paste keys into chat or commit them.
5. The runner uses boto3 1.35.99, R2's `auto` region and Signature V4. Transfers have
   bounded retries and stream-size/deadline checks. No delete or bulk sync exists.
6. Keep analytical schedules disabled until actual source/methodology/legacy parity
   and manual real-data runs pass. R2 or wealth readiness does not imply PSX readiness.

## ChatGPT instructions

Read current committed `data/canonical/portfolio.json` and the request/package
schemas before writing a request. Resolve the current dataset ID and published run
ID. Use the assessment date explicitly. Read existing assumptions before asking
for missing inputs. Unknowns remain null; source confirmation is never invented.

Create `requests/workspace/<request_id>.json` with a globally unique ID, requested
operation, dataset, expected run, assessment date, user and actual instruction.
Never change a submitted file. Simultaneous accepted updates on the same base may
produce stale-revision diagnostics; submit a new request against the new revision.
The scanner checks both workspace and legacy wealth paths in filename order.

| User instruction | Operation | Behaviour |
| --- | --- | --- |
| Run the value screen / review portfolio / update dividends | `run` | Reuses accepted inputs; commits calculated reports, diagnostics and workbook. No input package allowed. |
| What if I change a forecast or contribution? | `simulate` | Applies an optional package in an isolated checkout. Publishes scoped snapshot/workbook; canonical records stay unchanged. |
| Save these prices/balances/assumptions and recalculate | `accept-and-run` or `import` | Explicitly imports a complete typed update with new IDs/supersession, validates it and publishes calculated data/workbook together. |
| Check these inputs first | `validate` | Publishes diagnostics only; does not accept inputs or upload archives. |
| Approve/reject/defer this IC proposal | `decision` | Imports sourced append-only decisions, with the reviewed-basis hash; never creates orders. |
| Pull an approved file from R2 | `storage.pull` | Downloads exact allowed keys into ignored staging, checks/records SHA-256, publishes a transfer receipt. Does not accept financial data. |
| Archive this run's workbook/evidence | `storage.push` | Uploads exact paths in a committed run manifest under immutable content-addressed keys and verifies read-back bytes. |
| Check transfer completion | `storage.status` | Reads the committed transfer receipt. |

Available workflows are `portfolio`, `valuation`, `update-dividends`, `timing`,
`macro`, `watchlist`, `ic`, `retirement`, `cross-asset`, `daily`, and `event`.
All use shared state and preserve owner gates. A request selecting valuation
reproduces required valuation arithmetic. Events use controlled JSON packets;
there is no automatic PDF or live-news extraction.

```json
{
  "schema_version": "1.0",
  "request_id": "screen-unique-001",
  "operation": "run",
  "dataset_id": "REPLACE_WITH_ACCEPTED_DATASET",
  "expected_run_id": "REPLACE_WITH_PUBLISHED_RUN",
  "as_of": "2026-10-31",
  "authorized_by": "REPLACE_WITH_REQUESTING_USER",
  "instruction": "Run my valuation screen and IC review",
  "workflows": ["valuation", "ic"]
}
```

The example is a template, not current evidence. A `package` can contain new sources,
market cutoff, portfolio snapshots/ledger/prices, research, integration, wealth,
financial facts, shared profiles or IC decisions. Supplied collections are complete
active views, not arbitrary field patches. A portfolio update preserves other modules.
Dataset activation remains the dedicated explicit command; requests cannot promote
demo balances into real holdings. Sources and accepted record IDs stay immutable.

Read the receipt and verify its request hash before reporting success. Report each
module status independently and link its scoped workbook/snapshot. COMPLETE means
calculable, not profitable/funded/approved. PARTIAL includes missing/stale evidence,
deferred work or a failed requested archive. A valid calculation or accepted update
is retained when its optional archive fails; retry the transfer using a new ID and
that existing run ID, without repeating the financial import.

## R2 request and import references

A storage operation embeds a `storage` object with the same request ID and the
matching `pull`/`push` operation; use `docs/storage-request-schema.json`.
A pull supplies exact keys and optional expected SHA-256 values. Allowed default
read prefixes are `sources/` and `approved/`. A file pulled without an expected hash
is explicitly unpinned and **cannot** be imported. Inspect it and submit a new pinned
pull request before acceptance.

```json
{
  "request_id": "pull-unique-001",
  "operation": "pull",
  "objects": [
    {"key": "approved/prices.json", "sha256": "REPLACE_WITH_64_HEX_SHA256"}
  ]
}
```

This object is the `storage` payload inside a workspace envelope with operation
`storage.pull`, or the standalone CLI input. Successful receipts list artifact IDs,
keys, hashes, byte sizes and pin status. To import a verified JSON package, use
`package_artifact: {"receipt_id": "pull-unique-001", "artifact_id": "...hash..."}`
in a new `import`, `accept-and-run`, or `simulate` envelope. It must validate as a
workspace package. Original documents use `package.originals` transfer references
plus the existing licensed `EvidenceDocument` descriptor; raw local paths are forbidden.
A later ephemeral runner re-downloads missing staging bytes using the pinned receipt.

Archive requests supply `run_id` and exact `paths` from that committed run's manifest.
R2 keys use `archives/<run_id>/<sha256>/<filename>`; a verified manifest is written
last. R2's ETag is not treated as SHA-256. Git receipts determine publication and
financial acceptance, not the mere existence of an R2 object. Existing Git evidence,
main workbook and historical snapshots are retained; raw source files and archive
copies in R2 supplement this boundary.

```bash
uv run --locked investment-workspace storage pull --file inputs/private/pull.json --dry-run
uv run --locked investment-workspace storage pull --file inputs/private/pull.json
uv run --locked investment-workspace storage status --request-id pull-unique-001
uv run --locked investment-workspace storage push --file inputs/private/archive.json
uv run --locked investment-workspace request --pending --local-demo
uv run --locked investment-workspace decision-basis
```

Standalone transfer receipts are committed under `reports/storage/`. They do not
alter canonical financial records. Failed or interrupted transfers cannot produce
pinned accepted artifacts. Transfer IDs and receipts are immutable; retries use new
IDs. A content-hash mismatch never overwrites accepted data. Requests cannot specify
shell commands, executable code, credential values, arbitrary URLs, or local paths.

## Publication and recovery

All writers share one lock/concurrency group. Request content and expected accepted
revision are checked before work. A private Actions publication verifies remote HEAD,
uses a normal push, and retains a recovery bundle on failure. Publication is journaled
across canonical records, workbook and receipts. `recover` rolls back an interrupted
request publication; rerun `request --pending` after recovery. No force-push, automatic
conflict merge, schedule activation or trade execution is provided.
