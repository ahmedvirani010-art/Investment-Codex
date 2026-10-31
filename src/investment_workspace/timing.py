"""Decimal, split-adjusted PRICE returns; explicit session windows, no fetching."""

from decimal import Decimal

ZERO = Decimal(0)
ONE = Decimal(1)


def mean(values):
    return sum(values, ZERO) / len(values)


def adjusted_bars(history, cutoff):
    rows = []
    for bar in history.bars:
        if bar.session_date > cutoff:
            raise ValueError("history contains a post-cutoff bar")
        factor = ONE
        for action in history.actions:
            if bar.session_date < action.session_date <= cutoff:
                factor *= action.ratio
        rows.append({"session_date": bar.session_date,
                     **{key: getattr(bar, key) / factor for key in ("open", "high", "low", "close")},
                     "volume": bar.volume * factor, "traded_value": bar.traded_value})
    return rows


def reversion(closes, window):
    if len(closes) < window:
        return None
    values = closes[-window:]
    average = mean(values)
    deviation = mean([(v - average) ** 2 for v in values]).sqrt()
    return (values[-1] - average) / deviation if deviation else None


def indicators(bars, benchmark, policy):
    """Caller guarantees identical, verified completed sessions and liquidity."""
    closes = [b["close"] for b in bars]
    bench = [b["close"] for b in benchmark]
    lookback, lag = policy.relative_lookback, policy.momentum_lag
    required = max(lookback + lag + 1, policy.long_window + policy.slope_sessions,
                   policy.breakout_window + 1, policy.reversion_window, policy.liquidity_window)
    if len(closes) < required or len(bench) != len(closes):
        raise ValueError(f"insufficient synchronized history: need {required} completed sessions")
    relative = (closes[-1] / closes[-lookback-1]) / (bench[-1] / bench[-lookback-1]) - ONE
    previous = (closes[-lag-1] / closes[-lag-lookback-1]) / (bench[-lag-1] / bench[-lag-lookback-1]) - ONE
    short = mean(closes[-policy.short_window:])
    long = mean(closes[-policy.long_window:])
    old_long = mean(closes[-policy.long_window-policy.slope_sessions:-policy.slope_sessions])
    slope = long / old_long - ONE
    extension = closes[-1] / short - ONE
    if closes[-1] > long and short > long and slope > policy.flat_slope and relative > 0:
        stage = "STAGE_2"
    elif closes[-1] < long and short < long and slope < -policy.flat_slope and relative < 0:
        stage = "STAGE_4"
    elif abs(slope) <= policy.flat_slope:
        stage = "STAGE_1" if closes[-1] <= long else "STAGE_3"
    else:
        stage = "TRANSITION"
    z = reversion(closes, policy.reversion_window)
    calibrated = policy.calibration_status == "VALIDATED"
    signal = ("OVERSOLD" if z is not None and z <= policy.oversold_z else
              "OVERBOUGHT" if z is not None and z >= policy.overbought_z else "NEUTRAL") if calibrated and z is not None else "UNCALIBRATED" if not calibrated else "UNDEFINED_VARIANCE"
    return {"price_return": closes[-1] / closes[-lookback-1] - ONE,
            "benchmark_return": bench[-1] / bench[-lookback-1] - ONE,
            "relative_performance": relative, "rs_momentum": relative - previous,
            "short_sma": short, "long_sma": long, "sma_slope": slope, "stage": stage,
            "extension": extension, "extended": extension > policy.max_extension,
            "breakout": closes[-1] > max(b["high"] for b in bars[-policy.breakout_window-1:-1]),
            "z_score": z, "reversion_signal": signal,
            "average_traded_value": mean([b["traded_value"] for b in bars[-policy.liquidity_window:]]),
            "observations": len(bars), "lookback_sessions": lookback,
            "momentum_lag_sessions": lag, "return_basis": "SPLIT_ADJUSTED_PRICE",
            "stage_method": "DAILY_SMA_PROXY_V1", "formula_version": "timing-v1"}


def rank_rows(rows, minimum):
    eligible = [r for r in rows if r["status"] == "ELIGIBLE"]
    for row in rows:
        row["rank_universe_size"] = len(eligible)
        row["rs_percentile"] = None
    if len(eligible) < minimum:
        return
    for row in eligible:
        less = sum(r["relative_performance"] < row["relative_performance"] for r in eligible)
        ties = sum(r["relative_performance"] == row["relative_performance"] for r in eligible)
        row["rs_percentile"] = Decimal(100) * (Decimal(less) + Decimal(ties - 1) / 2) / (len(eligible) - 1)


def correlation(left, right, min_observations):
    if len(left) != len(right) or len(left) < min_observations:
        return None
    xbar, ybar = mean(left), mean(right)
    x = [v - xbar for v in left]
    y = [v - ybar for v in right]
    den = (sum((v * v for v in x), ZERO) * sum((v * v for v in y), ZERO)).sqrt()
    return sum((a * b for a, b in zip(x, y)), ZERO) / den if den else None


def backtest(bars, policy, memberships, ticker):
    """Long-only MR simulation: close signal -> next open, no current-bar fills.

    Parameters must predate start. Price-only returns exclude dividend cash.
    Membership must be known at each signal and fill date; callers verify sources.
    """
    if policy.backtest_start is None or policy.backtest_cost_rate is None or policy.calibration_status != "VALIDATED":
        return {"status": "BLOCKED", "reason": "Explicit start, fees and calibrated parameters required", "trades": []}
    start = policy.backtest_start
    if policy.effective_date > start or policy.valid_until < bars[-1]["session_date"]:
        return {"status": "BLOCKED", "reason": "Parameters not valid before test start/through test end", "trades": []}

    def member(day):
        snapshots = [m for m in memberships if m.effective_date <= day <= m.valid_until]
        if snapshots:
            latest = max(m.effective_date for m in snapshots)
            snapshots = [m for m in snapshots if m.effective_date == latest]
        if len(snapshots) != 1:
            raise ValueError("backtest needs unambiguous point-in-time membership")
        return ticker in snapshots[0].constituents

    rows = [b for b in bars if b["session_date"] >= start]
    try:
        for bar in rows:
            member(bar["session_date"])
    except ValueError as exc:
        return {"status": "BLOCKED", "reason": str(exc), "trades": []}
    closes = [b["close"] for b in bars]
    trades, entry, pending, equity = [], None, None, ONE
    fees = policy.backtest_cost_rate
    for i, bar in enumerate(bars):
        day = bar["session_date"]
        if day < start:
            continue
        if pending == "BUY" and member(day):
            entry = {"entry_date": day.isoformat(), "entry_price": bar["open"], "entry_cost": bar["open"] * (ONE + fees)}
        elif pending == "SELL" and entry:
            rate = bar["open"] * (ONE - fees) / entry["entry_cost"] - ONE
            trades.append({**entry, "exit_date": day.isoformat(), "exit_price": bar["open"], "return": rate})
            equity *= ONE + rate
            entry = None
        pending = None
        z = reversion(closes[max(0,i-policy.reversion_window+1):i+1], policy.reversion_window)
        if entry and (not member(day) or (z is not None and z >= 0)):
            pending = "SELL"
        elif entry is None and member(day) and z is not None and z <= policy.oversold_z:
            pending = "BUY"
    open_return = bars[-1]["close"] / entry["entry_cost"] - ONE if entry else None
    return {"status": "SIMULATED", "trades": trades, "closed_trade_count": len(trades),
            "closed_compounded_return": equity - ONE, "open_position": entry,
            "open_mark_return": open_return, "next_session_order": pending,
            "return_basis": "SPLIT_ADJUSTED_PRICE_EX_DIVIDENDS", "cost_rate": fees,
            "fill_rule": "NEXT_SESSION_OPEN", "limitations": "No slippage, taxes or market impact; no strategy efficacy claim"}
