export default function Research({ items = [] }) {
  return (
    <section id="research" className="panel">
      <h2>AI Research Dashboard</h2>
      {items.length > 0 ? (
        <ul className="article-list">
          {items.map((item, i) => (
            <li key={i}>
              <a href={item.url} target="_blank" rel="noreferrer">
                {item.title}
              </a>
              <small>
                {item.source} | {item.published_at}
              </small>
            </li>
          ))}
        </ul>
      ) : (
        <p>No research items detected yet.</p>
      )}
    </section>
  );
}
