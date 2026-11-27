// Datasets on the Setup page: which dataset is in use, choosing another,
// creating one, and merging several into one. The datasets live side by side
// in the data location; the sessions and samples shown everywhere come from
// the one in use. None of this works while a session is loaded, because the
// loaded session belongs to the dataset in use.

import { useEffect, useState } from "preact/hooks";

import { ApiError, api } from "./api.js";
import { html } from "./html.js";

const NEW = "__new__";

function describe(entry) {
  if (entry.error) return `unreadable: ${entry.error}`;
  return `${entry.sessions} sessions, ${entry.samples} samples`;
}

export function replaceConfirmation(target) {
  return (
    `Merge with replace? Where a session differs, the copy in "${target}" ` +
    "is replaced by the source's copy. This cannot be undone."
  );
}

function MergeResult({ result }) {
  const counts = Object.entries(result.counts)
    .map(([action, number]) => `${number} ${action}`)
    .join(", ");
  return html`<div class="merge-result" role="status">
    <p>Merged into ${result.target}: ${counts || "nothing to merge"}.</p>
    ${result.sessions.length > 0 &&
    html`<table class="sessions">
      <tbody>
        ${result.sessions.map(
          (entry) => html`<tr key=${entry.sessionId}>
            <td>${entry.source}</td>
            <td>${entry.sessionId.slice(0, 8)}</td>
            <td>${entry.action}</td>
            <td>${entry.message}</td>
          </tr>`,
        )}
      </tbody>
    </table>`}
  </div>`;
}

function MergeForm({ datasets, notices, disabled, onDone }) {
  const [sources, setSources] = useState([]);
  const [target, setTarget] = useState("");
  const [newName, setNewName] = useState("");
  const [onConflict, setOnConflict] = useState("skip");
  const [skipClips, setSkipClips] = useState(false);
  const [result, setResult] = useState(null);

  const targetName = target === NEW ? newName.trim() : target;
  const ready =
    sources.length > 0 &&
    targetName !== "" &&
    !sources.includes(targetName) &&
    !disabled;

  const toggle = (name) =>
    setSources((all) =>
      all.includes(name) ? all.filter((n) => n !== name) : [...all, name],
    );

  const merge = async () => {
    const replace = onConflict === "replace";
    if (replace && !window.confirm(replaceConfirmation(targetName))) return;
    const done = await notices.attempt(() =>
      api.post("/api/datasets/merge", {
        sources,
        target: targetName,
        onConflict,
        skipClips,
      }),
    );
    if (!done) return;
    setResult(done);
    onDone();
  };

  return html`<div class="form merge">
    <fieldset disabled=${disabled}>
      <legend>Merge these datasets</legend>
      ${datasets.map(
        (entry) => html`<label key=${entry.name} class="choice">
          <input
            type="checkbox"
            checked=${sources.includes(entry.name)}
            onChange=${() => toggle(entry.name)}
          />
          ${entry.name} (${describe(entry)})
        </label>`,
      )}
    </fieldset>
    <div class="row">
      <label>
        into
        <select
          value=${target}
          disabled=${disabled}
          onChange=${(event) => setTarget(event.target.value)}
        >
          <option value="">choose a dataset</option>
          ${datasets
            .filter((entry) => !sources.includes(entry.name))
            .map(
              (entry) =>
                html`<option key=${entry.name} value=${entry.name}>
                  ${entry.name}
                </option>`,
            )}
          <option value=${NEW}>a new dataset...</option>
        </select>
      </label>
      ${target === NEW &&
      html`<input
        type="text"
        placeholder="new dataset name"
        value=${newName}
        disabled=${disabled}
        onInput=${(event) => setNewName(event.target.value)}
      />`}
    </div>
    <fieldset disabled=${disabled}>
      <legend>A session that differs in the target</legend>
      ${[
        ["skip", "Keep the target's copy and report it"],
        ["replace", "Replace it with the source's copy"],
      ].map(
        ([value, text]) => html`<label key=${value} class="choice">
          <input
            type="radio"
            name="on-conflict"
            checked=${onConflict === value}
            onChange=${() => setOnConflict(value)}
          />
          ${text}
        </label>`,
      )}
    </fieldset>
    <label class="choice">
      <input
        type="checkbox"
        checked=${skipClips}
        disabled=${disabled}
        onChange=${(event) => setSkipClips(event.target.checked)}
      />
      Do not copy video clips
    </label>
    <div class="row">
      <button disabled=${!ready} onClick=${merge}>Merge</button>
      <button onClick=${() => onDone(true)}>Close</button>
    </div>
    ${result && html`<${MergeResult} result=${result} />`}
  </div>`;
}

export function DatasetsPanel({ snapshot, notices }) {
  const [datasets, setDatasets] = useState(null);
  const [newName, setNewName] = useState("");
  const [nameError, setNameError] = useState("");
  const [merging, setMerging] = useState(false);
  const locked = Boolean(snapshot.session);

  const refresh = async () => {
    const list = await notices.attempt(() => api.get("/api/datasets"));
    if (list) setDatasets(list);
  };
  useEffect(() => {
    refresh();
  }, [snapshot.dataset, locked, snapshot.samplesRevision]);

  const choose = (name) =>
    notices.attempt(() => api.put("/api/dataset", { name }));

  const create = async () => {
    setNameError("");
    try {
      await api.post("/api/datasets", { name: newName.trim() });
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
      setNameError(error.message);
      return;
    }
    setNewName("");
    await refresh();
  };

  const closeMerge = (close) => {
    refresh();
    if (close) setMerging(false);
  };

  return html`<section class="panel datasets">
    <h3>Dataset</h3>
    <p>
      Recording into <strong>${snapshot.dataset || "(none)"}</strong>.
    </p>
    ${locked &&
    html`<p class="locked" role="status">
      A session is loaded. End it or pause it before changing datasets.
    </p>`}
    <table class="sessions">
      <tbody>
        ${(datasets || []).map(
          (entry) => html`<tr key=${entry.name}>
            <td>${entry.name}</td>
            <td>${describe(entry)}</td>
            <td>
              ${entry.inUse
                ? html`<span>in use</span>`
                : html`<button
                    disabled=${locked || Boolean(entry.error)}
                    onClick=${() => choose(entry.name)}
                  >
                    Use
                  </button>`}
            </td>
          </tr>`,
        )}
      </tbody>
    </table>
    <div class="row">
      <input
        type="text"
        placeholder="new dataset name"
        value=${newName}
        disabled=${locked}
        onInput=${(event) => setNewName(event.target.value)}
      />
      <button disabled=${locked || newName.trim() === ""} onClick=${create}>
        New dataset
      </button>
    </div>
    ${nameError && html`<p class="locked" role="alert">${nameError}</p>`}
    ${merging
      ? html`<${MergeForm}
          datasets=${datasets || []}
          notices=${notices}
          disabled=${locked}
          onDone=${closeMerge}
        />`
      : html`<div class="row">
          <button
            disabled=${locked || !datasets || datasets.length < 1}
            onClick=${() => setMerging(true)}
          >
            Merge datasets...
          </button>
        </div>`}
  </section>`;
}
