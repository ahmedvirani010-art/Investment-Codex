"""Evidence-gated Phase 2 arithmetic. No retrieval, implicit assumptions or trades."""

from decimal import Decimal, localcontext

from .contracts import payload as record_payload, normalize
from .runtime import assessment_date, cached, BudgetExceeded


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
          "Entry_Levels": "entries", "Dividend_Calendar": "dividends", "Top_10": "ranking", "Forward_Bridge": "forecasts"}


def fair_value(model, scenario, sector, bundle=None):
    from .models import reference_value
    return reference_value(model, scenario, sector, bundle)


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
    assessment = assessment_date(bundle)
    sources = {s.source_id: s for s in bundle.sources}
    securities = {s.ticker: s for s in bundle.securities}
    if research.universe_date > cutoff:
        raise ValueError("universe date after cutoff")
    extra = {c.ticker for c in bundle.integration.candidates} if bundle.integration else set()
    if bundle.integration:
        extra |= {t for e in bundle.integration.events for t in e.affected_tickers}
        extra |= {t for m in bundle.integration.memberships if m.effective_date <= cutoff <= m.valid_until for t in m.constituents}
    required = sorted(set(research.required_tickers) | set(securities) | extra)
    if set(research.exclusions) - set(required) or any(not v.strip() for v in research.exclusions.values()):
        raise ValueError("exclusions require a required ticker and reason")
    if any(h["ticker"] in research.exclusions for h in state["holdings"] if Decimal(h["quantity"]) > 0):
        raise ValueError("current holdings cannot be excluded")

    def evidence_ok(ids):
        if not set(ids) <= sources.keys():
            raise ValueError("research references an unregistered source")
        return all(sources[i].evidence_label == "CONFIRMED" for i in ids)

    universe_ok = evidence_ok(research.universe_source_ids) and research.full_universe_verified and research.universe_valid_until >= assessment
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
        payload = record_payload(record)
        if not payload.get("covered_event_ids"):
            payload.pop("covered_event_ids", None)
        if record.record_id in old_records:
            if normalize(old_records[record.record_id]["payload"]) != payload:
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
              "earnings": [], "valuations": [], "entries": [], "dividends": [], "ranking": [], "forecasts": [], "entitlements":list(previous.get("research",{}).get("entitlements",[]))}
    provenance = {r["record_id"]: r for r in history}

    def meta(record, owner):
        ids = set(record.source_ids) | set(research.universe_source_ids) | {a.source_id for a in getattr(record, "adjustments", [])}
        return {"schema_version": "2.0", "record_id": record.record_id, "ticker": record.ticker,
                "owner": owner, "run_id": run_id, "upstream_run_ids": [provenance[record.record_id]["run_id"]],
                "effective_date": record.effective_date.isoformat(), "market_cutoff": cutoff.isoformat(),
                "source_ids": sorted(ids), "assumption_ids": [record.record_id] if owner == "valuation" else [],
                "input_hash": input_hash, "units": "PKR / shares / fraction as named",
                "model_version": getattr(record, "model_version", "reference-adapters-v1"), "confidence": "SYNTHETIC" if bundle.mode == "DEMO" else "SOURCE_DECLARED",
                "freshness": "CURRENT" if record.valid_until >= assessment else "STALE", "validation_status": "VALIDATED"}

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
                          and m.valid_until >= assessment and e.valid_until >= assessment
                          and m.event_checked_through == assessment and p and p.close is not None
                          and evidence_ok([p.source_id])
                          and (assessment - p.session_date).days <= bundle.policy.price_max_age_days):
                    outcome, reason = "BLOCKED_EVIDENCE", "Unverified/stale evidence, price or event coverage"
                elif m.accounting_basis != e.basis or m.share_basis_date != e.share_basis_date:
                    outcome, reason = "BLOCKED_EVIDENCE", "Earnings/forecast accounting or share basis mismatch"
                elif ticker in ISSUES and not any(r.ticker == ticker and r.issue == ISSUES[ticker]
                          and r.valid_until >= assessment and evidence_ok(r.source_ids) for r in research.resolutions):
                    outcome, reason = "BLOCKED_EVIDENCE", "Unresolved legacy conflict: " + ISSUES[ticker]
                elif m.certification != "VALIDATED":
                    outcome, reason = "BLOCKED_MODEL", "Provisional model; excluded from ranking"
                else:
                    for s in m.scenarios:
                        from .scenarios import resolve
                        resolve(bundle,s,basis=m.accounting_basis,period=m.forward_period,horizon=m.horizon_years)
                        from .models import bridge
                        from .sector_engines import forecast
                        forecast_rows = [forecast(f,m,bundle) for f in s.sector_forecasts] if s.sector_forecasts else [bridge(f,m,bundle) for f in s.operating_forecasts]
                        for index, forecast in enumerate(forecast_rows):
                            output['forecasts'].append(_json_numbers({**meta(m,'valuation'), **forecast,
                                'scenario':s.name,'year':index+1,'forecast_basis':m.forward_basis,'model_version':m.model_version}))
                        value = Decimal(cached('valuation', ticker + '.' + s.name,
                            {'model': record_payload(m), 'scenario': record_payload(s), 'sector': securities[ticker].sector,
                             'financials': [record_payload(f) for f in bundle.financials if f.record_id in ({of.revenue_fact_id for of in s.operating_forecasts}|{i for of in s.sector_forecasts for i in of.fact_ids})]},
                            lambda: fair_value(m, s, securities[ticker].sector, bundle)))
                        if m.origin == "LEGACY_RECOVERED" and (not m.legacy_column_map
                                or s.name not in m.historical_outputs
                                or abs(value - m.historical_outputs[s.name]) > m.reproduction_tolerance):
                            raise ValueError("legacy column map/output reproduction missing or inconsistent")
                        rows.append(_json_numbers({**meta(m, "valuation"), "scenario": s.name,
                            "scenario_id": s.scenario_id, "earnings_id": e.record_id,
                            "upstream_run_ids": sorted({provenance[e.record_id]["run_id"], provenance[m.record_id]["run_id"]}),
                            "source_ids": sorted(set(m.source_ids + e.source_ids + [a.source_id for a in e.adjustments] + [p.source_id]
                                + (m.approval.source_ids if m.approval else []) + [src for component in s.components for src in component.source_ids]
                                + [src for f in bundle.financials if f.record_id in ({of.revenue_fact_id for of in s.operating_forecasts}|{i for of in s.sector_forecasts for i in of.fact_ids}) for src in f.source_ids]) | set(research.universe_source_ids)),
                            "method": m.method, "model_version": m.model_version, "origin": m.origin, "certification": m.certification, "forward_period": m.forward_period,
                            "forward_basis": m.forward_basis, "reported_eps": e.reported_eps,
                            "forecast_contract":"NUMERICAL_V1" if s.sector_forecasts else "LEGACY_REFERENCE",
                            "scenario_mapping":resolve(bundle,s,basis=m.accounting_basis,period=m.forward_period,horizon=m.horizon_years),
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
        except BudgetExceeded as exc:
            outcome, reason = "BLOCKED_EVIDENCE", str(exc)
        except ValueError as exc:
            outcome, reason = "BLOCKED_MODEL", str(exc)
        if outcome.startswith('BLOCKED'):
            output['forecasts'] = [r for r in output['forecasts'] if r['ticker'] != ticker]
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
        row=dividend_result(d, bundle, state, meta(d, "dividends"), evidence_ok, previous.get("research",{}))
        output["dividends"].append(row)
        basis=row.get("entitlement_basis")
        if basis and not any(b["basis_id"]==basis["basis_id"] for b in output["entitlements"]):
            output["entitlements"].append(basis)
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
            ignored = {"run_id", "input_hash", "upstream_run_ids", "code_version", "code_hash"}
            if key == "entries" and bundle.integration:
                ignored |= {"resolved_timing_gate", "resolved_risk_gate", "gate_upstream_ids", "gate_source_ids", "entry_status"}
            if old and {k: v for k, v in row.items() if k not in ignored} == {k: v for k, v in old.items() if k not in ignored}:
                output[key][i] = old
    output["summary"] = {"valuation_status": "COMPLETE" if universe_ok and eligible and not any(c["outcome"].startswith("BLOCKED") for c in state["coverage"]) else "PARTIAL",
                         "coverage_counts": counts, "required_count": len(required), "eligible_count": len(eligible),
                         "universe_date": research.universe_date.isoformat(), "universe_basis": research.universe_basis,
                         "mode": bundle.mode}
    state["research"] = output


def dividend_result(d, bundle, state, metadata, evidence_ok, previous=None):
    from .dividends import result
    return result(d,bundle,state,metadata,evidence_ok,previous)
