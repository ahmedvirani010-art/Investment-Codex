# Publication and recovery

1. Acquire the OS `flock` on `.runtime/writer.lock` (nonblocking). Kernel locks
   release on process death; deleting a lock file is never needed.
2. Recover an existing journal if possible; require a clean working tree and no
   pre-existing staged work. Input files should be outside the checkout or in
   ignored `inputs/private/`.
3. Read the canonical dataset through `git show HEAD:data/canonical/portfolio.json`.
   Create a unique UTC run ID, immutable input blob and diagnostic entry.
4. Validate/reconcile in memory; on calculation failure retain last-good analysis.
5. Stage the JSON output set, workbook and checksummed manifest under
   `.runtime/staging/<run_id>/`. Validate workbook parity before file replacement.
6. Back up all replaced files and durably write `.runtime/pending.json`.
7. Atomically replace each generated file, stage **only** those paths, and commit.
   **The Git commit, not an individual rename, is the publication boundary.**
8. Write the commit SHA in an external `.runtime/publications/` log to avoid a
   self-referential manifest hash. Remove the journal after commitment.

Interrupted pre-commit publication is rolled back to the previous committed
revision. Recovery checks candidate/backup bytes and HEAD before changing files;
new manual edits or an unexpected commit block automatic recovery. The staged
candidate remains for inspection/retry. A post-commit journal is recognized by
its exact committed manifest and is finalized rather than ingested twice.
Persistent logs must be included in the next published Run_Log. Recovery
recalculates the retained input bundle with current code; note imports need to
retain and reapply their explicit request (covered by tests).

The manifest hashes the complete output set except itself (no self-hash), and
records the base commit, source-code hash, policy hash, cutoff, scope, input hash,
status, and local publication status. Historical validation finds the commit
containing that run's manifest, so later mutable `latest` paths do not invalidate
an older run. Readers resolve the committed state, not interrupted filesystem
contents. `validate` checks committed integrity and workbook parity; a FAILED
analytical run can pass publication-integrity validation.

This is a local POSIX/Git transaction protocol, not distributed transactional
storage or an exchange execution system. The kernel lock requires a filesystem
with working advisory locks. External edits or competing Git commands are not
workspace writers and must be kept out of an active run. Disk exhaustion or
unwritable Git metadata can block recording diagnostics; the CLI must report
that failure, never claim a successful update.

Push is a separate explicitly invoked action, outside the local publication
boundary. Failure retains the local commit and `.runtime/push-log` record.
Non-fast-forward divergence requires inspection and regeneration from accepted
canonical data. Never force-push or merge XLSX files. No remote push occurs on
init, import, run, export, replay, validate, or recover.
