# Dashboard Improvement Plan — From Scores to Decisions

Goal: turn the dashboard from a *score display* into a *decision tool* so it's
actually useful for buy / sell decisions.

The current Explosive Move Radar and AI Stock Opportunity Scanner surface
many abstract scores (Jump / Cat / Risk / Conf / Score / Confidence), but
never answer the three questions a trader actually has:

1. **What price do I buy at?**
2. **Where do I take profit and where do I stop?**
3. **How much should I size it?**

Everything below is organized around filling those gaps.

---

## Decisions needed from the user (drives scope)

1. **Trading style** — swing (2–8 weeks) / day trader / long-term investor?
   *Default assumption: swing.* Changes which signals matter and what
   targets / stops get computed.
2. **Portfolio input** — do you want to tell the dashboard what you own
   (tickers + shares + cost basis)?
   *Default: yes, paste-in stored in localStorage.*
   Unlocks exit signals, which is roughly half the value.
3. **Calibration tracking** — OK to persist every recommendation so we
   can show a real track record?
   *Default: yes, stored in the existing SQLite DB.*
   Without this you'll never know if the model has edge.

---

## Phase 0 — Kill noise, tighten what exists (½ day)

Pure frontend. Immediate signal-to-noise boost.

- Remove abstract pill scores (Jump / Cat / Risk / Conf) from the main
  Radar table. Move into the expanded drawer.
- Replace with one **Conviction** chip (derived from existing scores:
  high / med / low) and one **Setup** tag.
- Drop 1D% / 3D% / RelVol columns from the default view — move behind a
  "Show details" toggle.
- Result: each row scannable in 1 second instead of 10.

## Phase 1 — "What changed since you last looked" strip (½ day)

Frontend-only. Uses `score_delta` and `last_headline_minutes` already
computed server-side.

- Top-of-page strip: `3 new buy signals · 1 thesis invalidated · 2 scores
  dropped >0.1 · 4 new catalysts`.
- Each chip is clickable — filters the feed to that subset.
- Stores `last_viewed_at` in localStorage.
- The #1 reason you'd return daily. High leverage per hour invested.

## Phase 2 — Merge Scanner + Radar into one Trade Feed (1–2 days)

Big restructure. The two sections become one ranked list with filters.

- New `TradeFeed.jsx` replaces `StockScanner` + `ExplosiveMoveRadar`.
- Filters: horizon (swing / short-term momentum / breakout), setup,
  sector, conviction.
- Backend: keep the two endpoints internally, but add a single
  `/api/trade-feed` that merges them, normalizes conviction, and tags
  each row with a horizon.
- Expanded drawer keeps all the detailed metrics (Jump / Cat / headlines
  / fragility notes) for when you want to dig in.
- Delete `StockScanner.jsx` and `ExplosiveMoveRadar.jsx` once the feed
  covers their output.

## Phase 3 — Decision-ready numbers: entry / target / stop / size (2–3 days)

The phase that turns it from a dashboard into a decision tool. Backend
work required.

- New `app/services/trade_plan.py`. For each pick, compute:
  - **Entry**: current price ± tight range, or breakout level above
    recent high.
  - **Stop**: `entry − 2 × ATR(14)` or recent swing low, whichever is
    tighter.
  - **Target 1**: `entry + 2 × ATR(14)` or next resistance.
  - **Target 2**: `entry + 4 × ATR(14)`.
  - **R:R ratio**.
  - **Suggested size**: `(1% of portfolio) / (entry − stop)` — user
    enters portfolio size once in settings.
- Frontend: each card shows these numbers front-and-center. Scores
  become the *why*, these numbers become the *what*.
- **Prerequisite: daily historical bars.** Extend the market data fetch
  to pull 30 days of OHLC per ticker. One API call per ticker; cache
  results in SQLite.

## Phase 4 — Earnings / event awareness (1 day)

- Pull Finnhub earnings calendar (free tier supports this) for every
  ticker in the universe.
- Each trade card shows `Earnings in N days` if within horizon.
- Filter: "Hide picks with earnings in ≤ N days".
- Prevents walking into binary events.

## Phase 5 — Portfolio-aware exit signals (2–3 days)

*Only if you said yes to Decision #2.*

- Paste-in: ticker / shares / cost basis. Stored in localStorage or DB.
- New "Your positions" section above the trade feed.
- For each holding: current P&L, thesis-change flag, "approaching
  stop", "near target", sector / position-size warnings.
- Selling well is where retail traders actually win or lose — this
  section likely becomes the most-used one.

## Phase 6 — Track record widget (2 days)

*Only if you said yes to Decision #3.*

- Persist every `(ticker, recommendation, entry, target, stop,
  timestamp)` in the DB.
- Daily background task marks outcomes: hit target / hit stop /
  expired.
- Small always-visible widget:
  `Last 30d · 14 picks · 57% win · +2.3% avg vs SPY +0.9%`.
- Over a few months tells you whether the model has edge. Also lets
  you tune parameters with evidence.

## Phase 7 — Alerts (1–2 days)

- Browser push (PWA already set up) when:
  - A held position hits stop or target.
  - A new high-conviction buy appears.
  - A thesis invalidates.
- Threshold config in settings.
- Optional: email via SMTP or Resend.

---

## Suggested order of execution

| # | Phases                  | Days    | Why                                                    |
|---|-------------------------|---------|--------------------------------------------------------|
| 1 | Phase 0 + Phase 1       | 1       | Frontend-only, no backend risk, big scannability win.  |
| 2 | Phase 2                 | 1–2     | Structural cleanup — one unified feed.                 |
| 3 | Phase 3                 | 2–3     | Biggest single value jump. Moves from scores to trades.|
| 4 | Phase 5                 | 2–3     | Second biggest. Exit signals on current holdings.      |
| 5 | Phase 4, 6, 7           | ½–2 ea  | In any order.                                          |

Total end-to-end: **~10–14 dev-days**.

---

## Main tradeoff

Phase 3 is the only phase that needs real market data infrastructure
(ATR on daily bars for every ticker in the universe, cached). If the
Finnhub tier isn't generous enough, the fallback options are:

- Rate-limit the universe (smaller, higher-quality list of tickers).
- Swap in Stooq or yfinance as a historical-bars source.

Worth checking Finnhub limits before starting Phase 3.

---

## Next step

Answer the three decisions above, or say "go" and Phase 0 + Phase 1
start immediately (safe, frontend-only, no backend risk).
