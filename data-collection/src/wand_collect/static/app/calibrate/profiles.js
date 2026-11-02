// Saved calibrations. A profile holds a full set of vision and motion
// settings for one camera, room and lighting.

import { useEffect, useState } from "preact/hooks";

import { api } from "../api.js";
import { html } from "../html.js";

export function Profiles({ loaded, notices, locked }) {
  const [names, setNames] = useState([]);
  const [name, setName] = useState("");

  const refresh = async () => {
    const list = await notices.attempt(() => api.get("/api/profiles"));
    if (list) setNames(list.map((entry) => entry.name));
  };
  useEffect(() => {
    refresh();
  }, []);

  const run = async (action) => {
    await notices.attempt(action);
    await refresh();
  };

  const save = async () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    await run(() => api.put(`/api/profiles/${encodeURIComponent(trimmed)}`));
    setName("");
  };

  return html`<section class="panel">
    <h3>Profiles</h3>
    <div class="row">
      <input
        type="text"
        placeholder="Profile name"
        value=${name}
        disabled=${locked}
        onInput=${(event) => setName(event.target.value)}
      />
      <button disabled=${locked || !name.trim()} onClick=${save}>
        Save current settings
      </button>
    </div>
    ${names.length === 0 && html`<p class="hint">No saved profiles.</p>`}
    <ul class="profiles">
      ${names.map(
        (entry) => html`<li key=${entry}>
          <span>${entry}${entry === loaded ? " (loaded)" : ""}</span>
          <button
            disabled=${locked}
            onClick=${() =>
              run(() =>
                api.post(`/api/profiles/${encodeURIComponent(entry)}/load`),
              )}
          >
            Load
          </button>
          <button
            disabled=${locked}
            onClick=${() =>
              run(() =>
                api.delete(`/api/profiles/${encodeURIComponent(entry)}`),
              )}
          >
            Delete
          </button>
        </li>`,
      )}
    </ul>
  </section>`;
}
