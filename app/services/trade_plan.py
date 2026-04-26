"""Entry / Stop / Target / R:R from daily OHLC bars.

All values are diagnostics. Size suggestion is (1% of portfolio) / (entry - stop)
and is computed client-side from a user-entered portfolio value — the backend
just exposes the per-share risk (entry - stop) so the frontend can scale it.
"""
from __future__ import annotations

from typing import Any


def _ema(values: list[float], period: int) -> list[float]:
    """Exponential moving average. Returns one EMA value per input value
    *starting from index `period - 1`* (seeded with an SMA of the first `period`)."""
    if len(values) < period:
        return []
    k = 2.0 / (period + 1)
    sma_seed = sum(values[:period]) / period
    out: list[float] = [sma_seed]
    for v in values[period:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def _rsi_wilder(closes: list[float], period: int = 14) -> float | None:
    """Wilder's RSI — the canonical (1978) form. Returns the most recent RSI
    value in [0, 100], or None if not enough data."""
    if len(closes) < period + 1:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(0.0, diff))
        losses.append(max(0.0, -diff))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict | None:
    """Standard MACD(12,26,9). Returns {macd, signal, histogram, crossover}
    where crossover ∈ {"bull", "bear", None} based on the last 3 bars."""
    if len(closes) < slow + signal:
        return None
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    # Align to slow series (it's shorter)
    offset = len(ema_fast) - len(ema_slow)
    macd_line = [ema_fast[i + offset] - ema_slow[i] for i in range(len(ema_slow))]
    signal_line = _ema(macd_line, signal)
    if len(signal_line) < 2:
        return None
    # Align macd to signal
    sig_offset = len(macd_line) - len(signal_line)
    macd_aligned = macd_line[sig_offset:]

    last_macd = macd_aligned[-1]
    last_signal = signal_line[-1]
    last_hist = last_macd - last_signal

    # Detect a crossover in the last 3 bars (fresh signal)
    crossover: str | None = None
    lookback = min(3, len(signal_line) - 1)
    for i in range(-lookback, 0):
        prev_d = macd_aligned[i - 1] - signal_line[i - 1]
        curr_d = macd_aligned[i] - signal_line[i]
        if prev_d <= 0 and curr_d > 0:
            crossover = "bull"
            break
        if prev_d >= 0 and curr_d < 0:
            crossover = "bear"
            break

    return {
        "macd": last_macd,
        "signal": last_signal,
        "histogram": last_hist,
        "crossover": crossover,
    }


def _atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float | None:
    """Average True Range over `period` bars. Returns None if insufficient data."""
    n = len(closes)
    if n < period + 1 or len(highs) != n or len(lows) != n:
        return None
    trs: list[float] = []
    for i in range(1, n):
        h, l, prev_c = highs[i], lows[i], closes[i - 1]
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)
    # Wilder's smoothing: start with simple average of first `period` TRs,
    # then smooth forward. For MVP a simple trailing mean is fine.
    window = trs[-period:]
    if len(window) < period:
        return None
    return sum(window) / period


def _swing_low(lows: list[float], lookback: int = 10) -> float | None:
    if not lows:
        return None
    w = lows[-lookback:] if len(lows) >= lookback else lows
    return min(w) if w else None


def _recent_high(highs: list[float], lookback: int = 20) -> float | None:
    if not highs:
        return None
    w = highs[-lookback:] if len(highs) >= lookback else highs
    return max(w) if w else None


def compute_trade_plan(
    bars: list[dict[str, Any]],
    *,
    atr_mult_stop: float = 2.0,
    atr_mult_target1: float = 2.0,
    atr_mult_target2: float = 4.0,
    breakout_trigger: bool = False,
) -> dict[str, Any] | None:
    """Compute an entry/stop/target plan from daily OHLC bars.

    `breakout_trigger=True` uses the 20d high as a breakout entry trigger;
    otherwise entry = last close.

    Returns None if not enough data. Never invents numbers.
    """
    if not bars or len(bars) < 20:
        return None

    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    closes = [float(b["close"]) for b in bars]

    atr = _atr(highs, lows, closes, period=14)
    if atr is None or atr <= 0:
        return None

    last_close = closes[-1]
    if last_close <= 0:
        return None

    swing_low = _swing_low(lows, lookback=10)
    recent_high = _recent_high(highs, lookback=20)

    # Entry
    if breakout_trigger and recent_high is not None:
        entry = max(last_close, recent_high)
    else:
        entry = last_close

    # Stop: tighter of (entry - 2*ATR) vs recent swing low
    atr_stop = entry - atr_mult_stop * atr
    candidate_stops = [atr_stop]
    if swing_low is not None and swing_low > 0:
        candidate_stops.append(swing_low)
    stop = max(candidate_stops)  # "tighter" = closer to entry = higher stop (for long)
    # Safety: if stop ≥ entry, widen to the ATR stop
    if stop >= entry:
        stop = atr_stop
    if stop <= 0 or stop >= entry:
        return None

    risk_per_share = entry - stop
    if risk_per_share <= 0:
        return None

    target1 = entry + atr_mult_target1 * atr
    target2 = entry + atr_mult_target2 * atr

    rr1 = (target1 - entry) / risk_per_share if risk_per_share > 0 else None
    rr2 = (target2 - entry) / risk_per_share if risk_per_share > 0 else None

    # Confirmation indicators — RSI & MACD over the same close series.
    rsi = _rsi_wilder(closes, period=14)
    macd_info = _macd(closes)
    indicators: list[str] = []
    if rsi is not None:
        if rsi >= 70:
            indicators.append("Overbought")
        elif rsi <= 30:
            indicators.append("Oversold")
    if macd_info and macd_info["crossover"] == "bull":
        indicators.append("MACD↑")
    elif macd_info and macd_info["crossover"] == "bear":
        indicators.append("MACD↓")

    # Donchian 20d-high breakout — Turtle Trading classic.
    if recent_high is not None and last_close >= recent_high * 0.998:
        indicators.append("20d HIGH")
    elif swing_low is not None and last_close <= swing_low * 1.002:
        indicators.append("20d LOW")

    # Relative volume vs 30d average — institutional confirmation
    rel_volume = None
    volumes = [float(b.get("volume") or 0) for b in bars]
    recent_volumes = [v for v in volumes[-30:] if v > 0]
    today_vol = volumes[-1] if volumes else 0
    if recent_volumes and today_vol > 0:
        avg_vol = sum(recent_volumes) / len(recent_volumes)
        if avg_vol > 0:
            rel_volume = today_vol / avg_vol
            if rel_volume >= 1.8:
                indicators.append(f"VOL {rel_volume:.1f}x")
            elif rel_volume <= 0.5:
                indicators.append("VOL ↓")

    return {
        "entry": round(entry, 2),
        "stop": round(stop, 2),
        "target1": round(target1, 2),
        "target2": round(target2, 2),
        "atr14": round(atr, 3),
        "riskPerShare": round(risk_per_share, 3),
        "rewardRisk1": round(rr1, 2) if rr1 is not None else None,
        "rewardRisk2": round(rr2, 2) if rr2 is not None else None,
        "lastClose": round(last_close, 2),
        "recentHigh20d": round(recent_high, 2) if recent_high is not None else None,
        "swingLow10d": round(swing_low, 2) if swing_low is not None else None,
        "breakoutTrigger": bool(breakout_trigger),
        # Confirmation indicators
        "rsi14": round(rsi, 1) if rsi is not None else None,
        "macd": round(macd_info["macd"], 3) if macd_info else None,
        "macdSignal": round(macd_info["signal"], 3) if macd_info else None,
        "macdHistogram": round(macd_info["histogram"], 3) if macd_info else None,
        "macdCross": macd_info["crossover"] if macd_info else None,
        "relativeVolume": round(rel_volume, 2) if rel_volume is not None else None,
        "indicators": indicators,
        "note": (
            "Entry / stop / target computed from ATR(14) on daily bars. "
            "RSI & MACD shown as confirmation overlays — they don't change the score."
        ),
    }
