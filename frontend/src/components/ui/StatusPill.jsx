const VARIANT_MAP = {
  "Strong Buy Signal": "emerald",
  "Bullish": "emerald",
  "Actionable": "emerald",
  "Watch": "amber",
  "Watchlist": "blue",
  "Needs Confirmation": "amber",
  "Neutral": "slate",
  "Avoid / Insufficient Setup": "red",
  "Insufficient Evidence": "red",
  "High Risk Setup": "red",
  "Low": "emerald",
  "Medium": "amber",
  "High": "red",
};

export default function StatusPill({ label, className = "" }) {
  const variant = VARIANT_MAP[label] || "slate";
  return (
    <span className={`status-pill status-pill--${variant} ${className}`}>
      {label}
    </span>
  );
}
