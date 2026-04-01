import { useState } from "react";

const NAV_ITEMS = [
  { id: "overview", label: "Overview" },
  { id: "stocks", label: "Stock Intelligence" },
  { id: "explosive-radar", label: "Explosive Move Radar" },
  { id: "funding", label: "Startup Funding" },
  { id: "launches", label: "Product Launches" },
  { id: "research", label: "Research" },
];

export default function Sidebar({ activeSection, onNavigate }) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <aside className={`sidebar ${mobileOpen ? "sidebar--open" : ""}`}>
      <button
        className="sidebar-toggle"
        onClick={() => setMobileOpen((v) => !v)}
        aria-label="Toggle menu"
      >
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
          <path
            d="M3 5h14M3 10h14M3 15h14"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
          />
        </svg>
      </button>
      <div className="brand">AI Market</div>
      <nav className="side-nav">
        {NAV_ITEMS.map((item) => (
          <a
            key={item.id}
            href={`#${item.id}`}
            className={activeSection === item.id ? "active" : ""}
            onClick={(e) => {
              e.preventDefault();
              onNavigate(item.id);
              setMobileOpen(false);
            }}
          >
            {item.label}
          </a>
        ))}
      </nav>
    </aside>
  );
}
