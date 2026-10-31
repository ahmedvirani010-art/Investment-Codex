"""Strict input contracts. Monetary arithmetic uses Decimal, not binary floats."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

NonNegative = Annotated[Decimal, Field(ge=0, allow_inf_nan=False, max_digits=24, decimal_places=8)]
Positive = Annotated[Decimal, Field(gt=0, allow_inf_nan=False, max_digits=24, decimal_places=8)]
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]+$", max_length=100)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Source(StrictModel):
    source_id: Identifier
    title: str = Field(min_length=1)
    publisher: str = Field(min_length=1)
    effective_date: date
    locator: str = Field(min_length=1)
    evidence_label: Literal["CONFIRMED", "ESTIMATE", "ASSUMPTION", "UNVERIFIED"]


class Security(StrictModel):
    ticker: Identifier
    sector: str
    currency: Literal["PKR"] = "PKR"


class Position(StrictModel):
    ticker: Identifier
    quantity: NonNegative
    cost: NonNegative

    @model_validator(mode="after")
    def empty_position(self):
        if self.quantity == 0 and self.cost != 0:
            raise ValueError("zero quantity must have zero total cost")
        return self


class Snapshot(StrictModel):
    timestamp: datetime
    source_id: Identifier
    cash: NonNegative
    positions: list[Position]

    @model_validator(mode="after")
    def unique_and_dated(self):
        if self.timestamp.tzinfo is None:
            raise ValueError("snapshot timestamp must have a timezone")
        if len({p.ticker for p in self.positions}) != len(self.positions):
            raise ValueError("duplicate snapshot ticker")
        return self


class Transaction(StrictModel):
    transaction_id: Identifier
    timestamp: datetime
    settlement_date: date
    kind: Literal["BUY", "SELL", "DEPOSIT", "WITHDRAWAL", "DIVIDEND", "SPLIT"]
    ticker: Identifier | None = None
    quantity: NonNegative = Decimal(0)
    price: NonNegative = Decimal(0)
    amount: NonNegative = Decimal(0)
    fees: NonNegative = Decimal(0)
    taxes: NonNegative = Decimal(0)
    ratio: Positive | None = None
    source_id: Identifier

    @model_validator(mode="after")
    def semantics(self):
        if self.timestamp.tzinfo is None:
            raise ValueError("transaction timestamp must have a timezone")
        if self.settlement_date < self.timestamp.date():
            raise ValueError("settlement cannot precede transaction")
        if self.kind in {"BUY", "SELL"}:
            if not self.ticker or self.quantity <= 0 or self.price <= 0:
                raise ValueError("trade requires ticker, positive quantity and price")
            if self.amount != 0 or self.ratio is not None:
                raise ValueError("trade amount is computed; ratio is only for SPLIT")
        elif self.kind == "SPLIT":
            if not self.ticker or self.ratio is None:
                raise ValueError("split requires ticker and positive ratio")
            if any((self.quantity, self.price, self.amount, self.fees, self.taxes)):
                raise ValueError("split cannot carry cash or trade fields")
        else:
            if self.amount <= 0 or self.quantity or self.price or self.ratio is not None:
                raise ValueError("cash transaction requires amount and no trade fields")
            if self.kind == "DIVIDEND" and not self.ticker:
                raise ValueError("cash dividend receipt requires a ticker")
            if self.kind in {"DEPOSIT", "WITHDRAWAL"} and self.ticker:
                raise ValueError("deposit/withdrawal cannot name a security")
            if self.kind in {"DEPOSIT", "DIVIDEND"} and self.amount < self.fees + self.taxes:
                raise ValueError("net cash receipt cannot be negative")
        return self


class Price(StrictModel):
    ticker: Identifier
    session_date: date
    close: Positive | None
    source_id: Identifier
    adjustment_basis: Literal["CURRENT_SHARES"] = "CURRENT_SHARES"


class Policy(StrictModel):
    price_max_age_days: int = Field(default=3, ge=0)
    holdings_max_age_days: int = Field(default=3, ge=0)
    cash_tolerance: NonNegative = Decimal("0.01")
    cost_tolerance: NonNegative = Decimal("0.01")
    quantity_tolerance: NonNegative = Decimal("0.000001")
    max_position_weight: Annotated[Decimal, Field(gt=0, le=1)] | None = None
    # No default personal risk limits. Even reconciled data cannot enable sizing.


class Bundle(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    mode: Literal["DEMO", "USER_IMPORT"]
    market_cutoff: date
    sources: list[Source]
    securities: list[Security]
    opening: Snapshot
    closing: Snapshot
    transactions: list[Transaction]
    prices: list[Price]
    policy: Policy = Field(default_factory=Policy)
    research: "Research | None" = None

    @model_validator(mode="after")
    def links_and_dates(self):
        source_ids = [s.source_id for s in self.sources]
        tickers = [s.ticker for s in self.securities]
        if len(source_ids) != len(set(source_ids)) or len(tickers) != len(set(tickers)):
            raise ValueError("source and security IDs must be unique")
        referenced = {self.opening.source_id, self.closing.source_id}
        referenced.update(t.source_id for t in self.transactions)
        referenced.update(p.source_id for p in self.prices)
        if not referenced <= set(source_ids):
            raise ValueError("input references an unregistered source")
        used = {p.ticker for p in self.opening.positions + self.closing.positions}
        used.update(t.ticker for t in self.transactions if t.ticker)
        used.update(p.ticker for p in self.prices)
        if not used <= set(tickers):
            raise ValueError("input references an unregistered security")
        if self.opening.timestamp > self.closing.timestamp:
            raise ValueError("opening must precede closing snapshot")
        if self.closing.timestamp.date() > self.market_cutoff:
            raise ValueError("snapshot cannot be after market cutoff")
        if any(not self.opening.timestamp < t.timestamp <= self.closing.timestamp for t in self.transactions):
            raise ValueError("ledger must cover (opening, closing] only")
        if any(t.settlement_date > self.closing.timestamp.date() for t in self.transactions):
            raise ValueError("Phase 1 settled ledger cannot contain unsettled trades")
        if any(p.session_date > self.market_cutoff for p in self.prices):
            raise ValueError("future price relative to cutoff")
        if len({p.ticker for p in self.prices}) != len(self.prices):
            raise ValueError("one current price per security required")
        if any(s.effective_date > self.market_cutoff for s in self.sources):
            raise ValueError("source effective date after cutoff")
        return self


class NoteOverride(StrictModel):
    override_id: Identifier
    ticker: Identifier
    field: Literal["note"]
    value: str = Field(min_length=1, max_length=4000)
    author: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    effective_date: date
    expires_at: date | None = None
    confirmed: Literal[True]
    supersedes: Identifier | None = None

    @model_validator(mode="after")
    def expiry(self):
        if self.expires_at and self.expires_at < self.effective_date:
            raise ValueError("override expiry precedes effective date")
        if self.supersedes == self.override_id:
            raise ValueError("override cannot supersede itself")
        return self


# Phase 2 imports are explicit evidence packets, never inferred market data.
Signed = Annotated[Decimal, Field(allow_inf_nan=False, max_digits=24, decimal_places=8)]
Fraction = Annotated[Decimal, Field(ge=0, lt=1, allow_inf_nan=False)]


class ResearchRecord(StrictModel):
    record_id: Identifier
    ticker: Identifier
    effective_date: date
    valid_until: date
    source_ids: list[Identifier] = Field(min_length=1)
    supersedes: Identifier | None = None

    @model_validator(mode="after")
    def validity(self):
        if self.valid_until < self.effective_date or self.supersedes == self.record_id:
            raise ValueError("invalid research validity or supersession")
        return self


class Adjustment(StrictModel):
    description: str = Field(min_length=1)
    pretax_amount: Signed
    tax_effect: Signed
    rationale: str = Field(min_length=1)
    recurring_test: Literal["GENUINE_ONE_OFF"]
    source_id: Identifier
    locator: str = Field(min_length=1)


class Earnings(ResearchRecord):
    period_start: date
    period_end: date
    period_label: str = Field(min_length=1)
    basis: Literal["STANDALONE", "CONSOLIDATED"]
    reported_pat: Signed
    weighted_average_shares: Positive
    reported_eps: Signed
    share_basis_date: date
    adjustments: list[Adjustment] = Field(default_factory=list)
    quality: Literal["A", "B", "C", "D", "UNASSESSED"] = "UNASSESSED"
    quality_rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def bridge(self):
        if not self.period_start <= self.period_end <= self.effective_date:
            raise ValueError("invalid earnings period")
        if self.share_basis_date > self.effective_date:
            raise ValueError("future share basis")
        if abs(self.reported_pat / self.weighted_average_shares - self.reported_eps) > Decimal("0.000001"):
            raise ValueError("reported PAT / shares does not reconcile to EPS")
        return self


class Scenario(StrictModel):
    scenario_id: Identifier
    name: Literal["bear", "base", "bull"]
    forward_eps: Signed
    sustainable_dps: NonNegative
    exit_price: NonNegative
    horizon_dividends: NonNegative
    exit_basis: Literal["EX_DISTRIBUTION"]
    # Import modeled horizon dividends explicitly; never add pending receipts here.
    dividends_rationale: str = Field(min_length=1)
    discount_rate: Positive
    terminal_growth: Signed
    book_value_per_share: Positive | None = None
    sustainable_roe: Signed | None = None
    fcfe: list[Signed] = Field(default_factory=list)
    shares: Positive | None = None
    terminal_value: NonNegative | None = None
    payout_crosscheck: NonNegative | None = None
    drivers: dict[str, str] = Field(min_length=1)

    @model_validator(mode="after")
    def rates(self):
        if self.terminal_growth >= self.discount_rate:
            raise ValueError("terminal growth must be below discount rate")
        return self


class ValuationModel(ResearchRecord):
    earnings_id: Identifier
    method: Literal["BANK_JUSTIFIED_PB", "FCFE_DCF", "UNSUPPORTED"]
    model_version: str = Field(min_length=1)
    certification: Literal["PROVISIONAL", "VALIDATED"] = "PROVISIONAL"
    origin: Literal["NEW_EXPLICIT_MODEL", "LEGACY_RECOVERED"]
    methodology_rationale: str = Field(min_length=1)
    legacy_column_map: dict[str, str] = Field(default_factory=dict)
    historical_outputs: dict[str, NonNegative] = Field(default_factory=dict)
    reproduction_tolerance: NonNegative = Decimal("0.000001")
    forward_period: str = Field(min_length=1)
    forward_basis: Literal["FY", "CY", "NTM"]
    accounting_basis: Literal["STANDALONE", "CONSOLIDATED"]
    share_basis_date: date
    horizon_years: Positive
    sovereign_benchmark: NonNegative
    benchmark_date: date
    equity_risk_premium: NonNegative
    discount_rate_rationale: str = Field(min_length=1)
    margin_of_safety: Fraction
    timing_gate: Literal["PASSED", "BLOCKED", "UNKNOWN"] = "UNKNOWN"
    risk_gate: Literal["PASSED", "BLOCKED", "UNKNOWN"] = "UNKNOWN"
    event_checked_through: date | None = None
    scenarios: list[Scenario]
    dividend_tax_rate: Fraction | None = None
    capital_gains_tax_rate: Fraction | None = None
    entry_cost_rate: Fraction | None = None
    exit_cost_rate: Fraction | None = None
    liabilities_per_share: NonNegative | None = None

    @model_validator(mode="after")
    def scenario_set(self):
        if sorted(s.name for s in self.scenarios) != ["base", "bear", "bull"]:
            raise ValueError("exactly one bear/base/bull scenario required")
        if len({s.scenario_id for s in self.scenarios}) != 3:
            raise ValueError("scenario IDs must be unique")
        if self.benchmark_date > self.effective_date or self.share_basis_date > self.effective_date:
            raise ValueError("future benchmark/share basis")
        return self


class Dividend(ResearchRecord):
    announcement_date: date
    dividend_type: Literal["CASH"] = "CASH"
    dps: NonNegative
    ex_date: date | None = None
    record_date: date | None = None
    book_closure_start: date | None = None
    book_closure_end: date | None = None
    payment_date: date | None = None
    dates_verified: bool = False
    settlement_rule: Literal["SETTLED_BEFORE_EX"] | None = None
    tax_rate: Fraction | None = None
    receipt_transaction_ids: list[Identifier] = Field(default_factory=list)

    @model_validator(mode="after")
    def dates(self):
        if self.announcement_date > self.effective_date:
            raise ValueError("future announcement")
        if self.ex_date and self.ex_date < self.announcement_date:
            raise ValueError("ex date precedes announcement")
        if self.ex_date and self.record_date and self.record_date < self.ex_date:
            raise ValueError("record date precedes ex date")
        if self.book_closure_start and self.book_closure_end and self.book_closure_end < self.book_closure_start:
            raise ValueError("invalid book closure")
        if self.ex_date and self.payment_date and self.payment_date < self.ex_date:
            raise ValueError("payment precedes ex date")
        return self


class LegacyResolution(ResearchRecord):
    issue: Literal["POL_DPS", "BAHL_EPS", "OGDC_ENTITLEMENT", "INDU_CASH_INCOME", "AKBL_TREASURY_OCI"]
    rationale: str = Field(min_length=1)


class Research(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    universe_date: date
    universe_valid_until: date
    universe_source_ids: list[Identifier] = Field(min_length=1)
    required_tickers: list[Identifier]
    universe_basis: str = Field(min_length=1)
    # A supplied list is not automatically a verified KSE-100 membership snapshot.
    full_universe_verified: bool = False
    earnings: list[Earnings] = Field(default_factory=list)
    models: list[ValuationModel] = Field(default_factory=list)
    dividends: list[Dividend] = Field(default_factory=list)
    resolutions: list[LegacyResolution] = Field(default_factory=list)
    exclusions: dict[Identifier, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def unique(self):
        if self.universe_valid_until < self.universe_date:
            raise ValueError("invalid universe validity window")
        records = self.earnings + self.models + self.dividends + self.resolutions
        if len({r.record_id for r in records}) != len(records):
            raise ValueError("duplicate research record ID")
        for group in (self.earnings, self.models):
            if len({r.ticker for r in group}) != len(group):
                raise ValueError("one active earnings/model per ticker required")
        if len(set(self.required_tickers)) != len(self.required_tickers):
            raise ValueError("duplicate required ticker")
        return self


# Resolve the optional forward annotation after all Phase 2 contracts exist.
Bundle.model_rebuild()
