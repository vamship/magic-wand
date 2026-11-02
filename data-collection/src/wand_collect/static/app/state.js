// The browser's copy of the application: the latest state snapshot, the
// latest motion reading and whether the event stream is connected.
//
// The page never edits the snapshot. It only replaces it with the next one
// the server sends, so several windows always show the same thing.

import { useEffect, useState } from "preact/hooks";

export function createStore(initial = {}) {
  let value = { state: null, motion: null, connected: false, ...initial };
  const listeners = new Set();
  return {
    get: () => value,
    set(changes) {
      value = { ...value, ...changes };
      listeners.forEach((listener) => listener(value));
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

// Reads one part of the store. The component renders again only when that
// part changes, so the fast motion readings do not redraw the whole page.
export function useSelector(store, selector) {
  const [selected, setSelected] = useState(() => selector(store.get()));
  useEffect(() => {
    const check = (value) => {
      const next = selector(value);
      setSelected((previous) => (Object.is(previous, next) ? previous : next));
    };
    check(store.get());
    return store.subscribe(check);
  }, [store]);
  return selected;
}

const CLOSED = 2; // EventSource.CLOSED

// Connects the store to the event stream and keeps it connected. The browser
// retries a dropped connection by itself; if it gives up, this opens a new
// one. The server sends a whole snapshot first on every connection, so after
// a reconnect the store holds the current state. Returns a function that
// stops everything.
export function connectEvents(store, url = "/api/events", options = {}) {
  const { EventSourceClass = EventSource, retryMs = 2000 } = options;
  let source = null;
  let timer = null;
  let stopped = false;

  function open() {
    source = new EventSourceClass(url);
    source.onopen = () => store.set({ connected: true });
    source.addEventListener("state", (event) => {
      store.set({ state: JSON.parse(event.data) });
    });
    source.addEventListener("motion", (event) => {
      store.set({ motion: JSON.parse(event.data) });
    });
    source.onerror = () => {
      store.set({ connected: false });
      if (source.readyState === CLOSED && !stopped) {
        source.close();
        timer = setTimeout(open, retryMs);
      }
    };
  }

  open();
  return () => {
    stopped = true;
    clearTimeout(timer);
    source.close();
  };
}
