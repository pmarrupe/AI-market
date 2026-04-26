import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchPortfolio } from "../api";
import EmptyState from "./ui/EmptyState";

const STORAGE_KEY = "ai_market.portfolio_positions";

function readPositions() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writePositions(list) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
  } catch {
    /* ignore */
  }
}

function parseCSV(text) {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("#"))
    .map((line) => {
      const [t, s, c] = line.split(/[,\t]/).map((x) => (x || "").trim());
      const ticker = (t || "").toUpperCase();
      const shares = Number(s);
      const cost = Number(c);
      if (!ticker || !Number.isFinite(shares) || shares <= 0) return null;
      return { ticker, shares, costBasis: Number.isFinite(cost) && cost > 0 ? cost : null };
    })
    .filter(Boolean);
}

function positionFlags(pos, item) {
  const flags = [];
  const plan = item?.plan;
  const price = item?.price;
  if (plan && price) {
    if (price <= plan.stop * 1.03 && price > plan.stop) flags.push({ tone: "neg", label: "Near stop" });
    else if (price < plan.stop) flags.push({ tone: "neg", label: "Below stop" });
    if (price >= plan.target1 * 0.97 && price < plan.target1) flags.push({ tone: "pos", label: "Near T1" });
    else if (price >= plan.target1) flags.push({ tone: "pos", label: "Hit T1" });
  }
  const earnDays = item?.earnings?.daysToNext;
  if (earnDays != null && earnDays <= 7) flags.push({ tone: "warn", label: `Earnings ${earnDays}d` });
  if (item?.conviction === "Low") flags.push({ tone: "warn", label: "Conviction dropped" });
  if ((item?.flags || []).includes("Fragile")) flags.push({ tone: "warn", label: "Fragile" });
  if ((item?.flags || []).includes("No coverage")) flags.push({ tone: "neutral", label: "No coverage" });
  return flags;
}

export default function Portfolio() {
  const [positions, setPositions] = useState(readPositions);
  const [pasteText, setPasteText] = useState("");
  const [editing, setEditing] = useState(false);
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => writePositions(positions), [positions]);

  const tickers = useMemo(() => positions.map((p) => p.ticker), [positions]);

  const load = useCallback(async () => {
    if (tickers.length === 0) {
      setPayload(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await fetchPortfolio(tickers);
      setPayload(data);
    } catch (e) {
      setError(e.message || "Failed to load portfolio");
    } finally {
      setLoading(false);
    }
  }, [tickers]);

  useEffect(() => {
    load();
  }, [load]);

  const itemByTicker = useMemo(() => {
    const map = {};
    (payload?.items || []).forEach((it) => {
      if (it.ticker) map[it.ticker] = it;
    });
    return map;
  }, [payload]);

  const handlePaste = () => {
    const parsed = parseCSV(pasteText);
    if (parsed.length === 0) return;
    // Merge (overwrite by ticker)
    const byTicker = Object.fromEntries(positions.map((p) => [p.ticker, p]));
    parsed.forEach((p) => {
      byTicker[p.ticker] = p;
    });
    setPositions(Object.values(byTicker));
    setPasteText("");
    setEditing(false);
  };

  const removePosition = (ticker) => {
    setPositions((prev) => prev.filter((p) => p.ticker !== ticker));
  };

  const clearAll = () => {
    if (confirm("Clear all saved positions?")) setPositions([]);
  };

  const totals = useMemo(() => {
    let marketValue = 0;
    let costValue = 0;
    let hasAllPrices = true;
    positions.forEach((p) => {
      const it = itemByTicker[p.ticker];
      const price = it?.price;
      if (price != null && Number.isFinite(price)) {
        marketValue += price * p.shares;
      } else {
        hasAllPrices = false;
      }
      if (p.costBasis != null) {
        costValue += p.costBasis * p.shares;
      }
    });
    const pnl = hasAllPrices && costValue > 0 ? marketValue - costValue : null;
    return { marketValue, costValue, pnl, hasAllPrices };
  }, [positions, itemByTicker]);

  if (positions.length === 0 && !editing) {
    return (
      <section className="panel portfolio">
        <div className="portfolio__header">
          <h2>Your positions</h2>
          <button type="button" className="radar-apply" onClick={() => setEditing(true)}>
            Add positions
          </button>
        </div>
        <p className="detail-meta">
          Paste your holdings (ticker, shares, cost basis) to get exit signals, earnings warnings,
          and P&amp;L. Stored locally in your browser only.
        </p>
      </section>
    );
  }

  return (
    <section className="panel portfolio">
      <div className="portfolio__header">
        <h2>Your positions</h2>
        <div className="portfolio__actions">
          <button type="button" className="radar-apply" onClick={load} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh"}
          </button>
          <button type="button" className="radar-apply" onClick={() => setEditing((v) => !v)}>
            {editing ? "Done" : "Edit"}
          </button>
          {positions.length > 0 && (
            <button type="button" className="radar-apply portfolio__clear" onClick={clearAll}>
              Clear
            </button>
          )}
        </div>
      </div>

      {editing && (
        <div className="portfolio__editor">
          <p className="detail-meta">
            Paste one line per position: <code>TICKER, shares, costBasis</code> (cost optional).
          </p>
          <textarea
            value={pasteText}
            onChange={(e) => setPasteText(e.target.value)}
            rows={4}
            placeholder={"AAPL, 10, 150\nMSFT, 5, 400\nNVDA, 8"}
            className="portfolio__textarea"
          />
          <div className="portfolio__editor-actions">
            <button type="button" className="radar-apply" onClick={handlePaste}>
              Save
            </button>
            <button type="button" className="radar-apply" onClick={() => { setPasteText(""); setEditing(false); }}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {error && <p className="radar-drawer-warn">{error}</p>}

      {positions.length > 0 && (
        <>
          <div className="portfolio__totals">
            <div>
              <span className="detail-card-label">Positions</span>
              <p className="font-mono">{positions.length}</p>
            </div>
            <div>
              <span className="detail-card-label">Market value</span>
              <p className="font-mono">
                {totals.hasAllPrices ? `$${totals.marketValue.toFixed(0)}` : "—"}
              </p>
            </div>
            <div>
              <span className="detail-card-label">Cost</span>
              <p className="font-mono">
                {totals.costValue > 0 ? `$${totals.costValue.toFixed(0)}` : "—"}
              </p>
            </div>
            <div>
              <span className="detail-card-label">P&amp;L</span>
              <p
                className={`font-mono ${totals.pnl != null ? (totals.pnl > 0 ? "up" : totals.pnl < 0 ? "down" : "") : ""}`}
              >
                {totals.pnl != null
                  ? `${totals.pnl > 0 ? "+" : ""}$${totals.pnl.toFixed(0)}`
                  : "—"}
              </p>
            </div>
          </div>

          <div className="scanner-table-wrap">
            <table className="scanner-table">
              <thead>
                <tr>
                  <th>Ticker</th>
                  <th>Shares</th>
                  <th>Cost</th>
                  <th>Current</th>
                  <th>P&amp;L $</th>
                  <th>P&amp;L %</th>
                  <th>Conviction</th>
                  <th>Flags</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p) => {
                  const it = itemByTicker[p.ticker];
                  const price = it?.price;
                  const value = price != null ? price * p.shares : null;
                  const cost = p.costBasis != null ? p.costBasis * p.shares : null;
                  const pnl = value != null && cost != null ? value - cost : null;
                  const pnlPct = pnl != null && cost ? (pnl / cost) * 100 : null;
                  const flags = positionFlags(p, it);
                  return (
                    <tr key={p.ticker} className="stock-row">
                      <td className="td-ticker">
                        <strong>{p.ticker}</strong>
                      </td>
                      <td className="font-mono">{p.shares}</td>
                      <td className="font-mono">
                        {p.costBasis != null ? `$${p.costBasis.toFixed(2)}` : "—"}
                      </td>
                      <td className="font-mono">
                        {price != null ? `$${Number(price).toFixed(2)}` : "—"}
                      </td>
                      <td className={`font-mono ${pnl != null && pnl > 0 ? "up" : pnl != null && pnl < 0 ? "down" : ""}`}>
                        {pnl != null ? `${pnl > 0 ? "+" : ""}$${pnl.toFixed(0)}` : "—"}
                      </td>
                      <td className={`font-mono ${pnlPct != null && pnlPct > 0 ? "up" : pnlPct != null && pnlPct < 0 ? "down" : ""}`}>
                        {pnlPct != null ? `${pnlPct > 0 ? "+" : ""}${pnlPct.toFixed(2)}%` : "—"}
                      </td>
                      <td>
                        <span className={`radar-score radar-score--${
                          it?.conviction === "High" ? "high" :
                          it?.conviction === "Med" ? "mid" :
                          it?.conviction === "Low" ? "low" : "neutral"
                        }`}>
                          {it?.conviction || "—"}
                        </span>
                      </td>
                      <td className="radar-flags portfolio__flags">
                        {flags.length === 0 ? (
                          <span className="radar-flag radar-flag--ok">—</span>
                        ) : (
                          flags.map((f) => (
                            <span
                              key={f.label}
                              className={`portfolio__flag portfolio__flag--${f.tone}`}
                            >
                              {f.label}
                            </span>
                          ))
                        )}
                      </td>
                      <td>
                        <button
                          type="button"
                          className="portfolio__remove"
                          onClick={() => removePosition(p.ticker)}
                          title={`Remove ${p.ticker}`}
                        >
                          ×
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
