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
    url: str | None = Field(default=None, pattern=r"^https?://")
    published_at: datetime | None = None
    accessed_at: datetime | None = None
    document_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    coverage_through: date | None = None
    owner: str | None = None

    @model_validator(mode="after")
    def source_times(self):
        if any(t is not None and t.tzinfo is None for t in (self.published_at, self.accessed_at)):
            raise ValueError("source timestamps need timezone offsets")
        if self.published_at and self.accessed_at and self.published_at > self.accessed_at:
            raise ValueError("publication cannot follow access")
        return self


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
    integration: "Integration | None" = None
    dataset_id: Identifier | None = None
    financials: list["FinancialFact"] = Field(default_factory=list)
    migrations: list["WorkbookMigration"] = Field(default_factory=list)
    wealth: "Wealth | None" = None
    documents: list["EvidenceDocument"] = Field(default_factory=list)
    scenario_profiles: list["ScenarioProfile"] = Field(default_factory=list)
    decisions: list["ICDecision"] = Field(default_factory=list)

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
        if self.research and self.integration:
            research_ids = {r.record_id for group in (self.research.earnings, self.research.models, self.research.dividends, self.research.resolutions) for r in group}
            integrated_ids = {r.record_id for name in type(self.integration).model_fields if name != "schema_version"
                              for r in (getattr(self.integration, name) if isinstance(getattr(self.integration, name), list) else [getattr(self.integration, name)]) if r}
            if research_ids & integrated_ids:
                raise ValueError("record IDs cannot be reused across research and integration owners")
        if len({p.name for p in self.scenario_profiles})!=len(self.scenario_profiles):
            raise ValueError('one active shared profile per scenario name; use supersession for revisions')
        fact_groups={}
        for fact in self.financials:
            key=(fact.ticker,fact.period_start,fact.period_end,fact.accounting_basis,fact.line_item,fact.units)
            if key in fact_groups and fact_groups[key]!=fact.amount:
                raise ValueError('conflicting same-period financial facts require an explicit owned correction')
            fact_groups[key]=fact.amount
        owned=list(self.financials)+list(self.migrations)+list(self.scenario_profiles)+list(self.decisions)
        if self.research:
            owned += self.research.earnings+self.research.models+self.research.dividends+self.research.resolutions
        if self.integration:
            owned += [r for name in type(self.integration).model_fields if name!='schema_version' for r in
                      (getattr(self.integration,name) if isinstance(getattr(self.integration,name),list) else [getattr(self.integration,name)]) if r]
        if self.wealth:
            owned += [r for name in ('assets','flows','scenarios','plans','histories') for r in getattr(self.wealth,name)]
        if len({r.record_id for r in owned})!=len(owned):
            raise ValueError('record IDs must be unique across all owners')
        if len({(d.source_id,d.sha256,d.role) for d in self.documents})!=len(self.documents):
            raise ValueError('duplicate evidence document')
        if any(s.coverage_through and s.coverage_through>self.market_cutoff for s in self.sources):
            raise ValueError('observed source coverage cannot extend beyond input cutoff')
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
    crosscheck_tolerance: Fraction | None = None
    contract_years: int | None = Field(default=None, ge=1)
    components: list["SOTPComponent"] = Field(default_factory=list)
    parent_net_debt: Signed | None = None
    parent_liabilities: NonNegative | None = None
    minority_interests: NonNegative | None = None
    normalized_operating_eps: Signed | None = None
    earnings_multiple: Positive | None = None
    surplus_cash_per_share: NonNegative | None = None
    cash_income_excluded: bool | None = None
    profile: "ScenarioLink | None" = None
    sector_forecasts: list["SectorForecast"] = Field(default_factory=list)
    operating_forecasts: list["OperatingForecast"] = Field(default_factory=list)
    drivers: dict[str, str] = Field(min_length=1)

    @model_validator(mode="after")
    def rates(self):
        if self.terminal_growth >= self.discount_rate:
            raise ValueError("terminal growth must be below discount rate")
        return self


class ValuationModel(ResearchRecord):
    earnings_id: Identifier
    method: Literal["BANK_JUSTIFIED_PB", "FCFE_DCF", "FINITE_LIFE_FCFE", "SOTP", "ROE_BOOK", "NORMALIZED_MULTIPLE", "UNSUPPORTED"]
    model_version: str = Field(min_length=1)
    certification: Literal["PROVISIONAL", "VALIDATED"] = "PROVISIONAL"
    origin: Literal["NEW_EXPLICIT_MODEL", "LEGACY_RECOVERED"]
    methodology_rationale: str = Field(min_length=1)
    approval: "ModelApproval | None" = None
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
    covered_event_ids: list[Identifier] = Field(default_factory=list)
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
        if self.event_checked_through and self.event_checked_through > self.effective_date:
            raise ValueError("future event coverage")
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





# Phase 3 records share the append-only identity and evidence contract.
class MarketBar(StrictModel):
    session_date: date
    open: Positive
    high: Positive
    low: Positive
    close: Positive
    volume: NonNegative
    traded_value: NonNegative | None = None

    @model_validator(mode="after")
    def prices(self):
        if not self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high:
            raise ValueError("inconsistent OHLC range")
        return self


class CorporateAction(StrictModel):
    action_id: Identifier
    session_date: date
    kind: Literal["SPLIT", "BONUS"]
    ratio: Positive
    source_id: Identifier


class MarketHistory(ResearchRecord):
    role: Literal["SECURITY", "BENCHMARK"] = "SECURITY"
    price_basis: Literal["RAW"] = "RAW"
    action_coverage_through: date
    actions: list[CorporateAction] = Field(default_factory=list)
    bars: list[MarketBar] = Field(min_length=1)

    @model_validator(mode="after")
    def ordered(self):
        dates = [b.session_date for b in self.bars]
        if dates[-1] > self.effective_date:
            raise ValueError("history extends beyond its effective date")
        if dates != sorted(set(dates)):
            raise ValueError("history sessions must be sorted and unique")
        if len({a.action_id for a in self.actions}) != len(self.actions):
            raise ValueError("duplicate corporate action ID")
        return self


class SessionCalendar(ResearchRecord):
    sessions: list[date] = Field(min_length=1)
    exchange: str = Field(min_length=1)

    @model_validator(mode="after")
    def ordered(self):
        if self.sessions[-1] > self.effective_date:
            raise ValueError("calendar contains sessions after its effective date")
        if self.sessions != sorted(set(self.sessions)):
            raise ValueError("calendar must contain sorted unique completed sessions")
        return self


class Membership(ResearchRecord):
    constituents: list[Identifier] = Field(min_length=1)

    @model_validator(mode="after")
    def unique(self):
        if len(set(self.constituents)) != len(self.constituents):
            raise ValueError("duplicate universe constituent")
        return self


class TimingPolicy(ResearchRecord):
    benchmark: Identifier
    relative_lookback: int = Field(ge=2)
    momentum_lag: int = Field(ge=1)
    short_window: int = Field(ge=2)
    long_window: int = Field(ge=3)
    slope_sessions: int = Field(ge=1)
    flat_slope: Fraction
    liquidity_window: int = Field(ge=2)
    min_average_traded_value: NonNegative
    min_rank_universe: int = Field(ge=2)
    max_extension: Fraction
    breakout_window: int = Field(ge=2)
    reversion_window: int = Field(ge=2)
    oversold_z: Signed
    overbought_z: Signed
    calibration_status: Literal["PROVISIONAL", "VALIDATED"] = "PROVISIONAL"
    calibration_rationale: str = Field(min_length=1)
    backtest_start: date | None = None
    backtest_cost_rate: Fraction | None = None

    @model_validator(mode="after")
    def parameters(self):
        if self.short_window >= self.long_window or self.oversold_z >= 0 or self.overbought_z <= 0:
            raise ValueError("invalid trend/reversion parameters")
        return self


class MacroObservation(ResearchRecord):
    domain: Literal["PAKISTAN", "GLOBAL"]
    indicator: str = Field(min_length=1)
    evidence_kind: Literal["FACT", "INTERPRETATION", "SCENARIO"]
    value: Signed | None = None
    unit: str = Field(min_length=1)
    narrative: str = Field(min_length=1)
    regime: str | None = None


class MacroScenario(ResearchRecord):
    profile: "ScenarioLink | None" = None
    name: Literal["bear", "base", "bull"]
    probability: Fraction | None = None
    paths: dict[str, str] = Field(min_length=1)
    rationale: str = Field(min_length=1)


class NewsEvent(ResearchRecord):
    headline: str = Field(min_length=1)
    affected_tickers: list[Identifier] = Field(min_length=1)
    transmission: str = Field(min_length=1)
    urgency: Literal["IMMEDIATE", "WATCH", "NOISE"]
    requires_model_revision: bool = False
    eps_delta: Signed | None = None
    eps_period: str | None = None
    eps_calculation: str | None = None

    @model_validator(mode="after")
    def eps_basis(self):
        if self.eps_delta is not None and (not self.eps_period or not self.eps_calculation):
            raise ValueError("numerical EPS impact requires period and calculation evidence")
        if len(set(self.affected_tickers)) != len(self.affected_tickers):
            raise ValueError("duplicate event ticker")
        return self


class RiskLimits(ResearchRecord):
    user_confirmed: bool = False
    max_position_weight: Fraction
    max_sector_weight: Fraction
    max_factor_weight: Fraction
    minimum_cash_weight: Fraction
    per_trade_risk_budget: Fraction
    max_daily_participation: Fraction
    correlation_lookback: int = Field(ge=3)
    min_correlation_observations: int = Field(ge=3)

    @model_validator(mode="after")
    def positive_limits(self):
        if min(self.max_position_weight, self.max_sector_weight, self.max_factor_weight,
               self.per_trade_risk_budget, self.max_daily_participation) <= 0:
            raise ValueError("risk limits must be explicitly positive")
        return self


class FactorExposure(ResearchRecord):
    factors: list[Identifier] = Field(min_length=1)

    @model_validator(mode="after")
    def unique(self):
        if len(set(self.factors)) != len(self.factors):
            raise ValueError("duplicate economic factor")
        return self


class Catalyst(ResearchRecord):
    window_start: date
    window_end: date
    description: str = Field(min_length=1)
    probability_basis: str = Field(min_length=1)

    @model_validator(mode="after")
    def window(self):
        if self.window_end < self.window_start:
            raise ValueError("invalid catalyst window")
        return self


class WatchCandidate(ResearchRecord):
    author: str = Field(min_length=1)
    requested_stage: Literal["RESEARCH", "ON_HOLD", "PRICE_WATCH", "READY", "REJECTED", "ARCHIVED"] = "RESEARCH"
    thesis: str = Field(min_length=1)
    invalidation: str = Field(min_length=1)
    portfolio_fit: str = Field(min_length=1)
    desired_entry: Positive
    stop_price: Positive
    approach_fraction: Fraction
    catalyst_ids: list[Identifier] = Field(default_factory=list)
    requested_target_weight: Fraction | None = None
    next_review: date

    @model_validator(mode="after")
    def stop(self):
        if self.stop_price >= self.desired_entry:
            raise ValueError("stop must be below intended entry")
        return self


class ICProposal(ResearchRecord):
    action: Literal["ADD", "ACCUMULATE", "HOLD", "TRIM", "EXIT", "REVIEW"]
    reason: str = Field(min_length=1)
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    invalidation: str = Field(min_length=1)
    opportunity_cost: str = Field(min_length=1)
    candidate_id: Identifier | None = None


class AlertMethodology(ResearchRecord):
    methodology_id: str | None = None
    approved_replacement: bool = False
    bull_score: Annotated[Decimal, Field(ge=0, le=10, allow_inf_nan=False)] | None = None
    bear_score: Annotated[Decimal, Field(ge=0, le=10, allow_inf_nan=False)] | None = None
    rationale: str = Field(min_length=1)


class Integration(StrictModel):
    schema_version: Literal["3.0"] = "3.0"
    calendar: SessionCalendar | None = None
    memberships: list[Membership] = Field(default_factory=list)
    histories: list[MarketHistory] = Field(default_factory=list)
    timing_policy: TimingPolicy | None = None
    macro: list[MacroObservation] = Field(default_factory=list)
    macro_scenarios: list[MacroScenario] = Field(default_factory=list)
    events: list[NewsEvent] = Field(default_factory=list)
    risk_limits: RiskLimits | None = None
    factors: list[FactorExposure] = Field(default_factory=list)
    catalysts: list[Catalyst] = Field(default_factory=list)
    candidates: list[WatchCandidate] = Field(default_factory=list)
    proposals: list[ICProposal] = Field(default_factory=list)
    alert_methodology: AlertMethodology | None = None

    @model_validator(mode="after")
    def unique(self):
        records = [v for name in type(self).model_fields if name != "schema_version"
                   for v in (getattr(self, name) if isinstance(getattr(self, name), list) else [getattr(self, name)]) if v]
        if len({r.record_id for r in records}) != len(records):
            raise ValueError("duplicate integration record ID")
        for name in ("histories", "factors", "candidates", "proposals"):
            group = getattr(self, name)
            if len({r.ticker for r in group}) != len(group):
                raise ValueError("one active integration record per ticker/owner required")
        if len({m.name for m in self.macro_scenarios}) != len(self.macro_scenarios):
            raise ValueError("duplicate macro scenario")
        probabilities = [m.probability for m in self.macro_scenarios]
        if probabilities and all(p is not None for p in probabilities) and sum(probabilities) != 1:
            raise ValueError("scenario probabilities must sum to one")
        return self




UnitFraction = Annotated[Decimal, Field(ge=0, le=1, allow_inf_nan=False)]
GrowthRate = Annotated[Decimal, Field(gt=-1, allow_inf_nan=False, max_digits=24, decimal_places=8)]


class FinancialFact(ResearchRecord):
    period_start: date
    period_end: date
    accounting_basis: Literal['STANDALONE', 'CONSOLIDATED']
    line_item: str = Field(min_length=1)
    amount: Signed
    units: Literal['PKR', 'USD', 'PKR_PER_SHARE', 'SHARES', 'FRACTION', 'BBL', 'MCF', 'MMBTU', 'TONNES', 'UNITS', 'PKR_PER_UNIT', 'USD_PER_UNIT']
    locator: str = Field(min_length=1)

    @model_validator(mode='after')
    def periods(self):
        if not self.period_start <= self.period_end <= self.effective_date:
            raise ValueError('invalid financial-fact period')
        return self


class OperatingForecast(StrictModel):
    period: str = Field(min_length=1)
    revenue_fact_id: Identifier
    revenue_growth: GrowthRate
    ebitda_margin: Signed
    depreciation: NonNegative
    net_interest_expense: Signed
    other_income: Signed
    tax_charge: Signed
    capex: NonNegative
    working_capital_increase: Signed
    net_borrowing: Signed
    shares: Positive
    cash_income_included: bool


class SOTPComponent(StrictModel):
    component_id: Identifier
    equity_value: NonNegative
    ownership: UnitFraction
    source_ids: list[Identifier] = Field(min_length=1)


class ModelApproval(StrictModel):
    approved_by: str = Field(min_length=1)
    approved_date: date
    model_version: str = Field(min_length=1)
    methodology_validated: Literal[True]
    source_ids: list[Identifier] = Field(min_length=1)
    rationale: str = Field(min_length=1)


class SheetMapping(StrictModel):
    sheet: str = Field(min_length=1, max_length=31)
    collection: Literal['timing', 'mean_reversion', 'valuations', 'earnings', 'history']
    columns: dict[str, str] = Field(min_length=2)
    key_fields: list[str] = Field(default_factory=lambda: ['ticker'])
    header_row: int = Field(default=1, ge=1)
    ignored_columns: dict[str,str] = Field(default_factory=dict)
    price_basis: Literal['RAW','SPLIT_ADJUSTED'] = 'RAW'

    @model_validator(mode='after')
    def keys(self):
        if any(not reason.strip() for reason in self.ignored_columns.values()) or set(self.ignored_columns)&set(self.columns.values()):
            raise ValueError('ignored columns need explicit reasons and cannot be mapped')
        if not set(self.key_fields) <= self.columns.keys() or len(set(self.columns.values())) != len(self.columns):
            raise ValueError('mapping needs unique columns and mapped key fields')
        return self


class WorkbookMigration(ResearchRecord):
    kind: Literal['LEGACY_DATASTORE', 'MODEL_WORKBOOK']
    workbook_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    mappings: list[SheetMapping] = Field(min_length=1)
    approved_by: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    store_permitted: Literal[True]
    methodology_reviewed: bool = False
    ignored_sheets: dict[str,str] = Field(default_factory=dict)
    absolute_tolerance: NonNegative = Decimal('0.00000001')
    relative_tolerance: Annotated[Decimal, Field(ge=0,allow_inf_nan=False,decimal_places=16)] = Decimal('0.000000000001')

    @model_validator(mode='after')
    def unique_sheets(self):
        if any(not reason.strip() for reason in self.ignored_sheets.values()) or set(self.ignored_sheets)&{m.sheet for m in self.mappings}:
            raise ValueError('ignored sheets need reasons and cannot be mapped')
        if any(m.sheet=='_Workspace_Provenance' for m in self.mappings):
            raise ValueError('reserved compatibility provenance sheet')
        if len({m.sheet for m in self.mappings}) != len(self.mappings):
            raise ValueError('one mapping per legacy sheet required')
        return self


class WealthAsset(ResearchRecord):
    economic_id: Identifier
    kind: Literal['CASH', 'GOLD', 'VPS', 'PF', 'GRATUITY', 'CRYPTO', 'OTHER', 'PSX_SLEEVE']
    balance: NonNegative | None = None
    currency: Literal['PKR', 'USD'] = 'PKR'
    portfolio_link: Literal['TOTAL', 'EQUITY', 'CASH'] | None = None
    available_from: date
    fx_to_pkr: Positive | None = None
    fx_date: date | None = None
    fx_source_id: Identifier | None = None

    @model_validator(mode='after')
    def links(self):
        if self.portfolio_link and (self.balance is not None or self.currency != 'PKR'):
            raise ValueError('linked portfolio balances cannot be copied or FX converted')
        if self.kind == 'PSX_SLEEVE' and not self.portfolio_link:
            raise ValueError('PSX sleeve must reference the accepted portfolio')
        if self.kind == 'GRATUITY' and self.balance not in (None, Decimal(0)):
            raise ValueError('future gratuity belongs in a benefit flow, not current wealth')
        if self.currency == 'PKR' and self.fx_to_pkr not in (None, Decimal(1)):
            raise ValueError('PKR has no non-unit FX conversion')
        return self


class WealthFlow(ResearchRecord):
    asset_key: Identifier | None = None
    kind: Literal['CONTRIBUTION', 'BENEFIT', 'EXPENSE']
    amount: NonNegative | None
    amount_basis: Literal['NET'] = 'NET'
    price_basis: Literal['NOMINAL', 'REAL_AT_START']
    frequency: Literal['MONTHLY', 'ONCE']
    starts: date
    ends: date
    economic_claim_id: Identifier | None = None

    @model_validator(mode='after')
    def dates(self):
        if self.ends < self.starts or (self.frequency == 'ONCE' and self.starts != self.ends):
            raise ValueError('invalid wealth cash-flow dates')
        if self.kind != 'EXPENSE' and not self.asset_key:
            raise ValueError('inflow needs an asset destination')
        if self.kind == 'BENEFIT' and not self.economic_claim_id:
            raise ValueError('benefit needs a unique economic claim ID')
        return self


class AssetReturn(StrictModel):
    asset_key: Identifier
    annual_nominal_return: GrowthRate | None
    annual_fee_rate: Fraction | None
    return_tax_rate: Fraction | None
    withdrawal_tax_rate: Fraction | None


class WealthScenario(ResearchRecord):
    profile: "ScenarioLink | None" = None
    name: Literal['bear', 'base', 'bull']
    annual_inflation: GrowthRate | None
    returns: list[AssetReturn]

    @model_validator(mode='after')
    def unique_returns(self):
        if len({r.asset_key for r in self.returns}) != len(self.returns):
            raise ValueError('duplicate asset-return policy')
        return self


class RetirementPlan(ResearchRecord):
    start_date: date
    retirement_date: date
    months: int = Field(ge=1, le=1200)
    monthly_spending_real: NonNegative | None
    withdrawal_order: list[Identifier]

    @model_validator(mode='after')
    def monthly(self):
        if self.start_date.day != 1 or self.retirement_date.day != 1:
            raise ValueError('retirement dates must be month starts')
        if self.start_date < self.effective_date or self.retirement_date < self.start_date:
            raise ValueError('invalid retirement start/retirement date')
        if len(set(self.withdrawal_order)) != len(self.withdrawal_order):
            raise ValueError('duplicate withdrawal-order asset')
        return self


class AssetQuote(StrictModel):
    session_date: date
    close: Positive | None
    fx_to_pkr: Positive | None = None


class CrossAssetHistory(ResearchRecord):
    asset_key: Identifier
    currency: Literal['PKR', 'USD']
    return_basis: Literal['PRICE', 'TOTAL_RETURN']
    fx_source_id: Identifier | None = None
    quotes: list[AssetQuote] = Field(min_length=2)

    @model_validator(mode='after')
    def dates(self):
        dates = [q.session_date for q in self.quotes]
        if dates != sorted(set(dates)) or dates[-1] > self.effective_date:
            raise ValueError('invalid cross-asset history dates')
        return self


class Wealth(StrictModel):
    schema_version: Literal['4.0'] = '4.0'
    include_crypto: bool = False
    assets: list[WealthAsset] = Field(min_length=1)
    flows: list[WealthFlow] = Field(default_factory=list)
    scenarios: list[WealthScenario] = Field(default_factory=list)
    plans: list[RetirementPlan] = Field(default_factory=list)
    histories: list[CrossAssetHistory] = Field(default_factory=list)
    min_correlation_observations: int = Field(default=12, ge=3)

    @model_validator(mode='after')
    def identities(self):
        records = [r for g in (self.assets, self.flows, self.scenarios, self.plans, self.histories) for r in g]
        if len({r.record_id for r in records}) != len(records):
            raise ValueError('duplicate wealth record ID')
        if len({a.ticker for a in self.assets}) != len(self.assets) or len({a.economic_id for a in self.assets}) != len(self.assets):
            raise ValueError('duplicate wealth asset/economic balance')
        if not self.include_crypto and any(a.kind == 'CRYPTO' for a in self.assets):
            raise ValueError('crypto requires explicit opt-in')
        links = [a.portfolio_link for a in self.assets if a.portfolio_link]
        if len(set(links)) != len(links) or 'TOTAL' in links and len(links) != 1:
            raise ValueError('portfolio equity/cash would be counted twice')
        claims = [f.economic_claim_id for f in self.flows if f.kind == 'BENEFIT']
        if len(set(claims)) != len(claims) or set(claims) & {a.economic_id for a in self.assets}:
            raise ValueError('benefit claim already included in current assets or another flow')
        keys = {a.ticker for a in self.assets}
        if any(f.asset_key and f.asset_key not in keys for f in self.flows):
            raise ValueError('cash flow references unknown asset')
        if len({h.asset_key for h in self.histories}) != len(self.histories):
            raise ValueError('one active cross-asset history per asset required')
        if len({s.name for s in self.scenarios}) != len(self.scenarios):
            raise ValueError('duplicate wealth scenario')
        if any(set(p.withdrawal_order) != keys for p in self.plans):
            raise ValueError('explicit withdrawal order must cover each wealth asset once')
        if any(r.asset_key not in keys for s in self.scenarios for r in s.returns) or any(h.asset_key not in keys for h in self.histories):
            raise ValueError('return/history references unknown wealth asset')
        return self



class EvidenceDocument(StrictModel):
    source_id: Identifier
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    suffix: Literal['.pdf','.xlsx','.json','.csv','.md','.txt']
    role: Literal['SOURCE_DOCUMENT','EVIDENCE_CONTRACT','REPLACEMENT_PROMPTS','VALUATION_RERUN'] = 'SOURCE_DOCUMENT'
    store_permitted: Literal[True]



class ScenarioAssumption(StrictModel):
    value: Signed | None
    unit: str = Field(min_length=1)


class ScenarioProfile(ResearchRecord):
    name: Literal['bear','base','bull']
    profile_version: str = Field(min_length=1)
    financial_basis: str = Field(min_length=1)
    period: str = Field(min_length=1)
    horizon_years: Positive
    assumptions: dict[Identifier,ScenarioAssumption] = Field(min_length=1)


class ScenarioOverride(StrictModel):
    assumption: ScenarioAssumption
    rationale: str = Field(min_length=1)
    source_ids: list[Identifier] = Field(min_length=1)


class ScenarioLink(StrictModel):
    profile_id: Identifier
    financial_basis: str = Field(min_length=1)
    period: str = Field(min_length=1)
    horizon_years: Positive
    mapping_rationale: str | None = None
    source_ids: list[Identifier] = Field(default_factory=list)
    overrides: dict[Identifier,ScenarioOverride] = Field(default_factory=dict)
    bindings: dict[Identifier,str] = Field(default_factory=dict)
    binding_units: dict[Identifier,str] = Field(default_factory=dict)


class ForecastBase(StrictModel):
    period: str = Field(min_length=1)
    accounting_basis: Literal['STANDALONE','CONSOLIDATED']
    source_ids: list[Identifier] = Field(min_length=1)
    fact_ids: list[Identifier] = Field(min_length=1)
    fact_bindings: dict[str,Identifier] = Field(min_length=1)
    shares: Positive | None
    tax_charge: Signed | None
    methodology_version: Literal['sector-numeric-v1'] = 'sector-numeric-v1'


class RateBalance(StrictModel):
    average_balance: NonNegative | None
    annual_rate: Signed | None


class BankForecast(ForecastBase):
    engine: Literal['Bank']
    earning_assets: list[RateBalance] = Field(min_length=1)
    funding: list[RateBalance] = Field(min_length=1)
    fees: Signed | None
    treasury_income: Signed | None
    operating_costs: NonNegative | None
    credit_charge: Signed | None
    opening_equity: Positive | None
    oci: Signed | None
    capital_movements: Signed | None
    opening_eligible_capital: NonNegative | None
    eligible_oci: Signed | None
    risk_weighted_assets: NonNegative | None
    minimum_capital_ratio: UnitFraction | None
    distributable_reserves: NonNegative | None
    cash_available: NonNegative | None
    proposed_dividends: NonNegative | None


class CommodityVolume(StrictModel):
    name: Identifier
    unit: Literal['BBL','MCF','MMBTU','TONNES']
    opening_reserves: NonNegative | None
    reserve_additions: NonNegative | None
    production: NonNegative | None
    inventory_release: NonNegative | None
    sold: NonNegative | None
    price_currency: Literal['PKR','USD']
    realized_price: NonNegative | None
    fx_to_pkr: Positive | None
    operating_cost_per_unit_pkr: NonNegative | None


class EPForecast(ForecastBase):
    engine: Literal['E&P']
    commodities: list[CommodityVolume] = Field(min_length=1)
    royalties: NonNegative | None
    fixed_operating_costs: NonNegative | None
    depletion: NonNegative | None
    net_interest: Signed | None
    other_income: Signed | None
    opening_receivables: NonNegative | None
    collections: NonNegative | None
    other_working_capital_increase: Signed | None
    other_wc_excludes_receivables: Literal[True]
    capex: NonNegative | None
    net_borrowing: Signed | None
    cash_income_included: bool


class ProductVolume(StrictModel):
    product: Identifier
    unit: Literal['UNITS','TONNES']
    volume: NonNegative | None
    net_price_pkr: NonNegative | None
    variable_cost_per_unit_pkr: NonNegative | None


class IndustrialForecast(ForecastBase):
    engine: Literal['Industrial']
    products: list[ProductVolume] = Field(min_length=1)
    fixed_operating_costs: NonNegative | None
    depreciation: NonNegative | None
    net_interest: Signed | None
    other_income: Signed | None
    receivables_increase: Signed | None
    inventory_increase: Signed | None
    payables_increase: Signed | None
    capex: NonNegative | None
    net_borrowing: Signed | None
    midcycle_rationale: str = Field(min_length=1)
    cash_income_included: bool


SectorForecast = Annotated[BankForecast | EPForecast | IndustrialForecast, Field(discriminator='engine')]


class ICDecision(ResearchRecord):
    proposal_id: Identifier
    decision: Literal['APPROVE','REJECT','DEFER']
    decided_by: str = Field(min_length=1)
    decided_at: datetime
    reason: str = Field(min_length=1)
    reviewed_basis_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    approved_quantity: Positive | None = None
    transaction_ids: list[Identifier] = Field(default_factory=list)

    @model_validator(mode='after')
    def decision_fields(self):
        if self.decided_at.tzinfo is None or self.decided_at.date()>self.effective_date:
            raise ValueError('decision timestamp must have timezone and precede effective date')
        if len(set(self.transaction_ids))!=len(self.transaction_ids):
            raise ValueError('duplicate decision transaction link')
        if self.decision!='APPROVE' and (self.transaction_ids or self.approved_quantity is not None):
            raise ValueError('only approvals can link transactions or approve quantity')
        return self


Bundle.model_rebuild()
