// The Calibrate page: color calibration, manual adjustment, motion tuning,
// the guided measurement and profiles, for the current camera. Every value
// comes from the state, and every control is disabled while a session is
// loaded for capture.

import { api } from "../api.js";
import { html } from "../html.js";
import { useSelector } from "../state.js";
import { ColorCalibration } from "./color.js";
import { MotionTuning } from "./motion.js";
import { Profiles } from "./profiles.js";
import { VisionSliders } from "./vision.js";

export function isLocked(snapshot) {
  return Boolean(snapshot.session) && snapshot.session.role === "capture";
}

// Starts the session from the details given on Setup. The settings are fixed
// from then on, so this comes last.
function StartSession({ snapshot, store, notices, goTo }) {
  const draft = useSelector(store, (all) => all.draft);
  const locked = isLocked(snapshot);
  const start = async () => {
    const started = await notices.attempt(() =>
      api.post("/api/sessions", draft),
    );
    if (started) goTo("record");
  };
  if (locked) return null;
  return html`<section class="panel start">
    <h3>Start the session</h3>
    ${draft
      ? html`<p>
          ${[draft.name, draft.author, `${draft.handedness}-handed`]
            .filter(Boolean)
            .join(", ")}.
          <button onClick=${() => goTo("setup")}>Change</button>
        </p>`
      : html`<p class="hint">
          Enter the author and handedness on the Setup page first.
          <button onClick=${() => goTo("setup")}>Go to Setup</button>
        </p>`}
    <p class="hint">
      Settings are locked once the session starts. Calibrate first.
    </p>
    <button disabled=${!draft || !snapshot.camera.device} onClick=${start}>
      Start session
    </button>
    ${draft &&
    !snapshot.camera.device &&
    html`<p class="hint">No camera is in use.</p>`}
  </section>`;
}

export function Calibrate({ snapshot, store, notices, goTo }) {
  const locked = isLocked(snapshot);
  const { vision, motion, profile } = snapshot.settings;
  return html`<section class="calibrate">
    <h2>Calibrate</h2>
    ${locked &&
    html`<p class="locked" role="status">
      Settings are locked while a session is capturing. End the session to
      calibrate.
    </p>`}
    <${StartSession}
      snapshot=${snapshot}
      store=${store}
      notices=${notices}
      goTo=${goTo}
    />
    <div class="columns">
      <div>
        <${ColorCalibration}
          store=${store}
          notices=${notices}
          locked=${locked}
        />
        <${Profiles} loaded=${profile} notices=${notices} locked=${locked} />
      </div>
      <div>
        <${MotionTuning}
          store=${store}
          motion=${motion}
          notices=${notices}
          locked=${locked}
        />
        <${VisionSliders}
          vision=${vision}
          notices=${notices}
          locked=${locked}
        />
      </div>
    </div>
  </section>`;
}
