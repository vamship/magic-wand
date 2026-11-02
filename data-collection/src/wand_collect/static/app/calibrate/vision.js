// Manual adjustment of the vision settings. Each slider sends a partial
// change and takes effect on the live view; the value shown always comes
// from the state.

import { api } from "../api.js";
import { Slider } from "../controls.js";
import { html } from "../html.js";

const CONTROLS = [
  { key: "hueCenter", label: "Hue center", min: 0, max: 179, step: 1 },
  { key: "hueHalfWidth", label: "Hue half-width", min: 0, max: 90, step: 1 },
  { key: "satMin", label: "Saturation min", min: 0, max: 255, step: 1 },
  { key: "satMax", label: "Saturation max", min: 0, max: 255, step: 1 },
  { key: "valMin", label: "Brightness min", min: 0, max: 255, step: 1 },
  { key: "valMax", label: "Brightness max", min: 0, max: 255, step: 1 },
  { key: "blurSize", label: "Smoothing", min: 0, max: 15, step: 1 },
  { key: "cleanupSize", label: "Cleanup", min: 0, max: 15, step: 1 },
  { key: "minArea", label: "Smallest size", min: 0, max: 0.01, step: 0.0001 },
  { key: "maxArea", label: "Largest size", min: 0.005, max: 0.2, step: 0.001 },
  { key: "minRoundness", label: "Roundness", min: 0, max: 1, step: 0.05 },
];

export function VisionSliders({ vision, notices, locked }) {
  const change = (key) => (value) =>
    notices.attempt(() =>
      api.put("/api/settings", { vision: { [key]: value } }),
    );
  return html`<section class="panel">
    <h3>Adjust</h3>
    ${CONTROLS.map(
      (control) => html`<${Slider}
        key=${control.key}
        label=${control.label}
        value=${vision[control.key]}
        min=${control.min}
        max=${control.max}
        step=${control.step}
        disabled=${locked}
        onSend=${change(control.key)}
      />`,
    )}
  </section>`;
}
