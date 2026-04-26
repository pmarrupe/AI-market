import { useEffect, useState } from "react";
import { fetchTrackRecord } from "../api";

function pct(x) {
  if (x == null || !Number.isFinite(x)) return "—";
  const v = x * 100;
  return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
}

export default function TrackRecord() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let live = true;
    fetchTrackRecord(30)
      .then((d) => { if (live) setData(d); })
      .catch((e) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, []);

  const stats = data?.stats || {};
  const total = stats.total ?? 0;
  const winRate = stats.win_rate;
  const avgReturn = stats.avg_return;

  if (error) {
    return (
      <section className="track-record">
        <span className="track-record__label">Track record</span>
        <span className="track-record__muted">unavailable</span>
      </section>
    );
  }

  if (!data) {
    return (
      <section className="track-record">
        <span className="track-record__label">Track record</span>
        <span className="track-record__muted">loading…</span>
      </section>
    );
  }

  return (
    <section
      className="track-record"
      title="Rolling 30-day summary of recorded trade plans. Target_hit / stop_hit / expired outcomes resolved from daily bars."
    >
      <span className="track-record__label">Last 30d</span>
      <span className="track-record__value">
        {total} pick{total === 1 ? "" : "s"}
      </span>
      <span className="track-record__sep">·</span>
      <span
        className={`track-record__value ${
          winRate != null ? (winRate >= 0.5 ? "up" : "down") : ""
        }`}
      >
        {winRate != null ? `${Math.round(winRate * 100)}% win` : "no resolved"}
      </span>
      <span className="track-record__sep">·</span>
      <span
        className={`track-record__value ${
          avgReturn != null ? (avgReturn > 0 ? "up" : avgReturn < 0 ? "down" : "") : ""
        }`}
      >
        avg {pct(avgReturn)}
      </span>
      <span className="track-record__muted">
        &nbsp;({stats.wins || 0}W / {stats.losses || 0}L / {stats.expired || 0}X · {stats.open || 0} open)
      </span>
    </section>
  );
}
