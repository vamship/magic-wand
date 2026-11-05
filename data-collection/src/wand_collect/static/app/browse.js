// The Browse page: every sample in the dataset, with filters, per-label
// progress and a detail view in which a sample can be relabeled, rejected,
// restored or deleted, in any session. The table repeats its query when the
// samples revision changes, and it works while no session is loaded.

import { useEffect, useState } from "preact/hooks";

import { api } from "./api.js";
import { html } from "./html.js";
import {
  LabelSelect,
  TARGET_PER_LABEL,
  labelName,
  pathImage,
} from "./labels.js";
import { Scrub } from "./scrub.js";

const PAGE_SIZE = 25;
const NO_FILTERS = {
  label: "",
  session: "",
  author: "",
  from: "",
  to: "",
  status: "",
};

// The query string of a set of filters and a page.
export function queryFor(filters, page) {
  const params = new URLSearchParams();
  for (const [name, value] of Object.entries(filters)) {
    if (value) params.set(name, value);
  }
  params.set("order", "newest");
  params.set("page", String(page));
  params.set("pageSize", String(PAGE_SIZE));
  return params.toString();
}

function thumbnail(id) {
  return `/api/samples/${encodeURIComponent(id)}/thumbnail`;
}

function formatDate(text) {
  const date = new Date(text);
  return Number.isNaN(date.getTime()) ? text : date.toLocaleString();
}

function Progress({ snapshot }) {
  return html`<section class="panel">
    <h3>Accepted samples per label</h3>
    <ul class="progress">
      ${snapshot.labels.map((label) => {
        const count = snapshot.counts[label.id] || 0;
        const share = Math.min(100, (100 * count) / TARGET_PER_LABEL);
        return html`<li key=${label.id}>
          <span class="name">${label.name}</span>
          <span
            class="bar"
            role="progressbar"
            aria-valuemin="0"
            aria-valuemax=${TARGET_PER_LABEL}
            aria-valuenow=${count}
          >
            <span style=${`width: ${share}%`}></span>
          </span>
          <span class="number">${count} / ${TARGET_PER_LABEL}</span>
        </li>`;
      })}
    </ul>
  </section>`;
}

function Filters({ snapshot, filters, sessions, onChange }) {
  const authors = [...new Set(sessions.map((entry) => entry.author))].sort();
  const set = (name) => (event) => onChange({ [name]: event.target.value });
  return html`<section class="panel filters">
    <label>
      Label
      <select aria-label="Filter by label" onChange=${set("label")}
        value=${filters.label}>
        <option value="">all</option>
        ${snapshot.labels.map(
          (label) =>
            html`<option key=${label.id} value=${label.id}>
              ${label.name}
            </option>`,
        )}
      </select>
    </label>
    <label>
      Session
      <select aria-label="Filter by session" onChange=${set("session")}
        value=${filters.session}>
        <option value="">all</option>
        ${sessions.map(
          (entry) =>
            html`<option key=${entry.id} value=${entry.id}>
              ${entry.name || "(unnamed)"} - ${entry.author}
            </option>`,
        )}
      </select>
    </label>
    <label>
      Author
      <select aria-label="Filter by author" onChange=${set("author")}
        value=${filters.author}>
        <option value="">all</option>
        ${authors.map(
          (author) => html`<option key=${author} value=${author}>
            ${author}
          </option>`,
        )}
      </select>
    </label>
    <label>
      Status
      <select aria-label="Filter by status" onChange=${set("status")}
        value=${filters.status}>
        <option value="">all</option>
        <option value="accepted">accepted</option>
        <option value="rejected">rejected</option>
      </select>
    </label>
    <label>
      From
      <input type="date" aria-label="From date" value=${filters.from}
        onChange=${set("from")} />
    </label>
    <label>
      To
      <input type="date" aria-label="To date" value=${filters.to}
        onChange=${set("to")} />
    </label>
    <button onClick=${() => onChange(NO_FILTERS)}>Clear filters</button>
  </section>`;
}

function Detail({ snapshot, summary, notices, onClose }) {
  const [details, setDetails] = useState(null);
  const [overlay, setOverlay] = useState(false);
  const [busy, setBusy] = useState(false);
  const [scrubbing, setScrubbing] = useState(false);
  const id = summary.id;
  const url = `/api/samples/${encodeURIComponent(id)}`;

  useEffect(() => {
    setDetails(null);
    let current = true;
    notices
      .attempt(() => api.get(url))
      .then((found) => current && found && setDetails(found));
    return () => {
      current = false;
    };
  }, [id, snapshot.samplesRevision]);

  const hasClip = Boolean(details && details.hasClip);
  const act = async (action) => {
    setBusy(true);
    try {
      return await notices.attempt(action);
    } finally {
      setBusy(false);
    }
  };
  const toggle = () =>
    act(() =>
      api.patch(url, {
        status: summary.status === "accepted" ? "rejected" : "accepted",
      }),
    );
  const relabel = (label) => act(() => api.patch(url, { label }));
  const remove = async () => {
    if (!window.confirm("Delete this sample and its clip for good?")) return;
    const done = await act(() => api.delete(url));
    if (done !== undefined) onClose();
  };

  const showOverlay = overlay && hasClip;
  if (scrubbing && hasClip) {
    return html`<${Scrub}
      id=${id}
      details=${details}
      onClose=${() => setScrubbing(false)}
    />`;
  }
  return html`<section class="panel detail">
    <h3>Sample</h3>
    <img
      class="sample-image"
      key=${id + (showOverlay ? "o" : "p")}
      src=${pathImage(id, showOverlay ? "overlay" : "path")}
      alt="Path of the selected gesture"
    />
    <div class="row">
      <button aria-pressed=${!showOverlay} onClick=${() => setOverlay(false)}>
        Path only
      </button>
      ${hasClip &&
      html`<button
        aria-pressed=${showOverlay}
        onClick=${() => setOverlay(true)}
      >
        Overlay on camera frame
      </button>`}
      ${hasClip &&
      html`<button onClick=${() => setScrubbing(true)}>Scrub video</button>`}
    </div>
    ${details &&
    !hasClip &&
    html`<p class="hint">
      This sample has no video clip, so the overlay and video views are not
      available.
    </p>`}
    <dl class="facts">
      <dt>Label</dt>
      <dd>${labelName(snapshot, summary.label)}</dd>
      <dt>Status</dt>
      <dd class=${summary.status}>${summary.status}</dd>
      <dt>Session</dt>
      <dd>${summary.sessionName || "(unnamed)"} by ${summary.author}</dd>
      <dt>Captured</dt>
      <dd>${formatDate(summary.capturedAt)}</dd>
      ${details &&
      html`<dt>Points</dt>
        <dd>${details.positions.horizontal.length}</dd>
        <dt>Hand</dt>
        <dd>${details.handedness}</dd>`}
    </dl>
    <div class="row">
      <label>
        Relabel
        <${LabelSelect}
          snapshot=${snapshot}
          value=${summary.label}
          disabled=${busy}
          onChoose=${relabel}
        />
      </label>
      <button disabled=${busy} onClick=${toggle}>
        ${summary.status === "accepted" ? "Reject" : "Restore"}
      </button>
      <button disabled=${busy} onClick=${remove}>Delete</button>
      <button onClick=${onClose}>Close</button>
    </div>
  </section>`;
}

export function Browse({ snapshot, notices }) {
  const [filters, setFilters] = useState(NO_FILTERS);
  const [page, setPage] = useState(1);
  const [result, setResult] = useState({ items: [], total: 0 });
  const [sessions, setSessions] = useState([]);
  const [selected, setSelected] = useState(null);

  const change = (changes) => {
    setFilters((current) => ({ ...current, ...changes }));
    setPage(1);
  };

  useEffect(() => {
    notices.attempt(() => api.get("/api/sessions")).then((list) => {
      if (list) setSessions(list);
    });
  }, [snapshot.samplesRevision]);

  useEffect(() => {
    let current = true;
    notices
      .attempt(() => api.get(`/api/samples?${queryFor(filters, page)}`))
      .then((found) => current && found && setResult(found));
    return () => {
      current = false;
    };
  }, [filters, page, snapshot.samplesRevision]);

  const pages = Math.max(1, Math.ceil(result.total / PAGE_SIZE));
  const summary = result.items.find((item) => item.id === selected) || null;
  return html`<section class="browse">
    <h2>Browse</h2>
    <${Progress} snapshot=${snapshot} />
    <${Filters}
      snapshot=${snapshot}
      filters=${filters}
      sessions=${sessions}
      onChange=${change}
    />
    <div class="columns">
      <div>
        <p class="hint">${result.total} samples match.</p>
        <table class="samples">
          <tbody>
            ${result.items.map(
              (item) => html`<tr
                key=${item.id}
                class=${item.id === selected ? "selected" : ""}
                onClick=${() => setSelected(item.id)}
              >
                <td>
                  <img
                    loading="lazy"
                    src=${thumbnail(item.id)}
                    alt=""
                  />
                </td>
                <td>${labelName(snapshot, item.label)}</td>
                <td class=${item.status}>${item.status}</td>
                <td>${item.sessionName || "(unnamed)"}</td>
                <td>${item.author}</td>
                <td>${formatDate(item.capturedAt)}</td>
              </tr>`,
            )}
          </tbody>
        </table>
        <div class="row">
          <button disabled=${page <= 1} onClick=${() => setPage(page - 1)}>
            Previous page
          </button>
          <span>Page ${page} of ${pages}</span>
          <button disabled=${page >= pages} onClick=${() => setPage(page + 1)}>
            Next page
          </button>
        </div>
      </div>
      <div class="sticky-detail">
        ${summary
          ? html`<${Detail}
              snapshot=${snapshot}
              summary=${summary}
              notices=${notices}
              onClose=${() => setSelected(null)}
            />`
          : html`<p class="hint">Select a sample to see it here.</p>`}
      </div>
    </div>
  </section>`;
}
