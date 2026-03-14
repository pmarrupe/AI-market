import SectionHeader from "./SectionHeader";

export default function TrackerPanel({
  id,
  icon,
  title,
  badgeText,
  badgeVariant,
  emptyMessage = "No items yet.",
  featuredSlot,
  children,
}) {
  const hasContent = featuredSlot || children;

  return (
    <section id={id} className="trk-panel">
      <SectionHeader
        icon={icon}
        title={title}
        badgeText={badgeText}
        badgeVariant={badgeVariant}
      />
      {hasContent ? (
        <div className="trk-panel__content">
          {featuredSlot}
          {children && <div className="trk-panel__feed">{children}</div>}
        </div>
      ) : (
        <div className="trk-panel__empty">{emptyMessage}</div>
      )}
    </section>
  );
}
