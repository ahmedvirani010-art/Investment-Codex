"""Integrated Phase 3 evidence, timing, risk and decision workflows; no execution."""

from copy import deepcopy
from decimal import Decimal, ROUND_FLOOR, localcontext
from itertools import combinations

from .storage import digest, dumps
from .timing import adjusted_bars, backtest, correlation, indicators, mean, rank_rows

ZERO = Decimal(0)
ONE = Decimal(1)
SHEETS = {"RS_Trend": "timing", "Sector_Rotation": "sectors", "Mean_Reversion": "mean_reversion",
          "Macro": "macro", "Scenarios": "scenarios", "News_Impact": "events",
          "Portfolio_Risk": "risk", "Correlations": "correlations", "Watchlist": "watchlist",
          "Catalysts": "catalysts", "IC_Actions": "ic_actions", "Refresh_Queue": "refresh_queue",
          "Event_Propagation": "propagation", "Backtests": "backtests", "Backtest_Trades": "backtest_trades", "Alerts": "alerts"}
GROUPS = ("calendar", "memberships", "histories", "timing_policy", "macro", "macro_scenarios", "events",
          "risk_limits", "factors", "catalysts", "candidates", "proposals", "alert_methodology")
SINGLE = {"calendar", "timing_policy", "risk_limits", "alert_methodology"}


def records(integration):
    if integration is None:
        return []
    return [(name, r) for name in GROUPS for r in
            ([getattr(integration, name)] if name in SINGLE else getattr(integration, name)) if r]


def numbers(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: numbers(v) for k, v in value.items()}
    if isinstance(value, list):
        return [numbers(v) for v in value]
    return value


def calculate_workflows(bundle, state, previous, run_id, input_hash):
    with localcontext() as ctx:
        ctx.prec = 48
        return _calculate(bundle, state, previous, run_id, input_hash)


def _calculate(bundle, state, previous, run_id, input_hash):
    data = bundle.integration
    old = previous.get("integration", {})
    if data is None:
        if old.get("input"):
            raise ValueError("accepted integration cannot be omitted")
        return
    cutoff = bundle.market_cutoff
    sources = {s.source_id: s for s in bundle.sources}
    history = deepcopy(old.get("history", []))
    prior = {r["record_id"]: r for r in history}
    active = {r["record_id"]: (group, r) for group in GROUPS for r in
              ([old.get("input", {}).get(group)] if group in SINGLE else old.get("input", {}).get(group, [])) if r}
    current = records(data)
    superseded = set()
    for group, record in current:
        if record.effective_date > cutoff:
            raise ValueError("integration record effective after cutoff")
        ids = set(record.source_ids) | {a.source_id for a in getattr(record, "actions", [])}
        if not ids <= sources.keys():
            raise ValueError("integration references an unregistered source")
        payload = record.model_dump(mode="json")
        if record.record_id in prior:
            if prior[record.record_id]["payload"] != payload or record.record_id not in active:
                raise ValueError("integration record ID immutable; superseded records cannot be reactivated")
        else:
            if record.supersedes:
                previous_record = active.get(record.supersedes)
                if (not previous_record or previous_record[0] != group or previous_record[1]["ticker"] != record.ticker
                        or record.effective_date.isoformat() < previous_record[1]["effective_date"]
                        or record.supersedes in superseded):
                    raise ValueError("supersedes must reference one active same-owner/ticker record")
                superseded.add(record.supersedes)
            history.append({"record_id": record.record_id, "group": group, "payload": payload,
                            "run_id": run_id, "input_hash": input_hash})
    if set(active) - {r.record_id for _, r in current} - superseded:
        raise ValueError("accepted integration record omitted without supersession")
    provenance = {r["record_id"]: r for r in history}
    out = {"input": data.model_dump(mode="json"), "history": history,
           **{key: [] for key in SHEETS.values()}}

    def good(record):
        return bool(record and record.effective_date <= cutoff <= record.valid_until
                    and all(sources[s].evidence_label == "CONFIRMED" for s in record.source_ids))

    def meta(record, owner):
        return {"schema_version": "3.0", "record_id": record.record_id, "ticker": record.ticker,
                "owner": owner, "run_id": run_id, "upstream_run_ids": [provenance[record.record_id]["run_id"]],
                "effective_date": record.effective_date.isoformat(), "market_cutoff": cutoff.isoformat(),
                "source_ids": record.source_ids, "assumption_ids": [], "units": "PKR / shares / fraction as named",
                "confidence": "SYNTHETIC" if bundle.mode == "DEMO" else "SOURCE_DECLARED",
                "freshness": "CURRENT" if good(record) else "STALE_OR_UNVERIFIED",
                "validation_status": "VALIDATED" if good(record) else "BLOCKED", "input_hash": input_hash}

    def gap(ticker, field, reason, action, source_ids=None):
        row = {"ticker": ticker, "field": field, "reason": reason, "owner": field,
               "next_action": action, "source_ids": source_ids or []}
        state["data_gaps"].append(row)
        out["refresh_queue"].append({**row, "queue_status": "MISSING_STALE_OR_CONFLICTING", "network_attempted": False})

    # This queue precedes any potential network work. This release has only explicit local adapters.
    calendar = data.calendar
    sessions = calendar.sessions if good(calendar) else []
    if sessions and sessions[-1] > cutoff:
        raise ValueError("calendar contains a future/uncompleted session")
    if not sessions:
        gap(None, "prices", "UNVERIFIED_SESSION_CALENDAR", "Import a verified completed-session calendar")
    latest = sessions[-1] if sessions else None
    memberships = [m for m in data.memberships if good(m)]
    if memberships:
        most_recent = max(m.effective_date for m in memberships)
        memberships = [m for m in memberships if m.effective_date == most_recent]
    if len(memberships) != 1:
        membership = None
        gap(None, "universe", "MISSING_OR_AMBIGUOUS_MEMBERSHIP", "Import one current dated membership snapshot")
    else:
        membership = memberships[0]
    policy = data.timing_policy
    if not good(policy):
        gap(None, "timing", "MISSING_TIMING_POLICY", "Import dated indicator, liquidity and calibration parameters")
    series, eligible_rows = {}, []
    history_by_ticker = {h.ticker: h for h in data.histories}
    benchmark = history_by_ticker.get(policy.benchmark) if policy else None
    known_tickers = {s.ticker for s in bundle.securities}
    needed = known_tickers | {c.ticker for c in data.candidates} | (set(membership.constituents) if membership else set())
    if benchmark and benchmark.role != "BENCHMARK":
        raise ValueError("timing benchmark must have BENCHMARK role")
    # Align the complete declared calendar, rather than compressing gaps into shorter lookbacks.
    for h in data.histories:
        try:
            if not good(h) or latest is None or h.action_coverage_through < latest:
                raise ValueError("unverified/stale history or incomplete corporate-action coverage")
            if any(a.session_date > cutoff or sources[a.source_id].evidence_label != "CONFIRMED" for a in h.actions):
                raise ValueError("unverified/future corporate action")
            rows = adjusted_bars(h, cutoff)
            by_date = {r["session_date"]: r for r in rows}
            if set(by_date) - set(sessions):
                raise ValueError("history has sessions outside verified calendar")
            # Prefix differences are allowed; holes inside a declared history are not.
            relevant = [d for d in sessions if d >= rows[0]["session_date"]]
            if list(by_date) != relevant:
                raise ValueError("missing completed sessions in history")
            series[h.ticker] = rows
        except ValueError as exc:
            gap(h.ticker, "prices", "BLOCKED_HISTORY", str(exc), h.source_ids)
    for ticker in sorted(needed):
        h = history_by_ticker.get(ticker)
        row = {"ticker": ticker, "status": "BLOCKED", "reason": None, "rs_percentile": None,
               "source_ids": h.source_ids if h else [], "market_cutoff": cutoff.isoformat(), "owner": "price_history"}
        try:
            if not good(policy) or not membership or not benchmark or not latest:
                raise ValueError("missing verified calendar, policy, universe or benchmark")
            if ticker not in membership.constituents:
                raise ValueError("outside current point-in-time investable universe")
            if not h or h.role != "SECURITY" or ticker not in series or benchmark.ticker not in series:
                raise ValueError("missing verified security/benchmark history")
            bars = series[ticker]
            if policy.effective_date > cutoff:
                raise ValueError("post-cutoff timing policy")
            shared = max(bars[0]["session_date"], series[benchmark.ticker][0]["session_date"])
            bars = [b for b in bars if b["session_date"] >= shared]
            bench = [b for b in series[benchmark.ticker] if b["session_date"] >= shared]
            if [b["session_date"] for b in bars] != [b["session_date"] for b in bench]:
                raise ValueError("unsynchronized benchmark history")
            values = [b["traded_value"] for b in bars[-policy.liquidity_window:]]
            if len(values) < policy.liquidity_window or any(v is None for v in values):
                raise ValueError("missing observed traded values for liquidity screen")
            if mean(values) < policy.min_average_traded_value:
                raise ValueError("below explicit investable liquidity floor")
            current_price = next((p for p in bundle.prices if p.ticker == ticker), None)
            if current_price and current_price.session_date == latest and current_price.close != bars[-1]["close"]:
                raise ValueError("current price conflicts with verified history")
            row.update({**meta(h, "price_history"), **indicators(bars, bench, policy), "status": "ELIGIBLE", "reason": None,
                        "source_ids": sorted(set(h.source_ids + benchmark.source_ids + policy.source_ids + calendar.source_ids + membership.source_ids + [a.source_id for a in h.actions + benchmark.actions])),
                        "assumption_ids": [policy.record_id], "history_id": h.record_id,
                        "policy_id": policy.record_id, "membership_id": membership.record_id,
                        "latest_session": latest.isoformat()})
            eligible_rows.append(row)
        except ValueError as exc:
            row["reason"] = str(exc)
            gap(ticker, "timing", "BLOCKED_TIMING", str(exc), row["source_ids"])
        out["timing"].append(row)
    rank_rows(out["timing"], policy.min_rank_universe if policy else 2)
    if policy and len(eligible_rows) < policy.min_rank_universe:
        gap(None, "timing", "INSUFFICIENT_RANK_UNIVERSE", "Import enough eligible liquid synchronized histories")
    sectors = {s.ticker: s.sector for s in bundle.securities}
    for ticker in needed - set(sectors):
        sectors[ticker] = "UNKNOWN"
        gap(ticker, "securities", "MISSING_SECURITY_METADATA", "Import sector/security metadata before sector or risk review")
    for sector in sorted(set(sectors.values())):
        rows = [r for r in eligible_rows if sectors.get(r["ticker"]) == sector]
        total = sum(sectors.get(t) == sector for t in needed)
        out["sectors"].append({"sector": sector, "eligible_count": len(rows), "required_count": total,
            "price_breadth": Decimal(sum(r["stage"] == "STAGE_2" for r in rows)) / len(rows) if rows else None,
            "rs_breadth": Decimal(sum(r["relative_performance"] > 0 for r in rows)) / len(rows) if rows else None,
            "average_relative_performance": mean([r["relative_performance"] for r in rows]) if rows else None,
            "basis": "ELIGIBLE_NAMES_EQUAL_WEIGHT_PRICE_ONLY", "coverage": "PARTIAL" if len(rows) < total else "FULL"})
    for row in eligible_rows:
        out["mean_reversion"].append({k: row[k] for k in ("record_id", "ticker", "owner", "run_id", "market_cutoff", "source_ids", "assumption_ids", "z_score", "reversion_signal", "observations", "return_basis", "formula_version")})
        verified_memberships = [m for m in data.memberships if all(sources[s].evidence_label == "CONFIRMED" for s in m.source_ids)]
        point_in_time = bool(policy.backtest_start and all(sources[s].effective_date <= policy.backtest_start for s in policy.source_ids)
                             and all(sources[s].effective_date <= m.effective_date for m in verified_memberships for s in m.source_ids))
        test = backtest(series[row["ticker"]], policy, verified_memberships, row["ticker"]) if point_in_time else {
            "status": "BLOCKED", "reason": "Parameter/membership evidence not available at historical decision date", "trades": []}
        trades = test.pop("trades", [])
        out["backtest_trades"].extend({**meta(history_by_ticker[row["ticker"]], "price_history"), "trade_index": i, **trade}
                                      for i, trade in enumerate(trades, 1))
        out["backtests"].append({**meta(history_by_ticker[row["ticker"]], "price_history"), **test,
            "assumption_ids": [policy.record_id], "source_ids": sorted(set(row["source_ids"] + [s for m in verified_memberships for s in m.source_ids]))})
    # News transmits explicit EPS estimates; it never edits the owned earnings/forecast bridge.
    blocked_models = set()
    uncertain_events = set()
    model_by_ticker = {m.ticker: m for m in bundle.research.models} if bundle.research else {}
    prior_event_ids = {r["record_id"] for r in old.get("input", {}).get("events", [])}
    for event in data.events:
        out["events"].append({**meta(event, "macro_news"), **event.model_dump(mode="json"),
                              "impact_kind": "QUANTIFIED_ESTIMATE" if event.eps_delta is not None else "QUALITATIVE"})
        if not good(event):
            uncertain_events.update(event.affected_tickers)
            gap(event.ticker, "macro_news", "STALE_OR_UNVERIFIED_EVENT", "Verify the event and its transmission before readiness", event.source_ids)
        for ticker in event.affected_tickers:
            model = model_by_ticker.get(ticker)
            acknowledged = bool(good(event) and model and event.record_id in model.covered_event_ids and model.effective_date >= event.effective_date)
            needs = event.requires_model_revision and not acknowledged
            if needs:
                blocked_models.add(ticker)
                gap(ticker, "valuation", "EVENT_REQUIRES_OWNED_REVISION", "Revise the owned model and explicitly cover event " + event.record_id, event.source_ids)
            out["propagation"].append({"record_id": event.record_id, "ticker": ticker,
                "source_ids": event.source_ids, "event_run_id": provenance[event.record_id]["run_id"],
                "affected_owners": ["earnings", "valuation", "risk", "watchlist", "ic"],
                "status": "BLOCKED_REVISION" if needs else "REUSED_OWNED_INPUTS",
                "new_event": event.record_id not in prior_event_ids,
                "forward_eps_mutated": False, "acknowledged_model_id": model.record_id if acknowledged else None})
    if blocked_models and state.get("research"):
        research = state["research"]
        for key in ("valuations", "entries", "ranking"):
            research[key] = [r for r in research[key] if r["ticker"] not in blocked_models]
        for c in state["coverage"]:
            if c["ticker"] in blocked_models:
                c.update(outcome="BLOCKED_EVIDENCE", reason="Event requires owned model revision")
        research["summary"]["valuation_status"] = "PARTIAL"
        research["summary"]["eligible_count"] = len({r["ticker"] for r in research["valuations"]})
        research["summary"]["coverage_counts"] = {name: sum(c["outcome"] == name for c in state["coverage"])
                                                 for name in research["summary"]["coverage_counts"]}
        research["ranking"] = [{"rank": i, **row} for i, row in enumerate(sorted(
            [r for r in research["valuations"] if r["scenario"] == "base"],
            key=lambda r: (-Decimal(r["gross_return"]), r["ticker"])), 1)][:10]
    out["macro"] = [{**meta(m, "macro_news"), **m.model_dump(mode="json")} for m in data.macro]
    out["scenarios"] = [{**meta(m, "macro_news"), **m.model_dump(mode="json"), "evidence_kind": "HYPOTHETICAL_SCENARIO"} for m in data.macro_scenarios]
    for m in data.macro:
        if not good(m):
            gap(m.ticker, "macro_news", "STALE_OR_UNVERIFIED_MACRO", "Refresh dated observation", m.source_ids)
    method = data.alert_methodology
    alert_enabled = bool(good(method) and method.approved_replacement and method.methodology_id)
    out["alerts"].append({"status": "ENABLED_MANUAL_EVALUATION" if alert_enabled else "DISABLED_UNRECOVERED_METHODOLOGY",
        "threshold": "STRICTLY_GREATER_THAN_8.0", "bull_triggered": method.bull_score > 8 if alert_enabled and method.bull_score is not None else None,
        "bear_triggered": method.bear_score > 8 if alert_enabled and method.bear_score is not None else None,
        "methodology_id": method.methodology_id if method else None, "scheduled": False})
    risk_good, sizing = risk_outputs(bundle, state, data, out, series, good, meta, gap)
    timing_rows = {r["ticker"]: r for r in out["timing"]}
    for entry in state.get("research", {}).get("entries", []):
        t = timing_rows.get(entry["ticker"])
        imported_model = model_by_ticker[entry["ticker"]]
        timing_passed = bool(t and t["status"] == "ELIGIBLE" and t["rs_percentile"] is not None and t["stage"] == "STAGE_2" and not t["extended"])
        entry["resolved_timing_gate"] = "PASSED" if timing_passed and imported_model.timing_gate != "BLOCKED" else "BLOCKED"
        entry["resolved_risk_gate"] = "PASSED" if risk_good and imported_model.risk_gate != "BLOCKED" else "BLOCKED"
        entry["entry_status"] = "REVIEW" if entry["resolved_timing_gate"] == entry["resolved_risk_gate"] == "PASSED" else "BLOCKED"
        entry["gate_upstream_ids"] = [r for r in (t.get("record_id") if t else None, data.risk_limits.record_id if data.risk_limits else None) if r]
        entry["gate_source_ids"] = sorted(set((t.get("source_ids", []) if t else []) + (data.risk_limits.source_ids if data.risk_limits else [])))
    entry_rows = {r["ticker"]: r for r in state.get("research", {}).get("entries", [])}
    current_prices = {p.ticker: p for p in bundle.prices}
    held = {h["ticker"] for h in state["holdings"] if Decimal(h["quantity"]) > 0}
    catalyst_by_id = {c.record_id: c for c in data.catalysts}
    for c in data.catalysts:
        out["catalysts"].append({**meta(c, "ic_risk"), **c.model_dump(mode="json"),
            "days_to_start": (c.window_start-cutoff).days,
            "window_bucket": "30_DAY" if 0 <= (c.window_start-cutoff).days <= 30 else "90_DAY" if 0 <= (c.window_start-cutoff).days <= 90 else "OUTSIDE_90_DAYS_OR_PAST"})
    for candidate in data.candidates:
        p, t, entry = current_prices.get(candidate.ticker), timing_rows.get(candidate.ticker), entry_rows.get(candidate.ticker)
        catalyst_records = [catalyst_by_id.get(i) for i in candidate.catalyst_ids]
        if any(c is None or c.ticker != candidate.ticker for c in catalyst_records):
            raise ValueError("candidate catalyst IDs must resolve to the same ticker")
        fresh_price = bool(p and p.close is not None and latest == p.session_date and sources[p.source_id].evidence_label == "CONFIRMED")
        gates = {"evidence": good(candidate) and candidate.next_review >= cutoff and fresh_price and candidate.ticker not in uncertain_events,
            "valuation": bool(entry and candidate.desired_entry <= Decimal(entry["entry_ceiling"]) and candidate.ticker not in blocked_models),
            "portfolio_fit_risk": bool(entry and entry.get("resolved_risk_gate") == "PASSED") and risk_good and candidate.ticker in sizing and sizing[candidate.ticker]["quantity_cap"] is not None and sizing[candidate.ticker]["quantity_cap"] > 0,
            "catalyst": bool(catalyst_records) and all(good(c) and c.window_end >= cutoff and (c.window_start-cutoff).days <= 90 for c in catalyst_records),
            "timing": bool(entry and entry.get("resolved_timing_gate") == "PASSED" and t and t["status"] == "ELIGIBLE" and t["rs_percentile"] is not None and t["stage"] == "STAGE_2" and not t["extended"])}
        stage = candidate.requested_stage
        if stage == "READY" and not all(gates.values()):
            stage = "PRICE_WATCH"
        monitoring = "STALE" if not gates["evidence"] else "TRIGGERED" if p.close <= candidate.desired_entry else "APPROACHING" if p.close <= candidate.desired_entry*(ONE+candidate.approach_fraction) else "WATCHING"
        out["watchlist"].append({**meta(candidate, "watchlist"), **candidate.model_dump(mode="json"),
            "candidate_type": "ADD_ON" if candidate.ticker in held else "NEW_POSITION", "stage": stage,
            "monitoring_state": monitoring, "gates": gates, "decision_status": "PROPOSED",
            "sizing": sizing.get(candidate.ticker), "upstream_valuation_id": entry["record_id"] if entry else None,
            "upstream_timing_id": t.get("record_id") if t else None})
    candidates = {r["record_id"]: r for r in out["watchlist"]}
    proposals = {p.ticker: p for p in data.proposals}
    for ticker in sorted(held | set(proposals)):
        proposal = proposals.get(ticker)
        action, reason = (proposal.action, proposal.reason) if proposal else ("REVIEW", "No explicit IC proposal imported")
        candidate = candidates.get(proposal.candidate_id) if proposal and proposal.candidate_id else None
        if proposal and proposal.candidate_id and candidate is None:
            prior_candidate = provenance.get(proposal.candidate_id)
            if not prior_candidate or prior_candidate["group"] != "candidates" or prior_candidate["payload"]["ticker"] != ticker:
                raise ValueError("IC proposal candidate must resolve to the same ticker")
            action, reason = "REVIEW", "Linked candidate superseded; historical proposal retained"
        if candidate and candidate["ticker"] != ticker:
            raise ValueError("IC proposal candidate must resolve to the same ticker")
        if proposal and not good(proposal):
            action, reason = "REVIEW", "Stale or unverified proposal; original proposal retained"
        if action in {"ADD", "ACCUMULATE"} and (not candidate or candidate["stage"] != "READY" or candidate["monitoring_state"] != "TRIGGERED" or not risk_good):
            action, reason = "REVIEW", "ADD/ACCUMULATE blocked by readiness or risk dependencies"
        out["ic_actions"].append({**(meta(proposal, "ic_risk") if proposal else {"ticker": ticker, "owner": "ic_risk", "run_id": run_id}),
            "proposed_action": proposal.action if proposal else None, "action": action, "reason": reason,
            "decision_status": "PROPOSED", "execution_status": "NOT_EXECUTED",
            "confidence": proposal.confidence if proposal else "LOW",
            "invalidation": proposal.invalidation if proposal else None,
            "opportunity_cost": proposal.opportunity_cost if proposal else None,
            "candidate_id": proposal.candidate_id if proposal else None,
            "dependencies": ["verified owned valuation", "verified timing", "reconciled holdings", "confirmed risk limits"]})
    if not data.macro:
        gap(None, "macro_news", "MISSING_MACRO_OBSERVATIONS", "Import Pakistan/global observations with source dates")
    # No legacy tabs/formulas were supplied. A new workbook must not masquerade as verified compatibility.
    gap(None, "migration", "LEGACY_DATASTORE_NOT_MIGRATED", "Inspect and map the real PSX_Mean_Reversion_DataStore.xlsx before claiming parity")
    out["summary"] = {"integration_status": "PARTIAL" if out["refresh_queue"] else "COMPLETE",
        "required_timing_count": len(needed), "eligible_timing_count": len(eligible_rows),
        "latest_completed_session": latest.isoformat() if latest else None, "sizing_status": "ILLUSTRATIVE_ONLY" if bundle.mode == "DEMO" and risk_good else "RESEARCH_CAPS_ONLY" if risk_good else "BLOCKED",
        "legacy_datastore_status": "NOT_MIGRATED", "schedules_active": False, "mode": bundle.mode}
    all_input_sources = sorted({s for _, r in current for s in r.source_ids} | {a.source_id for h in data.histories for a in h.actions} | {p.source_id for p in bundle.prices}
                               | {bundle.opening.source_id, bundle.closing.source_id}
                               | {s for r in state.get("research", {}).get("valuations", []) for s in r["source_ids"]})
    policy_ids = [r.record_id for r in (data.timing_policy, data.risk_limits) if r]
    upstream = sorted({r["run_id"] for r in history} | {r["run_id"] for r in state.get("research", {}).get("valuations", [])})
    for key in SHEETS.values():
        for row in out[key]:
            identity = {k: row.get(k) for k in ("ticker", "row_kind", "name", "scenario", "sector", "left", "right", "field", "reason", "trade_index")}
            row.setdefault("record_id", key + "." + digest(dumps(identity))[:16])
            row.setdefault("schema_version", "3.0")
            row.setdefault("ticker", None)
            row.setdefault("owner", "price_history" if key in {"timing", "sectors", "mean_reversion", "backtests", "backtest_trades"} else "macro_news" if key in {"macro", "scenarios", "events", "alerts"} else "ic_risk")
            row.setdefault("run_id", run_id)
            row.setdefault("market_cutoff", cutoff.isoformat())
            row.setdefault("effective_date", cutoff.isoformat())
            row.setdefault("source_ids", all_input_sources)
            row.setdefault("assumption_ids", policy_ids)
            row.setdefault("upstream_run_ids", upstream)
            row.setdefault("units", "PKR / shares / fraction as named; percentile 0–100")
            row.setdefault("confidence", "SYNTHETIC" if bundle.mode == "DEMO" else "SOURCE_DECLARED")
            row.setdefault("freshness", "CURRENT_AT_DECLARED_CUTOFF")
            row.setdefault("validation_status", "BLOCKED" if str(row.get("status", "")).startswith(("BLOCKED", "INSUFFICIENT", "DISABLED")) else "VALIDATED")
            row.setdefault("model_version", "integrated-reference-v1")
    out = numbers(out)
    # Preserve record lineage for unchanged derived facts, including check results.
    for key in SHEETS.values():
        for i, row in enumerate(out[key]):
            old_row = next((r for r in old.get(key, []) if r.get("record_id") == row.get("record_id")
                            and r.get("ticker") == row.get("ticker") and r.get("scenario") == row.get("scenario")
                            and r.get("trade_index") == row.get("trade_index") and r.get("sector") == row.get("sector") and r.get("left") == row.get("left") and r.get("right") == row.get("right")), None)
            ignored = {"run_id", "input_hash", "upstream_run_ids", "new_event"}
            if old_row and {k: v for k, v in row.items() if k not in ignored} == {k: v for k, v in old_row.items() if k not in ignored}:
                out[key][i] = deepcopy(old_row)
    state["integration"] = out


def risk_outputs(bundle, state, data, out, series, good, meta, gap):
    limits = data.risk_limits
    assets = Decimal(state["summary"]["total_assets"]) if state["summary"]["total_assets"] is not None else None
    cash = Decimal(state["summary"]["cash"]) if state["summary"]["cash"] is not None else None
    factors = {f.ticker: f for f in data.factors}
    securities = {s.ticker: s for s in bundle.securities}
    sources = {s.source_id: s for s in bundle.sources}
    held = [h for h in state["holdings"] if Decimal(h["quantity"]) > 0]
    portfolio_ids = [bundle.opening.source_id, bundle.closing.source_id] + [t.source_id for t in bundle.transactions] + [p.source_id for p in bundle.prices]
    current = bool(assets and assets > 0 and cash is not None and not state["reconciliation"]
                   and (bundle.market_cutoff-bundle.closing.timestamp.date()).days <= bundle.policy.holdings_max_age_days
                   and all(h["freshness"] == "CURRENT" and h["market_value"] is not None for h in held)
                   and all(sources[s].evidence_label == "CONFIRMED" for s in portfolio_ids))
    limits_good = bool(good(limits) and limits.user_confirmed)
    factor_good = all(h["ticker"] in factors and good(factors[h["ticker"]]) for h in held)
    owned = state.get("research", {}).get("valuations", [])
    scenario_coverage = all(all(any(r["ticker"] == h["ticker"] and r["scenario"] == scenario for r in owned) for h in held)
                            and len({r["horizon_years"] for r in owned if r["scenario"] == scenario and r["ticker"] in {h["ticker"] for h in held}}) == 1
                            for scenario in ("bear", "base", "bull"))
    consistent_limits = not (limits_good and bundle.policy.max_position_weight is not None and bundle.policy.max_position_weight != limits.max_position_weight)
    timing_quality = {r["ticker"]: r["status"] for r in out["timing"]}
    market_quality = all(timing_quality.get(h["ticker"]) == "ELIGIBLE" for h in held)
    gate = current and limits_good and factor_good and scenario_coverage and consistent_limits and market_quality
    if not consistent_limits:
        gap(None, "ic_risk", "CONFLICTING_POSITION_LIMITS", "Reconcile portfolio policy with the authoritative risk limits")
    state["summary"]["data_gate_status"] = "PASSED" if current and bundle.mode != "DEMO" else "BLOCKED"
    sector_values, factor_values, position_values = {}, {}, {}
    for h in held:
        value = Decimal(h["market_value"]) if h["market_value"] is not None else None
        position_values[h["ticker"]] = value
        if value is None:
            sector_values[h["sector"]] = None
        elif sector_values.get(h["sector"], ZERO) is not None:
            sector_values[h["sector"]] = sector_values.get(h["sector"], ZERO) + value
        if h["ticker"] in factors and good(factors[h["ticker"]]):
            for factor in factors[h["ticker"]].factors:
                if value is None:
                    factor_values[factor] = None
                elif factor_values.get(factor, ZERO) is not None:
                    factor_values[factor] = factor_values.get(factor, ZERO) + value
    if not factor_good:
        factor_values = {factor: None for factor in factor_values}
    violations = []
    for kind, mapping, maximum in (("POSITION", position_values, limits.max_position_weight if limits_good else None),
                                   ("SECTOR", sector_values, limits.max_sector_weight if limits_good else None),
                                   ("FACTOR", factor_values, limits.max_factor_weight if limits_good else None)):
        for name, value in sorted(mapping.items()):
            weight = value / assets if value is not None and assets else None
            exceeded = weight > maximum if maximum is not None and weight is not None else None
            if exceeded:
                violations.append(kind + ":" + name)
            out["risk"].append({"row_kind": kind, "name": name, "value": value, "weight_total_sleeve": weight,
                                "max_weight": maximum, "limit_exceeded": exceeded, "basis": "TOTAL_SLEEVE_INCLUDING_CASH"})
    if limits_good and assets and cash is not None and cash / assets < limits.minimum_cash_weight:
        violations.append("MINIMUM_CASH")
    gate = gate and not violations
    if limits_good:
        state["data_gaps"] = [g for g in state["data_gaps"] if g["reason"] != "UNCONFIGURED_RISK_LIMITS"]
    if not gate:
        gap(None, "ic_risk", "BLOCKED_RISK_OR_SIZING", "Confirm risk limits, reconcile/freshen portfolio and factors; resolve breaches")
    out["risk"].append({"row_kind": "SUMMARY", "name": "portfolio", "risk_gate": "PASSED" if gate else "BLOCKED",
        "hhi_equity": state["summary"].get("hhi"), "effective_positions": state["summary"].get("effective_positions"),
        "violations": violations, "price_history_coverage": "FULL" if market_quality else "PARTIAL", "factor_coverage": "FULL" if factor_good else "PARTIAL", "scenario_coverage": "FULL" if scenario_coverage else "PARTIAL",
        "limits_id": limits.record_id if limits else None,
        "source_ids": sorted(set(portfolio_ids + (limits.source_ids if limits else []) + [s for f in data.factors for s in f.source_ids])),
        "assumption_ids": [limits.record_id] if limits else [], "sizing_status": "RESEARCH_CAPS_ONLY" if gate else "BLOCKED"})
    for name in ("bear", "base", "bull"):
        rows = {r["ticker"]: r for r in state.get("research", {}).get("valuations", []) if r["scenario"] == name}
        complete = bool(current and held and all(h["ticker"] in rows for h in held))
        horizons = {rows[h["ticker"]]["horizon_years"] for h in held if h["ticker"] in rows}
        complete = complete and len(horizons) == 1
        price_value = income = None
        if complete:
            price_value = sum((Decimal(h["quantity"]) * Decimal(rows[h["ticker"]]["horizon_exit_price"]) for h in held), ZERO)
            income = sum((Decimal(h["quantity"]) * Decimal(rows[h["ticker"]]["horizon_dividends"]) for h in held), ZERO)
        out["risk"].append({"row_kind": "SCENARIO", "name": name, "scenario": name,
            "horizon_years": next(iter(horizons)) if len(horizons) == 1 else None,
            "status": "CALCULATED" if complete else "BLOCKED_INCOMPLETE_OWNED_VALUATIONS",
            "scenario_assets": cash + price_value + income if complete else None,
            "price_return": (cash + price_value - assets) / assets if complete else None,
            "income_return": income / assets if complete else None,
            "total_return": (cash + price_value + income - assets) / assets if complete else None,
            "tax_basis": "GROSS", "source_ids": sorted({s for h in held if h["ticker"] in rows for s in rows[h["ticker"]]["source_ids"]}),
            "upstream_run_ids": sorted({rows[h["ticker"]]["run_id"] for h in held if h["ticker"] in rows})})
    if limits_good:
        for left, right in combinations(sorted(h["ticker"] for h in held), 2):
            count, result = 0, None
            if left in series and right in series:
                a = {b["session_date"]: b["close"] for b in series[left]}
                b = {b["session_date"]: b["close"] for b in series[right]}
                dates = sorted(set(a) & set(b))[-limits.correlation_lookback-1:]
                x = [a[t] / a[s] - ONE for s, t in zip(dates, dates[1:])]
                y = [b[t] / b[s] - ONE for s, t in zip(dates, dates[1:])]
                count = len(x)
                result = correlation(x, y, limits.min_correlation_observations)
            out["correlations"].append({"left": left, "right": right, "observations": count,
                "correlation": result, "return_basis": "SYNCHRONIZED_SPLIT_ADJUSTED_PRICE",
                "lookback_sessions": limits.correlation_lookback,
                "status": "CALCULATED" if result is not None else "INSUFFICIENT_HISTORY_OR_ZERO_VARIANCE"})
    timing = {r["ticker"]: r for r in out["timing"] if r["status"] == "ELIGIBLE"}
    sizing = {}
    for c in data.candidates:
        p = next((p for p in bundle.prices if p.ticker == c.ticker), None)
        t = timing.get(c.ticker)
        candidate_factors = factors.get(c.ticker)
        cap = None
        reasons = []
        if not gate:
            reasons.append("portfolio/risk gate blocked")
        if not good(c):
            reasons.append("stale or unverified candidate inputs")
        if c.requested_target_weight is None:
            reasons.append("target weight is unconfigured")
        if not p or p.close is None or p.close <= c.stop_price or not t or p.session_date.isoformat() != t.get("latest_session") or sources[p.source_id].evidence_label != "CONFIRMED":
            reasons.append("missing price or invalid stop relative to current price")
        if not t or not good(candidate_factors) or c.ticker not in securities:
            reasons.append("missing liquid timing history, sector or factor coverage")
        if not reasons:
            price = p.close
            remaining_position = min(limits.max_position_weight, c.requested_target_weight) * assets - position_values.get(c.ticker, ZERO)
            remaining_sector = limits.max_sector_weight * assets - sector_values.get(securities[c.ticker].sector, ZERO)
            remaining_factor = min(limits.max_factor_weight * assets - factor_values.get(f, ZERO) for f in candidate_factors.factors)
            remaining_cash = cash - assets * limits.minimum_cash_weight
            money = max(ZERO, min(remaining_position, remaining_sector, remaining_factor, remaining_cash))
            cap = min(money / price, assets * limits.per_trade_risk_budget / (price-c.stop_price),
                      t["average_traded_value"] * limits.max_daily_participation / price).to_integral_value(rounding=ROUND_FLOOR)
        sizing[c.ticker] = {"quantity_cap": cap, "status": "ILLUSTRATIVE_ONLY" if cap is not None and bundle.mode == "DEMO" else "PROPOSED_CAP" if cap is not None else "BLOCKED",
            "reasons": reasons, "target_weight": c.requested_target_weight,
            "limits_id": limits.record_id if limits else None, "basis": "Additional whole shares; no orders or trades"}
    # Never change accepted positions or mark a cap as an executable instruction.
    state["summary"]["sizing_status"] = "BLOCKED" if not gate or bundle.mode == "DEMO" else "RESEARCH_CAPS_ONLY"
    state["summary"]["sizing_reason"] = "Illustrative/proposed risk caps only; explicit execution is outside scope"
    return gate, sizing
