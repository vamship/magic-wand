// The Calibrate page: color calibration, manual adjustment, motion tuning,
// the guided measurement and profiles, for the current camera. Every value
// comes from the state, and every control is disabled while a session is
// loaded for capture.

import { html } from "../html.js";
import { ColorCalibration } from "./color.js";
import { MotionTuning } from "./motion.js";
import { Profiles } from "./profiles.js";
import { VisionSliders } from "./vision.js";

export function isLocked(snapshot) {
  return Boolean(snapshot.session) && snapshot.session.role === "capture";
}

export function Calibrate({ snapshot, store, notices }) {
  const locked = isLocked(snapshot);
  const { vision, motion, profile } = snapshot.settings;
  return html`<section class="calibrate">
    <h2>Calibrate</h2>
    ${locked &&
    html`<p class="locked" role="status">
      Settings are locked while a session is capturing. End the session to
      calibrate.
    </p>`}
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
