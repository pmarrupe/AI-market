from __future__ import annotations

import csv
import json
from functools import lru_cache
from pathlib import Path
from typing import List, Dict


BASE_DIR = Path(__file__).resolve().parent.parent
UNIVERSE_JSON = BASE_DIR / "data" / "sp500_universe.json"
UNIVERSE_CSV = BASE_DIR / "data" / "sp500_universe.csv"


@lru_cache(maxsize=1)
def load_sp500_universe() -> List[Dict[str, str]]:
  # Prefer CSV (full universe), fall back to JSON sample if present.
  if UNIVERSE_CSV.exists():
    try:
      out: List[Dict[str, str]] = []
      with UNIVERSE_CSV.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
          ticker = str(row.get("Symbol", "") or row.get("symbol", "")).upper()
          name = str(row.get("Security", "") or row.get("Name", "")).strip()
          sector = str(row.get("GICS Sector", "") or row.get("Sector", "")).strip() or "Other"
          if ticker:
            out.append({"ticker": ticker, "name": name or ticker, "sector": sector})
      return out
    except Exception:
      pass
  if not UNIVERSE_JSON.exists():
    return []
  try:
    with UNIVERSE_JSON.open("r", encoding="utf-8") as f:
      data = json.load(f)
    out: List[Dict[str, str]] = []
    for row in data:
      ticker = str(row.get("ticker", "")).upper()
      name = str(row.get("name", "")).strip()
      sector = str(row.get("sector", "")).strip() or "Other"
      if ticker:
        out.append({"ticker": ticker, "name": name or ticker, "sector": sector})
    return out
  except Exception:
    return []


@lru_cache(maxsize=1)
def _ticker_index() -> Dict[str, Dict[str, str]]:
  return {row["ticker"]: row for row in load_sp500_universe()}


def search_sp500(query: str, limit: int = 10) -> List[Dict[str, str]]:
  q = (query or "").strip().lower()
  if not q:
    return []
  universe = load_sp500_universe()
  results: List[Dict[str, str]] = []
  for row in universe:
    t = row["ticker"].lower()
    n = row["name"].lower()
    if t.startswith(q) or q in n:
      results.append(row)
    if len(results) >= limit:
      break
  return results


def get_sp500_entry(ticker: str) -> Dict[str, str] | None:
  return _ticker_index().get((ticker or "").upper())

