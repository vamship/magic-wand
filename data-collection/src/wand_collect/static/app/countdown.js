// The countdown. The state holds the time at which the countdown ends, in
// seconds since the Unix epoch (the application and the browser run on the
// same computer, so they share a clock). The page counts down locally; no
// ticks are sent.

import { useEffect, useState } from "preact/hooks";

// Seconds left, or null when there is no countdown. While paused the state
// holds the time remaining instead.
export function secondsLeft(capture, nowS) {
  if (!capture) return null;
  if (capture.state === "COUNTDOWN" && capture.countdownEndsAt != null) {
    return Math.max(0, capture.countdownEndsAt - nowS);
  }
  if (capture.state === "PAUSED" && capture.remainingS != null) {
    return capture.remainingS;
  }
  return null;
}

export function useCountdown(capture) {
  const [now, setNow] = useState(Date.now() / 1000);
  const running = Boolean(capture) && capture.state === "COUNTDOWN";
  useEffect(() => {
    if (!running) return undefined;
    setNow(Date.now() / 1000);
    const timer = setInterval(() => setNow(Date.now() / 1000), 100);
    return () => clearInterval(timer);
  }, [running]);
  return secondsLeft(capture, now);
}
