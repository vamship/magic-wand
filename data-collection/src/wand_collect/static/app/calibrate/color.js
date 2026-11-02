// Color calibration. The user freezes a frame, clicks on the wand tip, and
// sees the detection mask and the detected tip. More clicks refine the
// result; the tolerance control runs the calibration again.

import { useEffect, useState } from "preact/hooks";

import { api } from "../api.js";
import { Slider } from "../controls.js";
import { clickFraction } from "../geometry.js";
import { html } from "../html.js";
import { useSelector } from "../state.js";

const DEFAULT_TOLERANCE = 2.5;

function LiveView({ store, view, onView, locked }) {
  const motion = useSelector(store, (all) => all.motion);
  const moving = Boolean(motion && motion.moving);
  return html`
    <div class=${"stage" + (moving ? " moving" : " idle")}>
      <img class="live" src=${"/api/stream?view=" + view} alt="Live view" />
      <span class="badge">${moving ? "MOTION" : "IDLE"}</span>
    </div>
    <div class="row">
      <button
        aria-pressed=${view === "camera"}
        disabled=${locked}
        onClick=${() => onView("camera")}
      >
        Camera
      </button>
      <button
        aria-pressed=${view === "mask"}
        disabled=${locked}
        onClick=${() => onView("mask")}
      >
        Mask
      </button>
    </div>
  `;
}

function FrozenView({ frame, result, showMask, onClick }) {
  const tip = result && result.tip;
  return html`
    <div class="stage frozen">
      <img
        class="live"
        src=${frame}
        alt="Frozen frame: click on the wand tip"
        onClick=${onClick}
      />
      ${result &&
      showMask &&
      html`<img class="overlay" src=${result.mask} alt="Detection mask" />`}
      ${tip &&
      tip.found &&
      html`<span
        class="tip-marker"
        style=${{
          left: tip.horizontal * 100 + "%",
          top: tip.vertical * 100 + "%",
        }}
      ></span>`}
    </div>
  `;
}

function Outcome({ result }) {
  if (!result) {
    return html`<p class="hint">Click on the wand tip in the picture.</p>`;
  }
  const others = result.otherRegions;
  return html`<ul class="outcome">
    <li class=${result.tip.found ? "good" : "bad"}>
      ${result.tip.found
        ? "Tip found."
        : "Tip not found: click closer to the ball."}
    </li>
    <li class=${others === 0 ? "good" : "bad"}>
      ${others === 0
        ? "Nothing else is marked."
        : `${others} other region${others === 1 ? " is" : "s are"} also ` +
          "marked: lower the tolerance or click a more distinctive spot."}
    </li>
    <li>${result.sampleCount} pixels sampled.</li>
  </ul>`;
}

export function ColorCalibration({ store, notices, locked }) {
  const [view, setView] = useState("camera");
  const [frame, setFrame] = useState(null); // object URL of the frozen frame
  const [result, setResult] = useState(null);
  const [showMask, setShowMask] = useState(true);

  useEffect(() => () => frame && URL.revokeObjectURL(frame), [frame]);

  const freeze = async () => {
    const blob = await notices.attempt(() =>
      api.blob("POST", "/api/calibration/freeze"),
    );
    if (!blob) return;
    setResult(null);
    setFrame(URL.createObjectURL(blob));
  };

  const back = () => {
    setFrame(null);
    setResult(null);
  };

  const calibrate = async (body) => {
    const reply = await notices.attempt(() =>
      api.post("/api/calibration/clicks", body),
    );
    if (reply) setResult(reply);
  };

  const onClick = (event) => {
    if (locked) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const point = clickFraction(rect, event.clientX, event.clientY);
    calibrate({ points: [point] });
  };

  return html`<section class="panel">
    <h3>Color</h3>
    ${frame
      ? html`<${FrozenView}
          frame=${frame}
          result=${result}
          showMask=${showMask}
          onClick=${onClick}
        />`
      : html`<${LiveView}
          store=${store}
          view=${view}
          onView=${setView}
          locked=${locked}
        />`}
    <div class="row">
      ${frame
        ? html`<button onClick=${back}>Back to live view</button>
            <label>
              <input
                type="checkbox"
                checked=${showMask}
                onChange=${(event) => setShowMask(event.target.checked)}
              />
              Show mask
            </label>`
        : html`<button disabled=${locked} onClick=${freeze}>
            Freeze frame
          </button>`}
    </div>
    ${frame &&
    html`<${Outcome} result=${result} />
      <${Slider}
        label="Tolerance"
        value=${result ? result.tolerance : DEFAULT_TOLERANCE}
        min=${0.5}
        max=${6}
        step=${0.1}
        disabled=${locked || !result}
        onSend=${(tolerance) => calibrate({ tolerance })}
      />`}
  </section>`;
}
