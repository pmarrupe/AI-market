import MetaPill from "./MetaPill";
import { relativeTime } from "../../utils/time";

export default function TrackerListItem({
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
      className="trk-item"
    >
      <div className="trk-item__body">
        <span className="trk-item__title">{title}</span>
        {subtitle && <span className="trk-item__subtitle">{subtitle}</span>}
      </div>
      <div className="trk-item__right">
        <div className="trk-item__pills">
          {pills.map((pill, i) => (
            <MetaPill key={i} variant={pill.variant}>
              {pill.label}
            </MetaPill>
          ))}
        </div>
        <div className="trk-item__meta">
          {source && <span className="trk-item__source">{source}</span>}
          {timestamp && (
            <span className="trk-item__time">{relativeTime(timestamp)}</span>
          )}
        </div>
      </div>
    </a>
  );
}
