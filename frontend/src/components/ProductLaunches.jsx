import TrackerPanel from "./tracker/TrackerPanel";
import FeaturedTrackerItem from "./tracker/FeaturedTrackerItem";
import TrackerListItem from "./tracker/TrackerListItem";

function launchPills(item) {
  const pills = [];
  if (item.company_hint) {
    pills.push({ label: item.company_hint, variant: "source" });
  }
  return pills;
}

export default function ProductLaunches({ items = [] }) {
  const [featured, ...rest] = items;

  const badgeText = items.length > 0
    ? `${items.length} launch${items.length !== 1 ? "es" : ""}`
    : null;

  return (
    <TrackerPanel
      id="launches"
      icon={
        <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
          <path d="M10 2L12.5 7.5 18 8.5l-4 4 1 5.5-5-2.5-5 2.5 1-5.5-4-4 5.5-1z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
        </svg>
      }
      title="Product Launches"
      badgeText={badgeText}
      badgeVariant="live"
      emptyMessage="No product launches detected yet."
      featuredSlot={
        featured && (
          <FeaturedTrackerItem
            title={featured.product}
            subtitle={featured.company_hint ? `by ${featured.company_hint}` : null}
            url={featured.url}
            pills={launchPills(featured)}
            source={featured.source}
            timestamp={featured.published_at}
          />
        )
      }
    >
      {rest.map((item, i) => (
        <TrackerListItem
          key={i}
          title={item.product}
          url={item.url}
          pills={launchPills(item)}
          source={item.source}
          timestamp={item.published_at}
        />
      ))}
    </TrackerPanel>
  );
}
