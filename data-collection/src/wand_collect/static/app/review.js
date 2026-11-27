// The Review page: the samples of the loaded session in the sample workspace
// (the same grid and selected-sample panel as Browse, limited to the session),
// with what is specific to a session above it: resume capturing, pause or end
// the session, and choose the label of the next captures. The newest sample is
// first and selected, so a gesture that has just been captured is the one to
// look at.

import { useEffect } from "preact/hooks";

import { api } from "./api.js";
import { EndButton } from "./end.js";
import { HoldButton } from "./hold.js";
import { html } from "./html.js";
import { LabelSelect } from "./labels.js";
import { SampleWorkspace } from "./workspace.js";

function Button({ shortcuts, action, label, ...rest }) {
  const key = action ? shortcuts.keyFor(action) : "";
  return html`<button ...${rest}>
    ${label}${key && html` <kbd>${key}</kbd>`}
  </button>`;
}

export function Review({ snapshot, shortcuts, notices, goTo }) {
  const session = snapshot.session;
  const capturing = Boolean(session) && session.role === "capture";
  // A resumed session whose camera has not been checked goes back to
  // Calibrate for the check; a session that is loaded but not capturing yet
  // has nothing to resume, so it goes to Record.
  const checking = capturing && Boolean(session.cameraCheck);
  const notStarted = capturing && snapshot.capture.state === "STOPPED";
  const resume = () => {
    if (checking) {
      if (goTo) goTo("calibrate");
      return undefined;
    }
    if (notStarted) {
      if (goTo) goTo("record");
      return undefined;
    }
    const path = capturing
      ? "/api/recording/resume"
      : "/api/sessions/current/end";
    return notices.attempt(() => api.post(path));
  };
  const resumeLabel = !capturing
    ? "Close review"
    : checking
      ? "Check the camera first"
      : notStarted
        ? "Go to Record"
        : "Resume capturing";
  const chooseActive = (label) =>
    notices.attempt(() => api.put("/api/recording/label", { label }));

  // Escape resumes capturing; it never closes a review by accident.
  useEffect(() => {
    if (capturing) return shortcuts.on("pause", resume);
    return undefined;
  });

  if (!session) {
    return html`<section class="browse">
      <p class="hint">No session is loaded. Open one on the Setup page.</p>
    </section>`;
  }
  const latest = snapshot.latestSample;
  const top = html`<div class="review-top">
    <div class="row">
      <${Button}
        shortcuts=${shortcuts}
        action=${capturing ? "pause" : ""}
        label=${resumeLabel}
        onClick=${resume}
      />
      ${capturing && html`<${HoldButton} notices=${notices} />`}
      ${capturing &&
      html`<${EndButton}
        id=${session.id}
        name=${session.name}
        notices=${notices}
      />`}
      ${capturing &&
      html`<label>
        Next captures
        <${LabelSelect}
          snapshot=${snapshot}
          value=${snapshot.activeLabel}
          onChoose=${chooseActive}
        />
      </label>`}
    </div>
    ${Boolean(latest) &&
    latest.saving &&
    html`<p class="locked" role="status">
      The last gesture is still saving; it appears here when it is saved.
    </p>`}
  </div>`;
  return html`<section class="browse">
    <${SampleWorkspace}
      snapshot=${snapshot}
      notices=${notices}
      shortcuts=${shortcuts}
      filters=${{ session: session.id }}
      top=${top}
      emptyText="This session has no samples yet."
    />
  </section>`;
}
