# Phase 2 — numerical units and annual forecast periods

Implements code fixes V02 and V03 from the 31 October plan verification. Phase 1
changes remain intact; the remaining IC, reporting, storage and operational phases
are separate work.

## Dimensions and conversions

Every numerical binding in Bank, E&P and Industrial forecasts uses a closed driver
registry. Unsupported paths, metadata/boolean paths and out-of-range list indices
are rejected. Amounts must match their bound facts after dimension validation.

| Driver | Required financial-fact unit |
| --- | --- |
| Balances, income, costs, taxes, capital, cash, working capital and borrowing | PKR |
| Share counts | SHARES |
| Annual bank yields/funding rates and capital ratios | FRACTION |
| Commodity volumes/reserves | Declared BBL, MCF, MMBTU or TONNES |
| Industrial product volumes | Declared UNITS or TONNES |
| Commodity realized prices | PKR_PER_UNIT or USD_PER_UNIT, matching price_currency |
| Commodity operating costs; industrial net prices and variable costs | PKR_PER_UNIT |
| USD-to-PKR conversion | PKR_PER_USD |
| PKR-to-PKR identity conversion | FRACTION, with the forecast rate equal to one |

Per-unit price/cost facts must supply `quantity_unit` matching the commodity or
product volume unit, for example `units: USD_PER_UNIT, quantity_unit: BBL` for USD
per barrel. An unspecified denominator cannot be certified as matching. The field
is optional for legacy parsing; absence on a bound per-unit fact blocks current
numerical validation. Non-per-unit facts must omit the denominator.

Revenue still uses the explicitly supplied sold volume × realized price × FX.
For example, USD 5 per BBL × 2 PKR/USD equals PKR 10 per BBL. No FX rate is fetched,
no percentage/scaling convention is inferred, and no barrel/tonne or MCF/MMBTU
conversion is guessed. Other currencies, scaled monetary units and incompatible
physical bases must be explicitly normalized in sourced import facts before use;
the engine rejects them. Fact dates must include the assessment date, and existing
source, accounting-basis, share-count and payout gates remain enforced.

## Period validation

Typed sector forecasts accept contiguous annual grids such as FY27/FY28 or
FY2027/FY2028 and CY2027/CY2028. The prefix must match forward_basis; the first
label must equal forward_period. Year widths must be consistent, and subsequent
years must increase by exactly one. Gaps, reverse ordering, mixed FY/CY, mixed
short/long years and unrecognized labels are rejected. Use four-digit years across
a century boundary; FY99/FY00 is deliberately ambiguous and rejected.

Validated annual flows are discounted at years 1, 2, …; terminal value is discounted
at the last projection year. The investment holding horizon remains independent of
the annual DCF projection length. This contract does not claim exact calendar-date
or fractional-year discounting. NTM supports a single forecast labelled NTM;
multi-year NTM requires a future explicit dated mapping and is currently rejected.
The stricter grid contract applies to typed sector forecasts. Historical imported
reference models and snapshots remain parseable and replayable.

## Verification

Tests in tests/test_forecast_contracts.py cover every numerical driver with an
incompatible currency, canonical driver bindings, physical price denominators,
explicit FX, unsupported bindings, stale/future evidence, share-basis mismatches,
NTM restrictions and annual period ordering. Independent fixtures retain PAT/EPS
and FCFE values and compare a two-year DCF against hand-calculated discounting.
An integration test confirms a price expressed in SHARES blocks certification.

No original fixtures, accepted records or historical workbook snapshots are rewritten.
The additive absent quantity_unit field normalizes out of legacy identity comparisons.
Public FinancialFact schemas include the denominator and PKR_PER_USD unit. Software
validation is separate from source/methodology approval and production activation.

Verification result: 362 tests passed and one boto3 configuration test was skipped
because the SDK is unavailable locally. All 98 new Phase 2 cases passed, covering
54 numeric driver paths. Both original audit reproductions are now blocked as
expected; the contiguous FY27/FY28 control retains its hand-calculated value.
See [the probe evidence](phase2-forecast-validation-evidence.json). Historical run
20261031T085618170933Z-fbe64605 replayed with integrity and workbook parity PASS.
The five FinancialFact schemas match the live contract; the dependency lock and
whitespace checks passed. Changes remain local; fresh installation, CI and
publication belong to Phase 5.
