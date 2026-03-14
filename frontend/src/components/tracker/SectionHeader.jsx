export default function SectionHeader({ icon, title, badgeText, badgeVariant = "live" }) {
  return (
    <div className="trk-header">
      <div className="trk-header__left">
        {icon && <span className="trk-header__icon">{icon}</span>}
        <h2 className="trk-header__title">{title}</h2>
      </div>
      {badgeText && (
        <span className={`trk-header__badge trk-header__badge--${badgeVariant}`}>
          {badgeVariant === "live" && <span className="trk-header__pulse" />}
          {badgeText}
        </span>
      )}
    </div>
  );
}
