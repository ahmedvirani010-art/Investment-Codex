# Workspace instructions

- Use the existing checkout. Cloud tasks are already isolated; do not create a
  Git worktree unless the user explicitly requests one.
- Read README.md, docs/PRD.md, and docs/migration.md before changing scope.
- Install with `uv sync --locked`; run `uv run --locked pytest`.
- Keep Decimal arithmetic, null unknowns, evidence ownership, and historical
  decision lineage. Fixtures are synthetic and cannot become real holdings.
- Do not invent source APIs, current holdings, prices, tax assumptions, risk
  limits, recovered valuation equations, or measured AI usage.
- No trade execution or automatic remote push. Explicit push authorization is
  required; never force-push or merge binary workbooks.
- Accepted data and workbooks are locally committed together. Read committed
  snapshots, not working-tree files during interrupted publication.
- Preserve user-authored notes and files. Numerical workbook overrides are not
  supported in Phase 1. Accepted transaction/source IDs are immutable.
- Do not start services or schedules: Phase 1 is an offline CLI with no daemon.
- Git metadata and runtime journals are not application source. Do not commit
  `.runtime`, credentials, or broker account identifiers.

## ChatGPT wealth requests

- For Phase 4 requests made through ChatGPT/GitHub, read `docs/chatgpt-wealth.md`.
- Verify repository privacy before creating financial request files. The wealth
  request policy is independent of PSX legacy parity and remains disabled by default.
- What-if instructions use `simulate`; persist financial inputs only when the user
  explicitly requests an update, with new record/source IDs and explicit supersession.
- Read the committed receipt before reporting completion; show both module statuses
  and preserve missing assumptions as unknown. Never modify submitted request files.

## Unified requests, R2 and numerical contracts

- Read `docs/workspace-requests.md` for all-module GitHub requests and R2 operations.
- R2 pulls stage inputs; only an explicit import of a pinned validated artifact may
  update accepted records. Never place keys or arbitrary local paths in requests.
- Read `docs/numerical-models-v1.md` for scenario mappings, provisional numerical
  methodologies and append-only user IC decisions. Never infer missing tax, FX,
  physical-unit conversion or capital assumptions.
- Keep the remaining-sector numerical backlog and private-production/data gates
  visible. Source code deployment does not certify real models or activate schedules.

## Selected Cloudflare plugin target

- For interactive Cloudflare/R2 work, read `docs/cloudflare-r2-plugin.md` and
  `config/storage-target.json`. The selected bucket is `investmentcodex`.
- Keep plugin connectivity evidence separate from Python/Actions activation.
  The live text-object probe passed, but managed r2.dev public access was enabled
  at verification; resolve privacy before private financial uploads.
