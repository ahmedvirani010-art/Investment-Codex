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
