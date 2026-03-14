import MetaPill from "./MetaPill";
import { relativeTime } from "../../utils/time";

export default function FeaturedTrackerItem({
  title,
  subtitle,
  url,
  pills = [],
  source,
  timestamp,
}) {
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      className="trk-featured"
    >
      <div className="trk-featured__badge">Featured</div>
      <h3 className="trk-featured__title">{title}</h3>
      {subtitle && <p className="trk-featured__subtitle">{subtitle}</p>}
      <div className="trk-featured__pills">
        {pills.map((pill, i) => (
          <MetaPill key={i} variant={pill.variant}>
            {pill.label}
          </MetaPill>
        ))}
      </div>
      <div className="trk-featured__meta">
        {source && <span className="trk-featured__source">{source}</span>}
        {timestamp && (
          <span className="trk-featured__time">{relativeTime(timestamp)}</span>
        )}
      </div>
    </a>
  );
}
