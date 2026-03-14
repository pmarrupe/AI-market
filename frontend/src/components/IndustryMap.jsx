export default function IndustryMap({ items = [] }) {
  if (items.length === 0) {
    return (
      <section id="industry" className="panel">
        <h2>Industry-to-Stock Map</h2>
        <p>No sector mapping yet.</p>
      </section>
    );
  }

  return (
    <section id="industry" className="panel">
      <h2>Industry-to-Stock Map</h2>
      <div className="industry-grid">
        {items.map((item) => (
          <article key={item.sector} className="industry-card">
            <h3>{item.sector}</h3>
            <p className="chip-row">{item.tickers.join(", ")}</p>
            <div className="bar-track">
              <div
                className="bar-fill sector-bar"
                style={{ width: `${Math.floor(item.avg_score * 100)}%` }}
              />
            </div>
            <small>Average sector score: {item.avg_score.toFixed(3)}</small>
          </article>
        ))}
      </div>
    </section>
  );
}
