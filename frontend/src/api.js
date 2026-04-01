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
