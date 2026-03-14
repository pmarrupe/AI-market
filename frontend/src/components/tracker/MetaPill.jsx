export default function MetaPill({ children, variant = "default" }) {
  return <span className={`meta-pill meta-pill--${variant}`}>{children}</span>;
}
