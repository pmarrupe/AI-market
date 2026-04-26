/**
 * Map a MACD/Signal pair to a human-readable strength label.
 *
 * Inputs: raw macd & signal values from the plan dict.
 * Returns: { arrow, label, tone } or null if inputs missing.
 *
 * Buckets:
 *   - Direction:   histogram (macd − signal) sign decides bullish/bearish
 *   - Position:    macd > 0 = "established"; macd < 0 = "recovery / decline"
 *   - Gap width:   |histogram| / max(|macd|, |signal|) — tiny gap = weak signal
 */
export function macdLabel(macd, signal) {
  if (macd == null || signal == null) return null;
  const hist = macd - signal;
  if (hist === 0) return { arrow: "→", label: "Neutral", tone: "muted" };

  const scale = Math.max(Math.abs(macd), Math.abs(signal), 0.01);
  const relGap = Math.abs(hist) / scale;
  const direction = hist > 0 ? "bullish" : "bearish";
  const tone = hist > 0 ? "up" : "down";
  const arrow = hist > 0 ? "↑" : "↓";

  // Order matters — check most-specific cases first
  let label;
  if (relGap < 0.05) {
    // Tiny gap — could cross back any minute
    label = `Weak ${direction}`;
  } else if ((hist > 0 && macd < 0) || (hist < 0 && macd > 0)) {
    // Histogram says one direction, but MACD is in opposite territory →
    // we're in a transition zone (early reversal)
    label = `Early ${direction}`;
  } else if (relGap >= 0.20) {
    // Wide separation, in the same territory as the trend
    label = `Strong ${direction}`;
  } else {
    label = direction.charAt(0).toUpperCase() + direction.slice(1);
  }
  return { arrow, label, tone };
}
