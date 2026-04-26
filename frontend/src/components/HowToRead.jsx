import { useEffect, useState } from "react";

const STORAGE_KEY = "ai_market.how_to_read_open";

const SECTIONS = [
  {
    title: "What's the model telling me?",
    items: [
      ["Conviction: High", "The model thinks this is one of its better ideas right now. Top-tier picks."],
      ["Conviction: Med", "Worth watching — has some signal but not the strongest right now."],
      ["Conviction: Low", "Filler. Either weak signal, conflicting evidence, or pre-earnings penalty."],
      ["Setup", "What kind of trade pattern this looks like (breakout, momentum continuation, gap-and-go, etc.)."],
      ["Horizon", "Suggested holding window — Intraday (today), Short-term (a few days), Swing (1–2 weeks)."],
      ["Source: SCANNER + RADAR", "Both internal systems agree this ticker is interesting."],
    ],
  },
  {
    title: "What are the trade plan numbers?",
    items: [
      ["Entry", "Suggested buy price — usually today's close, or the 20-day high for breakout setups."],
      ["Stop", "If price drops here, sell to cap your loss. Set this BEFORE you buy, not after."],
      ["Target 1", "First profit target. Common practice: scale out half here, let the rest run to T2."],
      ["Target 2", "Second profit target — the runner."],
      ["R:R", "Reward-to-risk ratio. 2× means you'd make $2 for every $1 risked. Aim for ≥2."],
      ["ATR(14)", "Average daily price swing over the last 14 days. Used to size the stop."],
      ["Risk / share", "Entry − Stop. The dollar amount you lose per share if the stop fires."],
      ["Suggested shares", "(Portfolio × Risk%) ÷ Risk/share. Set Portfolio $ and Risk % at the top of the feed."],
    ],
  },
  {
    title: "What do the indicator chips mean?",
    items: [
      ["Overbought", "RSI ≥ 70 — the stock has run hot already. Pullback risk. Don't chase."],
      ["Oversold", "RSI ≤ 30 — beaten down hard. Possible bargain bounce."],
      ["Turning up (MACD↑)", "Momentum just flipped from down → up in the last 3 days. Early bullish signal."],
      ["Turning down (MACD↓)", "Momentum just flipped from up → down. Bearish — caution."],
      ["20d HIGH", "Price hit a new 20-day high today. Classic breakout (Turtle Trading)."],
      ["20d LOW", "Price hit a 20-day low — breakdown."],
      ["VOL Nx", "Today's volume is N times the 30-day average. ≥1.8× = institutional volume = real conviction."],
      ["VOL ↓", "Volume well below normal — moves on this much volume tend to be noise."],
      ["⚡ Earnings in Nd", "Days to next earnings report. ≤7 days = binary event risk (and conviction is auto-downgraded)."],
    ],
  },
  {
    title: "What about the warning flags?",
    items: [
      ["High risk", "Radar flagged this as risky — high volatility, thin liquidity, or sharp gap risk."],
      ["Fragile", "Setup looks vulnerable — usually price spike without confirmation, or thin float."],
      ["Low data", "We don't have enough news / signal coverage to be confident. Treat the score with skepticism."],
      ["Pre-earnings (Nd)", "Conviction was auto-downgraded because earnings are within 7 days."],
      ["No coverage", "This ticker isn't in our active universe — only basic price info is available."],
    ],
  },
];

function readOpen() {
  try {
    return localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function writeOpen(v) {
  try {
    localStorage.setItem(STORAGE_KEY, v ? "1" : "0");
  } catch {
    /* ignore */
  }
}

export default function HowToRead() {
  const [open, setOpen] = useState(readOpen);
  useEffect(() => writeOpen(open), [open]);

  return (
    <section className={`how-to-read ${open ? "how-to-read--open" : ""}`}>
      <button
        type="button"
        className="how-to-read__toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="how-to-read__caret">{open ? "▼" : "▶"}</span>
        <span className="how-to-read__title">
          {open ? "How to read this" : "New here? How to read this"}
        </span>
        <span className="how-to-read__hint">{open ? "(click to hide)" : "(click to expand)"}</span>
      </button>

      {open && (
        <div className="how-to-read__body">
          {SECTIONS.map((section) => (
            <div key={section.title} className="how-to-read__section">
              <h4 className="how-to-read__section-title">{section.title}</h4>
              <dl className="how-to-read__list">
                {section.items.map(([term, def]) => (
                  <div key={term} className="how-to-read__row">
                    <dt>{term}</dt>
                    <dd>{def}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ))}
          <p className="how-to-read__footer">
            None of this is financial advice — it's a research tool. Always confirm trades against
            your own research and risk tolerance.
          </p>
        </div>
      )}
    </section>
  );
}
