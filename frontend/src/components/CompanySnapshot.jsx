import { useEffect, useState } from "react";
import { fetchTickerInfo } from "../api";

function externalLinks(ticker) {
  const t = encodeURIComponent(ticker);
  return [
    { label: "Yahoo", href: `https://finance.yahoo.com/quote/${t}` },
    { label: "Finviz", href: `https://finviz.com/quote.ashx?t=${t}` },
    { label: "TradingView", href: `https://www.tradingview.com/symbols/${t}/` },
    { label: "Google News", href: `https://news.google.com/search?q=${t}+stock` },
    { label: "SEC", href: `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=${t}&type=10-K&dateb=&owner=include&count=10` },
  ];
}

function fmtNumber(n) {
  if (n == null || !Number.isFinite(n)) return "—";
  if (n >= 1e12) return `${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(0)}M`;
  return n.toLocaleString();
}

export default function CompanySnapshot({ ticker, sectorFallback }) {
  const [info, setInfo] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (!ticker) return;
    let live = true;
    setLoading(true);
    setError(null);
    setInfo(null);
    setExpanded(false);
    fetchTickerInfo(ticker)
      .then((r) => { if (live) setInfo(r?.info || null); })
      .catch((e) => { if (live) setError(e.message); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [ticker]);

  const links = externalLinks(ticker || "");

  return (
    <section className="company-snapshot">
      <div className="company-snapshot__head">
        <span className="detail-card-label">Company snapshot</span>
        <div className="company-snapshot__links">
          {links.map((l) => (
            <a
              key={l.label}
              href={l.href}
              target="_blank"
              rel="noreferrer"
              className="company-snapshot__link"
              title={`Open ${ticker} on ${l.label}`}
            >
              {l.label} ↗
            </a>
          ))}
        </div>
      </div>

      {loading && <p className="detail-meta">Loading company info…</p>}
      {error && !loading && (
        <p className="detail-meta">Couldn't load company info ({error}).</p>
      )}
      {!loading && !error && !info && (
        <p className="detail-meta">No company data available for {ticker}.</p>
      )}

      {info && (
        <>
          <div className="company-snapshot__meta">
            <span title="Sector"><strong>{info.sector || sectorFallback || "—"}</strong></span>
            <span title="Industry">{info.industry || "—"}</span>
            {info.exchange && <span className="dim">{info.exchange}</span>}
            {info.country && <span className="dim">{info.country}</span>}
          </div>

          <div className="company-snapshot__grid">
            <div>
              <span className="detail-card-label">Market cap</span>
              <p className="font-mono">{info.marketCap || "—"}</p>
            </div>
            <div>
              <span className="detail-card-label">Employees</span>
              <p className="font-mono">{fmtNumber(info.employees)}</p>
            </div>
            <div>
              <span className="detail-card-label">52w high</span>
              <p className="font-mono">
                {info.fiftyTwoWeekHigh != null ? `$${info.fiftyTwoWeekHigh.toFixed(2)}` : "—"}
              </p>
            </div>
            <div>
              <span className="detail-card-label">52w low</span>
              <p className="font-mono">
                {info.fiftyTwoWeekLow != null ? `$${info.fiftyTwoWeekLow.toFixed(2)}` : "—"}
              </p>
            </div>
          </div>

          {info.summary && (
            <div className="company-snapshot__summary">
              <p className={expanded ? "company-snapshot__text" : "company-snapshot__text company-snapshot__text--clamp"}>
                {info.summary}
              </p>
              {info.summary.length > 280 && (
                <button
                  type="button"
                  className="company-snapshot__more"
                  onClick={() => setExpanded((v) => !v)}
                >
                  {expanded ? "Show less" : "Show more"}
                </button>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
