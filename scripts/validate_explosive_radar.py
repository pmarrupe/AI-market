#!/usr/bin/env python3
"""
Developer CLI for Explosive Move Radar historical validation (rules-based sanity check).

Example:
  PYTHONPATH=. python scripts/validate_explosive_radar.py --tickers NVDA,AMD --json report.json

Requires network access to fetch Stooq/Finnhub OHLCV (same as the live radar).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Repo root on path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.services.explosive_radar_validation import (
    export_validation_csv,
    export_validation_json,
    run_historical_validation,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("validate_explosive_radar")


def main() -> int:
    p = argparse.ArgumentParser(description="Explosive Move Radar historical validation")
    p.add_argument("--tickers", required=True, help="Comma-separated tickers, e.g. NVDA,AMD")
    p.add_argument("--step", type=int, default=5, help="Bar step between samples (default 5)")
    p.add_argument("--min-jump", type=int, default=60, help="Only record events with jumpScore >= N")
    p.add_argument("--max-per-ticker", type=int, default=40, help="Cap signals per symbol")
    p.add_argument("--json", dest="json_path", help="Write full report JSON")
    p.add_argument("--csv", dest="csv_path", help="Write events CSV")
    args = p.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    settings = get_settings()
    report = run_historical_validation(
        tickers,
        finnhub_enabled=settings.finnhub_enabled,
        finnhub_api_key=settings.finnhub_api_key,
        step=args.step,
        min_jump_signal=args.min_jump,
        max_signals_per_ticker=args.max_per_ticker,
        articles=[],
        as_of_filter_articles=False,
    )

    s = report.get("summary") or {}
    logger.info("events=%s", report.get("eventCount"))
    logger.info("summary=%s", json.dumps(s, default=str))

    if args.json_path:
        export_validation_json(report, Path(args.json_path))
        logger.info("wrote %s", args.json_path)
    if args.csv_path:
        export_validation_csv(report, Path(args.csv_path))
        logger.info("wrote %s", args.csv_path)

    if not args.json_path and not args.csv_path:
        print(json.dumps(report, indent=2, default=str))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
