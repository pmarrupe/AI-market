# AI Market Agent

AI Market Agent is a lightweight MVP that:
- collects AI-related news from curated RSS feeds,
- generates short grounded summaries,
- computes transparent stock relevance scores,
- serves a web dashboard with top stories, innovation tracking, watchlist alerts, and top AI-linked stocks.

## What is included

- FastAPI backend (`app/main.py`)
- SQLite storage for articles and stock scores
- Background refresh endpoint (`POST /refresh`)
- Dashboard (`GET /`) with stories + stock ranking
- Innovation tracker and watchlist alert views
- Source citation links and per-stock score explanations
- Confidence thresholds that mark low-evidence outputs as insufficient evidence
- Factuality validation gate to suppress low-grounding summaries
- Lightweight story clustering and catalyst tagging
- Signal-quality scoring per article (source reliability + corroboration + novelty)
- Recommendation audit logging for traceability
- Market snapshots for momentum, liquidity, and valuation-sanity factors (with fallback)
- Optional LLM intelligence layer for higher-quality summaries and score adjustments
- Optional LLM-driven dynamic ticker universe from leading industries
- Multi-source ingestion: curated RSS + optional NewsAPI + optional Finnhub connectors

## Quick start

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -e .
```

3. Copy environment template:

```bash
cp .env.example .env
```

4. Run the app:

```bash
uvicorn app.main:app --reload
```

5. Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Configuration

Set values in `.env`:
- `DATABASE_PATH`: SQLite file location
- `NEWS_FEEDS`: Comma-separated RSS URLs
- `UNIVERSE_SOURCE`: `top_performers` (default) = S&P 500 subset ranked by Finnhub **daily % change**; `dynamic_llm` = LLM picks from industry lists; `static` = only `DEFAULT_TICKERS`
- `TOP_PERFORMER_POOL_MAX`: How many S&P names to quote per day (Finnhub rate limits — default 100)
- `TOP_PERFORMER_MIN_PRICE`: Skip quotes below this last price (filters penny noise)
- `DEFAULT_TICKERS`: Fallback list when movers/LLM fail, or the full universe when `UNIVERSE_SOURCE=static`
- `REFRESH_INTERVAL_MINUTES`: Suggested refresh cadence
- `SUMMARY_CONFIDENCE_THRESHOLD`: Minimum evidence score for publishing summaries
- `RECOMMENDATION_CONFIDENCE_THRESHOLD`: Minimum evidence score for stock recommendations
- `SCORING_MODEL_VERSION`: Version label recorded in recommendation audit logs
- `WATCHLIST_TICKERS`: Comma-separated watchlist symbols for alerting
- `ALERT_SCORE_THRESHOLD`: Alert when score is above threshold
- `ALERT_SENTIMENT_THRESHOLD`: Alert when absolute sentiment is above threshold
- `ALERT_DELTA_THRESHOLD`: Alert when score changes by this amount vs prior refresh
- `LLM_ENABLED`: Enable or disable LLM-powered enrichment (`true`/`false`)
- `LLM_API_KEY`: Provider API key (OpenAI-compatible)
- `LLM_MODEL`: Model name, e.g. `gpt-4o-mini`
- `LLM_BASE_URL`: OpenAI-compatible API base URL
- `LLM_TEMPERATURE`: LLM generation temperature
- `LLM_MAX_TOKENS`: Max completion tokens for LLM calls
- `LLM_SUMMARY_MAX_ARTICLES`: Max articles per refresh to enrich via LLM summaries (latency control)
- `DYNAMIC_UNIVERSE_ENABLED`: When `UNIVERSE_SOURCE=dynamic_llm`, use LLM to choose tickers from industry lists
- `DYNAMIC_UNIVERSE_SIZE`: Maximum number of dynamically selected tickers
- `DYNAMIC_UNIVERSE_EXPLORE_MODE`: Rotate in fresher names to avoid same list every refresh
- `DYNAMIC_UNIVERSE_BLEND_FALLBACK`: Blend `DEFAULT_TICKERS` into LLM picks for stability
- `DYNAMIC_UNIVERSE_MIN_FRESH`: Minimum fresh tickers to inject in explore mode
- `NEWSAPI_ENABLED`: Enable NewsAPI connector for broader article coverage
- `NEWSAPI_API_KEY`: NewsAPI key when connector is enabled
- `FINNHUB_ENABLED`: Enable Finnhub (news + daily price candles when key is set)
- `FINNHUB_API_KEY`: Finnhub API key — used for headlines and for market snapshots / price outlook when enabled

## API endpoints

- `GET /health` - health check
- `GET /api/articles` - latest articles
- `GET /api/stocks` - latest stock scores
- `GET /api/innovations` - latest detected innovation items
- `GET /api/alerts` - watchlist alerts based on current thresholds
- `GET /api/analysis-cards` - analyst-style cards with thesis, evidence, and uncertainties
- `POST /refresh` - fetch, summarize, and score now
- `GET /api/audit` - latest recommendation audit records
- `GET /api/source-health` - recent feed/source health checks
- `GET /api/price-forecast?ticker=NVDA` - empirical 10/20/30 **trading-day** outlook from daily closes: tries **Finnhub** when `FINNHUB_ENABLED` + `FINNHUB_API_KEY` are set, otherwise **Stooq** (no extra key). Returns `data_source`: `finnhub` or `stooq`. Not investment advice.
- `GET /api/explosive-radar` - rules-based **Explosive Move Radar** for the active scored universe (probabilistic, explainable). Query params: `min_jump`, `max_risk`, `setup_type`, `sector`, `min_price`, `max_price`, `news_catalyst_only`, `low_float_only`, `limit`, `sort` (`opportunity` default = ranked composite, or `jump`).
- `GET /api/explosive-radar/{ticker}` - single-ticker radar row (on-demand quote if not in universe when data is available).
- `GET /api/explosive-radar/config` - tunable weights file values plus short documentation strings.

## Explosive Move Radar

The dashboard includes an **Explosive Move Radar** section: a high-volatility / abnormal-momentum **radar**, not a guarantee of future prices.

- **Jump score (0–100)** — Structural energy from volume, **positive** multi-day drift (bearish volatility is no longer rewarded like upside), breakouts, gaps, and dollar volume. Micro dollar-volume and “orphan” 1-day spikes are **discounted**; gap-fades add risk.
- **Catalyst score (0–100)** — Linked headlines + keyword themes with **sqrt damping** so repeated keyword hits don’t dominate.
- **Risk score (0–100)** — Illiquidity, volatility expansion, orphan spikes, **gap fades**, **micro dollar volume**, and thin-history snapshots.
- **Confidence score (0–100)** — **Not direction.** Reflects data completeness (bars, RVOL, $ volume, news) and **signal agreement** across buckets. A high jump with low confidence is explicitly a “trust the signal less” situation.
- **Ranked opportunity score (0–100)** — Transparent linear blend: `ranked_jump_coef * jump + ranked_catalyst_coef * catalyst + ranked_confidence_coef * confidence + ranked_agreement_coef * agreement_count - ranked_risk_coef * risk`, then clamped. Tunable in `app/data/explosive_radar_weights.json`. Default API ordering uses `sort=opportunity` (this composite); `sort=jump` restores raw jump ordering.

**Setup labels** are deterministic and include types such as *Multi-Day Momentum Continuation*, *Gap-and-Go Speculative Move*, *Weak Quality Spike*, and *No Clear Edge*. Legacy filter strings (e.g. “News Catalyst Runner”) still map server-side.

**Weak-quality spikes** — High jump driven mainly by price/noise, tiny dollar volume, or missing confirmation: labeled *Weak Quality Spike* and surfaced as **fragile** in the UI when heuristics fire.

Weights live in `app/data/explosive_radar_weights.json`. Reported float, market cap, spreads, and dilution feeds are **not** wired yet; each row includes `missingDataFields` for the drawer.

### Historical validation (diagnostic)

Rules-only back-of-the-envelope check over recent daily bars (network required for OHLCV):

```bash
PYTHONPATH=. python scripts/validate_explosive_radar.py --tickers NVDA,AMD --json report.json --csv events.csv
```

Outputs aggregate stats (e.g. hit rates for high jump events, averages by setup type) plus per-event forward max gains / drawdowns. **Not** a trading simulator or guarantee — use to sanity-check whether the current rules behave plausibly on past data.

**Local mock data:** set `EXPLOSIVE_RADAR_MOCK=1` in the environment to return deterministic sample rows (labeled in the JSON response) without calling market providers.

Run scoring unit tests: `pytest tests/test_explosive_radar.py` (install `pytest` in your environment).

## Notes

- This project is designed as research intelligence, not personal investment advice.
- Recommendation quality improves with better market/news providers and richer factor models.
- When LLM is disabled or unavailable, the system automatically falls back to deterministic logic.
- Bloomberg content is consumed through RSS/public links in this project setup; enterprise Bloomberg APIs require separate licensing.
