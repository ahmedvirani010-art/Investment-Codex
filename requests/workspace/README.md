# Typed workspace requests

Create a new `<request_id>.json` on the verified private default branch. Requests
are immutable, including before first processing. Use `docs/workspace-request-schema.json`
and [the operator guide](../../docs/workspace-requests.md). A receipt is published
at `reports/requests/<request_id>.json`. Missing receipt means pending or blocked,
not completion. Never put credentials or real financial requests in a public repo.
