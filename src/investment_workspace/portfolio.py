"""Settled cash ledger and weighted-average cost reconciliation."""

from decimal import Decimal, localcontext

from .schemas import Bundle

ZERO = Decimal(0)


def calculate(bundle: Bundle) -> dict:
    with localcontext() as context:
        context.prec = 64
        return _calculate(bundle)


def _calculate(bundle: Bundle) -> dict:
    positions = {p.ticker: [p.quantity, p.cost] for p in bundle.opening.positions}
    cash = bundle.opening.cash
    realized = ZERO
    income = ZERO
    seen = {}
    ledger = []
    for tx in sorted(bundle.transactions, key=lambda t: (t.timestamp, t.transaction_id)):
        payload = tx.model_dump(mode="json")
        if tx.transaction_id in seen:
            if seen[tx.transaction_id] != payload:
                raise ValueError(f"conflicting transaction ID: {tx.transaction_id}")
            continue
        seen[tx.transaction_id] = payload
        quantity, cost = positions.get(tx.ticker, [ZERO, ZERO])
        charges = tx.fees + tx.taxes
        realized_tx = ZERO
        if tx.kind == "BUY":
            paid = tx.quantity * tx.price + charges
            quantity += tx.quantity
            cost += paid
            cash -= paid
        elif tx.kind == "SELL":
            if quantity < tx.quantity:
                raise ValueError(f"oversell: {tx.ticker}")
            basis = cost * tx.quantity / quantity
            proceeds = tx.quantity * tx.price - charges
            quantity -= tx.quantity
            cost -= basis
            realized_tx = proceeds - basis
            realized += realized_tx
            cash += proceeds
        elif tx.kind == "SPLIT":
            if quantity == 0:
                raise ValueError(f"split without an existing position: {tx.ticker}")
            quantity *= tx.ratio
        elif tx.kind == "DEPOSIT":
            cash += tx.amount - charges
        elif tx.kind == "WITHDRAWAL":
            cash -= tx.amount + charges
        elif tx.kind == "DIVIDEND":
            # Confirmed cash receipt only; entitlement and forecasts are Phase 2.
            cash += tx.amount - charges
            income += tx.amount - charges
        if cash < 0:
            raise ValueError(f"negative settled cash after {tx.transaction_id}")
        if tx.ticker and tx.kind != "DIVIDEND":
            positions[tx.ticker] = [quantity, cost]
        ledger.append({**payload, "cash_after": str(cash), "realized_gain": str(realized_tx)})

    closing = {p.ticker: p for p in bundle.closing.positions}
    prices = {p.ticker: p for p in bundle.prices}
    sectors = {s.ticker: s.sector for s in bundle.securities}
    gaps = []
    exceptions = []
    holdings = []
    all_tickers = sorted(set(positions) | set(closing))
    holdings_age = (bundle.market_cutoff - bundle.closing.timestamp.date()).days
    if holdings_age > bundle.policy.holdings_max_age_days:
        gaps.append({"ticker": None, "field": "holdings", "reason": "STALE_HOLDINGS", "owner": "portfolio", "next_action": "Import a dated settled snapshot"})
    if bundle.policy.max_position_weight is None:
        gaps.append({"ticker": None, "field": "risk_limits", "reason": "UNCONFIGURED_RISK_LIMITS", "owner": "user", "next_action": "Confirm portfolio limits before sizing"})
    for ticker in all_tickers:
        qty, cost = positions.get(ticker, [ZERO, ZERO])
        observed = closing.get(ticker)
        observed_qty = observed.quantity if observed else ZERO
        observed_cost = observed.cost if observed else ZERO
        qty_diff = observed_qty - qty
        cost_diff = observed_cost - cost
        reconciled = abs(qty_diff) <= bundle.policy.quantity_tolerance and abs(cost_diff) <= bundle.policy.cost_tolerance
        if not reconciled:
            exceptions.append({"ticker": ticker, "quantity_difference": str(qty_diff), "cost_difference": str(cost_diff), "ledger_quantity": str(qty), "snapshot_quantity": str(observed_qty), "ledger_cost": str(cost), "snapshot_cost": str(observed_cost), "timestamp": bundle.closing.timestamp.isoformat()})
            gaps.append({"ticker": ticker, "field": "position", "reason": "RECONCILIATION_EXCEPTION", "owner": "portfolio", "next_action": "Reconcile opening ledger and closing source"})
        if not qty and not observed_qty:
            continue
        price = prices.get(ticker)
        age = (bundle.market_cutoff - price.session_date).days if price else None
        freshness = "MISSING" if not price or price.close is None else "STALE" if age > bundle.policy.price_max_age_days else "CURRENT"
        if freshness != "CURRENT":
            gaps.append({"ticker": ticker, "field": "price", "reason": f"{freshness}_PRICE", "owner": "prices", "next_action": "Import a verified completed-session price"})
        # Use the declared closing snapshot for display, even when unreconciled.
        market_value = observed_qty * price.close if price and price.close is not None else None
        gain = market_value - observed_cost if market_value is not None else None
        holdings.append({"record_id": f"holding.{ticker}", "ticker": ticker, "sector": sectors[ticker], "quantity": str(observed_qty), "cost": str(observed_cost), "ledger_quantity": str(qty), "ledger_cost": str(cost), "price": str(price.close) if price and price.close is not None else None, "price_date": price.session_date.isoformat() if price else None, "market_value": str(market_value) if market_value is not None else None, "unrealized_gain": str(gain) if gain is not None else None, "unrealized_return_on_cost": str(gain / observed_cost) if gain is not None and observed_cost > 0 else None, "freshness": freshness, "reconciliation_state": "RECONCILED" if reconciled else "EXCEPTION", "source_ids": sorted({bundle.opening.source_id, bundle.closing.source_id} | {t.source_id for t in bundle.transactions if t.ticker == ticker} | ({price.source_id} if price else set()))})
    cash_difference = bundle.closing.cash - cash
    if abs(cash_difference) > bundle.policy.cash_tolerance:
        exceptions.append({"ticker": "CASH", "cash_difference": str(cash_difference), "ledger_cash": str(cash), "snapshot_cash": str(bundle.closing.cash), "timestamp": bundle.closing.timestamp.isoformat()})
        gaps.append({"ticker": None, "field": "cash", "reason": "CASH_RECONCILIATION_EXCEPTION", "owner": "portfolio", "next_action": "Reconcile cash, fees, taxes and receipts"})
    market_total = sum((Decimal(h["market_value"]) for h in holdings if h["market_value"] is not None), ZERO)
    fully_priced = all(h["market_value"] is not None for h in holdings)
    equity = market_total if fully_priced else None
    assets = equity + bundle.closing.cash if equity is not None else None
    for h in holdings:
        h["equity_weight"] = str(Decimal(h["market_value"]) / equity) if equity and h["market_value"] is not None else None
        h["total_sleeve_weight"] = str(Decimal(h["market_value"]) / assets) if assets and h["market_value"] is not None else None
    hhi = sum((Decimal(h["equity_weight"]) ** 2 for h in holdings), ZERO) if equity else None
    source_labels = {s.source_id: s.evidence_label for s in bundle.sources}
    unverified = any(source_labels[s] != "CONFIRMED" for s in {bundle.opening.source_id, bundle.closing.source_id} | {t.source_id for t in bundle.transactions} | {p.source_id for p in bundle.prices})
    if unverified and bundle.mode != "DEMO":
        gaps.append({"ticker": None, "field": "evidence", "reason": "UNVERIFIED_INPUT", "owner": "evidence", "next_action": "Confirm source evidence before sizing"})
    blocked = bool(gaps or exceptions or bundle.mode == "DEMO")
    summary = {"cash": str(bundle.closing.cash), "ledger_cash": str(cash), "cash_difference": str(cash_difference), "equity_value": str(equity) if equity is not None else None, "total_assets": str(assets) if assets is not None else None, "cost": str(sum((Decimal(h["cost"]) for h in holdings), ZERO)), "realized_gain": str(realized), "income_received": str(income), "hhi": str(hhi) if hhi is not None else None, "effective_positions": str(1 / hhi) if hhi else None, "sizing_status": "BLOCKED", "data_gate_status": "BLOCKED" if blocked else "PASSED", "sizing_reason": "Phase 1 does not implement executable sizing or risk review", "reconciliation_state": "EXCEPTION" if exceptions else "RECONCILED", "mode": bundle.mode, "holdings_timestamp": bundle.closing.timestamp.isoformat(), "market_cutoff": bundle.market_cutoff.isoformat(), "return_window_start": bundle.opening.timestamp.isoformat(), "return_window_end": bundle.closing.timestamp.isoformat()}
    coverage = [{"ticker": s.ticker, "outcome": "BLOCKED_MODEL", "owner": "valuation", "reason": "Phase 2 adapter and verified inputs not supplied"} for s in bundle.securities]
    return {"holdings": holdings, "transactions": ledger, "summary": summary, "reconciliation": exceptions, "data_gaps": gaps, "coverage": coverage}
