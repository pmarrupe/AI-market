export default function StockDashboard({ rows = [] }) {
  if (rows.length === 0) {
    return (
      <section className="panel">
        <h2>AI Stock Market Dashboard (Cross-Sector)</h2>
        <p>No stock market data yet. Use Refresh Intelligence.</p>
      </section>
    );
  }

  return (
    <section className="panel">
      <h2>AI Stock Market Dashboard (Cross-Sector)</h2>
      <table>
        <thead>
          <tr>
            <th>Sector</th>
            <th>Ticker</th>
            <th>Price</th>
            <th>1D</th>
            <th>AI Revenue Share</th>
            <th>AI GPU Exposure</th>
            <th>AI Datacenter Growth</th>
            <th>Score</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const changeClass =
              row.day_change > 0 ? "up" : row.day_change < 0 ? "down" : "";
            return (
              <tr key={row.ticker}>
                <td>{row.sector}</td>
                <td>{row.ticker}</td>
                <td>${(row.price ?? 0).toFixed(2)}</td>
                <td className={changeClass}>
                  {((row.day_change ?? 0) * 100).toFixed(2)}%
                </td>
                <td>
                  {((row.ai_revenue_share ?? 0) * 100).toFixed(1)}%
                  <div className="bar-track compact">
                    <div
                      className="bar-fill rev-bar"
                      style={{ width: `${Math.floor((row.ai_revenue_share ?? 0) * 100)}%` }}
                    />
                  </div>
                </td>
                <td>
                  {((row.gpu_shipments ?? 0) * 100).toFixed(1)}%
                  <div className="bar-track compact">
                    <div
                      className="bar-fill gpu-bar"
                      style={{ width: `${Math.floor((row.gpu_shipments ?? 0) * 100)}%` }}
                    />
                  </div>
                </td>
                <td>
                  {((row.datacenter_growth ?? 0) * 100).toFixed(1)}%
                  <div className="bar-track compact">
                    <div
                      className="bar-fill dc-bar"
                      style={{ width: `${Math.floor((row.datacenter_growth ?? 0) * 100)}%` }}
                    />
                  </div>
                </td>
                <td>{(row.score ?? 0).toFixed(3)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}
