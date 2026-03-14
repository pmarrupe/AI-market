import { useState, useMemo } from "react";
import StatusPill from "./ui/StatusPill";
import Tooltip from "./ui/Tooltip";
import TableSkeleton from "./ui/TableSkeleton";
import EmptyState from "./ui/EmptyState";

const SORT_OPTIONS = [
  { value: "rank_asc", label: "Best opportunities" },
  { value: "confidence_desc", label: "Highest confidence" },
  { value: "evidence_desc", label: "Most evidence" },
  { value: "momentum_desc", label: "Strongest momentum" },
  { value: "delta_desc", label: "Biggest Δ score" },
  { value: "headline_asc", label: "Most recent headline" },
];

function getSortKey(sortValue) {
  const map = {
    rank: "opportunityRank",
    confidence: "confidence",
    evidence: "evidence_count",
    momentum: "momentum",
    delta: "score_delta",
    headline: "last_headline_minutes",
  };
  return map[sortValue] || "opportunityRank";
}

export default function StockScanner({
  rows = [],
  sectors = [],
  signalLabels = [],
  riskLevels = [],
  timeHorizons = [],
  statuses = [],
  isLoading = false,
  onRequestRefresh,
}) {
  const [filters, setFilters] = useState({
    sector: "",
    signal: "",
    risk: "",
    horizon: "",
    status: "",
  });
  const [sortBy, setSortBy] = useState("rank_asc");
  const [expandedRows, setExpandedRows] = useState(new Set());

  const filtered = useMemo(() => {
    let result = rows.filter(
      (r) =>
        (!filters.sector || r.sector === filters.sector) &&
        (!filters.signal || r.signalLabel === filters.signal) &&
        (!filters.risk || r.riskLevel === filters.risk) &&
        (!filters.horizon || r.timeHorizon === filters.horizon) &&
        (!filters.status || r.status === filters.status)
    );

    const [metric, direction] = sortBy.split("_");
    const key = getSortKey(metric);
    result.sort((a, b) => {
      const aVal = a[key] ?? -999;
      const bVal = b[key] ?? -999;
      return direction === "asc" ? aVal - bVal : bVal - aVal;
    });

    return result;
  }, [rows, filters, sortBy]);

  const toggleRow = (ticker) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(ticker)) next.delete(ticker);
      else next.add(ticker);
      return next;
    });
  };

  const updateFilter = (key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  };

  const renderBody = () => {
    if (isLoading && rows.length === 0) {
      return <TableSkeleton columns={10} rows={6} />;
    }

    if (rows.length === 0) {
      return (
        <EmptyState
          title="No stock scores yet"
          description="Run the intelligence engine to populate AI-scored equities."
          actionLabel="Refresh Intelligence"
          onAction={onRequestRefresh}
          icon={
            <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
              <path d="M8 32l6-10 5 5 8-14 5 7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              <rect x="4" y="6" width="32" height="28" rx="4" stroke="currentColor" strokeWidth="1.5" />
            </svg>
          }
        />
      );
    }

    if (filtered.length === 0) {
      return (
        <EmptyState
          title="No matches"
          description="No stocks match the current filter combination. Try adjusting your criteria."
        />
      );
    }

    return (
      <div className="scanner-table-wrap">
        <table className="scanner-table">
          <thead>
            <tr>
              <th></th>
              <th>Ticker</th>
              <th>Sector</th>
              <th>Price</th>
              <th>1D</th>
              <th title="Model score 0–1">Score</th>
              <th>Confidence</th>
              <th>Risk</th>
              <th>Status</th>
              <th>AI Summary</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((row, idx) => (
              <StockRow
                key={row.ticker}
                row={row}
                expanded={expandedRows.has(row.ticker)}
                onToggle={() => toggleRow(row.ticker)}
                animDelay={idx * 30}
              />
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  return (
    <section id="stocks" className="scanner-section">
      <div className="scanner-header">
        <div className="scanner-title-row">
          <div className="scanner-title-group">
            <span className="scanner-icon">&#9878;</span>
            <div>
              <h2 className="scanner-title">AI Stock Opportunity Scanner</h2>
              <p className="scanner-subtitle">
                Real-time AI-scored equities &middot; {rows.length} tracked
              </p>
            </div>
          </div>
          <div className="scanner-filters">
            <select value={filters.sector} onChange={(e) => updateFilter("sector", e.target.value)} title="Sector">
              <option value="">Sector</option>
              {sectors.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <select value={filters.signal} onChange={(e) => updateFilter("signal", e.target.value)} title="Signal">
              <option value="">Signal</option>
              {signalLabels.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <select value={filters.risk} onChange={(e) => updateFilter("risk", e.target.value)} title="Risk">
              <option value="">Risk</option>
              {riskLevels.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <select value={filters.horizon} onChange={(e) => updateFilter("horizon", e.target.value)} title="Horizon">
              <option value="">Horizon</option>
              {timeHorizons.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <select value={filters.status} onChange={(e) => updateFilter("status", e.target.value)} title="Status">
              <option value="">Status</option>
              {statuses.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} title="Sort by">
              {SORT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
        </div>
      </div>
      {renderBody()}
    </section>
  );
}

function StockRow({ row, expanded, onToggle, animDelay = 0 }) {
  const dayChangeClass = row.day_change > 0 ? "up" : row.day_change < 0 ? "down" : "";
  const scoreWidth = Math.floor((row.score ?? 0) * 100);

  return (
    <>
      <tr
        className="stock-row stock-row--animate"
        style={{ animationDelay: `${animDelay}ms` }}
      >
        <td className="td-toggle">
          <button className="row-toggle" onClick={onToggle} aria-expanded={expanded}>
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
              <path d="M4 2l4 4-4 4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </td>
        <td className="td-ticker">
          <strong>{row.ticker}</strong>
          <StatusPill label={row.signalLabel} />
        </td>
        <td className="td-sector">{row.sector}</td>
        <td className="td-price font-mono">${(row.price ?? 0).toFixed(2)}</td>
        <td className={`td-change font-mono ${dayChangeClass}`}>
          {((row.day_change ?? 0) * 100).toFixed(2)}%
        </td>
        <td className="td-score">
          <div className="score-cell">
            <span className="font-mono">{(row.score ?? 0).toFixed(3)}</span>
            <div className="score-micro-bar">
              <div className="score-micro-fill" style={{ width: `${scoreWidth}%` }} />
            </div>
          </div>
        </td>
        <td className="td-confidence font-mono">{(row.confidence ?? 0).toFixed(2)}</td>
        <td className="td-risk">
          <StatusPill label={row.riskLevel} />
        </td>
        <td className="td-status">
          <StatusPill label={row.status} />
        </td>
        <td className="td-summary">
          <Tooltip text={row.aiSummary}>
            <span className="td-summary__truncated">{row.aiSummary}</span>
          </Tooltip>
        </td>
      </tr>
      {expanded && (
        <tr className="detail-row">
          <td colSpan={10}>
            <div className="detail-drawer">
              <div className="detail-cards">
                <div className="detail-card">
                  <div className="detail-card-label">Overview</div>
                  <strong>{row.ticker} — {row.company}</strong>
                  <p>
                    {row.signalLabel} &middot; {row.status} &middot; {row.riskLevel} risk
                    &middot; {row.timeHorizon}
                  </p>
                  <p>
                    Score <strong className="font-mono">{(row.score ?? 0).toFixed(3)}</strong> &middot; Confidence{" "}
                    <strong className="font-mono">{(row.confidence ?? 0).toFixed(3)}</strong> &middot; Momentum{" "}
                    <strong className="font-mono">{(row.momentum ?? 0).toFixed(3)}</strong>
                    {row.score_delta != null && (
                      <>
                        {" "}&middot; Δ{" "}
                        <span className={`font-mono ${row.score_delta > 0 ? "up" : row.score_delta < 0 ? "down" : ""}`}>
                          {row.score_delta > 0 ? "+" : ""}{row.score_delta.toFixed(3)}
                        </span>
                      </>
                    )}
                  </p>
                  <p className="detail-note">{row.recommendationNote}</p>
                </div>
                <div className="detail-card">
                  <div className="detail-card-label">Why Now</div>
                  <ul>
                    {(row.whyNowBullets || []).map((b, i) => <li key={i}>{b}</li>)}
                  </ul>
                  <p className="detail-meta">
                    {row.evidence_count} evidence items &middot; {row.last_headline_age}
                  </p>
                </div>
                <div className="detail-card">
                  <div className="detail-card-label">Linked Headlines</div>
                  {row.linked_headlines?.length > 0 ? (
                    <ul>
                      {row.linked_headlines.map((h, i) => <li key={i}>{h}</li>)}
                    </ul>
                  ) : (
                    <p className="detail-meta">No linked headlines yet.</p>
                  )}
                </div>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
