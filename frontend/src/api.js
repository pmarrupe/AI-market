const BASE = "";

export async function fetchDashboard() {
  const res = await fetch(`${BASE}/api/dashboard`);
  if (!res.ok) throw new Error(`Dashboard fetch failed: ${res.status}`);
  return res.json();
}

export async function refreshIntelligence() {
  const res = await fetch(`${BASE}/refresh`, { method: "POST" });
  if (!res.ok) throw new Error(`Refresh failed: ${res.status}`);
  return res.json();
}

export async function searchSP500(query, limit = 8) {
  const res = await fetch(
    `${BASE}/api/sp500/search?q=${encodeURIComponent(query)}&limit=${limit}`
  );
  if (!res.ok) throw new Error(`Search failed: ${res.status}`);
  return res.json();
}

export async function getSP500Opinion(ticker) {
  const res = await fetch(
    `${BASE}/api/sp500/opinion?ticker=${encodeURIComponent(ticker)}`
  );
  if (!res.ok) throw new Error(`Opinion fetch failed: ${res.status}`);
  return res.json();
}

export async function fetchTickerInfo(ticker) {
  const t = (ticker || "").trim().toUpperCase();
  if (!t) return { info: null };
  const res = await fetch(`${BASE}/api/ticker-info/${encodeURIComponent(t)}`);
  if (!res.ok) throw new Error(`Ticker info failed: ${res.status}`);
  return res.json();
}

export async function fetchChart(ticker, period = "1y") {
  const t = (ticker || "").trim().toUpperCase();
  if (!t) return { closes: [], dates: [] };
  const res = await fetch(
    `${BASE}/api/chart/${encodeURIComponent(t)}?period=${encodeURIComponent(period)}`,
  );
  if (!res.ok) throw new Error(`Chart failed: ${res.status}`);
  return res.json();
}

export async function fetchTrackRecord(windowDays = 30) {
  const res = await fetch(`${BASE}/api/track-record?window_days=${windowDays}`);
  if (!res.ok) throw new Error(`Track record fetch failed: ${res.status}`);
  return res.json();
}

export async function fetchPortfolio(tickers = []) {
  if (!tickers || tickers.length === 0) return { items: [] };
  const q = encodeURIComponent(tickers.join(","));
  const res = await fetch(`${BASE}/api/portfolio?tickers=${q}`);
  if (!res.ok) throw new Error(`Portfolio fetch failed: ${res.status}`);
  return res.json();
}

export async function fetchTradeFeed(query = {}) {
  const qs = new URLSearchParams();
  Object.entries(query).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "") return;
    qs.set(k, String(v));
  });
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  const res = await fetch(`${BASE}/api/trade-feed${suffix}`);
  if (!res.ok) throw new Error(`Trade feed failed: ${res.status}`);
  return res.json();
}

export async function fetchGrowthLeaders({ limit = 20 } = {}) {
  const qs = new URLSearchParams();
  qs.set("limit", String(limit));
  const res = await fetch(`${BASE}/api/growth-leaders?${qs.toString()}`);
  if (!res.ok) throw new Error(`Growth leaders failed: ${res.status}`);
  return res.json();
}

export async function fetchExplosiveRadar(query = {}) {
  const qs = new URLSearchParams();
  Object.entries(query).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "") return;
    qs.set(k, String(v));
  });
  if (!qs.has("sort")) qs.set("sort", "opportunity");
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  const res = await fetch(`${BASE}/api/explosive-radar${suffix}`);
  if (!res.ok) throw new Error(`Explosive radar failed: ${res.status}`);
  return res.json();
}

export async function fetchExplosiveRadarTicker(ticker) {
  const res = await fetch(
    `${BASE}/api/explosive-radar/${encodeURIComponent(ticker)}`
  );
  if (!res.ok) throw new Error(`Radar detail failed: ${res.status}`);
  return res.json();
}

export async function fetchExplosiveRadarConfig() {
  const res = await fetch(`${BASE}/api/explosive-radar/config`);
  if (!res.ok) throw new Error(`Radar config failed: ${res.status}`);
  return res.json();
}

export async function fetchPriceForecast(ticker) {
  const res = await fetch(
    `${BASE}/api/price-forecast?ticker=${encodeURIComponent(ticker)}`
  );
  if (!res.ok) {
    const errBody = await res.json().catch(() => ({}));
    const msg = errBody.error || `Forecast failed: ${res.status}`;
    throw new Error(msg);
  }
  return res.json();
}
