import { useCallback, useEffect, useState } from "react";
import { getServerStatus } from "../services/api";

export const STATUS_DEFAULTS = {
  // Wait a moment before the first request: it filters out drive-by loads (a
  // visitor who bounces, a scanner that runs scripts) so they don't wake a
  // sleeping host, and avoids a flash of banner on a warm server.
  startDelayMs: 1000,
  // A warm server answers well inside this; slower means the host is waking.
  wakingAfterMs: 2000,
  // A cold free host can hold the very first request for about a minute.
  requestTimeoutMs: 90000,
  retryDelayMs: 3000,
  // Stop retrying after this; offer a manual retry instead of looping forever.
  giveUpAfterMs: 300000,
};

/**
 * Warm-up and storage status in one small state machine.
 *
 *   idle -> checking -> ready                (warm server: no banner ever shown)
 *                   \-> waking -> ready      (cold server: "waking up" banner)
 *                              \-> unreachable (gave up: banner with Retry)
 *
 * Calls only the app's own server, never the storage provider. After `ready`
 * it makes no further requests.
 */
export function useServerStatus(options = {}) {
  const cfg = { ...STATUS_DEFAULTS, ...options };
  const { startDelayMs, wakingAfterMs, requestTimeoutMs, retryDelayMs, giveUpAfterMs } = cfg;

  const [phase, setPhase] = useState("idle");
  const [storage, setStorage] = useState({ state: "unmanaged" });
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [run, setRun] = useState(0); // bump to start over (the Retry button)

  useEffect(() => {
    let cancelled = false;
    let finished = false;
    const timers = new Set();
    let ticker = null;

    const later = (fn, ms) => {
      const t = setTimeout(() => {
        timers.delete(t);
        fn();
      }, ms);
      timers.add(t);
    };
    const stopTicker = () => {
      if (ticker) clearInterval(ticker);
      ticker = null;
    };

    setPhase("idle");
    setElapsedSeconds(0);

    later(() => {
      if (cancelled) return;
      const startedAt = Date.now();
      setPhase("checking");
      later(() => {
        if (!cancelled && !finished) setPhase("waking");
      }, wakingAfterMs);
      ticker = setInterval(() => {
        setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
      }, 1000);

      const attempt = async () => {
        try {
          const result = await getServerStatus({ timeoutMs: requestTimeoutMs });
          if (cancelled) return;
          finished = true;
          stopTicker();
          setStorage(result);
          setPhase("ready");
        } catch {
          if (cancelled) return;
          if (Date.now() - startedAt >= giveUpAfterMs) {
            finished = true;
            stopTicker();
            setPhase("unreachable");
          } else {
            later(attempt, retryDelayMs);
          }
        }
      };
      attempt();
    }, startDelayMs);

    return () => {
      cancelled = true;
      timers.forEach(clearTimeout);
      stopTicker();
    };
    // `run` restarts the machine; the timing options are stable constants.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run]);

  const retry = useCallback(() => setRun((n) => n + 1), []);
  return { phase, storage, elapsedSeconds, retry };
}
