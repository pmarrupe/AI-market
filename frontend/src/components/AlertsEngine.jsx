import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchPortfolio, fetchTradeFeed } from "../api";

const SETTINGS_KEY = "ai_market.alerts_settings";
const STATE_KEY = "ai_market.alerts_last_state";
const POSITIONS_KEY = "ai_market.portfolio_positions";

const DEFAULT_SETTINGS = {
  enabled: false,
  pollMinutes: 15,
  newHighConviction: true,
  thesisInvalidated: true,
  positionStop: true,
  positionTarget: true,
};

function readSettings() {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (!raw) return DEFAULT_SETTINGS;
    return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

function writeSettings(s) {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(s));
  } catch {
    /* ignore */
  }
}

function readState() {
  try {
    const raw = localStorage.getItem(STATE_KEY);
    return raw ? JSON.parse(raw) : { seenHighConviction: {}, lastConviction: {} };
  } catch {
    return { seenHighConviction: {}, lastConviction: {} };
  }
}

function writeState(s) {
  try {
    localStorage.setItem(STATE_KEY, JSON.stringify(s));
  } catch {
    /* ignore */
  }
}

function readPositions() {
  try {
    const raw = localStorage.getItem(POSITIONS_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function notify(title, body) {
  try {
    if (typeof Notification === "undefined") return;
    if (Notification.permission !== "granted") return;
    new Notification(title, { body, tag: title });
  } catch {
    /* ignore */
  }
}

export default function AlertsEngine() {
  const [settings, setSettings] = useState(readSettings);
  const [permission, setPermission] = useState(
    typeof Notification !== "undefined" ? Notification.permission : "unsupported",
  );
  const [expanded, setExpanded] = useState(false);
  const [lastCheckAt, setLastCheckAt] = useState(null);
  const [lastFired, setLastFired] = useState([]);
  const stateRef = useRef(readState());
  const timerRef = useRef(null);

  useEffect(() => writeSettings(settings), [settings]);

  const requestPermission = useCallback(async () => {
    if (typeof Notification === "undefined") return;
    try {
      const p = await Notification.requestPermission();
      setPermission(p);
    } catch {
      /* ignore */
    }
  }, []);

  const runCheck = useCallback(async () => {
    const fired = [];
    try {
      const feed = await fetchTradeFeed({ limit: 30, with_plans: false });
      const items = feed?.items || [];
      const prevState = stateRef.current || { seenHighConviction: {}, lastConviction: {} };

      if (settings.newHighConviction) {
        for (const it of items) {
          if (it.conviction === "High" && !prevState.seenHighConviction[it.ticker]) {
            fired.push({
              title: `New high-conviction buy: ${it.ticker}`,
              body: `${it.setup} · ${it.topReason || ""}`.slice(0, 180),
            });
          }
        }
      }

      if (settings.thesisInvalidated) {
        for (const it of items) {
          const prev = prevState.lastConviction[it.ticker];
          if (prev === "High" && it.conviction === "Low") {
            fired.push({
              title: `Thesis invalidated: ${it.ticker}`,
              body: `Conviction dropped High → Low. ${it.topReason || ""}`.slice(0, 180),
            });
          }
        }
      }

      const nextState = {
        seenHighConviction: {},
        lastConviction: {},
      };
      for (const it of items) {
        if (it.conviction === "High") nextState.seenHighConviction[it.ticker] = true;
        if (it.conviction) nextState.lastConviction[it.ticker] = it.conviction;
      }
      stateRef.current = nextState;
      writeState(nextState);
    } catch (err) {
      // feed fetch failed — skip this cycle silently
    }

    if (settings.positionStop || settings.positionTarget) {
      const positions = readPositions();
      if (positions.length > 0) {
        try {
          const portfolio = await fetchPortfolio(positions.map((p) => p.ticker));
          const items = portfolio?.items || [];
          for (const it of items) {
            const price = it.price;
            const plan = it.plan;
            if (price == null || !plan) continue;
            if (settings.positionStop && price <= plan.stop) {
              fired.push({
                title: `${it.ticker}: stop reached`,
                body: `Price ${price} ≤ stop ${plan.stop}.`,
              });
            } else if (settings.positionTarget && price >= plan.target1) {
              fired.push({
                title: `${it.ticker}: target 1 hit`,
                body: `Price ${price} ≥ target ${plan.target1}.`,
              });
            }
          }
        } catch (err) {
          // portfolio fetch failed — skip
        }
      }
    }

    fired.forEach((f) => notify(f.title, f.body));
    setLastFired(fired.slice(-4));
    setLastCheckAt(Date.now());
  }, [settings]);

  useEffect(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (!settings.enabled) return;
    if (permission !== "granted") return;
    const interval = Math.max(3, settings.pollMinutes) * 60 * 1000;
    runCheck();
    timerRef.current = setInterval(runCheck, interval);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      timerRef.current = null;
    };
  }, [settings.enabled, settings.pollMinutes, permission, runCheck]);

  const statusLabel = useMemo(() => {
    if (permission === "unsupported") return "Notifications unsupported in this browser";
    if (permission === "denied") return "Notifications blocked — allow in your browser settings";
    if (permission !== "granted") return "Click to enable browser notifications";
    if (!settings.enabled) return "Alerts off";
    return `Checking every ${settings.pollMinutes}m`;
  }, [permission, settings.enabled, settings.pollMinutes]);

  return (
    <section className="panel alerts">
      <div className="alerts__row">
        <span className="alerts__label">Alerts</span>
        <span className="alerts__status">{statusLabel}</span>
        {permission !== "granted" && permission !== "unsupported" && (
          <button type="button" className="radar-apply" onClick={requestPermission}>
            Enable browser notifications
          </button>
        )}
        {permission === "granted" && (
          <>
            <label className="alerts__toggle">
              <input
                type="checkbox"
                checked={settings.enabled}
                onChange={(e) =>
                  setSettings((s) => ({ ...s, enabled: e.target.checked }))
                }
              />
              On
            </label>
            <button
              type="button"
              className="radar-apply"
              onClick={() => setExpanded((v) => !v)}
            >
              {expanded ? "Hide settings" : "Settings"}
            </button>
            <button type="button" className="radar-apply" onClick={runCheck}>
              Check now
            </button>
          </>
        )}
        {lastCheckAt && (
          <span className="alerts__muted">
            last check {new Date(lastCheckAt).toLocaleTimeString()}
          </span>
        )}
      </div>

      {expanded && (
        <div className="alerts__settings">
          <label>
            Poll interval (min):
            <input
              type="number"
              min={3}
              max={120}
              step={1}
              value={settings.pollMinutes}
              onChange={(e) =>
                setSettings((s) => ({ ...s, pollMinutes: Number(e.target.value) || 15 }))
              }
            />
          </label>
          <label>
            <input
              type="checkbox"
              checked={settings.newHighConviction}
              onChange={(e) => setSettings((s) => ({ ...s, newHighConviction: e.target.checked }))}
            />
            New high-conviction ideas
          </label>
          <label>
            <input
              type="checkbox"
              checked={settings.thesisInvalidated}
              onChange={(e) => setSettings((s) => ({ ...s, thesisInvalidated: e.target.checked }))}
            />
            Thesis invalidated (High → Low)
          </label>
          <label>
            <input
              type="checkbox"
              checked={settings.positionStop}
              onChange={(e) => setSettings((s) => ({ ...s, positionStop: e.target.checked }))}
            />
            Position hit stop
          </label>
          <label>
            <input
              type="checkbox"
              checked={settings.positionTarget}
              onChange={(e) => setSettings((s) => ({ ...s, positionTarget: e.target.checked }))}
            />
            Position hit target
          </label>
          <p className="alerts__note">
            Alerts fire only while this tab is open. Backend email/push is not yet wired.
          </p>
        </div>
      )}

      {lastFired.length > 0 && (
        <ul className="alerts__recent">
          {lastFired.map((f, i) => (
            <li key={i}>
              <strong>{f.title}</strong> <span className="alerts__muted">— {f.body}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
