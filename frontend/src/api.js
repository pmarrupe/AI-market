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
