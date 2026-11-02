// Limits how often a function runs while its caller fires it continuously,
// such as a slider being dragged. The first call runs at once; calls that
// follow within `waitMs` are merged into one call with the latest arguments,
// made when the wait is over, so the final value is never lost.

export function throttle(fn, waitMs) {
  let timer = null;
  let pending = null;
  let last = -Infinity;

  function run(args) {
    last = Date.now();
    fn(...args);
  }

  function throttled(...args) {
    const remaining = waitMs - (Date.now() - last);
    if (remaining <= 0) {
      clearTimeout(timer);
      timer = null;
      pending = null;
      run(args);
      return;
    }
    pending = args;
    if (timer === null) {
      timer = setTimeout(() => {
        timer = null;
        const args = pending;
        pending = null;
        if (args) run(args);
      }, remaining);
    }
  }

  // Drops a call that is still waiting.
  throttled.cancel = () => {
    clearTimeout(timer);
    timer = null;
    pending = null;
  };
  return throttled;
}
