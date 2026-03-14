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
- `DEFAULT_TICKERS`: Comma-separated list of tickers to score
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
- `DYNAMIC_UNIVERSE_ENABLED`: Use LLM to choose top industry-leader tickers each refresh
- `DYNAMIC_UNIVERSE_SIZE`: Maximum number of dynamically selected tickers
- `DYNAMIC_UNIVERSE_EXPLORE_MODE`: Rotate in fresher names to avoid same list every refresh
- `DYNAMIC_UNIVERSE_BLEND_FALLBACK`: Blend `DEFAULT_TICKERS` into LLM picks for stability
- `DYNAMIC_UNIVERSE_MIN_FRESH`: Minimum fresh tickers to inject in explore mode
- `NEWSAPI_ENABLED`: Enable NewsAPI connector for broader article coverage
- `NEWSAPI_API_KEY`: NewsAPI key when connector is enabled
- `FINNHUB_ENABLED`: Enable Finnhub news connector for market headlines
- `FINNHUB_API_KEY`: Finnhub API key when connector is enabled

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

## Notes

- This project is designed as research intelligence, not personal investment advice.
- Recommendation quality improves with better market/news providers and richer factor models.
- When LLM is disabled or unavailable, the system automatically falls back to deterministic logic.
- Bloomberg content is consumed through RSS/public links in this project setup; enterprise Bloomberg APIs require separate licensing.
