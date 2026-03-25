"""
Rules-based Explosive Move Radar: probabilistic setup detection (not price guarantees).

Jump / Catalyst / Risk / Confidence scores are 0–100. Missing inputs degrade gracefully.

KNOWN WEAKNESSES (v1 rules — documented for maintainers):
- Keyword catalysts can false-positive on generic headlines; we now sqrt-damp hit counts.
- 1-day moves used to stack heavily with 3d/5d in the same bucket; momentum now down-weights
  bearish "volatility" and orphan spikes dampen jump.
- Low-dollar-volume names could still score high on RVOL alone; we now crush jump when dvol is tiny.
- No real float/cap/spread feeds yet — confidenceScore penalizes missing fields; "Low Float" is heuristic.
- Historical validation uses price-only unless articles are passed with as_of filtering.
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from app.models import Article, StockScore
from app.services.dashboards import resolve_stock_sector
from app.services.explosive_radar_data import DailyBarSeries, fetch_daily_bars_for_radar
from app.services.sp500 import get_sp500_entry

WEIGHTS_PATH = Path(__file__).resolve().parent.parent / "data" / "explosive_radar_weights.json"
# Aligns with explosive_radar_data MIN_BARS_RADAR — enough bars for RVOL + breakout windows.
MIN_BARS_FOR_FULL_RVOL = 25

# Deterministic setup taxonomy (prefer first match in classify_setup_deterministic).
SETUP_FRESH_IPO = "Fresh IPO Momentum"
SETUP_NEWS_BREAKOUT = "News Catalyst Breakout"
SETUP_LOW_LIQ_SPIKE = "Low Liquidity Spike"
SETUP_MULTI_DAY = "Multi-Day Momentum Continuation"
SETUP_GAP_GO = "Gap-and-Go Speculative Move"
SETUP_WEAK_QUALITY = "Weak Quality Spike"
SETUP_SECTOR_SYMPATHY = "Sector Sympathy Move"
SETUP_VOL_REVERSAL = "High Volume Reversal"
SETUP_NO_EDGE = "No Clear Edge"

# Back-compat aliases for filters / old mocks (map to new strings in filter if needed)
SETUP_LEGACY = {
    "Low Float Breakout": SETUP_LOW_LIQ_SPIKE,
    "News Catalyst Runner": SETUP_NEWS_BREAKOUT,
    "Speculative Momentum": SETUP_GAP_GO,
    "No Clear Setup": SETUP_NO_EDGE,
}

# Headlines + summaries scanned for catalyst themes (case-insensitive).
CATALYST_KEYWORD_GROUPS: dict[str, list[str]] = {
    "earnings": ["earnings", "eps", "guidance", "beat estimates"],
    "contract": ["contract", "award", "wins deal", "order worth"],
    "partnership": ["partnership", "collaboration", "teams up", "strategic alliance"],
    "acquisition": ["acquisition", "acquires", "merger", "takeover", "buyout"],
    "fda": ["fda", "approval", "clinical trial", "phase 3"],
    "ai": [" artificial intelligence", " ai ", "machine learning", " generative ai"],
    "defense": ["defense", "pentagon", "dod", "military"],
    "crypto": ["crypto", "bitcoin", "blockchain", "token"],
    "semiconductor": ["semiconductor", "chip", "foundry", "wafer"],
    "quantum": ["quantum"],
    "government": ["government", "federal", "subsidy", "grant"],
    "ipo": ["ipo", "goes public", "listing", "debut", "uplist"],
}

SYMPATHY_TERMS = ("sympathy", "peer", "laggard", "follow", "ripple", "group move")


def load_explosive_radar_weights() -> dict[str, float]:
    raw: dict[str, Any] = {}
    if WEIGHTS_PATH.exists():
        try:
            raw = json.loads(WEIGHTS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
    out: dict[str, float] = {}
    for k, v in raw.items():
        if k.startswith("_"):
            continue
        try:
            out[k] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def _clamp_score(x: float) -> int:
    return int(round(max(0.0, min(100.0, x))))


def _true_range(high: float, low: float, prev_close: float) -> float:
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def _atr_series(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float]:
    if len(closes) < period + 1:
        return []
    trs: list[float] = []
    for i in range(1, len(closes)):
        trs.append(_true_range(highs[i], lows[i], closes[i - 1]))
    atrs: list[float] = []
    for i in range(period - 1, len(trs)):
        window = trs[i - period + 1 : i + 1]
        atrs.append(sum(window) / len(window))
    return atrs


def _pct_change(closes: list[float], days: int) -> float | None:
    """Return fractional change over `days` calendar bars (e.g. days=1 is last close vs prior)."""
    if len(closes) < days + 1:
        return None
    old = closes[-(days + 1)]
    new = closes[-1]
    if old <= 0:
        return None
    return (new - old) / old


def _relative_volume(volumes: list[float], lookback: int = 20) -> float | None:
    if len(volumes) < lookback + 1:
        return None
    last = volumes[-1]
    hist = [v for v in volumes[-(lookback + 1) : -1] if v > 0]
    if not hist:
        return None
    avg = sum(hist) / len(hist)
    if avg <= 0:
        return None
    return last / avg


def _breakout_20d(closes: list[float]) -> bool | None:
    if len(closes) < 22:
        return None
    prior = closes[-22:-1]
    if not prior:
        return None
    return closes[-1] > max(prior)


def _gap_pct(opens: list[float], closes: list[float]) -> float | None:
    if len(opens) < 2 or len(closes) < 2:
        return None
    prev_c = closes[-2]
    o = opens[-1]
    if prev_c <= 0:
        return None
    return (o - prev_c) / prev_c


def _dollar_volume_last(volumes: list[float], closes: list[float]) -> float | None:
    if not volumes or not closes:
        return None
    if volumes[-1] <= 0 or closes[-1] <= 0:
        return None
    return volumes[-1] * closes[-1]


def _volatility_expansion_ratio(highs: list[float], lows: list[float], closes: list[float]) -> float | None:
    """Recent ATR / mean ATR of prior window; None if not enough data."""
    atrs = _atr_series(highs, lows, closes, 14)
    if len(atrs) < 11:
        return None
    recent = sum(atrs[-5:]) / 5
    prior = sum(atrs[-15:-5]) / 10
    if prior <= 0:
        return None
    return recent / prior


def _price_tier_score(price: float) -> float:
    """
    Softer preference for mid/small nominal prices where % moves often look larger in scans.
    Not a fundamental cap proxy — documented in reasons when used.
    """
    if price <= 0:
        return 0.0
    if 3 <= price <= 120:
        return 1.0
    if price < 3:
        return 0.55
    return max(0.2, 1.0 - min(0.8, (price - 120) / 400))


def _weighted_average(pairs: list[tuple[float, float]]) -> float:
    """pairs: (value 0..1, weight). Ignores weight<=0."""
    num = 0.0
    den = 0.0
    for val, w in pairs:
        if w <= 0:
            continue
        num += val * w
        den += w
    if den <= 0:
        return 0.0
    return num / den


def _scan_catalyst_keywords(text: str) -> tuple[int, list[str]]:
    t = f" {text.lower()} "
    matched_labels: list[str] = []
    hits = 0
    for label, kws in CATALYST_KEYWORD_GROUPS.items():
        for kw in kws:
            if kw in t:
                hits += 1
                matched_labels.append(label)
                break
    return hits, matched_labels


def _articles_for_ticker(
    articles: list[Article],
    ticker: str,
    *,
    max_age_days: int = 21,
    as_of: datetime | None = None,
) -> list[Article]:
    """
    Linked articles for ticker. If as_of is set (historical validation), only articles with
    published_at <= as_of (end of UTC day) and within max_age_days before as_of.
    """
    upper = ticker.upper()
    now = datetime.now(timezone.utc)
    if as_of is not None:
        ref = as_of if as_of.tzinfo else as_of.replace(tzinfo=timezone.utc)
        cutoff = ref - timedelta(days=max_age_days)
        upper_bound = ref
    else:
        cutoff = now - timedelta(days=max_age_days)
        upper_bound = now
    out: list[Article] = []
    for a in articles:
        if upper not in a.tickers:
            continue
        try:
            pub = a.published_at
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if pub < cutoff or pub > upper_bound:
            continue
        out.append(a)
    out.sort(key=lambda x: x.published_at, reverse=True)
    return out


def _recent_ipo_buzz(linked: list[Article]) -> bool:
    for a in linked[:12]:
        blob = f"{a.title} {a.summary}"
        if re.search(r"\bipo\b|goes public|listing|nasdaq debut|nyse debut", blob, re.I):
            return True
    return False


def _sector_sympathy_news(linked: list[Article]) -> bool:
    for a in linked[:15]:
        low = f"{a.title} {a.summary}".lower()
        if any(s in low for s in SYMPATHY_TERMS):
            return True
    return False


def _gap_continuation_ratio(
    gap: float | None,
    open_: float | None,
    close: float | None,
) -> float | None:
    """How much of the upside gap was held/extended by the close (0–1+). None if not applicable."""
    if gap is None or open_ is None or close is None or open_ <= 0:
        return None
    if gap <= 0.005:
        return None
    prev_implied = open_ / (1.0 + gap) if (1.0 + gap) != 0 else None
    if prev_implied is None or prev_implied <= 0:
        return None
    intraday = (close - open_) / open_
    if intraday < -0.02:
        return 0.05
    return max(0.0, min(1.5, intraday / max(gap, 1e-6)))


def _count_signal_agreements(
    *,
    change_1d: float | None,
    change_3d: float | None,
    change_5d: float | None,
    rvol: float | None,
    breakout: bool | None,
    catalyst_score: int,
    news_count: int,
    gap: float | None,
    open_: float | None,
    close: float | None,
    sector_sympathy: bool,
    keyword_labels: list[str],
) -> int:
    """Independent buckets aligning = higher-quality explosive context (0–6)."""
    n = 0
    if (change_3d or 0) >= 0.018 and (change_5d or 0) >= 0.018:
        n += 1
    if rvol is not None and rvol >= 2.0 and breakout is True:
        n += 1
    if catalyst_score >= 38 and news_count >= 1:
        n += 1
    if (rvol or 0) >= 2.0 and (change_1d or 0) >= 0.025 and catalyst_score >= 34:
        n += 1
    if gap and open_ and close and open_ > 0:
        body = (close - open_) / open_
        if gap >= 0.015 and body >= 0.003 and (change_1d or 0) >= 0:
            n += 1
    if news_count >= 2 and len(keyword_labels) >= 1:
        n += 1
    if sector_sympathy and news_count >= 1 and catalyst_score >= 30:
        n += 1
    return min(6, n)


def _dollar_volume_jump_mult(dvol: float | None, w: dict[str, float]) -> float:
    """
    Crush jump contribution when dollar liquidity is micro-cap style.
    Thresholds are USD approximations — not exchange quality metrics.
    """
    if dvol is None or dvol <= 0:
        return float(w.get("dvol_missing_jump_mult", 0.72))
    micro = float(w.get("dvol_micro_usd", 1_200_000))
    low = float(w.get("dvol_low_usd", 4_500_000))
    if dvol < micro:
        return float(w.get("dvol_micro_jump_mult", 0.42))
    if dvol < low:
        return float(w.get("dvol_low_jump_mult", 0.68))
    return 1.0


def _is_weak_quality(
    *,
    jump_score: int,
    confidence_score: int,
    catalyst_score: int,
    dvol: float | None,
    rvol: float | None,
    change_3d: float | None,
    liquidity: float,
) -> bool:
    """Thin, hype-only, or unconfirmed spikes — label explicitly."""
    if jump_score < 52:
        return False
    if confidence_score < 42 and jump_score >= 58:
        return True
    if dvol is not None and dvol < 650_000 and jump_score >= 55:
        return True
    if catalyst_score < 22 and jump_score >= 62 and (rvol or 0) < 2.0:
        return True
    if liquidity < 0.22 and jump_score >= 60 and (change_3d or 0) < 0.01:
        return True
    return False


def _compute_ranked_opportunity_score(
    jump: int,
    catalyst: int,
    risk: int,
    confidence: int,
    agreement_count: int,
    w: dict[str, float],
) -> int:
    """
    Transparent composite for ranking. Tunable via ranked_* coefficients in JSON.
    Linear mix then clamp — not a probability.
    """
    agr = float(agreement_count)
    raw = (
        float(w.get("ranked_jump_coef", 0.36)) * jump
        + float(w.get("ranked_catalyst_coef", 0.18)) * catalyst
        + float(w.get("ranked_confidence_coef", 0.22)) * confidence
        + float(w.get("ranked_agreement_coef", 3.4)) * agr
        - float(w.get("ranked_risk_coef", 0.32)) * risk
    )
    return _clamp_score(raw)


def _compute_confidence_score(
    *,
    bars: DailyBarSeries | None,
    bars_snapshot_only: bool,
    rvol: float | None,
    dvol: float | None,
    news_count: int,
    catalyst_score: int,
    jump_score: int,
    agreement_count: int,
    liquidity: float,
    data_flags: dict[str, bool],
    w: dict[str, float],
) -> tuple[int, list[str]]:
    """
    Data completeness + signal independence (not directional bullishness).
    Returns (score 0–100, human missing-field labels).
    """
    missing_labels: list[str] = []
    flag_labels = {
        "marketCap": "Market cap",
        "floatShares": "Reported float",
        "ipoDate": "Listing / IPO date",
        "bidAskSpread": "Bid/ask spread",
        "dilutionData": "Dilution / shelf data",
    }
    for k, lab in flag_labels.items():
        if not data_flags.get(k):
            missing_labels.append(lab)

    base = float(w.get("confidence_base", 52.0))
    conf = base

    if bars is not None and len(bars.closes) >= 30:
        conf += float(w.get("confidence_bars_bonus", 16.0))
    elif bars is not None and len(bars.closes) >= MIN_BARS_FOR_FULL_RVOL:
        conf += float(w.get("confidence_bars_partial_bonus", 8.0))

    if bars_snapshot_only:
        conf -= float(w.get("confidence_snapshot_penalty", 22.0))

    if rvol is not None:
        conf += float(w.get("confidence_rvol_bonus", 7.0))
    else:
        conf -= float(w.get("confidence_no_rvol_penalty", 9.0))

    if dvol is not None:
        if dvol >= float(w.get("dvol_healthy_usd", 12_000_000)):
            conf += 6.0
        elif dvol < float(w.get("dvol_low_usd", 4_500_000)):
            conf -= float(w.get("confidence_low_dvol_penalty", 12.0))
    else:
        conf -= 5.0

    if news_count >= 2:
        conf += float(w.get("confidence_news_bonus", 6.0))
    elif news_count == 1:
        conf += 3.0

    if news_count == 0 and jump_score >= 48:
        conf -= float(w.get("confidence_price_only_penalty", 14.0))

    if catalyst_score >= 45 and jump_score >= 40:
        conf += float(w.get("confidence_catalyst_align_bonus", 5.0))

    if agreement_count >= 4:
        conf += float(w.get("confidence_agreement_bonus", 10.0))
    elif agreement_count >= 2:
        conf += 5.0

    if liquidity < float(w.get("confidence_liquidity_floor", 0.28)):
        conf -= float(w.get("confidence_illiquidity_penalty", 11.0))

    conf -= float(w.get("confidence_missing_flag_penalty", 3.5)) * min(
        5, len(missing_labels)
    )

    return _clamp_score(conf), missing_labels


def classify_setup_deterministic(
    *,
    jump_score: int,
    catalyst_score: int,
    change_1d: float | None,
    change_3d: float | None,
    change_5d: float | None,
    rvol: float | None,
    gap: float | None,
    open_last: float | None,
    close_last: float | None,
    keyword_labels: list[str],
    news_count: int,
    low_float_heuristic: bool,
    sector_sympathy: bool,
    ipo_buzz: bool,
    liquidity: float,
    dvol: float | None,
    breakout: bool | None,
    weak_quality: bool,
) -> str:
    """
    Ordered, mutually exclusive labels. First match wins.
    """
    c1 = change_1d or 0.0
    c3 = change_3d or 0.0
    c5 = change_5d or 0.0
    gc = _gap_continuation_ratio(gap, open_last, close_last)

    if weak_quality:
        return SETUP_WEAK_QUALITY

    if c3 >= 0.02 and c5 >= 0.02 and jump_score >= 38 and (rvol or 0) >= 1.35:
        return SETUP_MULTI_DAY

    if gap and gap >= 0.02 and gc is not None and gc >= 0.4 and c1 >= -0.005:
        return SETUP_GAP_GO

    if catalyst_score >= 46 and breakout is True and news_count >= 1:
        return SETUP_NEWS_BREAKOUT

    if (liquidity <= 0.33 or low_float_heuristic) and (
        c1 >= 0.045 or (rvol or 0) >= 3.2
    ):
        return SETUP_LOW_LIQ_SPIKE

    if ipo_buzz and c3 >= 0.04 and jump_score >= 36:
        return SETUP_FRESH_IPO

    if sector_sympathy and catalyst_score >= 32 and news_count >= 1:
        return SETUP_SECTOR_SYMPATHY

    if c1 >= 0.035 and c5 <= -0.008 and (rvol or 0) >= 2.0:
        return SETUP_VOL_REVERSAL

    if jump_score < 30 and catalyst_score < 30:
        return SETUP_NO_EDGE

    return SETUP_NO_EDGE


def compute_explosive_radar_row(
    ticker: str,
    stock: StockScore,
    bars: DailyBarSeries | None,
    linked_articles: list[Article],
    weights: dict[str, float],
) -> dict[str, Any]:
    """
    Build one radar row dict matching the frontend/API contract (extended with confidence
    and ranked opportunity — additive fields for clients).
    """
    reasons: list[str] = []
    risk_notes: list[str] = []
    w = weights

    entry = get_sp500_entry(ticker)
    company = (entry or {}).get("name") or ticker
    sector = resolve_stock_sector(ticker)

    data_flags = {
        "marketCap": False,
        "floatShares": False,
        "ipoDate": False,
        "bidAskSpread": False,
        "dilutionData": False,
    }

    # --- Catalyst: sqrt damp on raw keyword hit counts to limit spam stacking
    keyword_hits_total = 0
    all_labels: list[str] = []
    for a in linked_articles:
        blob = f"{a.title} {a.summary} {a.source_excerpt}"
        hits, labels = _scan_catalyst_keywords(blob)
        keyword_hits_total += hits
        all_labels.extend(labels)
    keyword_labels = list(dict.fromkeys(all_labels))[:8]
    news_count = len(linked_articles)

    kw_norm = min(1.0, math.sqrt(max(0, keyword_hits_total) / 7.0)) if keyword_hits_total else 0.0
    news_norm = min(1.0, news_count / 5.0) if news_count else 0.0
    catalyst_pairs = [
        (kw_norm, float(w.get("catalyst_keyword_weight", 0.55))),
        (news_norm, float(w.get("catalyst_news_count_weight", 0.45))),
    ]
    catalyst_score = _clamp_score(_weighted_average(catalyst_pairs) * 100)
    if news_count:
        reasons.append(f"{news_count} recent headline(s) linked to this ticker")
    if keyword_labels:
        reasons.append(
            "Recent headlines match catalyst themes: " + ", ".join(keyword_labels[:6])
        )
    if not linked_articles:
        reasons.append("No linked headlines in the current snapshot — catalyst score is muted")

    bars_snapshot_only = bars is None
    change_1d = _pct_change(bars.closes, 1) if bars else None
    change_3d = _pct_change(bars.closes, 3) if bars else None
    change_5d = _pct_change(bars.closes, 5) if bars else None
    rvol = _relative_volume(bars.volumes, 20) if bars else None
    gap = _gap_pct(bars.opens, bars.closes) if bars else None
    breakout = _breakout_20d(bars.closes) if bars else None
    vol_x = _volatility_expansion_ratio(bars.highs, bars.lows, bars.closes) if bars else None
    dvol = _dollar_volume_last(bars.volumes, bars.closes) if bars else None
    open_last = bars.opens[-1] if bars and bars.opens else None
    close_last = bars.closes[-1] if bars and bars.closes else None

    price = bars.closes[-1] if bars and bars.closes else (stock.price or 0.0)
    if price <= 0:
        price = stock.price or 0.0

    if bars is None and (stock.price or 0) > 0:
        reasons.append(
            "Full OHLCV history unavailable — explosive-move metrics lean on cached quote fields "
            "and news only"
        )
        if change_1d is None:
            change_1d = stock.day_change
        if change_5d is None:
            change_5d = stock.momentum

    liquidity = float(stock.liquidity or 0.0)

    low_float_rvol = float(w.get("low_float_rvol_hint", 4.0))
    low_float_liq = float(w.get("low_float_liquidity_cap", 0.35))
    low_float_heuristic = bool(
        rvol is not None
        and rvol >= low_float_rvol
        and liquidity <= low_float_liq
        and not data_flags["floatShares"]
    )
    if low_float_heuristic:
        reasons.append(
            "High relative volume with lower liquidity score — possible tight-float-style behavior "
            "(heuristic; reported float not available)"
        )

    ipo_buzz = _recent_ipo_buzz(linked_articles)
    if ipo_buzz:
        reasons.append("Headlines reference IPO / listing / public debut themes (verify listing details independently)")

    sector_sympathy = _sector_sympathy_news(linked_articles)

    # --- Jump: structure features (then multiplicative quality gates — avoids junk RVOL spikes)
    jump_pairs: list[tuple[float, float]] = []
    if rvol is not None:
        rv_norm = min(1.0, max(0.0, (rvol - 1.0) / 5.0))
        jump_pairs.append((rv_norm, float(w.get("relative_volume_weight", 0.2))))
        reasons.append(f"Relative volume is {rvol:.2f}x the recent average")
    else:
        reasons.append("Relative volume: data unavailable (need more volume history)")

    for label, ch, days in (
        ("1-day", change_1d, 1),
        ("3-day", change_3d, 3),
        ("5-day", change_5d, 5),
    ):
        if ch is not None:
            mag = abs(ch)
            directional = max(0.0, ch) * 4.0
            vol_component = min(1.0, mag * 2.2)
            # Down-weight bearish volatility — it used to inflate "jump" on sell-offs.
            vol_adj = vol_component if ch >= 0 else vol_component * 0.22
            combined = min(1.0, 0.72 * min(1.0, directional) + 0.28 * vol_adj)
            if days == 3:
                jump_pairs.append((combined, float(w.get("momentum_3d_weight", 0.14))))
            elif days == 5:
                jump_pairs.append((combined, float(w.get("momentum_weight", 0.18))))
            elif days == 1:
                jump_pairs.append((combined, float(w.get("momentum_weight", 0.18)) * 0.55))
            reasons.append(f"{label} return is {ch*100:+.2f}%")

    if breakout is True:
        jump_pairs.append((1.0, float(w.get("breakout_weight", 0.1))))
        reasons.append("Price is above the prior 20-session closing high")
    elif breakout is False and bars is not None:
        jump_pairs.append((0.12, float(w.get("breakout_weight", 0.1))))

    if vol_x is not None:
        vx_norm = min(1.0, max(0.0, (vol_x - 1.0) / 0.8))
        jump_pairs.append((vx_norm, float(w.get("volatility_expansion_weight", 0.1))))
        reasons.append(f"Short-term volatility (ATR proxy) is expanded vs prior regime ({vol_x:.2f}x)")
    else:
        reasons.append("ATR / volatility expansion: insufficient history for full read")

    if gap is not None and abs(gap) >= 0.01:
        g_norm = min(1.0, abs(gap) / 0.08)
        jump_pairs.append((g_norm, float(w.get("gap_weight", 0.08))))
        reasons.append(f"Session gap vs prior close is {gap*100:+.2f}%")

    if dvol is not None and dvol > 0:
        dv_norm = min(1.0, math.log10(dvol + 1.0) / 8.5)
        jump_pairs.append((dv_norm, float(w.get("dollar_volume_weight", 0.1))))

    if price > 0:
        pt = _price_tier_score(price)
        jump_pairs.append((pt, float(w.get("price_tier_weight", 0.05))))
        if pt >= 0.85:
            reasons.append(
                "Nominal price sits in a range often associated with larger percentage swings in scans "
                "(not a quality judgment)"
            )

    if low_float_heuristic:
        jump_pairs.append((0.85, float(w.get("float_tightness_weight", 0.12))))
    if ipo_buzz:
        jump_pairs.append((0.75, float(w.get("ipo_recency_weight", 0.1))))

    jump_raw = _weighted_average(jump_pairs) * 100
    jump_raw *= _dollar_volume_jump_mult(dvol, w)

    c1 = change_1d or 0.0
    c3 = change_3d or 0.0
    gc_pre = _gap_continuation_ratio(gap, open_last, close_last)
    if c1 >= 0.065 and c3 < 0.014:
        jump_raw *= float(w.get("orphan_spike_jump_mult", 0.76))
        reasons.append("One-day surge with weak 3-day follow-through — jump score discounted")

    if gap and gap >= 0.028 and gc_pre is not None and gc_pre < 0.22:
        jump_raw *= float(w.get("gap_fade_jump_mult", 0.72))
        risk_notes.append("Gap up faded intraday — fragile continuation")

    if liquidity < 0.33 and not (breakout is True and (rvol or 0) >= 3.0):
        liq_scale = float(w.get("low_liquidity_jump_mult", 0.68)) + (1.0 - float(w.get("low_liquidity_jump_mult", 0.68))) * (
            liquidity / 0.33
        )
        jump_raw *= max(0.45, min(1.0, liq_scale))

    jump_score = _clamp_score(jump_raw)

    # --- Risk (stronger micro-liquidity + gap-fade + follow-through)
    risk_pairs: list[tuple[float, float]] = []
    liq_risk = 1.0 - min(1.0, max(0.0, liquidity))
    risk_pairs.append((liq_risk, float(w.get("liquidity_penalty_weight", 0.35))))
    if liquidity < 0.35:
        risk_notes.append("Liquidity score from the core model is on the lower side")

    if vol_x is not None and vol_x >= 1.35:
        vx_risk = min(1.0, (vol_x - 1.0) / 1.2)
        risk_pairs.append((vx_risk, float(w.get("volatility_penalty_weight", 0.3))))
        risk_notes.append("Volatility expansion elevates gap / reversal risk")

    if c1 >= 0.065 and c3 < 0.018 and (rvol is None or rvol < 2.2):
        risk_pairs.append((0.78, float(w.get("spike_risk_weight", 0.22))))
        risk_notes.append("Large one-day move without volume confirmation or 3-day follow-through")

    if c1 >= 0.15:
        risk_pairs.append((0.68, float(w.get("momentum_exhaustion_penalty_weight", 0.16))))
        risk_notes.append("Very large single-day move — elevated mean-reversion / volatility risk")

    if rvol is not None and rvol >= 8:
        risk_pairs.append((0.55, float(w.get("volatility_penalty_weight", 0.3)) * 0.5))
        risk_notes.append("Extremely elevated relative volume — flow can reverse quickly")

    if dvol is not None and dvol < float(w.get("dvol_micro_usd", 1_200_000)):
        risk_pairs.append((0.85, float(w.get("micro_dvol_risk_weight", 0.24))))
        risk_notes.append("Very low dollar volume — prints are easy to distort")
    elif dvol is None and bars is not None:
        risk_pairs.append((0.38, float(w.get("missing_dvol_risk_weight", 0.12))))
        risk_notes.append("Dollar volume unavailable — treat liquidity risk as uncertain")

    if gap and gap >= 0.03 and gc_pre is not None and gc_pre < 0.28:
        risk_pairs.append((0.62, float(w.get("gap_fade_risk_weight", 0.18))))

    if bars_snapshot_only:
        risk_pairs.append((0.45, float(w.get("snapshot_data_risk_weight", 0.14))))
        risk_notes.append("Score uses thin history / snapshot — forward path is less knowable")

    risk_score = _clamp_score(_weighted_average(risk_pairs) * 100)
    if not risk_notes:
        risk_notes.append("No extreme structural risk flags from this ruleset (still high-volatility context possible)")

    agreement_count = _count_signal_agreements(
        change_1d=change_1d,
        change_3d=change_3d,
        change_5d=change_5d,
        rvol=rvol,
        breakout=breakout,
        catalyst_score=catalyst_score,
        news_count=news_count,
        gap=gap,
        open_=open_last,
        close=close_last,
        sector_sympathy=sector_sympathy,
        keyword_labels=keyword_labels,
    )
    if agreement_count >= 3:
        reasons.append(
            f"Signal agreement: {agreement_count} independent buckets align (momentum, volume, catalyst, etc.)"
        )

    confidence_score, missing_data_fields = _compute_confidence_score(
        bars=bars,
        bars_snapshot_only=bars_snapshot_only,
        rvol=rvol,
        dvol=dvol,
        news_count=news_count,
        catalyst_score=catalyst_score,
        jump_score=jump_score,
        agreement_count=agreement_count,
        liquidity=liquidity,
        data_flags=data_flags,
        w=w,
    )

    weak_quality = _is_weak_quality(
        jump_score=jump_score,
        confidence_score=confidence_score,
        catalyst_score=catalyst_score,
        dvol=dvol,
        rvol=rvol,
        change_3d=change_3d,
        liquidity=liquidity,
    )

    setup_type = classify_setup_deterministic(
        jump_score=jump_score,
        catalyst_score=catalyst_score,
        change_1d=change_1d,
        change_3d=change_3d,
        change_5d=change_5d,
        rvol=rvol,
        gap=gap,
        open_last=open_last,
        close_last=close_last,
        keyword_labels=keyword_labels,
        news_count=news_count,
        low_float_heuristic=low_float_heuristic,
        sector_sympathy=sector_sympathy,
        ipo_buzz=ipo_buzz,
        liquidity=liquidity,
        dvol=dvol,
        breakout=breakout,
        weak_quality=weak_quality,
    )

    ranked_opportunity_score = _compute_ranked_opportunity_score(
        jump_score,
        catalyst_score,
        risk_score,
        confidence_score,
        agreement_count,
        w,
    )

    if catalyst_score >= 42 and news_count >= 1:
        setup_driver = "catalyst-backed"
    elif jump_score >= 52 and catalyst_score < 28:
        setup_driver = "price-driven"
    else:
        setup_driver = "mixed"

    fragile_setup = bool(
        (risk_score >= 58 and confidence_score < 52)
        or (dvol is not None and dvol < 2_000_000 and jump_score >= 56)
        or (gap and gap >= 0.025 and gc_pre is not None and gc_pre < 0.32)
        or (c1 >= 0.07 and c3 < 0.012)
    )

    if setup_driver == "price-driven" and jump_score >= 55:
        reasons.append("Setup is mostly price-driven — narrative confirmation is thin")

    sq_parts = [f"Agreement {agreement_count}/6", f"Confidence {confidence_score}"]
    if fragile_setup:
        sq_parts.append("Fragile")
    signal_quality_summary = "; ".join(sq_parts)

    top_reason = reasons[0] if reasons else "Insufficient data for a detailed narrative"

    badges: list[str] = []
    if ipo_buzz:
        badges.append("Fresh IPO")
    if low_float_heuristic:
        badges.append("Low Float")
    if catalyst_score >= 50 and news_count:
        badges.append("News Catalyst")
    if risk_score >= 60:
        badges.append("High Risk")
    if jump_score >= 60:
        badges.append("Momentum")
    if confidence_score < 46:
        badges.append("Low confidence")
    if fragile_setup:
        badges.append("Fragile")

    change_1d_pct = round((change_1d or 0.0) * 100, 2) if change_1d is not None else None
    change_3d_pct = round((change_3d or 0.0) * 100, 2) if change_3d is not None else None

    return {
        "ticker": ticker.upper(),
        "companyName": company,
        "sector": sector,
        "price": round(price, 4) if price else None,
        "change1dPct": change_1d_pct,
        "change3dPct": change_3d_pct,
        "change5dPct": round((change_5d or 0.0) * 100, 2) if change_5d is not None else None,
        "relativeVolume": round(rvol, 2) if rvol is not None else None,
        "jumpScore": jump_score,
        "catalystScore": catalyst_score,
        "riskScore": risk_score,
        "confidenceScore": confidence_score,
        "rankedOpportunityScore": ranked_opportunity_score,
        "signalAgreementCount": agreement_count,
        "setupType": setup_type,
        "setupDriver": setup_driver,
        "fragileSetup": fragile_setup,
        "signalQualitySummary": signal_quality_summary,
        "missingDataFields": missing_data_fields,
        "reasons": reasons[:14],
        "riskNotes": risk_notes[:10],
        "topReason": top_reason,
        "badges": badges,
        "dataSource": bars.source if bars else None,
        "dataFlags": data_flags,
        "lowFloatHeuristic": low_float_heuristic,
        "headlines": [{"title": a.title, "source": a.source, "url": str(a.url)} for a in linked_articles[:8]],
        "priceHistory": [round(c, 4) for c in bars.closes[-60:]] if bars and bars.closes else [],
    }


def sort_radar_rows(rows: list[dict[str, Any]], sort_by: str | None = None) -> None:
    """In-place sort for API responses (opportunity default)."""
    mode = (sort_by or "opportunity").strip().lower()
    if mode == "jump":
        rows.sort(key=lambda r: (r["jumpScore"], r["catalystScore"], r["rankedOpportunityScore"]), reverse=True)
    else:
        rows.sort(
            key=lambda r: (
                r["rankedOpportunityScore"],
                r["confidenceScore"],
                r["jumpScore"],
            ),
            reverse=True,
        )


def build_explosive_radar_payload(
    stocks: list[StockScore],
    articles: list[Article],
    *,
    finnhub_enabled: bool,
    finnhub_api_key: str,
    weights: dict[str, float] | None = None,
    sort_by: str = "opportunity",
) -> list[dict[str, Any]]:
    w = weights or load_explosive_radar_weights()
    rows: list[dict[str, Any]] = []
    with httpx.Client(timeout=18.0, follow_redirects=True) as client:
        for stock in stocks:
            t = stock.ticker.upper()
            linked = _articles_for_ticker(articles, t)
            bars = fetch_daily_bars_for_radar(
                t,
                finnhub_enabled=finnhub_enabled,
                finnhub_api_key=finnhub_api_key,
                client=client,
            )
            rows.append(compute_explosive_radar_row(t, stock, bars, linked, w))
    sort_radar_rows(rows, sort_by)
    return rows


def summarize_radar_rows(rows: list[dict[str, Any]], weights: dict[str, float]) -> dict[str, int]:
    hi_jump = float(weights.get("jump_score_high_threshold", 65))
    hi_cat = float(weights.get("catalyst_score_high_threshold", 55))
    hi_risk = float(weights.get("risk_score_high_threshold", 60))
    return {
        "stocksScanned": len(rows),
        "highJumpCandidates": sum(1 for r in rows if r.get("jumpScore", 0) >= hi_jump),
        "newsDrivenCandidates": sum(
            1 for r in rows if r.get("catalystScore", 0) >= hi_cat and r.get("headlines")
        ),
        "highRiskCandidates": sum(1 for r in rows if r.get("riskScore", 0) >= hi_risk),
    }


def mock_explosive_radar_rows() -> list[dict[str, Any]]:
    """
    Deterministic sample rows for local UI work when EXPLOSIVE_RADAR_MOCK=1.
    Marked explicitly in payload metadata — not live market data.
    """
    return [
        {
            "ticker": "MOCK1",
            "companyName": "Mock Dynamics Inc. (sample)",
            "sector": "Semiconductors",
            "price": 24.5,
            "change1dPct": 12.4,
            "change3dPct": 28.0,
            "change5dPct": 31.2,
            "relativeVolume": 6.2,
            "jumpScore": 82,
            "catalystScore": 74,
            "riskScore": 58,
            "confidenceScore": 71,
            "rankedOpportunityScore": 78,
            "signalAgreementCount": 4,
            "setupDriver": "catalyst-backed",
            "fragileSetup": False,
            "signalQualitySummary": "Agreement 4/6; Confidence 71",
            "missingDataFields": [
                "Market cap",
                "Reported float",
                "Listing / IPO date",
                "Bid/ask spread",
                "Dilution / shelf data",
            ],
            "setupType": SETUP_NEWS_BREAKOUT,
            "reasons": [
                "Relative volume is 6.20x the recent average",
                "3-day return is +28.00%",
                "Recent headlines match catalyst themes: ai, semiconductor, contract",
                "Short-term volatility (ATR proxy) is expanded vs prior regime (1.35x)",
            ],
            "riskNotes": [
                "Volatility expansion elevates gap / reversal risk",
                "Liquidity score from the core model is on the lower side",
            ],
            "topReason": "Relative volume is 6.20x the recent average",
            "badges": ["News Catalyst", "Momentum", "High Risk"],
            "dataSource": "mock",
            "dataFlags": {
                "marketCap": False,
                "floatShares": False,
                "ipoDate": False,
                "bidAskSpread": False,
                "dilutionData": False,
            },
            "lowFloatHeuristic": True,
            "headlines": [
                {
                    "title": "Mock Dynamics announces AI edge contract (sample headline)",
                    "source": "mock-feed",
                    "url": "https://example.com/mock",
                }
            ],
            "priceHistory": [20 + i * 0.08 for i in range(40)],
        },
        {
            "ticker": "MOCK2",
            "companyName": "Mock Biotech Labs (sample)",
            "sector": "Healthcare AI",
            "price": 8.1,
            "change1dPct": 4.2,
            "change3dPct": -6.0,
            "change5dPct": -12.0,
            "relativeVolume": 3.4,
            "jumpScore": 48,
            "catalystScore": 52,
            "riskScore": 44,
            "confidenceScore": 55,
            "rankedOpportunityScore": 49,
            "signalAgreementCount": 2,
            "setupDriver": "mixed",
            "fragileSetup": False,
            "signalQualitySummary": "Agreement 2/6; Confidence 55",
            "missingDataFields": [
                "Market cap",
                "Reported float",
                "Listing / IPO date",
                "Bid/ask spread",
                "Dilution / shelf data",
            ],
            "setupType": SETUP_VOL_REVERSAL,
            "reasons": [
                "1-day return is +4.20%",
                "3-day return is -6.00%",
                "2 recent headline(s) linked to this ticker",
            ],
            "riskNotes": ["No extreme structural risk flags from this ruleset (still high-volatility context possible)"],
            "topReason": "1-day return is +4.20%",
            "badges": ["News Catalyst"],
            "dataSource": "mock",
            "dataFlags": {
                "marketCap": False,
                "floatShares": False,
                "ipoDate": False,
                "bidAskSpread": False,
                "dilutionData": False,
            },
            "lowFloatHeuristic": False,
            "headlines": [],
            "priceHistory": [],
        },
    ]


def build_explosive_radar_row_for_ticker(
    ticker: str,
    stock: StockScore,
    articles: list[Article],
    *,
    finnhub_enabled: bool,
    finnhub_api_key: str,
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    w = weights or load_explosive_radar_weights()
    sym = ticker.strip().upper()
    linked = _articles_for_ticker(articles, sym)
    with httpx.Client(timeout=18.0, follow_redirects=True) as client:
        bars = fetch_daily_bars_for_radar(
            sym,
            finnhub_enabled=finnhub_enabled,
            finnhub_api_key=finnhub_api_key,
            client=client,
        )
    return compute_explosive_radar_row(sym, stock, bars, linked, w)


def filter_explosive_radar_rows(
    rows: list[dict[str, Any]],
    *,
    min_jump: int | None = None,
    max_risk: int | None = None,
    setup_type: str | None = None,
    sector: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    news_catalyst_only: bool = False,
    low_float_only: bool = False,
    float_reported_available: bool = False,
) -> list[dict[str, Any]]:
    out = list(rows)
    if min_jump is not None:
        out = [r for r in out if (r.get("jumpScore") or 0) >= min_jump]
    if max_risk is not None:
        out = [r for r in out if (r.get("riskScore") or 0) <= max_risk]
    if setup_type:
        st = SETUP_LEGACY.get(setup_type.strip(), setup_type.strip())
        out = [r for r in out if r.get("setupType") == st]
    if sector:
        sec = sector.strip().lower()
        out = [r for r in out if str(r.get("sector") or "").lower() == sec]
    if min_price is not None:
        out = [r for r in out if (r.get("price") or 0) >= min_price]
    if max_price is not None:
        out = [r for r in out if (r.get("price") or 0) <= max_price]
    if news_catalyst_only:
        out = [
            r
            for r in out
            if (r.get("catalystScore") or 0) >= 45
            and (r.get("headlines") or [])
        ]
    if low_float_only:
        if float_reported_available:
            out = [r for r in out if r.get("dataFlags", {}).get("floatShares")]
        else:
            out = [r for r in out if r.get("lowFloatHeuristic")]
    return out
