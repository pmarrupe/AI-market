const SPARKLINE_PATHS = {
  up: "M0 28 L8 24 L16 26 L24 20 L32 18 L40 14 L48 16 L56 10 L64 8 L72 4 L80 2",
  down: "M0 4 L8 6 L16 8 L24 12 L32 14 L40 18 L48 16 L56 22 L64 24 L72 26 L80 28",
  flat: "M0 16 L8 14 L16 17 L24 15 L32 16 L40 14 L48 15 L56 17 L64 14 L72 16 L80 15",
};

export default function StatCard({
  icon,
  label,
  value,
  variant = "blue",
  trend = "flat",
}) {
  const sparkPath = SPARKLINE_PATHS[trend] || SPARKLINE_PATHS.flat;

  return (
    <div className={`stat-card stat-card--${variant}`}>
      <svg
        className="stat-card__sparkline"
        viewBox="0 0 80 30"
        preserveAspectRatio="none"
      >
        <path d={sparkPath} fill="none" stroke="currentColor" strokeWidth="1.5" />
      </svg>
      <div className="stat-card__top">
        {icon && <span className="stat-card__icon">{icon}</span>}
        <span className="stat-card__label">{label}</span>
      </div>
      <div className="stat-card__value">{value}</div>
    </div>
  );
}
