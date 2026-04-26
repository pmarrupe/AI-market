/**
 * Map a MACD/Signal pair (and optional RSI) to a human-readable strength label.
 *
 * Inputs: raw macd, signal, and optional rsi (0-100) from the plan dict.
 * Returns: { arrow, label, tone, qualifier? } or null if inputs missing.
 *
 * Buckets:
 *   - Direction:   histogram (macd − signal) sign decides bullish/bearish
 *   - Position:    macd > 0 = "established"; macd < 0 = "recovery / decline"
 *   - Gap width:   |histogram| / max(|macd|, |signal|) — tiny gap = weak signal
 *
 * The optional `qualifier` flags RSI extremes ("overbought" / "oversold"),
 * separately colored so the trend reading stays honest while the user is
 * warned about the entry risk:
 *   - Bullish + Overbought  → "don't chase, wait for pullback"
 *   - Bearish + Oversold    → "don't short, possible bounce"
 *   - Bullish + Oversold    → "recovery bounce, supportive"
 *   - Bearish + Overbought  → "rolling over from a peak"
 */
export function macdLabel(macd, signal, rsi = null) {
  if (macd == null || signal == null) return null;
  const hist = macd - signal;

  // Direction-agnostic RSI qualifier helper
  const qualifierFor = (direction) => {
    if (rsi == null || !Number.isFinite(rsi)) return null;
    if (rsi >= 70) {
      return {
        text: "overbought",
        tone: direction === "bullish" ? "warn" : "muted",
      };
    }
    if (rsi <= 30) {
      return {
        text: "oversold",
        tone: direction === "bearish" ? "warn" : "muted",
      };
    }
    return null;
  };

  if (hist === 0) {
    return { arrow: "→", label: "Neutral", tone: "muted", qualifier: qualifierFor(null) };
  }

  const scale = Math.max(Math.abs(macd), Math.abs(signal), 0.01);
  const relGap = Math.abs(hist) / scale;
  const direction = hist > 0 ? "bullish" : "bearish";
  const tone = hist > 0 ? "up" : "down";
  const arrow = hist > 0 ? "↑" : "↓";

  let label;
  if (relGap < 0.05) {
    label = `Weak ${direction}`;
  } else if ((hist > 0 && macd < 0) || (hist < 0 && macd > 0)) {
    label = `Early ${direction}`;
  } else if (relGap >= 0.20) {
    label = `Strong ${direction}`;
  } else {
    label = direction.charAt(0).toUpperCase() + direction.slice(1);
  }
  return { arrow, label, tone, qualifier: qualifierFor(direction) };
}
