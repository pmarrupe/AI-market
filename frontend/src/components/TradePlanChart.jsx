/**
 * Compact SVG chart for the trade-plan drawer.
 * Renders the recent close history as a line and overlays the entry/stop/T1/T2
 * levels as horizontal dashed lines. Includes a shaded "risk zone" between
 * entry and stop, and a current-price marker dot.
 *
 * Pure SVG, no chart library. Tuned for the 520px-wide drawer.
 */
export default function TradePlanChart({ plan, currentPrice }) {
  if (!plan) return null;
  const closes = plan.recentCloses || [];
  if (closes.length < 2) {
    return <div className="trade-chart__empty">Price history unavailable.</div>;
  }

  const W = 480;
  const H = 200;
  const PAD_L = 8;
  const PAD_R = 84; // room for right-side price labels (e.g. "T2 $376.13")
  const PAD_T = 14;
  const PAD_B = 12;
  const innerW = W - PAD_L - PAD_R;
  const innerH = H - PAD_T - PAD_B;

  // Domain — include the plan levels so they're always visible
  const levels = [plan.entry, plan.stop, plan.target1, plan.target2].filter(
    (v) => v != null && Number.isFinite(v),
  );
  const allValues = [...closes, ...levels];
  if (currentPrice != null && Number.isFinite(currentPrice)) {
    allValues.push(currentPrice);
  }
  const minV = Math.min(...allValues);
  const maxV = Math.max(...allValues);
  const span = maxV - minV || 1;
  // 6% padding top/bottom so the line/levels don't touch the edges
  const pad = span * 0.06;
  const yMin = minV - pad;
  const yMax = maxV + pad;
  const ySpan = yMax - yMin || 1;

  const xAt = (i) => PAD_L + (i / (closes.length - 1)) * innerW;
  const yAt = (v) => PAD_T + (1 - (v - yMin) / ySpan) * innerH;

  const linePath = closes.map((c, i) => `${i === 0 ? "M" : "L"}${xAt(i).toFixed(2)},${yAt(c).toFixed(2)}`).join(" ");
  const areaPath =
    `${linePath} L${xAt(closes.length - 1).toFixed(2)},${(PAD_T + innerH).toFixed(2)} L${PAD_L.toFixed(2)},${(PAD_T + innerH).toFixed(2)} Z`;

  const yEntry = yAt(plan.entry);
  const yStop = yAt(plan.stop);
  const yT1 = yAt(plan.target1);
  const yT2 = yAt(plan.target2);

  // Shaded risk zone between entry (top) and stop (bottom)
  const riskTop = Math.min(yEntry, yStop);
  const riskBot = Math.max(yEntry, yStop);
  // Shaded reward zone between entry and target1
  const rewardTop = Math.min(yEntry, yT1);
  const rewardBot = Math.max(yEntry, yT1);

  const xRight = PAD_L + innerW;
  const last = closes[closes.length - 1];
  const yLast = yAt(last);
  const cx = xRight;

  const fmt = (v) => (v >= 100 ? v.toFixed(2) : v.toFixed(2));
  const Level = ({ y, color, label, value }) => (
    <g>
      <line
        x1={PAD_L}
        x2={xRight}
        y1={y}
        y2={y}
        stroke={color}
        strokeWidth="1"
        strokeDasharray="4 3"
        opacity="0.85"
      />
      <text
        x={xRight + 6}
        y={y + 3.5}
        fill={color}
        fontSize="10"
        fontFamily="JetBrains Mono, monospace"
        opacity="0.95"
      >
        {label} ${fmt(value)}
      </text>
    </g>
  );

  return (
    <svg
      className="trade-chart"
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      height={H}
      preserveAspectRatio="none"
      role="img"
      aria-label="Price chart with trade plan levels"
    >
      <defs>
        <linearGradient id="tcline" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="rgba(139, 159, 248, 0.30)" />
          <stop offset="100%" stopColor="rgba(139, 159, 248, 0)" />
        </linearGradient>
      </defs>

      {/* risk zone (entry → stop, red tint) */}
      <rect
        x={PAD_L}
        y={riskTop}
        width={innerW}
        height={Math.max(0, riskBot - riskTop)}
        fill="rgba(239, 139, 122, 0.10)"
      />
      {/* reward zone (entry → target1, green tint) */}
      <rect
        x={PAD_L}
        y={rewardTop}
        width={innerW}
        height={Math.max(0, rewardBot - rewardTop)}
        fill="rgba(93, 211, 158, 0.10)"
      />

      {/* price area + line */}
      <path d={areaPath} fill="url(#tcline)" />
      <path d={linePath} fill="none" stroke="#8b9ff8" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />

      {/* level lines + labels */}
      <Level y={yT2} color="#5dd39e" label="T2" value={plan.target2} />
      <Level y={yT1} color="#5dd39e" label="T1" value={plan.target1} />
      <Level y={yEntry} color="#b0b1bf" label="Entry" value={plan.entry} />
      <Level y={yStop} color="#ef8b7a" label="Stop" value={plan.stop} />

      {/* current price marker — label only if meaningfully different from Entry */}
      <circle cx={cx} cy={yLast} r="3.5" fill="#8b9ff8" stroke="#0b0c10" strokeWidth="1.5" />
      {Math.abs(last - plan.entry) / Math.max(plan.entry, 1) > 0.005 && (
        <text
          x={cx + 6}
          y={yLast + 3.5}
          fill="#8b9ff8"
          fontSize="10"
          fontFamily="JetBrains Mono, monospace"
          fontWeight="600"
        >
          ${fmt(last)}
        </text>
      )}
    </svg>
  );
}
