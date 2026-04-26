/**
 * Compact SVG chart for the trade-plan drawer.
 * - In default (60D) mode: renders price line + entry/stop/T1/T2 dashed
 *   levels + risk/reward shading + current-price marker
 * - When `closesOverride` is passed (1Y / 5Y mode), renders only the price
 *   line (levels would visually compress out of usefulness on a long chart)
 *
 * Pure SVG, no chart library. Tuned for the 520px-wide drawer.
 */
export default function TradePlanChart({ plan, currentPrice, closesOverride = null, showLevels = true }) {
  if (!plan && !closesOverride) return null;
  const closes = closesOverride && closesOverride.length >= 2
    ? closesOverride
    : (plan?.recentCloses || []);
  if (closes.length < 2) {
    return <div className="trade-chart__empty">Price history unavailable.</div>;
  }
  const renderLevels = showLevels && !closesOverride && plan;

  const W = 480;
  const H = 200;
  const PAD_L = 8;
  const PAD_R = 84; // room for right-side price labels (e.g. "T2 $376.13")
  const PAD_T = 14;
  const PAD_B = 12;
  const innerW = W - PAD_L - PAD_R;
  const innerH = H - PAD_T - PAD_B;

  // Domain — include plan levels only when we'll render them
  const levels = renderLevels
    ? [plan.entry, plan.stop, plan.target1, plan.target2].filter(
        (v) => v != null && Number.isFinite(v),
      )
    : [];
  const allValues = [...closes, ...levels];
  if (currentPrice != null && Number.isFinite(currentPrice)) {
    allValues.push(currentPrice);
  }
  const minV = Math.min(...allValues);
  const maxV = Math.max(...allValues);
  const span = maxV - minV || 1;
  const pad = span * 0.06;
  const yMin = minV - pad;
  const yMax = maxV + pad;
  const ySpan = yMax - yMin || 1;

  const xAt = (i) => PAD_L + (i / (closes.length - 1)) * innerW;
  const yAt = (v) => PAD_T + (1 - (v - yMin) / ySpan) * innerH;

  const linePath = closes.map((c, i) => `${i === 0 ? "M" : "L"}${xAt(i).toFixed(2)},${yAt(c).toFixed(2)}`).join(" ");
  const areaPath =
    `${linePath} L${xAt(closes.length - 1).toFixed(2)},${(PAD_T + innerH).toFixed(2)} L${PAD_L.toFixed(2)},${(PAD_T + innerH).toFixed(2)} Z`;

  const yEntry = renderLevels ? yAt(plan.entry) : 0;
  const yStop = renderLevels ? yAt(plan.stop) : 0;
  const yT1 = renderLevels ? yAt(plan.target1) : 0;
  const yT2 = renderLevels ? yAt(plan.target2) : 0;

  const riskTop = Math.min(yEntry, yStop);
  const riskBot = Math.max(yEntry, yStop);
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

      {renderLevels && (
        <>
          <rect
            x={PAD_L}
            y={riskTop}
            width={innerW}
            height={Math.max(0, riskBot - riskTop)}
            fill="rgba(239, 139, 122, 0.10)"
          />
          <rect
            x={PAD_L}
            y={rewardTop}
            width={innerW}
            height={Math.max(0, rewardBot - rewardTop)}
            fill="rgba(93, 211, 158, 0.10)"
          />
        </>
      )}

      {/* price area + line */}
      <path d={areaPath} fill="url(#tcline)" />
      <path d={linePath} fill="none" stroke="#8b9ff8" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />

      {renderLevels && (
        <>
          {Number.isFinite(plan.target2) && (
            <Level y={yT2} color="#5dd39e" label="T2" value={plan.target2} />
          )}
          {Number.isFinite(plan.target1) && (
            <Level y={yT1} color="#5dd39e" label="T1" value={plan.target1} />
          )}
          {Number.isFinite(plan.entry) && (
            <Level y={yEntry} color="#b0b1bf" label="Entry" value={plan.entry} />
          )}
          {Number.isFinite(plan.stop) && (
            <Level y={yStop} color="#ef8b7a" label="Stop" value={plan.stop} />
          )}
        </>
      )}

      {/* current price marker (always shown) */}
      <circle cx={cx} cy={yLast} r="3.5" fill="#8b9ff8" stroke="#0b0c10" strokeWidth="1.5" />
      {(!renderLevels || Math.abs(last - plan.entry) / Math.max(plan.entry, 1) > 0.005) && (
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
