import { useEffect, useState } from "react";
import { fetchGrowthLeaders } from "../api";

function pct(v) {
  if (v == null || !Number.isFinite(v)) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${(v * 100).toFixed(1)}%`;
}

function pctTone(v) {
  if (v == null || !Number.isFinite(v)) return "muted";
  if (v >= 0.30) return "pos";
  if (v >= 0.10) return "pos-soft";
  if (v <= -0.10) return "neg";
  return "muted";
}

function trendBadge(metrics) {
  if (!metrics) return null;
  const { sma50, sma200, lastClose } = metrics;
  if (sma50 == null || sma200 == null || lastClose == null) return null;
  const above200 = lastClose > sma200;
  const goldenCross = sma50 > sma200;
  if (above200 && goldenCross) return { label: "Stage 2", tone: "pos" };
  if (above200 && !goldenCross) return { label: "Recovering", tone: "pos-soft" };
  if (!above200 && goldenCross) return { label: "Wobbly", tone: "muted" };
  return { label: "Below trend", tone: "neg" };
}

export default function GrowthLeaders({ open, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchGrowthLeaders({ limit: 20 })
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message || "Failed to load growth leaders");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      if (e.key === "Escape") onClose?.();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const items = data?.items || [];
  const spy = data?.spyReturn6mo;

  return (
    <div
      className="growth-modal-backdrop"
      role="presentation"
      onClick={onClose}
    >
      <div
        className="growth-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="growth-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="growth-modal__head">
          <div>
            <h3 id="growth-modal-title">Growth Leaders</h3>
            <p className="growth-modal__sub">
              Stocks showing the multi-quarter signature — sustained price strength,
              trend alignment, 52w-high proximity, outperformance vs SPY, volume pickup.
              Months horizon. Not a prediction; surfaces the pattern.
            </p>
          </div>
          <button
            type="button"
            className="growth-modal__close"
            onClick={onClose}
            aria-label="Close"
          >
            ×
          </button>
        </div>

        {loading && (
          <div className="growth-modal__state">
            <div className="loading-spinner" />
            <p>Scanning universe — fetching 1y of bars per ticker…</p>
          </div>
        )}
        {error && !loading && (
          <div className="growth-modal__state growth-modal__state--err">
            <p>Failed: {error}</p>
          </div>
        )}
        {!loading && !error && items.length === 0 && (
          <div className="growth-modal__state">
            <p>No growth leaders found in the current universe.</p>
          </div>
        )}

        {!loading && !error && items.length > 0 && (
          <>
            <div className="growth-modal__meta">
              <span>Scanned {data.totalScanned} stocks</span>
              <span>·</span>
              <span>SPY 6mo: {pct(spy)}</span>
              <span>·</span>
              <span>Top {items.length} by composite score</span>
            </div>
            <div className="growth-modal__table-wrap">
              <table className="growth-modal__table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Ticker</th>
                    <th title="Composite of 6mo return, RS vs SPY, trend, proximity to high, volume">
                      Score
                    </th>
                    <th title="6-month price return">6mo</th>
                    <th title="12-month price return">12mo</th>
                    <th title="Distance below 52-week high (lower is better)">From hi</th>
                    <th title="Trend alignment with 50d/200d MAs">Trend</th>
                    <th title="20-day vs 60-day average volume ratio">Vol</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((row, i) => {
                    const m = row.metrics || {};
                    const tb = trendBadge(m);
                    return (
                      <tr key={row.ticker}>
                        <td className="growth-modal__rank">{i + 1}</td>
                        <td>
                          <strong>{row.ticker}</strong>
                          <div className="growth-modal__co">
                            {row.company || ""}
                            {row.sector ? (
                              <span className="growth-modal__sector"> · {row.sector}</span>
                            ) : null}
                          </div>
                        </td>
                        <td>
                          <span className="growth-modal__score">
                            {(row.growthScore * 100).toFixed(0)}
                          </span>
                        </td>
                        <td className={`growth-modal__num growth-modal__num--${pctTone(m.return6mo)}`}>
                          {pct(m.return6mo)}
                        </td>
                        <td className={`growth-modal__num growth-modal__num--${pctTone(m.return12mo)}`}>
                          {pct(m.return12mo)}
                        </td>
                        <td className="growth-modal__num">
                          {m.distFromHigh != null ? `-${(m.distFromHigh * 100).toFixed(1)}%` : "—"}
                        </td>
                        <td>
                          {tb ? (
                            <span className={`growth-modal__chip growth-modal__chip--${tb.tone}`}>
                              {tb.label}
                            </span>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="growth-modal__num">
                          {m.vol20over60 != null ? `${m.vol20over60.toFixed(2)}×` : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="growth-modal__disclaimer">{data.disclaimer}</p>
          </>
        )}
      </div>
    </div>
  );
}
