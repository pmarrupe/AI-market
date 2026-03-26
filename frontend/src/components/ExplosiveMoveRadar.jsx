import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchExplosiveRadar } from "../api";
import StatCard from "./ui/StatCard";
import TableSkeleton from "./ui/TableSkeleton";
import EmptyState from "./ui/EmptyState";
import Tooltip from "./ui/Tooltip";

const SETUP_TYPES = [
  "",
  "Fresh IPO Momentum",
  "News Catalyst Breakout",
  "Low Liquidity Spike",
  "Multi-Day Momentum Continuation",
  "Gap-and-Go Speculative Move",
  "Weak Quality Spike",
  "Sector Sympathy Move",
  "High Volume Reversal",
  "No Clear Edge",
];

const TT = {
  jump:
    "Jump (0–100): structural momentum/volume/breakout energy. High jump without confidence can still be fragile.",
  catalyst:
    "Catalyst (0–100): linked headlines + theme keywords (sqrt-damped). Not fact-checking — narrative proximity only.",
  risk: "Risk (0–100): illiquidity, gap fades, orphan spikes, micro dollar volume, volatility expansion.",
  confidence:
    "Confidence (0–100): data completeness + cross-checks (history, RVOL, $ volume, news, agreement). Not direction.",
  ranked:
    "Ranked opportunity: tunable blend of jump, catalyst, confidence, signal agreement minus risk. Default list order from API uses this when sort=opportunity.",
  ticker: "Ticker symbol.",
  company: "Company name associated with the ticker.",
  price: "Latest snapshot price used by the radar (not intraday).",
  change1dPct: "1-day price change percent (used to detect momentum/extension).",
  change3dPct: "3-day price change percent (used to detect multi-day continuation).",
  relativeVolume:
    "Relative volume vs recent baseline (higher usually = stronger activity).",
  setupType:
    "Setup type: the classification of why the move might happen (e.g., gap-and-go, momentum continuation).",
  flags:
    "Flags summarize data/structure issues (e.g., Fragile = thin liquidity / gap-fade risk; Low data = low confidence).",
  topReason:
    "Top reason: a short human-readable summary from the radar model describing the most important driver(s).",
};

function scoreTone(score) {
  if (score == null || Number.isNaN(score)) return "neutral";
  if (score >= 65) return "high";
  if (score >= 40) return "mid";
  return "low";
}

function Sparkline({ values }) {
  if (!values || values.length < 2) {
    return (
      <div className="radar-spark-empty">Price history unavailable</div>
    );
  }
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
    <svg
      className="radar-spark"
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      aria-hidden
    >
      <polyline
        fill="none"
        stroke="url(#radarSparkGrad)"
        strokeWidth="1.5"
        points={pts.join(" ")}
      />
      <defs>
        <linearGradient id="radarSparkGrad" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#4f7dff" />
          <stop offset="100%" stopColor="#75c2ff" />
        </linearGradient>
      </defs>
    </svg>
  );
}

export default function ExplosiveMoveRadar() {
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);
  const [filters, setFilters] = useState({
    minJump: "",
    maxRisk: "",
    setupType: "",
    sector: "",
    minPrice: "",
    maxPrice: "",
    newsOnly: false,
    lowFloatOnly: false,
    serverSort: "opportunity",
  });
  const [sort, setSort] = useState({
    key: "rankedOpportunityScore",
    dir: "desc",
  });

  const buildQuery = useCallback((f) => {
    const q = {};
    if (f.minJump !== "" && !Number.isNaN(Number(f.minJump))) {
      q.min_jump = Number(f.minJump);
    }
    if (f.maxRisk !== "" && !Number.isNaN(Number(f.maxRisk))) {
      q.max_risk = Number(f.maxRisk);
    }
    if (f.setupType) q.setup_type = f.setupType;
    if (f.sector) q.sector = f.sector;
    if (f.minPrice !== "" && !Number.isNaN(Number(f.minPrice))) {
      q.min_price = Number(f.minPrice);
    }
    if (f.maxPrice !== "" && !Number.isNaN(Number(f.maxPrice))) {
      q.max_price = Number(f.maxPrice);
    }
    if (f.newsOnly) q.news_catalyst_only = true;
    if (f.lowFloatOnly) q.low_float_only = true;
    if (f.serverSort) q.sort = f.serverSort;
    return q;
  }, []);

  const load = useCallback(
    async (f = null) => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchExplosiveRadar(buildQuery(f || filters));
        setPayload(data);
      } catch (e) {
        setError(e.message || "Failed to load radar");
        setPayload(null);
      } finally {
        setLoading(false);
      }
    },
    [buildQuery, filters]
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchExplosiveRadar({ sort: "opportunity" });
        if (!cancelled) setPayload(data);
      } catch (e) {
        if (!cancelled) {
          setError(e.message || "Failed to load radar");
          setPayload(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const sectors = useMemo(() => {
    const items = payload?.items || [];
    const s = new Set();
    items.forEach((r) => {
      if (r.sector) s.add(r.sector);
    });
    return Array.from(s).sort();
  }, [payload]);

  const sortedItems = useMemo(() => {
    const items = [...(payload?.items || [])];
    const { key, dir } = sort;
    const mul = dir === "asc" ? 1 : -1;
    items.sort((a, b) => {
      const av = a[key] ?? -1e12;
      const bv = b[key] ?? -1e12;
      if (typeof av === "string" && typeof bv === "string") {
        return mul * av.localeCompare(bv);
      }
      return mul * (av - bv);
    });
    return items;
  }, [payload, sort]);

  const toggleSort = (key) => {
    setSort((prev) =>
      prev.key === key
        ? { key, dir: prev.dir === "asc" ? "desc" : "asc" }
        : { key, dir: "desc" }
    );
  };

  const sortLabel = (key, label) => (
    <button
      type="button"
      className="radar-th-sort"
      onClick={() => toggleSort(key)}
    >
      {label}
      {sort.key === key ? (sort.dir === "asc" ? " ↑" : " ↓") : ""}
    </button>
  );

  const sortTh = (key, label, tip) => (
    <th>
      <Tooltip text={tip}>
        <button
          type="button"
          className="radar-th-sort"
          onClick={() => toggleSort(key)}
        >
          {label}
          {sort.key === key ? (sort.dir === "asc" ? " ↑" : " ↓") : ""}
        </button>
      </Tooltip>
    </th>
  );

  const staticTh = (label, tip) => (
    <th>
      <Tooltip text={tip}>
        <span className="radar-th-sort">{label}</span>
      </Tooltip>
    </th>
  );

  const summary = payload?.summary || {};
  const floatReported = payload?.meta?.floatReportedAvailable;

  return (
    <section id="explosive-radar" className="scanner-section explosive-radar">
      <div className="scanner-header">
        <div className="scanner-title-row">
          <div className="scanner-title-group">
            <span className="scanner-icon" aria-hidden>
              ◆
            </span>
            <div>
              <h2 className="scanner-title">Explosive Move Radar</h2>
              <p className="scanner-subtitle">
                Abnormal momentum / catalyst radar — probabilistic setup detection,
                not price guarantees. High-volatility breakout setups only.
              </p>
            </div>
          </div>
          <button type="button" className="radar-refresh" onClick={() => load()}>
            Refresh radar
          </button>
        </div>
        {payload?.disclaimer && (
          <p className="radar-disclaimer">{payload.disclaimer}</p>
        )}
        {payload?.mock && (
          <p className="radar-mock-pill">Mock sample data (EXPLOSIVE_RADAR_MOCK)</p>
        )}
      </div>

      <div className="radar-kpi-row">
        <StatCard
          label="Stocks scanned"
          value={summary.stocksScanned ?? "—"}
          variant="blue"
          trend="flat"
          icon={
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
              <rect x="2" y="3" width="12" height="10" rx="1" stroke="currentColor" strokeWidth="1.3" />
            </svg>
          }
        />
        <StatCard
          label="High jump score"
          value={summary.highJumpCandidates ?? "—"}
          variant="purple"
          trend="up"
          icon={
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
              <path d="M3 12l4-6 3 3 5-7" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
            </svg>
          }
        />
        <StatCard
          label="News-driven"
          value={summary.newsDrivenCandidates ?? "—"}
          variant="green"
          trend="up"
          icon={
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
              <path d="M4 3h8v10H4z" stroke="currentColor" strokeWidth="1.2" />
              <path d="M6 6h4M6 9h4" stroke="currentColor" strokeWidth="1.2" />
            </svg>
          }
        />
        <StatCard
          label="High risk"
          value={summary.highRiskCandidates ?? "—"}
          variant="gold"
          trend="down"
          icon={
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
              <path d="M8 2v10M8 14h.01" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
            </svg>
          }
        />
      </div>

      <div className="scanner-filters radar-filters">
        <input
          type="number"
          className="radar-input"
          placeholder="Min jump"
          min={0}
          max={100}
          value={filters.minJump}
          onChange={(e) =>
            setFilters((f) => ({ ...f, minJump: e.target.value }))
          }
        />
        <input
          type="number"
          className="radar-input"
          placeholder="Max risk"
          min={0}
          max={100}
          value={filters.maxRisk}
          onChange={(e) =>
            setFilters((f) => ({ ...f, maxRisk: e.target.value }))
          }
        />
        <select
          value={filters.setupType}
          onChange={(e) =>
            setFilters((f) => ({ ...f, setupType: e.target.value }))
          }
        >
          {SETUP_TYPES.map((s) => (
            <option key={s || "all"} value={s}>
              {s || "All setup types"}
            </option>
          ))}
        </select>
        <select
          value={filters.sector}
          onChange={(e) =>
            setFilters((f) => ({ ...f, sector: e.target.value }))
          }
        >
          <option value="">All sectors</option>
          {sectors.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <input
          type="number"
          className="radar-input"
          placeholder="Min price"
          min={0}
          step="0.01"
          value={filters.minPrice}
          onChange={(e) =>
            setFilters((f) => ({ ...f, minPrice: e.target.value }))
          }
        />
        <input
          type="number"
          className="radar-input"
          placeholder="Max price"
          min={0}
          step="0.01"
          value={filters.maxPrice}
          onChange={(e) =>
            setFilters((f) => ({ ...f, maxPrice: e.target.value }))
          }
        />
        <label className="radar-check">
          <input
            type="checkbox"
            checked={filters.newsOnly}
            onChange={(e) =>
              setFilters((f) => ({ ...f, newsOnly: e.target.checked }))
            }
          />
          News catalyst only
        </label>
        <select
          className="radar-select"
          value={filters.serverSort}
          onChange={(e) =>
            setFilters((f) => ({ ...f, serverSort: e.target.value }))
          }
          title="Server-side ordering before client column sort"
        >
          <option value="opportunity">Rank: opportunity (default)</option>
          <option value="jump">Rank: jump score</option>
        </select>
        <label
          className={`radar-check ${!floatReported ? "radar-check--muted" : ""}`}
          title={
            floatReported
              ? "Filter to tickers with reported float"
              : "No reported float in data — uses high RVOL + low liquidity heuristic"
          }
        >
          <input
            type="checkbox"
            checked={filters.lowFloatOnly}
            onChange={(e) =>
              setFilters((f) => ({ ...f, lowFloatOnly: e.target.checked }))
            }
          />
          Low float only
        </label>
        <button type="button" className="radar-apply" onClick={() => load()}>
          Apply filters
        </button>
      </div>

      <div className="scanner-table-wrap radar-table-wrap">
        {loading && !payload && <TableSkeleton columns={13} rows={5} />}
        {error && (
          <EmptyState title="Radar unavailable" description={error} />
        )}
        {!loading && !error && sortedItems.length === 0 && (
          <EmptyState
            title="No setups match"
            description="Relax filters or refresh intelligence so tickers have fresh history."
          />
        )}
        {!loading && !error && sortedItems.length > 0 && (
          <div className="radar-legend">
            <span className="radar-legend__label">Score color tone</span>
            <span className="radar-legend__item">
              <span className="radar-score radar-score--high">High</span> (>= 65)
            </span>
            <span className="radar-legend__item">
              <span className="radar-score radar-score--mid">Mid</span> (40–64)
            </span>
            <span className="radar-legend__item">
              <span className="radar-score radar-score--low">Low</span> (&lt; 40)
            </span>
            <span className="radar-legend__note">
              Applies to Opp / Jump / Cat / Risk / Conf (confidence is data quality, not direction).
            </span>
          </div>
        )}
        {!error && sortedItems.length > 0 && (
          <table className="scanner-table radar-table">
            <thead>
              <tr>
                <th>
                  <Tooltip text={TT.ticker}>
                    <span>{sortLabel("ticker", "Ticker")}</span>
                  </Tooltip>
                </th>
                {staticTh("Company", TT.company)}
                {sortTh("price", "Price", TT.price)}
                {sortTh("change1dPct", "1D %", TT.change1dPct)}
                {sortTh("change3dPct", "3D %", TT.change3dPct)}
                {sortTh("relativeVolume", "Rel vol", TT.relativeVolume)}
                {sortTh("rankedOpportunityScore", "Opp", TT.ranked)}
                {sortTh("jumpScore", "Jump", TT.jump)}
                {sortTh("catalystScore", "Cat", TT.catalyst)}
                {sortTh("riskScore", "Risk", TT.risk)}
                {sortTh("confidenceScore", "Conf", TT.confidence)}
                <th>
                  <Tooltip text={TT.setupType}>
                    <span>{sortLabel("setupType", "Setup")}</span>
                  </Tooltip>
                </th>
                {staticTh("Flags", TT.flags)}
                {staticTh("Top reason", TT.topReason)}
              </tr>
            </thead>
            <tbody>
              {sortedItems.map((row) => (
                <tr
                  key={row.ticker}
                  className={`stock-row radar-row${row.fragileSetup ? " radar-row--fragile" : ""}`}
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
                  <td className="td-ticker">
                    <strong>{row.ticker}</strong>
                  </td>
                  <td className="radar-co">{row.companyName}</td>
                  <td className="td-price">
                    {row.price != null ? `$${Number(row.price).toFixed(2)}` : "—"}
                  </td>
                  <td className="td-change">
                    {row.change1dPct != null
                      ? `${Number(row.change1dPct).toFixed(2)}%`
                      : "—"}
                  </td>
                  <td className="td-change">
                    {row.change3dPct != null
                      ? `${Number(row.change3dPct).toFixed(2)}%`
                      : "—"}
                  </td>
                  <td>
                    {row.relativeVolume != null
                      ? `${Number(row.relativeVolume).toFixed(2)}x`
                      : "—"}
                  </td>
                  <td>
                    <span
                      className={`radar-score radar-score--opp-${scoreTone(
                        row.rankedOpportunityScore
                      )}`}
                    >
                      {row.rankedOpportunityScore ?? "—"}
                    </span>
                  </td>
                  <td>
                    <span
                      className={`radar-score radar-score--${scoreTone(row.jumpScore)}`}
                    >
                      {row.jumpScore}
                    </span>
                  </td>
                  <td>
                    <span
                      className={`radar-score radar-score--cat-${scoreTone(row.catalystScore)}`}
                    >
                      {row.catalystScore}
                    </span>
                  </td>
                  <td>
                    <span
                      className={`radar-score radar-score--risk-${scoreTone(row.riskScore)}`}
                    >
                      {row.riskScore}
                    </span>
                  </td>
                  <td>
                    <span
                      className={`radar-score radar-score--conf-${scoreTone(
                        row.confidenceScore
                      )}`}
                    >
                      {row.confidenceScore ?? "—"}
                    </span>
                  </td>
                  <td>
                    <span className="pill radar-setup-pill">{row.setupType}</span>
                    <div className="radar-driver">{row.setupDriver || "—"}</div>
                  </td>
                  <td className="radar-flags">
                    {row.fragileSetup && (
                      <span className="radar-flag radar-flag--fragile">Fragile</span>
                    )}
                    {(row.confidenceScore ?? 100) < 45 && (
                      <span className="radar-flag radar-flag--lowconf">Low data</span>
                    )}
                    {!row.fragileSetup &&
                      (row.confidenceScore ?? 100) >= 45 && (
                        <span className="radar-flag radar-flag--ok">—</span>
                      )}
                  </td>
                  <td className="radar-reason">{row.topReason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {selected && (
        <div
          className="radar-drawer-backdrop"
          role="presentation"
          onClick={() => setSelected(null)}
        >
          <aside
            className="radar-drawer"
            role="dialog"
            aria-modal="true"
            aria-labelledby="radar-drawer-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="radar-drawer-head">
              <h3 id="radar-drawer-title">
                {selected.ticker}{" "}
                <span className="radar-drawer-sub">{selected.companyName}</span>
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
              {(selected.badges || []).map((b) => (
                <span key={b} className="signal-badge signal-watch">
                  {b}
                </span>
              ))}
            </div>
            {selected.fragileSetup && (
              <p className="radar-drawer-warn">
                Fragile setup: thin liquidity, gap fade, or price spike without confirmation —
                treat jump score as noisy.
              </p>
            )}
            <div className="radar-drawer-metrics">
              <div>
                <span className="detail-card-label">Price</span>
                <p>
                  {selected.price != null
                    ? `$${Number(selected.price).toFixed(2)}`
                    : "—"}
                </p>
              </div>
              <div>
                <span className="detail-card-label">Driver</span>
                <p>{selected.setupDriver || "—"}</p>
              </div>
              <div>
                <span className="detail-card-label">Opp / jump / cat / risk / conf</span>
                <p>
                  {selected.rankedOpportunityScore ?? "—"} / {selected.jumpScore} /{" "}
                  {selected.catalystScore} / {selected.riskScore} /{" "}
                  {selected.confidenceScore ?? "—"}
                </p>
              </div>
              <div>
                <span className="detail-card-label">Setup</span>
                <p>{selected.setupType}</p>
              </div>
              <div>
                <span className="detail-card-label">Data source</span>
                <p>{selected.dataSource || "—"}</p>
              </div>
            </div>
            <div className="detail-card-label">Signal quality</div>
            <div className="detail-card radar-detail-block">
              <p>{selected.signalQualitySummary || "—"}</p>
              <p className="detail-meta">
                Agreement buckets (momentum/volume/catalyst/…):{" "}
                {selected.signalAgreementCount ?? 0}/6
              </p>
            </div>
            <div className="detail-card-label">What is missing</div>
            <ul className="radar-drawer-list">
              {(selected.missingDataFields || []).length === 0 ? (
                <li className="detail-note">Structural flags only — vendor fields not wired.</li>
              ) : (
                (selected.missingDataFields || []).map((x) => (
                  <li key={x}>{x}</li>
                ))
              )}
            </ul>
            <div className="detail-card-label">Why this may fail</div>
            <ul className="radar-drawer-list radar-drawer-list--risk">
              {(selected.riskNotes || []).map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
            <div className="detail-card-label">Recent closes (sparkline)</div>
            <Sparkline values={selected.priceHistory} />
            <div className="detail-card-label">Explainability</div>
            <ul className="radar-drawer-list">
              {(selected.reasons || []).map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
            <div className="detail-card-label">Headlines</div>
            {(selected.headlines || []).length === 0 ? (
              <p className="detail-note">No linked headlines in snapshot.</p>
            ) : (
              <ul className="radar-drawer-list">
                {selected.headlines.map((h) => (
                  <li key={h.title}>
                    <a href={h.url} target="_blank" rel="noreferrer">
                      {h.title}
                    </a>
                    <span className="detail-meta"> · {h.source}</span>
                  </li>
                ))}
              </ul>
            )}
          </aside>
        </div>
      )}
    </section>
  );
}
