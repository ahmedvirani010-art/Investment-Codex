# Phase 4 — deterministic wealth planning

This is a scenario calculator, not personal allocation advice or trade execution.
All supplied examples are synthetic; current asset balances and assumptions must be
imported explicitly. Unknown balances, FX or tax/return policies block affected
outputs. Nominal PKR, real PKR and accessible balances are separate.

```bash
uv run --locked python -m investment_workspace import-wealth --file inputs/private/wealth.json
uv run --locked python -m investment_workspace run retirement --offline --require-full-coverage
uv run --locked python -m investment_workspace run cross-asset --offline
uv run --locked python -m investment_workspace --root /tmp/wealth-demo init --offline --phase4
```

A specialized package contains exactly `sources` and `wealth`. The unified evidence
package also accepts wealth and originals. See `docs/wealth-schema.json` and the
complete `fixtures/phase4-demo.json`. The optional bundle field is backward compatible
with earlier snapshots; accepted wealth records cannot be silently omitted later.

## Assets and benefits

The wealth summary identifies whether the PSX portfolio is included. Results cover
declared assets only and do not assert that every personal asset was supplied.

Assets support outside cash, gold, VPS/PF, gratuity, optional crypto, other declared
assets and linked PSX balances. Stable economic IDs prevent duplicate balances.
Crypto requires explicit opt-in. Current balances are nonnegative; borrowing is not
assumed. `available_from` keeps locked balances invested but unavailable for spending.

A portfolio link references TOTAL, EQUITY or CASH from the accepted portfolio;
a copied balance is forbidden. TOTAL cannot coexist with another portfolio link,
and individual links cannot repeat. External balances stay outside PSX holdings and
cash totals. Linked balances require reconciled, fresh, confirmed portfolio inputs.
Native USD balances need a dated confirmed FX source and explicit PKR conversion.

Future gratuity is a sourced BENEFIT flow, not a positive current gratuity balance.
A benefit's economic claim ID cannot repeat another benefit or an existing asset
claim. Vesting unlocks an existing PF/VPS balance; it does not add the same benefit
again. CONTRIBUTION/BENEFIT flows are supplied **net PKR**, with nominal or explicitly
inflation-linked price basis, one-time/monthly frequency and dated destination.
EXPENSE flows supplement retirement spending and use the explicit withdrawal order.

## Monthly scenarios

A plan supplies month-start planning/retirement dates, horizon, base-real monthly
spending and a complete withdrawal order. Each bear/base/bull scenario supplies
inflation and, for every asset, total nominal PKR return, annual fee, tax on positive
return and effective gross-withdrawal withholding. Explicit zero means none;
null does not. These are supplied scenario conventions, not inferred tax law.
Starting balances are the dated imported amounts used as planning-start assumptions;
no unstated stub-period growth or account balance recovery is performed.

For each month:

1. Apply `(1 + annual return)^(1/12) − 1` to opening balances. Apply the annual fee
   geometrically and the explicit tax rate to positive monthly return.
2. Add the month's net contributions/benefits after returns. Inflate REAL_AT_START
   flows by the scenario's cumulative inflation index.
3. From the retirement month, inflate base-real spending to month-end nominal PKR.
   Add extra expense flows.
4. Withdraw through the explicit order, using only assets unlocked by month-end.
   Gross up withdrawals for supplied withholding. Never make a balance negative.
5. Report unmet spending/unfunded charges as funding gaps, retaining the first
   depletion date. Later benefits do not erase an earlier shortfall or imply a loan.

Real balance divides nominal balance by the cumulative inflation index. Outputs
include asset balances, accessible/locked totals, growth, fees, taxes, inflows,
spending, net withdrawals and cumulative gaps. A completely calculated scenario
may report FUNDING_SHORTFALL; that is a result, not missing data. Monetary arithmetic
uses Decimal with 48-digit intermediate precision. No stochastic simulation or
claimed probability of retirement success is produced.

## Cross-asset comparisons

Imported histories declare asset, currency, PRICE/TOTAL_RETURN basis and dated quotes.
USD histories require explicit per-date FX and a confirmed FX source; rates are not
forward filled. Missing quotes/FX block the affected performance output. Individual
holding-period returns are dimensionless; correlations use synchronized PKR returns,
a declared observation minimum and matching return bases. Known constant cash
returns yield null correlation with UNDEFINED_ZERO_VARIANCE, not invented zero
correlation or a diversification claim. Incompatible bases/insufficient samples remain
partial. Comparisons cover the supplied histories only and never rebalance holdings.

Wealth_Assets, Wealth_Flows, Retirement, Retirement_Summary, Cross_Asset and
Asset_Correlations are generated from canonical wealth records and checked for
Excel parity. Evidence, assumptions, history, cached projections and chosen-run
replay use the same local publication boundary as the investment modules.
