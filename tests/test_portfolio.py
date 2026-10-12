from copy import deepcopy
from decimal import Decimal

import pytest
from pydantic import ValidationError

from investment_workspace.portfolio import calculate
from investment_workspace.schemas import Bundle


def test_hand_calculated_portfolio_and_split(bundle):
    state = calculate(Bundle.model_validate(bundle))
    assert state["summary"]["reconciliation_state"] == "RECONCILED"
    assert Decimal(state["summary"]["cash"]) == Decimal("15220")
    assert Decimal(state["summary"]["realized_gain"]) == Decimal("370")
    assert Decimal(state["summary"]["income_received"]) == Decimal("200")
    assert Decimal(state["summary"]["equity_value"]) == Decimal("20450")
    assert Decimal(state["summary"]["total_assets"]) == Decimal("35670")
    holdings = {h["ticker"]: h for h in state["holdings"]}
    assert Decimal(holdings["DEMO-INDUSTRIAL"]["quantity"]) == 40
    assert Decimal(holdings["DEMO-INDUSTRIAL"]["cost"]) == 4000
    assert Decimal(holdings["DEMO-LOSS"]["unrealized_gain"]) == -250
    assert state["summary"]["sizing_status"] == "BLOCKED"
    assert all(row["outcome"] == "BLOCKED_MODEL" for row in state["coverage"])


def test_duplicate_import_does_not_double_charge_cash(bundle):
    baseline = calculate(Bundle.model_validate(bundle))
    bundle["transactions"].append(deepcopy(bundle["transactions"][1]))
    assert calculate(Bundle.model_validate(bundle)) == baseline


def test_conflicting_transaction_id_fails(bundle):
    duplicate = deepcopy(bundle["transactions"][1])
    duplicate["price"] = "101"
    bundle["transactions"].append(duplicate)
    with pytest.raises(ValueError, match="conflicting transaction"):
        calculate(Bundle.model_validate(bundle))


def test_quantity_cost_cash_exceptions_block_sizing(bundle):
    bundle["closing"]["positions"][0]["quantity"] = "81"
    bundle["closing"]["positions"][0]["cost"] = "8050"
    bundle["closing"]["cash"] = "15000"
    state = calculate(Bundle.model_validate(bundle))
    by_ticker = {r["ticker"]: r for r in state["reconciliation"]}
    assert Decimal(by_ticker["DEMO-BANK"]["quantity_difference"]) == 1
    assert Decimal(by_ticker["DEMO-BANK"]["cost_difference"]) == 50
    assert Decimal(by_ticker["CASH"]["cash_difference"]) == -220
    assert state["summary"]["sizing_status"] == "BLOCKED"


def test_stale_and_missing_prices_not_zero(bundle):
    bundle["prices"][0]["session_date"] = "2026-09-01"
    bundle["prices"][1]["close"] = None
    state = calculate(Bundle.model_validate(bundle))
    assert state["holdings"][0]["freshness"] == "STALE"
    assert state["summary"]["equity_value"] is None
    assert state["summary"]["total_assets"] is None
    assert state["summary"]["sizing_status"] == "BLOCKED"
    assert {g["reason"] for g in state["data_gaps"]} >= {"STALE_PRICE", "MISSING_PRICE"}


@pytest.mark.parametrize("case", ["future_price", "unknown_source", "negative_cost", "unsettled", "naive_timestamp", "unknown_field", "zero_price", "ambiguous_cash_trade"])
def test_invalid_inputs_rejected(bundle, case):
    if case == "future_price":
        bundle["prices"][0]["session_date"] = "2026-10-10"
    elif case == "unknown_source":
        bundle["prices"][0]["source_id"] = "missing"
    elif case == "negative_cost":
        bundle["closing"]["positions"][0]["cost"] = "-1"
    elif case == "unsettled":
        bundle["transactions"][1]["settlement_date"] = "2026-10-12"
    elif case == "naive_timestamp":
        bundle["closing"]["timestamp"] = "2026-10-09T18:00:00"
    elif case == "unknown_field":
        bundle["broker_account"] = "not-supported"
    elif case == "zero_price":
        bundle["prices"][0]["close"] = "0"
    else:
        bundle["transactions"][1]["amount"] = "5000"
    with pytest.raises(ValidationError):
        Bundle.model_validate(bundle)


def test_oversell_and_negative_cash_fail(bundle):
    bundle["transactions"][2]["quantity"] = "101"
    with pytest.raises(ValueError, match="oversell"):
        calculate(Bundle.model_validate(bundle))
    bundle["transactions"][2]["quantity"] = "20"
    bundle["opening"]["cash"] = "100"
    with pytest.raises(ValueError, match="negative settled cash"):
        calculate(Bundle.model_validate(bundle))
