# Historical dividend entitlement and current assessment dates

Verified entitlement now carries an immutable basis ID, original dividend identity,
ex/record dates, quantity, opening snapshot, supporting transactions, sources and
calculation version. Research retains its entitlement registry across subsequent
windows. A previously received dividend does not become unconfirmed merely because
its ex-date is outside the latest ledger window or its review period expires.

A superseding dividend with identical entitlement terms can reuse the historical
basis for later receipts. Changed terms require a new verified calculation; if the
necessary window is unavailable, CORRECTION_PENDING preserves the prior verified
result and records a gap. Earlier proof stays in history. Cash receives no extra
credit from pending receivables.

Gross and net pending are separate. Net pending uses the declared withholding rate
on remaining gross entitlement. Unknown withholding leaves net pending null;
withholding discrepancies and overpayments are reconciliation exceptions. Receipt
fees remain expenses in net cash received and never create unpaid dividend amounts.
Partial receipts and overdue balances remain visible independently.

Catalyst countdowns, 30/90-day buckets and expired-window eligibility use the
assessment date. The original market cutoff remains separately visible.

Derived analytical rows now carry code version/hash from their calculation run.
Unchanged carried rows retain their original calculation lineage. Older snapshots
are not rewritten. Date-only Excel fields use native dates; timezone-bearing
source timestamps stay ISO text. Formatting distinguishes rates, ranks, correlations,
confidence and compound blocked/stale states. Both old and new workbook formats
are checked against their canonical values.
