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
          In use: ${camera.device}, asked for
          ${describeMode(camera.requested)}, delivering
          ${describeMode(camera.actual)}.
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
  const end = () =>
    notices.attempt(() => api.post("/api/sessions/current/end"));
  return html`<section class="panel current">
    <h3>Current session</h3>
    <p>
      ${session.name}
      (${capturing ? "loaded for capture" : "open for review only"})
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

function NewSession({ snapshot, notices, goTo }) {
  const saved = remembered();
  const [author, setAuthor] = useState(saved.author || "");
  const [handedness, setHandedness] = useState(saved.handedness || "");
  const [name, setName] = useState("");
  const [notes, setNotes] = useState("");
  const locked = isCapturing(snapshot);
  const ready = author.trim() !== "" && handedness !== "";

  const start = async (next) => {
    remember({ author: author.trim(), handedness });
    const body = { author: author.trim(), handedness };
    if (name.trim()) body.name = name.trim();
    if (notes.trim()) body.notes = notes.trim();
    const started = await notices.attempt(() =>
      api.post("/api/sessions", body),
    );
    if (started) goTo(next);
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
    <div class="row">
      <button disabled=${locked || !ready} onClick=${() => start("calibrate")}>
        Start and calibrate
      </button>
      <button disabled=${locked || !ready} onClick=${() => start("record")}>
        Start and record (settings already calibrated)
      </button>
    </div>
  </section>`;
}

function formatDate(text) {
  const date = new Date(text);
  return Number.isNaN(date.getTime()) ? text : date.toLocaleString();
}

function SessionList({ snapshot, notices, goTo }) {
  const [sessions, setSessions] = useState(null);
  const session = snapshot.session;
  const locked = isCapturing(snapshot);
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
            <td>${entry.name || "(unnamed)"}</td>
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
                disabled=${locked}
                onClick=${() => load(entry.id, "resume")}
              >
                Resume
              </button>`}
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

export function Setup({ snapshot, notices, goTo }) {
  return html`<section class="setup">
    <h2>Setup</h2>
    <div class="columns">
      <div>
        <${CameraPanel} snapshot=${snapshot} notices=${notices} />
      </div>
      <div>
        <${CurrentSession} snapshot=${snapshot} notices=${notices} />
        <${NewSession}
          snapshot=${snapshot}
          notices=${notices}
          goTo=${goTo}
        />
      </div>
    </div>
    <${SessionList} snapshot=${snapshot} notices=${notices} goTo=${goTo} />
  </section>`;
}
