from __future__ import annotations

import sqlite3
import json
from contextlib import contextmanager
from datetime import datetime, timezone

from app.models import Article, RecommendationAuditRecord, StockScore


def _to_iso(dt: datetime) -> str:
    return dt.isoformat()


def _from_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


class Store:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.init_db()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    source TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    published_at TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    tickers TEXT NOT NULL,
                    sentiment REAL NOT NULL,
                    cluster_id TEXT NOT NULL DEFAULT '',
                    catalyst_type TEXT NOT NULL DEFAULT 'other',
                    source_excerpt TEXT NOT NULL DEFAULT '',
                    signal_score REAL NOT NULL DEFAULT 0.0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS stock_scores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    price REAL NOT NULL DEFAULT 0.0,
                    day_change REAL NOT NULL DEFAULT 0.0,
                    score REAL NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    momentum REAL NOT NULL,
                    liquidity REAL NOT NULL DEFAULT 0.0,
                    valuation_sanity REAL NOT NULL DEFAULT 0.0,
                    sentiment REAL NOT NULL,
                    relevance REAL NOT NULL,
                    explanation TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS stock_score_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    score REAL NOT NULL,
                    confidence REAL NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS recommendation_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    input_payload TEXT NOT NULL,
                    output_payload TEXT NOT NULL,
                    source_urls TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS source_health (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    status TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    checked_at TEXT NOT NULL
                )
                """
            )
            self._ensure_column(conn, "articles", "cluster_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "articles", "catalyst_type", "TEXT NOT NULL DEFAULT 'other'")
            self._ensure_column(conn, "articles", "source_excerpt", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "articles", "signal_score", "REAL NOT NULL DEFAULT 0.0")
            self._ensure_column(conn, "stock_scores", "confidence", "REAL NOT NULL DEFAULT 0.0")
            self._ensure_column(conn, "stock_scores", "price", "REAL NOT NULL DEFAULT 0.0")
            self._ensure_column(conn, "stock_scores", "day_change", "REAL NOT NULL DEFAULT 0.0")
            self._ensure_column(conn, "stock_scores", "liquidity", "REAL NOT NULL DEFAULT 0.0")
            self._ensure_column(
                conn, "stock_scores", "valuation_sanity", "REAL NOT NULL DEFAULT 0.0"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_bars_cache (
                    ticker TEXT PRIMARY KEY,
                    bars_json TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT '',
                    fetched_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS earnings_cache (
                    ticker TEXT PRIMARY KEY,
                    events_json TEXT NOT NULL,
                    fetched_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS company_info_cache (
                    ticker TEXT PRIMARY KEY,
                    info_json TEXT NOT NULL,
                    fetched_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trade_plan_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    entry REAL NOT NULL,
                    stop REAL NOT NULL,
                    target1 REAL NOT NULL,
                    target2 REAL NOT NULL,
                    atr REAL NOT NULL,
                    conviction TEXT NOT NULL DEFAULT '',
                    setup TEXT NOT NULL DEFAULT '',
                    outcome TEXT NOT NULL DEFAULT 'open',
                    created_at TEXT NOT NULL,
                    resolved_at TEXT
                )
                """
            )

    def _ensure_column(
        self, conn: sqlite3.Connection, table_name: str, column_name: str, column_type: str
    ) -> None:
        columns = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        names = {column[1] for column in columns}
        if column_name not in names:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")

    def upsert_articles(self, articles: list[Article]) -> None:
        with self.connect() as conn:
            for article in articles:
                conn.execute(
                    """
                    INSERT INTO articles (
                        title, source, url, published_at, summary, tickers, sentiment,
                        cluster_id, catalyst_type, source_excerpt, signal_score
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(url) DO UPDATE SET
                        title=excluded.title,
                        source=excluded.source,
                        published_at=excluded.published_at,
                        summary=excluded.summary,
                        tickers=excluded.tickers,
                        sentiment=excluded.sentiment,
                        cluster_id=excluded.cluster_id,
                        catalyst_type=excluded.catalyst_type,
                        source_excerpt=excluded.source_excerpt,
                        signal_score=excluded.signal_score
                    """,
                    (
                        article.title,
                        article.source,
                        str(article.url),
                        _to_iso(article.published_at),
                        article.summary,
                        ",".join(article.tickers),
                        article.sentiment,
                        article.cluster_id,
                        article.catalyst_type,
                        article.source_excerpt,
                        article.signal_score,
                    ),
                )

    def replace_stock_scores(self, scores: list[StockScore]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO stock_score_history (ticker, score, confidence, updated_at)
                SELECT ticker, score, confidence, updated_at
                FROM stock_scores
                """
            )
            conn.execute("DELETE FROM stock_scores")
            for score in scores:
                conn.execute(
                    """
                    INSERT INTO stock_scores (
                        ticker, price, day_change, score, confidence, momentum, liquidity, valuation_sanity,
                        sentiment, relevance, explanation, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        score.ticker,
                        score.price,
                        score.day_change,
                        score.score,
                        score.confidence,
                        score.momentum,
                        score.liquidity,
                        score.valuation_sanity,
                        score.sentiment,
                        score.relevance,
                        score.explanation,
                        _to_iso(score.updated_at),
                    ),
                )

    def get_articles(self, limit: int = 50) -> list[Article]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT title, source, url, published_at, summary, tickers, sentiment,
                       cluster_id, catalyst_type, source_excerpt, signal_score
                FROM articles
                ORDER BY published_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            Article(
                title=row[0],
                source=row[1],
                url=row[2],
                published_at=_from_iso(row[3]),
                summary=row[4],
                tickers=[t for t in row[5].split(",") if t],
                sentiment=row[6],
                cluster_id=row[7],
                catalyst_type=row[8],
                source_excerpt=row[9],
                signal_score=row[10],
            )
            for row in rows
        ]

    def get_stock_scores(self, limit: int = 20) -> list[StockScore]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT ticker, score, confidence, momentum, liquidity, valuation_sanity,
                       sentiment, relevance, explanation, updated_at, price, day_change
                FROM stock_scores
                ORDER BY score DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            StockScore(
                ticker=row[0],
                score=row[1],
                confidence=row[2],
                momentum=row[3],
                liquidity=row[4],
                valuation_sanity=row[5],
                sentiment=row[6],
                relevance=row[7],
                explanation=row[8],
                updated_at=_from_iso(row[9]),
                price=row[10],
                day_change=row[11],
            )
            for row in rows
        ]

    def get_stock_scores_by_tickers(self, tickers: list[str]) -> dict[str, StockScore]:
        """
        Fetch stored StockScore rows for a specific set of tickers.
        Used to avoid overwriting valid price fields with zeros when live snapshots fail.
        """
        normalized = [t.strip().upper() for t in (tickers or []) if t and t.strip()]
        if not normalized:
            return {}

        placeholders = ",".join("?" for _ in normalized)
        query = f"""
            SELECT ticker, score, confidence, momentum, liquidity, valuation_sanity,
                   sentiment, relevance, explanation, updated_at, price, day_change
            FROM stock_scores
            WHERE ticker IN ({placeholders})
        """
        with self.connect() as conn:
            rows = conn.execute(query, tuple(normalized)).fetchall()

        out: dict[str, StockScore] = {}
        for row in rows:
            out[str(row[0])] = StockScore(
                ticker=row[0],
                score=row[1],
                confidence=row[2],
                momentum=row[3],
                liquidity=row[4],
                valuation_sanity=row[5],
                sentiment=row[6],
                relevance=row[7],
                explanation=row[8],
                updated_at=_from_iso(row[9]),
                price=row[10],
                day_change=row[11],
            )
        return out

    def append_recommendation_audit(
        self, scores: list[StockScore], articles: list[Article], model_version: str
    ) -> None:
        with self.connect() as conn:
            for score in scores:
                linked = [a for a in articles if score.ticker in a.tickers]
                source_urls = [str(a.url) for a in linked]
                input_payload = json.dumps(
                    {
                        "linked_article_count": len(linked),
                        "average_sentiment": score.sentiment,
                        "relevance": score.relevance,
                    },
                    sort_keys=True,
                )
                output_payload = json.dumps(score.model_dump(mode="json"), sort_keys=True)
                conn.execute(
                    """
                    INSERT INTO recommendation_audit (
                        ticker, model_version, input_payload, output_payload, source_urls, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        score.ticker,
                        model_version,
                        input_payload,
                        output_payload,
                        ",".join(source_urls),
                        _to_iso(datetime.now(timezone.utc)),
                    ),
                )

    def get_recommendation_audit(self, limit: int = 100) -> list[RecommendationAuditRecord]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT ticker, model_version, input_payload, output_payload, source_urls, created_at
                FROM recommendation_audit
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            RecommendationAuditRecord(
                ticker=row[0],
                model_version=row[1],
                input_payload=row[2],
                output_payload=row[3],
                source_urls=[url for url in row[4].split(",") if url],
                created_at=_from_iso(row[5]),
            )
            for row in rows
        ]

    def append_source_health(self, entries: list[dict[str, str]]) -> None:
        with self.connect() as conn:
            for entry in entries:
                conn.execute(
                    """
                    INSERT INTO source_health (source, status, detail, checked_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        entry.get("source", "unknown"),
                        entry.get("status", "unknown"),
                        entry.get("detail", ""),
                        _to_iso(datetime.now(timezone.utc)),
                    ),
                )

    def get_source_health(self, limit: int = 50) -> list[dict[str, str]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT source, status, detail, checked_at
                FROM source_health
                ORDER BY checked_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {"source": row[0], "status": row[1], "detail": row[2], "checked_at": row[3]}
            for row in rows
        ]

    def get_previous_score_map(self) -> dict[str, float]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT h.ticker, h.score
                FROM stock_score_history h
                INNER JOIN (
                    SELECT ticker, MAX(id) AS max_id
                    FROM stock_score_history
                    GROUP BY ticker
                ) latest ON latest.max_id = h.id
                """
            ).fetchall()
        return {row[0]: row[1] for row in rows}

    def get_cached_bars(
        self, ticker: str, max_age_hours: float = 12.0
    ) -> list[dict] | None:
        """Return cached OHLC bars (oldest→newest) if fresh enough, else None."""
        sym = (ticker or "").strip().upper()
        if not sym:
            return None
        with self.connect() as conn:
            row = conn.execute(
                "SELECT bars_json, fetched_at FROM daily_bars_cache WHERE ticker = ?",
                (sym,),
            ).fetchone()
        if not row:
            return None
        try:
            fetched = _from_iso(row[1])
        except Exception:
            return None
        age_hours = (datetime.now(timezone.utc) - fetched).total_seconds() / 3600
        if age_hours > max_age_hours:
            return None
        try:
            bars = json.loads(row[0])
            return bars if isinstance(bars, list) else None
        except Exception:
            return None

    def set_cached_bars(self, ticker: str, bars: list[dict], source: str = "") -> None:
        sym = (ticker or "").strip().upper()
        if not sym or not bars:
            return
        payload = json.dumps(bars)
        now_iso = _to_iso(datetime.now(timezone.utc))
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO daily_bars_cache (ticker, bars_json, source, fetched_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET
                    bars_json = excluded.bars_json,
                    source = excluded.source,
                    fetched_at = excluded.fetched_at
                """,
                (sym, payload, source, now_iso),
            )

    def get_cached_earnings(
        self, ticker: str, max_age_hours: float = 24.0
    ) -> list[dict] | None:
        sym = (ticker or "").strip().upper()
        if not sym:
            return None
        with self.connect() as conn:
            row = conn.execute(
                "SELECT events_json, fetched_at FROM earnings_cache WHERE ticker = ?",
                (sym,),
            ).fetchone()
        if not row:
            return None
        try:
            fetched = _from_iso(row[1])
        except Exception:
            return None
        age_hours = (datetime.now(timezone.utc) - fetched).total_seconds() / 3600
        if age_hours > max_age_hours:
            return None
        try:
            events = json.loads(row[0])
            return events if isinstance(events, list) else None
        except Exception:
            return None

    def set_cached_earnings(self, ticker: str, events: list[dict]) -> None:
        sym = (ticker or "").strip().upper()
        if not sym:
            return
        payload = json.dumps(events)
        now_iso = _to_iso(datetime.now(timezone.utc))
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO earnings_cache (ticker, events_json, fetched_at)
                VALUES (?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET
                    events_json = excluded.events_json,
                    fetched_at = excluded.fetched_at
                """,
                (sym, payload, now_iso),
            )

    def get_cached_company_info(
        self, ticker: str, max_age_hours: float = 168.0
    ) -> dict | None:
        sym = (ticker or "").strip().upper()
        if not sym:
            return None
        with self.connect() as conn:
            row = conn.execute(
                "SELECT info_json, fetched_at FROM company_info_cache WHERE ticker = ?",
                (sym,),
            ).fetchone()
        if not row:
            return None
        try:
            fetched = _from_iso(row[1])
        except Exception:
            return None
        age_hours = (datetime.now(timezone.utc) - fetched).total_seconds() / 3600
        if age_hours > max_age_hours:
            return None
        try:
            info = json.loads(row[0])
            return info if isinstance(info, dict) else None
        except Exception:
            return None

    def set_cached_company_info(self, ticker: str, info: dict) -> None:
        sym = (ticker or "").strip().upper()
        if not sym or not info:
            return
        payload = json.dumps(info)
        now_iso = _to_iso(datetime.now(timezone.utc))
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO company_info_cache (ticker, info_json, fetched_at)
                VALUES (?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET
                    info_json = excluded.info_json,
                    fetched_at = excluded.fetched_at
                """,
                (sym, payload, now_iso),
            )

    def record_trade_plan(
        self,
        *,
        ticker: str,
        entry: float,
        stop: float,
        target1: float,
        target2: float,
        atr: float,
        conviction: str = "",
        setup: str = "",
    ) -> int | None:
        sym = (ticker or "").strip().upper()
        if not sym:
            return None
        now_iso = _to_iso(datetime.now(timezone.utc))
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO trade_plan_audit
                (ticker, entry, stop, target1, target2, atr, conviction, setup, outcome, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)
                """,
                (sym, entry, stop, target1, target2, atr, conviction, setup, now_iso),
            )
            return cur.lastrowid

    def record_trade_plan_if_no_open(
        self,
        *,
        ticker: str,
        entry: float,
        stop: float,
        target1: float,
        target2: float,
        atr: float,
        conviction: str = "",
        setup: str = "",
    ) -> int | None:
        """Record a new open plan only if there isn't already an open plan for
        this ticker. Returns the new plan id, or None if skipped."""
        sym = (ticker or "").strip().upper()
        if not sym:
            return None
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM trade_plan_audit WHERE ticker = ? AND outcome = 'open' LIMIT 1",
                (sym,),
            ).fetchone()
            if row:
                return None
        return self.record_trade_plan(
            ticker=sym, entry=entry, stop=stop, target1=target1, target2=target2,
            atr=atr, conviction=conviction, setup=setup,
        )

    def get_open_trade_plans(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, ticker, entry, stop, target1, target2, atr, conviction, setup, created_at
                FROM trade_plan_audit
                WHERE outcome = 'open'
                ORDER BY created_at DESC
                """
            ).fetchall()
        return [
            {
                "id": r[0], "ticker": r[1], "entry": r[2], "stop": r[3],
                "target1": r[4], "target2": r[5], "atr": r[6],
                "conviction": r[7], "setup": r[8], "created_at": r[9],
            }
            for r in rows
        ]

    def resolve_trade_plan(self, plan_id: int, outcome: str) -> None:
        now_iso = _to_iso(datetime.now(timezone.utc))
        with self.connect() as conn:
            conn.execute(
                "UPDATE trade_plan_audit SET outcome = ?, resolved_at = ? WHERE id = ?",
                (outcome, now_iso, plan_id),
            )

    def get_trade_plan_stats(self, since_days: int = 30) -> dict:
        """Summary of resolved trade plans over the window."""
        from datetime import timedelta
        cutoff_iso = _to_iso(datetime.now(timezone.utc) - timedelta(days=since_days))
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT outcome, COUNT(*)
                FROM trade_plan_audit
                WHERE created_at >= ?
                GROUP BY outcome
                """,
                (cutoff_iso,),
            ).fetchall()
        totals = {r[0]: r[1] for r in rows}
        total = sum(totals.values())
        wins = totals.get("target_hit", 0)
        losses = totals.get("stop_hit", 0)
        expired = totals.get("expired", 0)
        open_ = totals.get("open", 0)
        resolved = wins + losses + expired
        win_rate = (wins / resolved) if resolved > 0 else None
        return {
            "window_days": since_days,
            "total": total,
            "open": open_,
            "resolved": resolved,
            "wins": wins,
            "losses": losses,
            "expired": expired,
            "win_rate": round(win_rate, 3) if win_rate is not None else None,
        }
