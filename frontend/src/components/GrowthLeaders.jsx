import { Fragment, useEffect, useState } from "react";
import { fetchGrowthLeaders, fetchChart } from "../api";

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

function SixMoSparkline({ closes, dates, width = 760, height = 160 }) {
  if (!closes || closes.length < 2) {
    return <div className="growth-modal__chart-empty">No price history available.</div>;
  }
  const padL = 56, padR = 12, padT = 12, padB = 22;
  const innerW = width - padL - padR;
  const innerH = height - padT - padB;

  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const range = max - min || 1;
  const stepX = innerW / (closes.length - 1);

  const points = closes.map((c, i) => {
    const x = padL + i * stepX;
    const y = padT + (1 - (c - min) / range) * innerH;
    return [x, y];
  });
  const path = points
    .map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`)
    .join(" ");
  const areaPath = `${path} L${(padL + innerW).toFixed(1)},${(padT + innerH).toFixed(1)} L${padL.toFixed(1)},${(padT + innerH).toFixed(1)} Z`;

  const start = closes[0];
  const end = closes[closes.length - 1];
  const ret = (end - start) / start;
  const lineColor = ret >= 0 ? "#16a34a" : "#dc2626";
  const fillColor = ret >= 0 ? "rgba(22,163,74,0.10)" : "rgba(220,38,38,0.10)";

  const startDate = dates?.[0] ?? "";
  const endDate = dates?.[dates.length - 1] ?? "";

  return (
    <svg
      className="growth-modal__chart-svg"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      role="img"
      aria-label="6 month price chart"
    >
      <line x1={padL} y1={padT} x2={padL} y2={padT + innerH} stroke="var(--border)" strokeWidth="1" />
      <line x1={padL} y1={padT + innerH} x2={padL + innerW} y2={padT + innerH} stroke="var(--border)" strokeWidth="1" />

      <text x={padL - 6} y={padT + 4} textAnchor="end" fontSize="10" fill="var(--text-dim)">
        ${max.toFixed(2)}
      </text>
      <text x={padL - 6} y={padT + innerH} textAnchor="end" fontSize="10" fill="var(--text-dim)">
        ${min.toFixed(2)}
      </text>

      <path d={areaPath} fill={fillColor} stroke="none" />
      <path d={path} fill="none" stroke={lineColor} strokeWidth="2" />

      <circle
        cx={points[points.length - 1][0]}
        cy={points[points.length - 1][1]}
        r="3"
        fill={lineColor}
      />

      <text x={padL} y={height - 6} fontSize="10" fill="var(--text-dim)">{startDate}</text>
      <text x={padL + innerW} y={height - 6} textAnchor="end" fontSize="10" fill="var(--text-dim)">{endDate}</text>
    </svg>
  );
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
  const [expandedTicker, setExpandedTicker] = useState(null);
  const [chartByTicker, setChartByTicker] = useState({});
  const [chartLoading, setChartLoading] = useState(null);
  const [chartError, setChartError] = useState({});

  const handleRowClick = async (ticker) => {
    if (expandedTicker === ticker) {
      setExpandedTicker(null);
      return;
    }
    setExpandedTicker(ticker);
    if (chartByTicker[ticker]) return;
    setChartLoading(ticker);
    setChartError((m) => ({ ...m, [ticker]: null }));
    try {
      const c = await fetchChart(ticker, "6mo");
      setChartByTicker((m) => ({ ...m, [ticker]: c }));
    } catch (e) {
      setChartError((m) => ({ ...m, [ticker]: e.message || "Failed to load chart" }));
    } finally {
      setChartLoading((cur) => (cur === ticker ? null : cur));
    }
  };

  useEffect(() => {
    if (!open) {
      setExpandedTicker(null);
      return;
    }
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
                    const isExpanded = expandedTicker === row.ticker;
                    const chart = chartByTicker[row.ticker];
                    const isChartLoading = chartLoading === row.ticker;
                    const cErr = chartError[row.ticker];
                    return (
                      <Fragment key={row.ticker}>
                        <tr
                          className={`growth-modal__row${isExpanded ? " growth-modal__row--open" : ""}`}
                          onClick={() => handleRowClick(row.ticker)}
                          tabIndex={0}
                          role="button"
                          aria-expanded={isExpanded}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              handleRowClick(row.ticker);
                            }
                          }}
                        >
                          <td className="growth-modal__rank">{i + 1}</td>
                          <td>
                            <strong>{row.ticker}</strong>
                            <span className="growth-modal__caret" aria-hidden>
                              {isExpanded ? "▾" : "▸"}
                            </span>
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
                        {isExpanded && (
                          <tr className="growth-modal__chart-row">
                            <td colSpan={8}>
                              <div className="growth-modal__chart">
                                <div className="growth-modal__chart-head">
                                  <span>{row.ticker} · 6 month price</span>
                                  {m.lastClose != null && (
                                    <span className="growth-modal__chart-price">
                                      ${m.lastClose.toFixed(2)}
                                      <span className={`growth-modal__num growth-modal__num--${pctTone(m.return6mo)}`}>
                                        {" "}({pct(m.return6mo)})
                                      </span>
                                    </span>
                                  )}
                                </div>
                                {isChartLoading && (
                                  <div className="growth-modal__chart-empty">Loading chart…</div>
                                )}
                                {!isChartLoading && cErr && (
                                  <div className="growth-modal__chart-empty">Failed: {cErr}</div>
                                )}
                                {!isChartLoading && !cErr && chart && (
                                  <SixMoSparkline closes={chart.closes} dates={chart.dates} />
                                )}
                              </div>
                            </td>
                          </tr>
                        )}
                      </Fragment>
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
