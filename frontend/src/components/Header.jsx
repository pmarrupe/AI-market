import { useState } from "react";
import { refreshIntelligence } from "../api";

export default function Header({ onRefreshDone }) {
  const [refreshing, setRefreshing] = useState(false);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await refreshIntelligence();
      onRefreshDone();
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <header className="header">
      <div>
        <p className="eyebrow">Dashboard</p>
        <h1>AI Market Command Center</h1>
      </div>
      <button onClick={handleRefresh} disabled={refreshing}>
        {refreshing ? "Refreshing…" : "Refresh Intelligence"}
      </button>
    </header>
  );
}
