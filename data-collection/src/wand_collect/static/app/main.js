// The application shell: navigation, connection indicator, notices and the
// page. It holds no rules; it shows what the state says.

import { render } from "preact";
import { useEffect, useRef, useState } from "preact/hooks";

import { api } from "./api.js";
import { html } from "./html.js";
import { PAGES, pageAfter, pageFor } from "./nav.js";
import { createNotices } from "./notices.js";
import { renderPage } from "./pages/index.js";
import { createShortcuts } from "./shortcuts.js";
import { connectEvents, createStore, useSelector } from "./state.js";

export const store = createStore();
export const notices = createNotices();
export const shortcuts = createShortcuts();

function useNotices() {
  const [items, setItems] = useState(notices.get());
  useEffect(() => notices.subscribe(setItems), []);
  return items;
}

function Indicator({ connected }) {
  const text = connected ? "Connected" : "Reconnecting...";
  return html`<div class=${"indicator" + (connected ? " connected" : "")}>
    <span class="dot"></span>${text}
  </div>`;
}

function Notices({ items }) {
  return html`<div class="notices" role="alert">
    ${items.map(
      (item) => html`<div class="notice" key=${item.id}>
        <span>${item.message}</span>
        <span class="code">${item.code}</span>
        <button
          aria-label="Dismiss"
          onClick=${() => notices.dismiss(item.id)}
        >
          ×
        </button>
      </div>`,
    )}
  </div>`;
}

function App() {
  const snapshot = useSelector(store, (all) => all.state);
  const connected = useSelector(store, (all) => all.connected);
  const items = useNotices();
  const [page, setPage] = useState("setup");
  const target = pageFor(snapshot);
  const lastTarget = useRef(null);

  useEffect(() => {
    setPage((current) => pageAfter(current, lastTarget.current, target));
    lastTarget.current = target;
  }, [target]);

  const current = PAGES.find((entry) => entry.id === page);
  return html`<div class="shell">
    <header class="bar">
      <h1>Magic Wand</h1>
      <nav>
        ${PAGES.map(
          (entry) => html`<button
            key=${entry.id}
            aria-current=${entry.id === page ? "page" : undefined}
            onClick=${() => setPage(entry.id)}
          >
            ${entry.title}
          </button>`,
        )}
      </nav>
      <${Indicator} connected=${connected} />
    </header>
    <${Notices} items=${items} />
    <main>
      ${snapshot
        ? renderPage(page, current.title, {
            snapshot,
            store,
            shortcuts,
            notices,
            goTo: setPage,
          })
        : html`<p>Connecting to the application...</p>`}
    </main>
  </div>`;
}

async function start() {
  const config = await notices.attempt(() => api.get("/api/config"));
  if (config) shortcuts.setBindings(config.shortcuts);
  shortcuts.attach();
  connectEvents(store);
  render(html`<${App} />`, document.getElementById("app"));
}

start();
