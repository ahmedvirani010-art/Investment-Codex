# Cloudflare plugin — selected R2 target

The user selected investmentcodex. config/storage-target.json records its account,
bucket and preferred interactive transport. This is an operator selection, not a
runtime configuration file consumed by the Python adapter. Existing production and
storage-processing policies remain disabled.

A live authenticated Cloudflare-plugin test on 31 October 2026 listed the account's
buckets and objects, confirmed that a content-addressed probe key was absent,
uploaded a 133-byte synthetic JSON object, downloaded its exact bytes and verified
SHA-256. The probe contains no financial records or credentials. It remains under
approved/connectivity/ as test evidence; no object was overwritten or deleted.

- Bucket: investmentcodex
- SHA-256: 2416285e69a7aaec2869f53b2e3b54b5a73327c0d18ac53a0135cf31ed45c705
- Key: approved/connectivity/2416285e69a7aaec2869f53b2e3b54b5a73327c0d18ac53a0135cf31ed45c705.json
- Evidence: reports/storage/cloudflare-plugin-connectivity-2026-10-31.json

The access-settings check returned managed r2.dev public access enabled and no
custom domains. Access settings were not changed. The bucket is not yet verified
for private financial storage; disable public access or resolve the intended public
use before private financial files are uploaded. Repository privacy, real-source
approval and manual production checks remain separate gates.

For interactive transfers through ChatGPT, read the selected target and existing
config/storage.json prefixes/limits first. Resolve Cloudflare API endpoints through
the plugin's search tool, then use authenticated requests against this exact account
and bucket. Source pulls use sources/ or approved/; accepted-run archives use
archives/ with immutable content-addressed keys. Downloading never accepts financial
records. Preserve pinned SHA-256 checks, staging/import separation, source ownership,
licensing and dataset rules, and record durable Git receipts at publication.

The live check establishes small text-object read/write connectivity only. It does
not certify binary workbook transport, the complete import/archive workflow, or
Python/GitHub Actions connectivity. ChatGPT plugin authentication is not inherited
by GitHub Actions. The current request executor has no plugin-backed transport; it
still requires its own runner configuration and bucket-scoped credentials. Do not
mark that integration complete or enable processing based on this probe alone.

This evidence and target selection are local and await Phase 5 publication. The
connectivity receipt has financial_acceptance: false and is not an importable pull
receipt or a claim that financial records have been accepted.
