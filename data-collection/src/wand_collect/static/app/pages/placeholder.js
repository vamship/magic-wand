// A stand-in for a page that is not built yet. It shows the live state, so
// the shell can be checked end to end.

import { html } from "../html.js";
import { useCountdown } from "../countdown.js";
import { useSelector } from "../state.js";

function Facts({ snapshot, motion }) {
  const left = useCountdown(snapshot.capture);
  const camera = snapshot.camera;
  const session = snapshot.session;
  return html`
    <dl class="facts">
      <dt>Session</dt>
      <dd>${session ? `${session.name} (${session.role})` : "none"}</dd>
      <dt>Capture</dt>
      <dd>
        ${snapshot.capture.state}
        ${left !== null ? ` - ${left.toFixed(1)} s` : ""}
      </dd>
      <dt>Camera</dt>
      <dd>
        ${camera.device
          ? `${camera.device} (${camera.actual.width}x` +
            `${camera.actual.height} at ${camera.actual.fps.toFixed(1)} fps)`
          : "none"}
      </dd>
      <dt>Motion</dt>
      <dd>
        ${motion
          ? `${motion.state}, speed ${motion.speed.toFixed(2)}`
          : "no readings"}
      </dd>
      <dt>Labels</dt>
      <dd>
        ${snapshot.labels.map((label) => label.name).join(", ") || "none"}
      </dd>
    </dl>
  `;
}

export function Placeholder({ title, note, snapshot, store, video }) {
  const motion = useSelector(store, (all) => all.motion);
  return html`
    <section>
      <h2>${title}</h2>
      <p>${note}</p>
      ${video &&
      html`<div class="panel">
        <img class="live" src="/api/stream" alt="Live camera view" />
      </div>`}
      <div class="panel">
        <${Facts} snapshot=${snapshot} motion=${motion} />
      </div>
    </section>
  `;
}
