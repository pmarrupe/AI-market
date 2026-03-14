import TrackerPanel from "./tracker/TrackerPanel";
import FeaturedTrackerItem from "./tracker/FeaturedTrackerItem";
import TrackerListItem from "./tracker/TrackerListItem";
import { relativeTime } from "../utils/time";

function fundingPills(item) {
  const pills = [];
  if (item.stage) {
    pills.push({ label: item.stage, variant: "stage" });
  }
  if (item.amount && item.amount !== "Undisclosed") {
    pills.push({ label: item.amount, variant: "amount" });
  }
  return pills;
}

function fundingSubtitle(item) {
  const parts = [];
  if (item.amount === "Undisclosed") parts.push("Undisclosed amount");
  if (item.stage && item.amount && item.amount !== "Undisclosed") {
    parts.push(`${item.stage} round`);
  }
  return parts.join(" · ") || null;
}

export default function StartupFunding({ items = [] }) {
  const [featured, ...rest] = items;

  const badgeText = items.length > 0
    ? `${items.length} event${items.length !== 1 ? "s" : ""}`
    : null;

  return (
    <TrackerPanel
      id="funding"
      icon={
        <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
          <rect x="3" y="9" width="3.5" height="8" rx="1" stroke="currentColor" strokeWidth="1.4" />
          <rect x="8.25" y="5" width="3.5" height="12" rx="1" stroke="currentColor" strokeWidth="1.4" />
          <rect x="13.5" y="2" width="3.5" height="15" rx="1" stroke="currentColor" strokeWidth="1.4" />
          <path d="M2 18.5h16" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
        </svg>
      }
      title="Startup & Funding"
      badgeText={badgeText}
      badgeVariant="live"
      emptyMessage="No startup funding items detected yet."
      featuredSlot={
        featured && (
          <FeaturedTrackerItem
            title={featured.startup}
            subtitle={fundingSubtitle(featured)}
            url={featured.url}
            pills={fundingPills(featured)}
            source={featured.source}
            timestamp={featured.published_at}
          />
        )
      }
    >
      {rest.map((item, i) => (
        <TrackerListItem
          key={i}
          title={item.startup}
          subtitle={fundingSubtitle(item)}
          url={item.url}
          pills={fundingPills(item)}
          source={item.source}
          timestamp={item.published_at}
        />
      ))}
    </TrackerPanel>
  );
}
