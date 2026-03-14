import StatCard from "./ui/StatCard";

export default function KPIGrid({ data }) {
  const items = [
    {
      label: "Stocks tracked",
      value: data.stocks?.length ?? 0,
      variant: "blue",
      trend: "up",
      icon: (
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
          <path d="M3 13l3.5-5L9 10.5 13 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      ),
    },
    {
      label: "Funding events",
      value: data.startup_funding?.length ?? 0,
      variant: "green",
      trend: "up",
      icon: (
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
          <path d="M8 2v12M4.5 5.5L8 2l3.5 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M3 14h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      ),
    },
    {
      label: "Product launches",
      value: data.product_launches?.length ?? 0,
      variant: "purple",
      trend: "flat",
      icon: (
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
          <path d="M8 2L10 6.5 15 7.3 11.5 10.5 12.3 15 8 12.8 3.7 15l.8-4.5L1 7.3l5-0.8z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
        </svg>
      ),
    },
    {
      label: "Research items",
      value: data.research_items?.length ?? 0,
      variant: "gold",
      trend: "flat",
      icon: (
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
          <circle cx="8" cy="8" r="5.5" stroke="currentColor" strokeWidth="1.4" />
          <path d="M8 5v3l2 1.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      ),
    },
  ];

  return (
    <section id="overview" className="kpi-grid">
      {items.map((item) => (
        <StatCard key={item.label} {...item} />
      ))}
    </section>
  );
}
