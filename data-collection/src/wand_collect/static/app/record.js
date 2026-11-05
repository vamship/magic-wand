// The Record page: what the user sees while capturing. It shows the live
// view, the state of the capture cycle, the countdown, the active label and
// its count, and the latest sample. It offers no review actions; pressing
// Escape or clicking anywhere pauses capturing, and the shell then moves to
// the Review page.

import { useCallback, useEffect, useRef } from "preact/hooks";

import { api } from "./api.js";
import { useCountdown } from "./countdown.js";
import { html } from "./html.js";
import {
  LabelSelect,
  TARGET_PER_LABEL,
  labelName,
  pathImage,
  useLabelKeys,
} from "./labels.js";

const DISCARDS = {
  too_long: "The gesture took too long.",
  too_short: "The gesture was too short.",
  too_small: "The gesture was too small.",
  tracking_lost: "The wand tip was lost during the gesture.",
};

export function discardMessage(discard) {
  return DISCARDS[discard.reason] || `Discarded: ${discard.reason}`;
}

const CAPTURING = ["COUNTDOWN", "READY", "RECORDING"];

function Cue({ state, left }) {
  if (state === "COUNTDOWN") {
    const shown = left === null ? "" : Math.ceil(left);
    return html`<div class="cue countdown" role="status">
      <span class="big">${shown}</span>
      <span>Get ready</span>
    </div>`;
  }
  if (state === "READY") {
    return html`<div class="cue ready" role="status">
      <span class="big">Go</span>
      <span>Draw the gesture now</span>
    </div>`;
  }
  if (state === "RECORDING") {
    return html`<div class="cue recording" role="status">
      <span class="big">Recording</span>
    </div>`;
  }
  return html`<div class="cue stopped" role="status">
    <span>Choose a label, then press Start.</span>
  </div>`;
}

function Latest({ snapshot }) {
  const latest = snapshot.latestSample;
  if (!latest) {
    return html`<p class="hint">The latest gesture appears here.</p>`;
  }
  return html`<div class="latest">
    ${latest.saving
      ? html`<div class="saving">Saving...</div>`
      : html`<img
          key=${latest.id}
          src=${pathImage(latest.id)}
          alt="Path of the latest gesture"
        />`}
    <p>
      ${labelName(snapshot, latest.label)}
      - ${latest.saving ? "saving" : "saved"}
      ${!latest.saving && !latest.clipAvailable && " (no video clip)"}
    </p>
  </div>`;
}

export function Record({ snapshot, shortcuts, notices }) {
  const capture = snapshot.capture;
  const active = snapshot.activeLabel;
  const left = useCountdown(capture);
  const capturing = CAPTURING.includes(capture.state);
  const seen = useRef(snapshot.lastDiscard && snapshot.lastDiscard.timestampS);

  const chooseLabel = useCallback(
    (id) =>
      notices.attempt(() => api.put("/api/recording/label", { label: id })),
    [notices],
  );
  const start = () => notices.attempt(() => api.post("/api/recording/start"));
  const pause = useCallback(() => {
    if (CAPTURING.includes(snapshot.capture.state)) {
      notices.attempt(() => api.post("/api/recording/pause"));
    }
  }, [snapshot.capture.state, notices]);

  useLabelKeys(shortcuts, snapshot, chooseLabel);
  useEffect(() => shortcuts.on("pause", pause), [shortcuts, pause]);

  // A discard shows its reason once.
  useEffect(() => {
    const discard = snapshot.lastDiscard;
    if (!discard || discard.timestampS === seen.current) return;
    seen.current = discard.timestampS;
    notices.add(discardMessage(discard), "discard");
  }, [snapshot.lastDiscard]);

  const onPageClick = (event) => {
    const tag = event.target.tagName;
    if (["BUTTON", "SELECT", "OPTION", "INPUT"].includes(tag)) return;
    pause();
  };

  const count = active ? snapshot.counts[active] || 0 : 0;
  return html`<section class="record" onClick=${onPageClick}>
    <h2>Record</h2>
    <div class="columns">
      <div>
        <div class=${"stage " + capture.state.toLowerCase()}>
          <img class="live" src="/api/stream" alt="Live camera view" />
        </div>
        <${Cue} state=${capture.state} left=${left} />
      </div>
      <div>
        <div class="panel">
          <h3>Label</h3>
          <div class="row">
            <${LabelSelect}
              snapshot=${snapshot}
              value=${active}
              onChoose=${chooseLabel}
            />
            <button
              disabled=${capture.state !== "STOPPED" || !active}
              onClick=${start}
            >
              Start
            </button>
          </div>
          ${active &&
          html`<p class="count">
            <strong>${count}</strong> of ${TARGET_PER_LABEL} accepted for
            ${labelName(snapshot, active)}
          </p>`}
          ${capturing &&
          html`<p class="hint">
            Press <kbd>${shortcuts.keyFor("pause")}</kbd> or click to pause.
          </p>`}
        </div>
        <div class="panel">
          <h3>Latest gesture</h3>
          <${Latest} snapshot=${snapshot} />
        </div>
      </div>
    </div>
  </section>`;
}
