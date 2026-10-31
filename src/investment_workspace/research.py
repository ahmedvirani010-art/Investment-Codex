"""Evidence-gated Phase 2 arithmetic. No retrieval, implicit assumptions or trades."""

from decimal import Decimal, localcontext


ZERO = Decimal(0)
ISSUES = {"POL": "POL_DPS", "BAHL": "BAHL_EPS", "OGDC": "OGDC_ENTITLEMENT",
          "INDU": "INDU_CASH_INCOME", "AKBL": "AKBL_TREASURY_OCI"}
DRIVERS = {
    "Bank": {"treasury_gains", "credit_costs", "oci", "capital", "dividend_capacity"},
    "E&P": {"reserves", "production", "realized_prices", "collections", "depletion", "capex", "tax", "payout"},
    "Industrial": {"operating_drivers", "midcycle_margins", "capex", "working_capital", "net_debt"},
}
COLLECTIONS = ("earnings", "models", "dividends", "resolutions")
SHEETS = {"Earnings_Bridge": "earnings", "Valuation": "valuations",
          "Entry_Levels": "entries", "Dividend_Calendar": "dividends", "Top_10": "ranking"}


def fair_value(model, scenario, sector):
    """Explicit reference adapters v1, not recovered proprietary equations."""
    s = scenario
    missing = DRIVERS.get(sector, set()) - s.drivers.keys()
    if missing or any(not v.strip() for v in s.drivers.values()):
        raise ValueError("missing sector driver evidence: " + ", ".join(sorted(missing)))
    if model.method == "BANK_JUSTIFIED_PB" and sector == "Bank":
        if s.book_value_per_share is None or s.sustainable_roe is None:
            raise ValueError("bank model needs book value and sustainable ROE")
        value = s.book_value_per_share * (s.sustainable_roe - s.terminal_growth) / (s.discount_rate - s.terminal_growth)
    elif model.method == "FCFE_DCF" and sector in {"E&P", "Industrial"}:
        if not s.fcfe or s.shares is None or s.terminal_value is None:
            raise ValueError("FCFE model needs annual equity cash flows, shares and explicit terminal equity value")
        if sector == "E&P" and s.payout_crosscheck is None:
            raise ValueError("E&P requires a payout cross-check")
        # Terminal equity value is explicitly supplied; finite reserve/contract life is not inferred.
        value = (sum((cf / (1 + s.discount_rate) ** year for year, cf in enumerate(s.fcfe, 1)), ZERO)
                 + s.terminal_value / (1 + s.discount_rate) ** len(s.fcfe)) / s.shares
    else:
        raise ValueError(f"unsupported sector/method: {sector}/{model.method}")
    if value <= 0:
        raise ValueError("non-positive equity value; no entry level or ranking")
    return value


def return_bridge(model, s, value, price):
    if price is None or price <= 0:
        return {"margin_of_safety": None, "gross_return": None, "annualized_return": None, "net_return": None}
    gross = (s.exit_price + s.horizon_dividends - price) / price
    annualized = (1 + gross) ** (1 / model.horizon_years) - 1 if gross > -1 else None
    tax = [model.dividend_tax_rate, model.capital_gains_tax_rate,
           model.entry_cost_rate, model.exit_cost_rate, model.liabilities_per_share]
    net = None
    if all(x is not None for x in tax):
        paid = price * (1 + model.entry_cost_rate)
        proceeds = (s.exit_price * (1 - model.exit_cost_rate)
                    - max(ZERO, s.exit_price - price) * model.capital_gains_tax_rate
                    + s.horizon_dividends * (1 - model.dividend_tax_rate) - model.liabilities_per_share)
        net = (proceeds - paid) / paid
    return {"margin_of_safety": 1 - price / value, "gross_return": gross,
            "annualized_return": annualized, "net_return": net}


def _json_numbers(row):
    return {k: str(v) if isinstance(v, Decimal) else v for k, v in row.items()}


def calculate_research(bundle, state, previous, run_id, input_hash):
    with localcontext() as ctx:
        ctx.prec = 48
        return _calculate(bundle, state, previous, run_id, input_hash)


def _calculate(bundle, state, previous, run_id, input_hash):
    research = bundle.research
    if research is None:
        if previous.get("research", {}).get("input"):
            raise ValueError("accepted research cannot be omitted; use import-research to revise it")
        return
    cutoff = bundle.market_cutoff
    sources = {s.source_id: s for s in bundle.sources}
    securities = {s.ticker: s for s in bundle.securities}
    if research.universe_date > cutoff:
        raise ValueError("universe date after cutoff")
    required = sorted(set(research.required_tickers) | set(securities))
    if set(research.exclusions) - set(required) or any(not v.strip() for v in research.exclusions.values()):
        raise ValueError("exclusions require a required ticker and reason")
    if any(h["ticker"] in research.exclusions for h in state["holdings"] if Decimal(h["quantity"]) > 0):
        raise ValueError("current holdings cannot be excluded")

    def evidence_ok(ids):
        if not set(ids) <= sources.keys():
            raise ValueError("research references an unregistered source")
        return all(sources[i].evidence_label == "CONFIRMED" for i in ids)

    universe_ok = evidence_ok(research.universe_source_ids) and research.full_universe_verified and research.universe_valid_until >= cutoff
    history = list(previous.get("research", {}).get("history", []))
    old_records = {r["record_id"]: r for r in history}
    active_old = {r["record_id"]: r for group in COLLECTIONS
                  for r in previous.get("research", {}).get("input", {}).get(group, [])}
    records = [r for group in COLLECTIONS for r in getattr(research, group)]
    new_ids = {r.record_id for r in records}
    for record in records:
        if record.ticker not in required:
            raise ValueError("research record outside required universe")
        if record.effective_date > cutoff:
            raise ValueError("research record effective after cutoff")
        evidence_ok(record.source_ids)
        payload = record.model_dump(mode="json")
        if record.record_id in old_records:
            if old_records[record.record_id]["payload"] != payload:
                raise ValueError("research record ID is immutable; use a new ID and supersedes")
            if record.record_id not in active_old:
                raise ValueError("superseded research record cannot be reactivated")
        else:
            if record.supersedes:
                old = active_old.get(record.supersedes)
                if not old or old["ticker"] != record.ticker or record.effective_date.isoformat() < old["effective_date"]:
                    raise ValueError("supersedes must reference an active record for the same ticker")
                group = next(g for g in COLLECTIONS if record in getattr(research, g))
                if record.supersedes not in {r["record_id"] for r in previous["research"]["input"][group]}:
                    raise ValueError("supersession cannot change analytical owner")
            history.append({"record_id": record.record_id, "payload": payload, "run_id": run_id,
                            "input_hash": input_hash, "source_ids": record.source_ids})
    for old in active_old.values():
        if old["record_id"] not in new_ids and not any(r.supersedes == old["record_id"] for r in records):
            raise ValueError("accepted research record omitted without explicit supersession")

    output = {"input": research.model_dump(mode="json"), "history": history,
              "earnings": [], "valuations": [], "entries": [], "dividends": [], "ranking": []}
    provenance = {r["record_id"]: r for r in history}

    def meta(record, owner):
        ids = set(record.source_ids) | set(research.universe_source_ids) | {a.source_id for a in getattr(record, "adjustments", [])}
        return {"schema_version": "2.0", "record_id": record.record_id, "ticker": record.ticker,
                "owner": owner, "run_id": run_id, "upstream_run_ids": [provenance[record.record_id]["run_id"]],
                "effective_date": record.effective_date.isoformat(), "market_cutoff": cutoff.isoformat(),
                "source_ids": sorted(ids), "assumption_ids": [record.record_id] if owner == "valuation" else [],
                "input_hash": input_hash, "units": "PKR / shares / fraction as named",
                "model_version": "reference-adapters-v1", "confidence": "SYNTHETIC" if bundle.mode == "DEMO" else "SOURCE_DECLARED",
                "freshness": "CURRENT" if record.valid_until >= cutoff else "STALE", "validation_status": "VALIDATED"}

    earnings = {e.ticker: e for e in research.earnings}
    for e in research.earnings:
        evidence_ok([a.source_id for a in e.adjustments])
        normalized = e.reported_pat + sum((a.pretax_amount + a.tax_effect for a in e.adjustments), ZERO)
        output["earnings"].append(_json_numbers({**meta(e, "earnings"), **e.model_dump(mode="json"),
            "source_ids": sorted(set(e.source_ids + [a.source_id for a in e.adjustments]) | set(research.universe_source_ids)), "normalized_pat": normalized, "normalized_eps": normalized / e.weighted_average_shares,
            "reported_eps": e.reported_eps, "quality": e.quality}))

    models = {m.ticker: m for m in research.models}
    prices = {p.ticker: p for p in bundle.prices}
    state["coverage"] = []
    for ticker in required:
        outcome, reason = "BLOCKED_MODEL", "No accepted sector model"
        e, m, p = earnings.get(ticker), models.get(ticker), prices.get(ticker)
        rows = []
        try:
            if ticker in research.exclusions:
                outcome, reason = "EXCLUDED_WITH_REASON", research.exclusions[ticker]
            elif m is not None:
                if ticker not in securities:
                    raise ValueError("missing security sector")
                if e is None or m.earnings_id != e.record_id:
                    outcome, reason = "BLOCKED_EVIDENCE", "Missing owned earnings bridge"
                elif not (evidence_ok(m.source_ids + e.source_ids + [a.source_id for a in e.adjustments])
                          and m.valid_until >= cutoff and e.valid_until >= cutoff
                          and m.event_checked_through == cutoff and p and p.close is not None
                          and evidence_ok([p.source_id])
                          and (cutoff - p.session_date).days <= bundle.policy.price_max_age_days):
                    outcome, reason = "BLOCKED_EVIDENCE", "Unverified/stale evidence, price or event coverage"
                elif m.accounting_basis != e.basis or m.share_basis_date != e.share_basis_date:
                    outcome, reason = "BLOCKED_EVIDENCE", "Earnings/forecast accounting or share basis mismatch"
                elif ticker in ISSUES and not any(r.ticker == ticker and r.issue == ISSUES[ticker]
                          and r.valid_until >= cutoff and evidence_ok(r.source_ids) for r in research.resolutions):
                    outcome, reason = "BLOCKED_EVIDENCE", "Unresolved legacy conflict: " + ISSUES[ticker]
                elif m.certification != "VALIDATED":
                    outcome, reason = "BLOCKED_MODEL", "Provisional model; excluded from ranking"
                else:
                    for s in m.scenarios:
                        value = fair_value(m, s, securities[ticker].sector)
                        if m.origin == "LEGACY_RECOVERED" and (not m.legacy_column_map
                                or s.name not in m.historical_outputs
                                or abs(value - m.historical_outputs[s.name]) > m.reproduction_tolerance):
                            raise ValueError("legacy column map/output reproduction missing or inconsistent")
                        rows.append(_json_numbers({**meta(m, "valuation"), "scenario": s.name,
                            "scenario_id": s.scenario_id, "earnings_id": e.record_id,
                            "upstream_run_ids": sorted({provenance[e.record_id]["run_id"], provenance[m.record_id]["run_id"]}),
                            "source_ids": sorted(set(m.source_ids + e.source_ids + [a.source_id for a in e.adjustments] + [p.source_id]) | set(research.universe_source_ids)),
                            "method": m.method, "model_version": m.model_version, "forward_period": m.forward_period,
                            "forward_basis": m.forward_basis, "reported_eps": e.reported_eps,
                            "normalized_eps": next(r["normalized_eps"] for r in output["earnings"] if r["ticker"] == ticker),
                            "forward_eps": s.forward_eps, "sustainable_dps": s.sustainable_dps,
                            "present_fair_value": value, "horizon_exit_price": s.exit_price,
                            "horizon_dividends": s.horizon_dividends, "horizon_years": m.horizon_years,
                            "payout_crosscheck": s.payout_crosscheck,
                            **return_bridge(m, s, value, p.close)}))
                    if not Decimal(rows[0]["present_fair_value"]) > 0:
                        raise ValueError("invalid value")
                    vals = {r["scenario"]: Decimal(r["present_fair_value"]) for r in rows}
                    if not vals["bear"] <= vals["base"] <= vals["bull"]:
                        raise ValueError("scenario fair values must be ordered bear <= base <= bull")
                    output["valuations"].extend(rows)
                    base = next(s for s in m.scenarios if s.name == "base")
                    hurdle = m.sovereign_benchmark + m.equity_risk_premium
                    mos_entry = vals["base"] * (1 - m.margin_of_safety)
                    hurdle_entry = (base.exit_price + base.horizon_dividends) / (1 + hurdle) ** m.horizon_years
                    output["entries"].append(_json_numbers({**meta(m, "valuation"),
                        "mos_entry_ceiling": mos_entry, "hurdle_entry_ceiling": hurdle_entry,
                        "entry_ceiling": min(mos_entry, hurdle_entry), "hurdle": hurdle,
                        "benchmark_date": m.benchmark_date.isoformat(), "timing_gate": m.timing_gate,
                        "risk_gate": m.risk_gate, "entry_status": "REVIEW" if m.timing_gate == m.risk_gate == "PASSED" else "BLOCKED",
                        "sizing_status": "BLOCKED", "basis": "GROSS; net planning requires tax/cost settings"}))
                    # New inputs are revalued; unchanged records preserve original lineage below.
                    outcome, reason = "REVALUED", "Validated explicit model; arithmetic and evidence gates passed"
        except ValueError as exc:
            outcome, reason = "BLOCKED_MODEL", str(exc)
        state["coverage"].append({"ticker": ticker, "outcome": outcome, "reason": reason, "owner": "valuation",
                                  "run_id": run_id, "market_cutoff": cutoff.isoformat(),
                                  "source_ids": m.source_ids if m else research.universe_source_ids})
        if outcome.startswith("BLOCKED"):
            state["data_gaps"].append({"ticker": ticker, "field": "valuation", "reason": outcome,
                "detail": reason, "owner": "valuation", "next_action": "Import verified missing inputs or explicit model revision"})

    used_receipts = set()
    for d in research.dividends:
        ids = set(d.receipt_transaction_ids)
        if len(ids) != len(d.receipt_transaction_ids) or ids & used_receipts:
            raise ValueError("dividend cash receipt cannot be linked twice")
        used_receipts |= ids
        output["dividends"].append(dividend_result(d, bundle, state, meta(d, "dividends"), evidence_ok))
    if not universe_ok:
        state["data_gaps"].append({"ticker": None, "field": "universe", "reason": "UNVERIFIED_UNIVERSE",
            "owner": "valuation", "next_action": "Supply dated verified constituents plus holdings/watchlist/requested names"})
    counts = {name: sum(c["outcome"] == name for c in state["coverage"]) for name in
              ("REVALUED", "VERIFIED_CURRENT", "VERIFIED_CARRIED_FORWARD", "BLOCKED_EVIDENCE", "BLOCKED_MODEL", "EXCLUDED_WITH_REASON")}
    eligible = [r for r in output["valuations"] if r["scenario"] == "base"]
    output["ranking"] = [{"rank": i, **r} for i, r in enumerate(sorted(eligible,
            key=lambda r: (-Decimal(r["gross_return"]), r["ticker"])), 1)][:10]
    # Reuse exact last-good rows when the full input and calculation context match.
    old_research = previous.get("research", {})
    for key in SHEETS.values():
        old_rows = old_research.get(key, [])
        for i, row in enumerate(output[key]):
            old = next((r for r in old_rows if r.get("record_id") == row.get("record_id")
                        and r.get("scenario") == row.get("scenario")), None)
            ignored = {"run_id", "input_hash", "upstream_run_ids"}
            if old and {k: v for k, v in row.items() if k not in ignored} == {k: v for k, v in old.items() if k not in ignored}:
                output[key][i] = old
    output["summary"] = {"valuation_status": "COMPLETE" if universe_ok and eligible and not any(c["outcome"].startswith("BLOCKED") for c in state["coverage"]) else "PARTIAL",
                         "coverage_counts": counts, "required_count": len(required), "eligible_count": len(eligible),
                         "universe_date": research.universe_date.isoformat(), "universe_basis": research.universe_basis,
                         "mode": bundle.mode}
    state["research"] = output


def dividend_result(d, bundle, state, metadata, evidence_ok):
    quantity = gross = net = None
    status = "PENDING_CONFIRMATION"
    receipts = [t for t in state["transactions"] if t["transaction_id"] in d.receipt_transaction_ids]
    if len(receipts) != len(d.receipt_transaction_ids) or any(t["kind"] != "DIVIDEND" or t["ticker"] != d.ticker for t in receipts):
        raise ValueError("receipt must reference an accepted DIVIDEND transaction for the same ticker")
    verified = (evidence_ok(d.source_ids) and d.valid_until >= bundle.market_cutoff and d.dates_verified
                and d.ex_date is not None and d.record_date is not None and d.settlement_rule == "SETTLED_BEFORE_EX")
    # Only compute entitlement inside the reconciled ledger window. Current holdings prove nothing before opening.
    if verified and bundle.opening.timestamp.date() < d.ex_date <= bundle.closing.timestamp.date() and not state["reconciliation"] and evidence_ok([bundle.opening.source_id, bundle.closing.source_id] + [t.source_id for t in bundle.transactions]):
        quantity = next((p.quantity for p in bundle.opening.positions if p.ticker == d.ticker), ZERO)
        for tx in sorted({t.transaction_id: t for t in bundle.transactions}.values(), key=lambda t: (t.timestamp, t.transaction_id)):
            if tx.ticker != d.ticker or tx.settlement_date >= d.ex_date:
                continue
            if tx.kind == "BUY":
                quantity += tx.quantity
            elif tx.kind == "SELL":
                quantity -= tx.quantity
            elif tx.kind == "SPLIT":
                quantity *= tx.ratio
        gross = quantity * d.dps
        net = gross * (1 - d.tax_rate) if d.tax_rate is not None else None
        status = "NOT_ENTITLED" if quantity == 0 else "ENTITLED"
        if quantity and d.payment_date:
            status = "OVERDUE" if d.payment_date < bundle.market_cutoff else "RECEIVABLE"
        if receipts:
            total = sum((Decimal(t["amount"]) for t in receipts), ZERO)
            withheld = sum((Decimal(t["taxes"]) for t in receipts), ZERO)
            status = "RECEIVED" if total == gross and d.tax_rate is not None and withheld == gross * d.tax_rate else "RECEIPT_EXCEPTION"
    received_gross = sum((Decimal(t["amount"]) for t in receipts), ZERO) if receipts else None
    received_net = sum((Decimal(t["amount"]) - Decimal(t["taxes"]) - Decimal(t["fees"]) for t in receipts), ZERO) if receipts else None
    row = {**metadata, **d.model_dump(mode="json"), "status": status, "eligible_quantity": quantity,
           "gross_entitlement": gross, "net_entitlement": net,
           "gross_received": received_gross, "net_received": received_net,
           "gross_pending": max(ZERO, gross - (received_gross or ZERO)) if gross is not None else None,
           "cash_treatment": "Receipt already included in portfolio cash; never added again"}
    if status in {"PENDING_CONFIRMATION", "RECEIPT_EXCEPTION"}:
        state["data_gaps"].append({"ticker": d.ticker, "field": "dividend", "reason": status,
            "owner": "dividends", "next_action": "Verify dates, ledger window, settlement rule, tax and cash receipt"})
    return _json_numbers(row)
