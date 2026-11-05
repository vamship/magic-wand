// The Setup page: choose the camera, start a new session, or open an
// existing one. Every value comes from the state or the server; a command's
// response only says whether it was accepted.

import { useEffect, useState } from "preact/hooks";

import { api } from "./api.js";
import { html } from "./html.js";

const REMEMBERED = "wand.setup";

// Whether the camera delivers a different mode than was asked for.
export function modesDiffer(requested, actual) {
  if (!requested || !actual) return false;
  if (requested.width !== actual.width) return true;
  if (requested.height !== actual.height) return true;
  const fps = Math.abs(requested.fps - actual.fps);
  return requested.fps > 0 && fps / requested.fps > 0.1;
}

export function describeMode(mode) {
  if (!mode) return "unknown";
  const fps = Number(mode.fps).toFixed(mode.fps % 1 ? 1 : 0);
  return `${mode.width}x${mode.height} at ${fps} fps`;
}

function remembered() {
  try {
    return JSON.parse(localStorage.getItem(REMEMBERED)) || {};
  } catch (error) {
    return {};
  }
}

function remember(values) {
  try {
    localStorage.setItem(REMEMBERED, JSON.stringify(values));
  } catch (error) {
    // Storage may be blocked; the form just starts empty next time.
  }
}

export function isCapturing(snapshot) {
  return Boolean(snapshot.session) && snapshot.session.role === "capture";
}

function CameraPanel({ snapshot, notices }) {
  const [cameras, setCameras] = useState(null);
  const camera = snapshot.camera;
  const locked = isCapturing(snapshot);
  const inUse =
    `In use: ${camera.device}, asked for ${describeMode(camera.requested)}, ` +
    `delivering ${describeMode(camera.actual)}.`;

  const refresh = async () => {
    const list = await notices.attempt(() => api.get("/api/cameras"));
    if (list) setCameras(list);
  };
  useEffect(() => {
    refresh();
  }, [camera.index]);

  const choose = (index) =>
    notices.attempt(() => api.put("/api/camera", { index }));

  return html`<section class="panel">
    <h3>Camera</h3>
    <div class="row">
      <label>
        Camera
        <select
          value=${camera.index ?? ""}
          disabled=${locked || !cameras || cameras.length === 0}
          onChange=${(event) => choose(Number(event.target.value))}
        >
          ${camera.index === null && html`<option value="">none</option>`}
          ${(cameras || []).map(
            (entry) => html`<option key=${entry.index} value=${entry.index}>
              ${entry.name || `Camera ${entry.index}`}
            </option>`,
          )}
        </select>
      </label>
      <button disabled=${locked} onClick=${refresh}>Refresh list</button>
    </div>
    ${cameras && cameras.length === 0 &&
    html`<p class="hint">No cameras were found.</p>`}
    ${camera.device
      ? html`<p class="mode">
          ${inUse}
        </p>`
      : html`<p class="hint">No camera is in use.</p>`}
    ${modesDiffer(camera.requested, camera.actual) &&
    html`<p class="locked" role="status">
      The camera delivers a different mode than was asked for. Recordings
      will use ${describeMode(camera.actual)}.
    </p>`}
    ${camera.device &&
    html`<img class="live" src="/api/stream" alt="Live camera view" />`}
  </section>`;
}

function CurrentSession({ snapshot, notices }) {
  const session = snapshot.session;
  if (!session) return null;
  const capturing = session.role === "capture";
  const role = capturing ? "loaded for capture" : "open for review only";
  const end = () =>
    notices.attempt(() => api.post("/api/sessions/current/end"));
  return html`<section class="panel current">
    <h3>Current session</h3>
    <p>
      ${`${session.name} (${role})`}
    </p>
    ${capturing &&
    html`<p class="locked" role="status">
      End the session before starting or resuming another one.
    </p>`}
    <button onClick=${end}>
      ${capturing ? "End session" : "Close review"}
    </button>
  </section>`;
}

function NewSession({ snapshot, store, goTo }) {
  const draft = store.get().draft || {};
  const saved = remembered();
  const [author, setAuthor] = useState(draft.author ?? saved.author ?? "");
  const [handedness, setHandedness] = useState(
    draft.handedness ?? saved.handedness ?? "",
  );
  const [name, setName] = useState(draft.name ?? "");
  const [notes, setNotes] = useState(draft.notes ?? "");
  const locked = isCapturing(snapshot);
  const ready = author.trim() !== "" && handedness !== "";

  // Nothing is started here. The details wait on the Calibrate page, which
  // starts the session once the settings are final.
  const proceed = () => {
    const details = { author: author.trim(), handedness };
    if (name.trim()) details.name = name.trim();
    if (notes.trim()) details.notes = notes.trim();
    remember({ author: details.author, handedness });
    store.set({ draft: details });
    goTo("calibrate");
  };

  return html`<section class="panel">
    <h3>New session</h3>
    ${locked &&
    html`<p class="hint">A session is capturing. End it first.</p>`}
    <div class="form">
      <label>
        Author
        <input
          type="text"
          value=${author}
          disabled=${locked}
          onInput=${(event) => setAuthor(event.target.value)}
        />
      </label>
      <fieldset disabled=${locked}>
        <legend>Handedness</legend>
        ${["left", "right"].map(
          (value) => html`<label key=${value} class="choice">
            <input
              type="radio"
              name="handedness"
              value=${value}
              checked=${handedness === value}
              onChange=${() => setHandedness(value)}
            />
            ${value}
          </label>`,
        )}
      </fieldset>
      <label>
        Session name (optional)
        <input
          type="text"
          value=${name}
          disabled=${locked}
          onInput=${(event) => setName(event.target.value)}
        />
      </label>
      <label>
        Notes (optional)
        <input
          type="text"
          value=${notes}
          disabled=${locked}
          onInput=${(event) => setNotes(event.target.value)}
        />
      </label>
    </div>
    <p class="hint">
      Next you calibrate the camera. The session starts from the Calibrate
      page, and its settings are fixed from then on.
    </p>
    <div class="row">
      <button disabled=${locked || !ready} onClick=${proceed}>
        Continue to calibrate
      </button>
    </div>
  </section>`;
}

function formatDate(text) {
  const date = new Date(text);
  return Number.isNaN(date.getTime()) ? text : date.toLocaleString();
}

// Changes the name and notes of one session. They describe the session, so
// they can change at any time, for any session.
function DetailsEditor({ entry, notices, onDone }) {
  const [name, setName] = useState(entry.name || "");
  const [notes, setNotes] = useState(entry.notes || "");
  const save = async () => {
    const saved = await notices.attempt(() =>
      api.patch(`/api/sessions/${entry.id}`, { name, notes }),
    );
    if (saved) onDone(true);
  };
  return html`<div class="form">
    <label>
      Session name
      <input
        type="text"
        value=${name}
        onInput=${(event) => setName(event.target.value)}
      />
    </label>
    <label>
      Notes
      <input
        type="text"
        value=${notes}
        onInput=${(event) => setNotes(event.target.value)}
      />
    </label>
    <div class="row">
      <button onClick=${save}>Save</button>
      <button onClick=${() => onDone(false)}>Cancel</button>
    </div>
  </div>`;
}

function SessionList({ snapshot, notices, goTo }) {
  const [sessions, setSessions] = useState(null);
  const [editing, setEditing] = useState(null);
  const session = snapshot.session;
  const locked = isCapturing(snapshot);
  const isCurrent = (entry) =>
    locked && Boolean(session) && session.id === entry.id;
  const key = session ? `${session.id}:${session.role}` : "none";

  const refresh = async () => {
    const list = await notices.attempt(() => api.get("/api/sessions"));
    if (list) setSessions(list);
  };
  useEffect(() => {
    refresh();
  }, [key, snapshot.samplesRevision]);

  const load = async (id, mode) => {
    const loaded = await notices.attempt(() =>
      api.post(`/api/sessions/${id}/load?mode=${mode}`),
    );
    if (!loaded) return;
    (loaded.warnings || []).forEach((text) => notices.add(text, "warning"));
    goTo(mode === "resume" ? "record" : "review");
  };

  // The session already loaded for capture continues where it paused.
  const continueCurrent = async () => {
    if (snapshot.capture.state === "PAUSED") {
      const done = await notices.attempt(() =>
        api.post("/api/recording/resume"),
      );
      if (!done) return;
    }
    goTo("record");
  };

  const finishEditing = async (saved) => {
    setEditing(null);
    if (saved) await refresh();
  };

  const remove = async (entry) => {
    const text =
      `Delete the session "${entry.name || "(unnamed)"}" by ${entry.author} ` +
      `with its ${entry.sampleCount} samples and their video clips? ` +
      "This cannot be undone.";
    if (!window.confirm(text)) return;
    await notices.attempt(() => api.delete(`/api/sessions/${entry.id}`));
    await refresh();
  };

  return html`<section class="panel">
    <h3>Sessions</h3>
    ${sessions && sessions.length === 0 &&
    html`<p class="hint">No sessions yet.</p>`}
    <table class="sessions">
      <tbody>
        ${[...(sessions || [])].reverse().map(
          (entry) => html`<tr key=${entry.id}>
            <td>
              ${editing === entry.id
                ? html`<${DetailsEditor}
                    entry=${entry}
                    notices=${notices}
                    onDone=${finishEditing}
                  />`
                : html`${entry.name || "(unnamed)"}
                    ${entry.notes &&
                    html`<div class="hint">${entry.notes}</div>`}`}
            </td>
            <td>${entry.author}</td>
            <td>${formatDate(entry.startedAt)}</td>
            <td>${entry.sampleCount} samples</td>
            <td>${entry.open ? "open" : "ended"}</td>
            <td>
              <button
                disabled=${locked}
                onClick=${() => load(entry.id, "review")}
              >
                Review
              </button>
              ${entry.open &&
              html`<button
                disabled=${locked && !isCurrent(entry)}
                onClick=${() =>
                  isCurrent(entry)
                    ? continueCurrent()
                    : load(entry.id, "resume")}
              >
                Resume
              </button>`}
              <button onClick=${() => setEditing(entry.id)}>Edit</button>
              <button
                disabled=${Boolean(session) && session.id === entry.id}
                title=${session && session.id === entry.id
                  ? "End or close the session first"
                  : "Delete the session and its samples"}
                onClick=${() => remove(entry)}
              >
                Delete
              </button>
            </td>
          </tr>`,
        )}
      </tbody>
    </table>
  </section>`;
}

export function Setup({ snapshot, store, notices, goTo }) {
  return html`<section class="setup">
    <h2>Setup</h2>
    <div class="columns">
      <div>
        <${CameraPanel} snapshot=${snapshot} notices=${notices} />
      </div>
      <div>
        <${CurrentSession} snapshot=${snapshot} notices=${notices} />
        <${NewSession} snapshot=${snapshot} store=${store} goTo=${goTo} />
      </div>
    </div>
    <${SessionList} snapshot=${snapshot} notices=${notices} goTo=${goTo} />
  </section>`;
}
