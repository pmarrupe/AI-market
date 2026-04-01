import StatCard from "./ui/StatCard";

function formatFundingTotal(items) {
  if (!items || items.length === 0) return "$0";
  let totalM = 0;
  for (const item of items) {
    const raw = (item.amount || "").toUpperCase();
    const match = raw.match(/([\d.]+)\s*(B|BILLION|M|MILLION)/);
    if (!match) continue;
    const num = parseFloat(match[1]);
    const unit = match[2];
    if (unit.startsWith("B")) totalM += num * 1000;
    else totalM += num;
  }
  if (totalM >= 1000) return `$${(totalM / 1000).toFixed(1)}B`;
  if (totalM > 0) return `$${Math.round(totalM)}M`;
  return `${items.length}`;
}

function topSectorFromRows(stockRows) {
  if (!stockRows || stockRows.length === 0) return "—";
  return stockRows[0].sector || "—";
}

export default function SummaryBar({ data }) {
  const funding = data.startup_funding || [];
  const launches = data.product_launches || [];
  const research = data.research_items || [];
  const stockRows = data.stock_rows || [];

  return (
    <div className="summary-bar">
      <StatCard
        variant="green"
        trend="up"
        icon={
          <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
            <path d="M8 2v12M4.5 5.5L8 2l3.5 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M3 14h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        }
        label="Funding Tracked"
        value={formatFundingTotal(funding)}
      />
      <StatCard
        variant="blue"
        trend="up"
        icon={
          <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
            <path d="M3 13l3.5-5L9 10.5 13 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        }
        label="New Launches"
        value={launches.length}
      />
      <StatCard
        variant="purple"
        trend="flat"
        icon={
          <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
            <rect x="2" y="3" width="12" height="10" rx="2" stroke="currentColor" strokeWidth="1.4" />
            <path d="M5 7h6M5 9.5h4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
          </svg>
        }
        label="Top Sector"
        value={topSectorFromRows(stockRows)}
      />
      <StatCard
        variant="gold"
        trend="flat"
        icon={
          <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
            <circle cx="8" cy="8" r="5.5" stroke="currentColor" strokeWidth="1.4" />
            <path d="M8 5v3l2 1.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        }
        label="Research Items"
        value={research.length}
      />
    </div>
  );
}
