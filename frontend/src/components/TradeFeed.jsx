import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchTradeFeed } from "../api";
import StatCard from "./ui/StatCard";
import TableSkeleton from "./ui/TableSkeleton";
import EmptyState from "./ui/EmptyState";
import Tooltip from "./ui/Tooltip";
import TradePlanChart from "./TradePlanChart";

const HORIZON_ORDER = ["Intraday", "Short-term", "Swing", "Long-term watch", "Unclear"];
const PORTFOLIO_KEY = "ai_market.portfolio_value";
const RISK_PCT_KEY = "ai_market.portfolio_risk_pct";

function readNumber(key, fallback) {
  try {
    const v = localStorage.getItem(key);
    if (v == null || v === "") return fallback;
    const n = Number(v);
    return Number.isFinite(n) && n > 0 ? n : fallback;
  } catch {
    return fallback;
  }
}

function writeNumber(key, value) {
  try {
    if (value == null || value === "" || !Number.isFinite(Number(value))) {
      localStorage.removeItem(key);
    } else {
      localStorage.setItem(key, String(value));
    }
  } catch {
    /* ignore */
  }
}

function suggestShares(portfolioValue, riskPct, riskPerShare) {
  if (!portfolioValue || !riskPct || !riskPerShare) return null;
  const dollarsAtRisk = portfolioValue * (riskPct / 100);
  const shares = Math.floor(dollarsAtRisk / riskPerShare);
  return shares > 0 ? shares : null;
}

function relativeTimeFromUTC(utcStr) {
  if (!utcStr) return null;
  // Backend sends "YYYY-MM-DD HH:MM:SS UTC"
  const iso = utcStr.replace(" UTC", "Z").replace(" ", "T");
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  const diffSec = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (diffSec < 5) return "just now";
  if (diffSec < 60) return `${diffSec}s ago`;
  const min = Math.floor(diffSec / 60);
  if (min < 60) return `${min}m ago`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function convictionTone(label) {
  if (label === "High") return "high";
  if (label === "Med") return "mid";
  if (label === "Low") return "low";
  return "neutral";
}

function flagTone(flag) {
  if (flag === "Fragile" || flag === "High risk") return "neg";
  if (flag === "Low data") return "warn";
  return "neutral";
}

const FLAG_PRIORITY = ["High risk", "Fragile", "Low data", "No coverage"];

function primaryFlag(flags) {
  if (!flags || flags.length === 0) return null;
  for (const f of FLAG_PRIORITY) {
    if (flags.includes(f)) return f;
  }
  return flags[0];
}

function indicatorTone(label) {
  if (label === "MACD↑" || label === "Oversold" || label === "20d HIGH") return "pos";
  if (label === "MACD↓" || label === "Overbought" || label === "20d LOW") return "neg";
  if (label && label.startsWith("VOL ")) {
    if (label === "VOL ↓") return "neg";
    return "pos"; // "VOL Nx" with N >= 1.8
  }
  return "neutral";
}

function Sparkline({ values }) {
  if (!values || values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const pad = 2;
  const w = 120;
  const h = 40;
  const span = max - min || 1;
  const pts = values.map((v, i) => {
    const x = pad + (i / (values.length - 1)) * (w - pad * 2);
    const y = h - pad - ((v - min) / span) * (h - pad * 2);
    return `${x},${y}`;
  });
  return (
    <svg className="radar-spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden>
      <polyline fill="none" stroke="#75c2ff" strokeWidth="1.5" points={pts.join(" ")} />
    </svg>
  );
}

export default function TradeFeed({ sortIntent = null, onRequestRefresh }) {
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);
  const [filters, setFilters] = useState({
    horizon: "",
    setup: "",
    sector: "",
    conviction: "",
    sort: "conviction_desc",
    hideEarningsWithin: "",
  });
  const [portfolioValue, setPortfolioValue] = useState(() => readNumber(PORTFOLIO_KEY, 10000));
  const [riskPct, setRiskPct] = useState(() => readNumber(RISK_PCT_KEY, 1));
  const [showDetails, setShowDetails] = useState(false);

  useEffect(() => writeNumber(PORTFOLIO_KEY, portfolioValue), [portfolioValue]);
  useEffect(() => writeNumber(RISK_PCT_KEY, riskPct), [riskPct]);

  const buildQuery = useCallback(
    (f, opts = {}) => ({
      horizon: f.horizon || undefined,
      setup: f.setup || undefined,
      sector: f.sector || undefined,
      conviction: f.conviction || undefined,
      sort: f.sort || "conviction_desc",
      hide_earnings_within_days: f.hideEarningsWithin || undefined,
      force: opts.force ? "true" : undefined,
      limit: 100,
    }),
    [],
  );

  const load = useCallback(
    async (f = null, opts = {}) => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchTradeFeed(buildQuery(f || filters, opts));
        setPayload(data);
      } catch (e) {
        setError(e.message || "Failed to load trade feed");
        setPayload(null);
      } finally {
        setLoading(false);
      }
    },
    [buildQuery, filters],
  );

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!sortIntent || !sortIntent.intent) return;
    setFilters((f) => ({ ...f, sort: sortIntent.intent }));
    load({ ...filters, sort: sortIntent.intent });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sortIntent]);

  const items = payload?.items || [];
  const facets = payload?.facets || {};
  const summary = payload?.summary || {};
  const sectors = facets.sectors || [];
  const setups = facets.setups || [];
  const horizons = (facets.horizons || []).slice().sort(
    (a, b) => HORIZON_ORDER.indexOf(a) - HORIZON_ORDER.indexOf(b),
  );
  const convictions = facets.convictions || ["High", "Med", "Low"];

  const sortOptions = useMemo(
    () => [
      { value: "conviction_desc", label: "Highest conviction (R:R-weighted)" },
      { value: "quality_desc", label: "Best score × R:R" },
      { value: "delta_desc", label: "Biggest Δ score (up)" },
      { value: "delta_asc", label: "Biggest Δ score (down)" },
      { value: "headline_asc", label: "Most recent headline" },
      { value: "jump_desc", label: "Biggest jump (radar)" },
    ],
    [],
  );

  const updateFilter = (key, value) => {
    setFilters((f) => ({ ...f, [key]: value }));
  };

  const applyAndReload = () => load();

  return (
    <section id="stocks" className="scanner-section trade-feed">
      <div className="scanner-header">
        <div className="scanner-title-row">
          <div className="scanner-title-group">
            <span className="scanner-icon" aria-hidden>◆</span>
            <div>
              <h2 className="scanner-title">Trade Feed</h2>
              <p className="scanner-subtitle">
                Unified ranked list &middot; {summary.total ?? 0} ideas &middot;{" "}
                {summary.highConviction ?? 0} high conviction &middot;{" "}
                {summary.bothSources ?? 0} confirmed by both sources
                {payload?.generated_at && (
                  <>
                    {" "}&middot; <span className="trade-feed__freshness">
                      updated {relativeTimeFromUTC(payload.generated_at)}
                    </span>
                  </>
                )}
              </p>
            </div>
          </div>
          <button
            type="button"
            className="radar-refresh"
            onClick={() => load(null, { force: true })}
            disabled={loading}
            title="Re-fetch trade feed and recompute trade plans (bypasses 12h bar cache)"
          >
            {loading ? "Refreshing…" : "Refresh feed"}
          </button>
        </div>
        {payload?.disclaimer && <p className="radar-disclaimer">{payload.disclaimer}</p>}
      </div>

      <div className="radar-kpi-row">
        <StatCard label="Total ideas" value={summary.total ?? "—"} variant="blue" trend="flat" />
        <StatCard label="High conviction" value={summary.highConviction ?? "—"} variant="purple" trend="up" />
        <StatCard label="Both sources agree" value={summary.bothSources ?? "—"} variant="green" trend="up" />
        <StatCard label="Radar-only spikes" value={summary.radarOnly ?? "—"} variant="gold" trend="down" />
      </div>

      <div className="trade-feed__settings" title="Used to compute suggested share size from entry − stop">
        <label>
          Portfolio $
          <input
            type="number"
            min={0}
            step="100"
            value={portfolioValue}
            onChange={(e) => setPortfolioValue(Number(e.target.value) || 0)}
          />
        </label>
        <label>
          Risk %
          <input
            type="number"
            min={0}
            max={5}
            step="0.1"
            value={riskPct}
            onChange={(e) => setRiskPct(Number(e.target.value) || 0)}
          />
        </label>
        <span className="trade-feed__settings-note">
          Plans attached: {payload?.summary?.plansAttached ?? 0}
        </span>
      </div>

      <div className="scanner-filters radar-filters">
        <select value={filters.horizon} onChange={(e) => updateFilter("horizon", e.target.value)} title="Horizon">
          <option value="">All horizons</option>
          {horizons.map((h) => <option key={h} value={h}>{h}</option>)}
        </select>
        <select value={filters.setup} onChange={(e) => updateFilter("setup", e.target.value)} title="Setup">
          <option value="">All setups</option>
          {setups.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={filters.sector} onChange={(e) => updateFilter("sector", e.target.value)} title="Sector">
          <option value="">All sectors</option>
          {sectors.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={filters.conviction} onChange={(e) => updateFilter("conviction", e.target.value)} title="Conviction">
          <option value="">Any conviction</option>
          {convictions.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={filters.sort} onChange={(e) => updateFilter("sort", e.target.value)} title="Sort by">
          {sortOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <select
          value={filters.hideEarningsWithin}
          onChange={(e) => updateFilter("hideEarningsWithin", e.target.value)}
          title="Hide picks with earnings within N days (Finnhub calendar)"
        >
          <option value="">Earnings: show all</option>
          <option value="3">Hide earnings ≤ 3d</option>
          <option value="7">Hide earnings ≤ 7d</option>
          <option value="14">Hide earnings ≤ 14d</option>
        </select>
        <label className="radar-check" title="Show Horizon / R:R / Size columns inline">
          <input
            type="checkbox"
            checked={showDetails}
            onChange={(e) => setShowDetails(e.target.checked)}
          />
          Show details
        </label>
        <button type="button" className="radar-apply" onClick={applyAndReload}>Apply</button>
      </div>

      <div className="scanner-table-wrap radar-table-wrap">
        {loading && !payload && <TableSkeleton columns={showDetails ? 11 : 8} rows={6} />}
        {error && (
          <EmptyState
            title="Trade feed unavailable"
            description={error}
            actionLabel="Retry"
            onAction={() => load()}
          />
        )}
        {!loading && !error && items.length === 0 && (
          <EmptyState
            title="No trade ideas match"
            description="Relax the filters or refresh intelligence."
            actionLabel="Refresh intelligence"
            onAction={onRequestRefresh}
          />
        )}
        {!error && items.length > 0 && (
          <table className="scanner-table radar-table trade-feed__table">
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Conviction</th>
                <th>Setup</th>
                {showDetails && <th>Horizon</th>}
                <th>
                  <Tooltip text="Entry price — last close, or 20d breakout level for gap/breakout setups.">
                    <span>Entry</span>
                  </Tooltip>
                </th>
                <th>
                  <Tooltip text="Stop — tighter of (entry − 2×ATR14) vs 10d swing low.">
                    <span>Stop</span>
                  </Tooltip>
                </th>
                <th>
                  <Tooltip text="Target 1 = entry + 2×ATR14.">
                    <span>T1</span>
                  </Tooltip>
                </th>
                {showDetails && (
                  <th>
                    <Tooltip text="Reward-to-risk to Target 1.">
                      <span>R:R</span>
                    </Tooltip>
                  </th>
                )}
                {showDetails && (
                  <th>
                    <Tooltip text="Suggested share count = (portfolio × risk%) / (entry − stop). Set portfolio $ + risk % above.">
                      <span>Size</span>
                    </Tooltip>
                  </th>
                )}
                <th>Flag</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => {
                const plan = row.plan;
                const shares = plan
                  ? suggestShares(portfolioValue, riskPct, plan.riskPerShare)
                  : null;
                const flags = row.flags || [];
                const mainFlag = primaryFlag(flags);
                const extraFlags = flags.length - (mainFlag ? 1 : 0);
                return (
                <tr
                  key={row.ticker}
                  className="stock-row radar-row"
                  onClick={() => setSelected(row)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setSelected(row);
                    }
                  }}
                  tabIndex={0}
                  role="button"
                >
                  <td className="td-ticker trade-feed__ticker-cell">
                    <div className="trade-feed__ticker-main">
                      <strong>{row.ticker}</strong>
                      <span className="font-mono trade-feed__ticker-price">
                        {row.price != null ? `$${Number(row.price).toFixed(2)}` : "—"}
                      </span>
                    </div>
                    <div className="trade-feed__co">
                      {row.company || ""}
                      {row.earnings && row.earnings.daysToNext != null && (
                        <span
                          className={`trade-feed__earnings${
                            row.earnings.daysToNext <= 7 ? " trade-feed__earnings--soon" : ""
                          }`}
                          title={`Next earnings ${row.earnings.nextDate}${
                            row.earnings.nextHour ? " · " + row.earnings.nextHour : ""
                          }`}
                        >
                          ⚡ {row.earnings.daysToNext}d
                        </span>
                      )}
                    </div>
                  </td>
                  <td>
                    <span className={`radar-score radar-score--${convictionTone(row.conviction)}`}>
                      {row.conviction}
                    </span>
                  </td>
                  <td className="trade-feed__setup-cell">
                    <span className="pill radar-setup-pill">{row.setup}</span>
                    {(plan?.indicators || []).map((ind) => (
                      <span
                        key={ind}
                        className={`indicator-chip indicator-chip--${indicatorTone(ind)}`}
                        title={
                          ind === "Overbought" ? `RSI ${plan.rsi14} — extended; risk of pullback` :
                          ind === "Oversold" ? `RSI ${plan.rsi14} — washed out; mean-reversion candidate` :
                          ind === "MACD↑" ? "Fresh MACD bullish crossover (last 3 bars)" :
                          ind === "MACD↓" ? "Fresh MACD bearish crossover (last 3 bars)" : ind
                        }
                      >
                        {ind}
                      </span>
                    ))}
                  </td>
                  {showDetails && <td className="dim">{row.horizon || "—"}</td>}
                  <td className="font-mono td-price">
                    {plan ? `$${plan.entry.toFixed(2)}` : "—"}
                  </td>
                  <td className="font-mono td-price trade-feed__stop">
                    {plan ? `$${plan.stop.toFixed(2)}` : "—"}
                  </td>
                  <td className="font-mono td-price trade-feed__target">
                    {plan ? `$${plan.target1.toFixed(2)}` : "—"}
                  </td>
                  {showDetails && (
                    <td className="font-mono">
                      {plan && plan.rewardRisk1 != null ? `${plan.rewardRisk1.toFixed(2)}×` : "—"}
                    </td>
                  )}
                  {showDetails && (
                    <td className="font-mono">
                      {shares != null ? shares : "—"}
                    </td>
                  )}
                  <td className="radar-flags">
                    {mainFlag ? (
                      <>
                        <span
                          className={`radar-flag radar-flag--${
                            flagTone(mainFlag) === "neg" ? "fragile" : "lowconf"
                          }`}
                        >
                          {mainFlag}
                        </span>
                        {extraFlags > 0 && (
                          <span
                            className="radar-flag radar-flag--ok trade-feed__flag-more"
                            title={flags.slice(1).join(" · ")}
                          >
                            +{extraFlags}
                          </span>
                        )}
                      </>
                    ) : (
                      <span className="radar-flag radar-flag--ok">—</span>
                    )}
                  </td>
                  <td className="trade-feed__source">
                    {(row.sources || []).map((s) => (
                      <span key={s} className={`trade-feed__source-tag trade-feed__source-tag--${s}`}>
                        {s}
                      </span>
                    ))}
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {selected && (
        <div className="radar-drawer-backdrop" role="presentation" onClick={() => setSelected(null)}>
          <aside
            className="radar-drawer"
            role="dialog"
            aria-modal="true"
            aria-labelledby="tf-drawer-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="radar-drawer-head">
              <h3 id="tf-drawer-title">
                {selected.ticker}{" "}
                <span className="radar-drawer-sub">{selected.company}</span>
              </h3>
              <button
                type="button"
                className="radar-drawer-close"
                onClick={() => setSelected(null)}
                aria-label="Close"
              >
                ×
              </button>
            </div>

            <div className="radar-badge-row">
              <span className={`radar-score radar-score--${convictionTone(selected.conviction)}`}>
                Conviction: {selected.conviction}
              </span>
              <span className="pill radar-setup-pill">{selected.setup}</span>
              <span className="pill">Horizon: {selected.horizon}</span>
              {(selected.sources || []).map((s) => (
                <span key={s} className={`trade-feed__source-tag trade-feed__source-tag--${s}`}>
                  {s}
                </span>
              ))}
            </div>

            {(selected.flags || []).length > 0 && (
              <p className="radar-drawer-warn">Flags: {(selected.flags || []).join(" · ")}</p>
            )}

            {selected.plan && (
              <>
                <div className="detail-card-label">Trade plan</div>
                <div className="detail-card radar-detail-block trade-feed__plan">
                  <div className="trade-feed__chart-wrap">
                    <TradePlanChart plan={selected.plan} currentPrice={selected.price} />
                    <div className="trade-feed__chart-legend">
                      <span><i style={{ background: "#5dd39e" }} />Targets</span>
                      <span><i style={{ background: "#b0b1bf" }} />Entry</span>
                      <span><i style={{ background: "#ef8b7a" }} />Stop</span>
                      <span><i style={{ background: "#8b9ff8" }} />Price (60d)</span>
                    </div>
                  </div>
                  <div className="trade-feed__plan-grid">
                    <div><span className="detail-card-label">Entry</span><p>${selected.plan.entry.toFixed(2)}</p></div>
                    <div><span className="detail-card-label">Stop</span><p className="trade-feed__stop">${selected.plan.stop.toFixed(2)}</p></div>
                    <div><span className="detail-card-label">Target 1</span><p className="trade-feed__target">${selected.plan.target1.toFixed(2)}</p></div>
                    <div><span className="detail-card-label">Target 2</span><p className="trade-feed__target">${selected.plan.target2.toFixed(2)}</p></div>
                    <div><span className="detail-card-label">ATR(14)</span><p>{selected.plan.atr14.toFixed(3)}</p></div>
                    <div><span className="detail-card-label">R:R</span><p>{selected.plan.rewardRisk1 ?? "—"}× / {selected.plan.rewardRisk2 ?? "—"}×</p></div>
                    <div><span className="detail-card-label">Risk / share</span><p>${selected.plan.riskPerShare.toFixed(2)}</p></div>
                    <div>
                      <span className="detail-card-label">Suggested shares</span>
                      <p>
                        {suggestShares(portfolioValue, riskPct, selected.plan.riskPerShare) ?? "—"}
                      </p>
                    </div>
                    {selected.plan.rsi14 != null && (
                      <div>
                        <span className="detail-card-label">RSI(14)</span>
                        <p className={
                          selected.plan.rsi14 >= 70 ? "down" :
                          selected.plan.rsi14 <= 30 ? "up" : ""
                        }>
                          {selected.plan.rsi14.toFixed(1)}
                        </p>
                      </div>
                    )}
                    {selected.plan.macd != null && (
                      <div>
                        <span className="detail-card-label">MACD / Signal</span>
                        <p className={
                          selected.plan.macdHistogram > 0 ? "up" :
                          selected.plan.macdHistogram < 0 ? "down" : ""
                        }>
                          {selected.plan.macd.toFixed(2)} / {selected.plan.macdSignal.toFixed(2)}
                        </p>
                      </div>
                    )}
                  </div>
                  <p className="detail-meta">{selected.plan.note}</p>
                </div>
              </>
            )}

            <div className="radar-drawer-metrics">
              <div>
                <span className="detail-card-label">Price</span>
                <p>{selected.price != null ? `$${Number(selected.price).toFixed(2)}` : "—"}</p>
              </div>
              <div>
                <span className="detail-card-label">Sector</span>
                <p>{selected.sector || "—"}</p>
              </div>
              <div>
                <span className="detail-card-label">Top reason</span>
                <p>{selected.topReason || "—"}</p>
              </div>
            </div>

            {selected.scanner && (
              <>
                <div className="detail-card-label">Scanner detail</div>
                <div className="detail-card radar-detail-block">
                  <p>
                    Score <strong className="font-mono">{(selected.scanner.score ?? 0).toFixed(3)}</strong>{" "}
                    · Confidence <strong className="font-mono">{(selected.scanner.confidence ?? 0).toFixed(2)}</strong>
                    {" "}· Momentum <strong className="font-mono">{(selected.scanner.momentum ?? 0).toFixed(3)}</strong>
                    {selected.scanner.scoreDelta != null && (
                      <> · Δ <span className={`font-mono ${selected.scanner.scoreDelta > 0 ? "up" : selected.scanner.scoreDelta < 0 ? "down" : ""}`}>
                        {selected.scanner.scoreDelta > 0 ? "+" : ""}{selected.scanner.scoreDelta.toFixed(3)}
                      </span></>
                    )}
                  </p>
                  <p className="detail-meta">
                    {selected.scanner.signalLabel} · {selected.scanner.status} · {selected.scanner.riskLevel} risk
                    {selected.scanner.lastHeadlineAge ? ` · headline ${selected.scanner.lastHeadlineAge}` : ""}
                  </p>
                  {selected.scanner.recommendationNote && (
                    <p className="detail-note">{selected.scanner.recommendationNote}</p>
                  )}
                </div>
                {(selected.scanner.whyNowBullets || []).length > 0 && (
                  <>
                    <div className="detail-card-label">Why now</div>
                    <ul className="radar-drawer-list">
                      {selected.scanner.whyNowBullets.map((b, i) => <li key={i}>{b}</li>)}
                    </ul>
                  </>
                )}
                {(selected.scanner.linkedHeadlines || []).length > 0 && (
                  <>
                    <div className="detail-card-label">Linked headlines</div>
                    <ul className="radar-drawer-list">
                      {selected.scanner.linkedHeadlines.map((h, i) => <li key={i}>{h}</li>)}
                    </ul>
                  </>
                )}
              </>
            )}

            {selected.radar && (
              <>
                <div className="detail-card-label">Radar detail</div>
                <div className="detail-card radar-detail-block">
                  <p>
                    Opp <strong>{selected.radar.rankedOpportunityScore ?? "—"}</strong> · Jump{" "}
                    <strong>{selected.radar.jumpScore ?? "—"}</strong> · Cat{" "}
                    <strong>{selected.radar.catalystScore ?? "—"}</strong> · Risk{" "}
                    <strong>{selected.radar.riskScore ?? "—"}</strong> · Conf{" "}
                    <strong>{selected.radar.confidenceScore ?? "—"}</strong>
                  </p>
                  <p className="detail-meta">
                    Agreement {selected.radar.signalAgreementCount ?? 0}/6 · Driver:{" "}
                    {selected.radar.setupDriver || "—"}
                  </p>
                  {selected.radar.signalQualitySummary && (
                    <p className="detail-note">{selected.radar.signalQualitySummary}</p>
                  )}
                </div>
                {(selected.radar.reasons || []).length > 0 && (
                  <>
                    <div className="detail-card-label">Explainability</div>
                    <ul className="radar-drawer-list">
                      {selected.radar.reasons.map((r) => <li key={r}>{r}</li>)}
                    </ul>
                  </>
                )}
                {(selected.radar.riskNotes || []).length > 0 && (
                  <>
                    <div className="detail-card-label">Why this may fail</div>
                    <ul className="radar-drawer-list radar-drawer-list--risk">
                      {selected.radar.riskNotes.map((r) => <li key={r}>{r}</li>)}
                    </ul>
                  </>
                )}
                {(selected.radar.priceHistory || []).length >= 2 && (
                  <>
                    <div className="detail-card-label">Recent closes</div>
                    <Sparkline values={selected.radar.priceHistory} />
                  </>
                )}
                {(selected.radar.headlines || []).length > 0 && (
                  <>
                    <div className="detail-card-label">Radar headlines</div>
                    <ul className="radar-drawer-list">
                      {selected.radar.headlines.map((h) => (
                        <li key={h.title}>
                          <a href={h.url} target="_blank" rel="noreferrer">{h.title}</a>
                          {h.source && <span className="detail-meta"> · {h.source}</span>}
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </>
            )}
          </aside>
        </div>
      )}
    </section>
  );
}
