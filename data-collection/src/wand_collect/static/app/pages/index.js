// The pages. Each is a function of the state snapshot; the ones not built
// yet use the placeholder.

import { html } from "../html.js";
import { Calibrate } from "../calibrate/index.js";
import { Placeholder } from "./placeholder.js";

const NOTES = {
  setup: "Choose a camera and start or load a session.",
  calibrate: "Calibrate the ball color and tune the motion thresholds.",
  record: "Capture gestures.",
  review: "Review, reject, relabel and delete samples.",
  browse: "Browse every sample in the dataset.",
};

export function renderPage(id, title, props) {
  if (id === "calibrate") return html`<${Calibrate} ...${props} />`;
  return html`<${Placeholder}
    title=${title}
    note=${NOTES[id]}
    video=${["setup", "calibrate", "record"].includes(id)}
    ...${props}
  />`;
}
