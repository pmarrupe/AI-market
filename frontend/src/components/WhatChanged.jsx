import { useEffect, useMemo, useRef, useState } from "react";

const STORAGE_KEY = "ai_market.last_viewed_at";
const DEFAULT_LOOKBACK_MIN = 1440;

function minutesSince(tsMs) {
  if (!tsMs) return null;
  return Math.max(0, Math.floor((Date.now() - tsMs) / 60000));
}

function readLastViewed() {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (!v) return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  } catch {
    return null;
  }
}

function writeLastViewed(ts) {
  try {
    localStorage.setItem(STORAGE_KEY, String(ts));
  } catch {
    /* ignore quota / private-mode errors */
  }
}

function formatLookback(minutes) {
  if (minutes == null) return "last 24h";
  if (minutes < 60) return `last ${minutes}m`;
  const h = Math.floor(minutes / 60);
  if (h < 24) return `last ${h}h`;
  const d = Math.floor(h / 24);
  return `last ${d}d`;
}

export default function WhatChanged({ stockRows = [], onChipAction }) {
  const [lastViewedAt] = useState(() => readLastViewed());
  const commitOnUnloadRef = useRef(false);

  useEffect(() => {
    if (!stockRows || stockRows.length === 0) return;
    commitOnUnloadRef.current = true;
    return () => {
      if (commitOnUnloadRef.current) {
        writeLastViewed(Date.now());
      }
    };
  }, [stockRows]);

  const lookbackMin = useMemo(() => {
    const since = minutesSince(lastViewedAt);
    return since == null ? DEFAULT_LOOKBACK_MIN : since;
  }, [lastViewedAt]);

  const counts = useMemo(() => {
    const rows = stockRows || [];
    let newBuys = 0;
    let dropped = 0;
    let invalidated = 0;
    let freshCatalysts = 0;

    for (const r of rows) {
      const delta = Number(r.score_delta);
      const sig = r.signalLabel || "";
      const status = r.status || "";
      const ageMin = r.last_headline_minutes;

      if (Number.isFinite(delta)) {
        if (delta >= 0.1 && (sig.includes("Buy") || sig === "Bullish")) newBuys += 1;
        if (delta <= -0.1) dropped += 1;
        if (
          delta <= -0.1 &&
          (sig.startsWith("Avoid") || status === "High Risk Setup" || sig === "Neutral")
        ) {
          invalidated += 1;
        }
      }

      if (Number.isFinite(ageMin) && ageMin != null && ageMin <= lookbackMin) {
        freshCatalysts += 1;
      }
    }

    return { newBuys, dropped, invalidated, freshCatalysts };
  }, [stockRows, lookbackMin]);

  const handleClick = (intent) => {
    if (onChipAction) onChipAction(intent);
    const el = document.getElementById("stocks");
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const chips = [
    {
      key: "new_buys",
      label: `${counts.newBuys} new buy signal${counts.newBuys === 1 ? "" : "s"}`,
      intent: "delta_desc",
      tone: "pos",
      title: "Rows whose score jumped ≥ 0.10 with a bullish signal",
      disabled: counts.newBuys === 0,
    },
    {
      key: "invalidated",
      label: `${counts.invalidated} thesis invalidated`,
      intent: "delta_asc",
      tone: "neg",
      title: "Rows whose score fell ≥ 0.10 into a cautious signal",
      disabled: counts.invalidated === 0,
    },
    {
      key: "dropped",
      label: `${counts.dropped} score${counts.dropped === 1 ? "" : "s"} dropped > 0.1`,
      intent: "delta_asc",
      tone: "neg",
      title: "Rows whose score fell ≥ 0.10 since the last evaluation",
      disabled: counts.dropped === 0,
    },
    {
      key: "catalysts",
      label: `${counts.freshCatalysts} new catalyst${counts.freshCatalysts === 1 ? "" : "s"}`,
      intent: "headline_asc",
      tone: "neutral",
      title: `Headlines fresher than ${formatLookback(lookbackMin)}`,
      disabled: counts.freshCatalysts === 0,
    },
  ];

  const nothing = chips.every((c) => c.disabled);

  return (
    <section className="panel what-changed" aria-label="What changed since your last visit">
      <div className="what-changed__row">
        <span className="what-changed__label">Since your {formatLookback(lookbackMin)}:</span>
        {nothing ? (
          <span className="what-changed__empty">
            Nothing notable moved — refresh intelligence to re-score.
          </span>
        ) : (
          <div className="what-changed__chips">
            {chips.map((c) => (
              <button
                key={c.key}
                type="button"
                className={`what-changed__chip what-changed__chip--${c.tone}${
                  c.disabled ? " what-changed__chip--disabled" : ""
                }`}
                title={c.title}
                onClick={() => !c.disabled && handleClick(c.intent)}
                disabled={c.disabled}
              >
                {c.label}
              </button>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
