// Label helpers shared by the pages that work with samples.

import { useEffect } from "preact/hooks";

import { html } from "./html.js";

export const TARGET_PER_LABEL = 1000;

// The display name of a label id (the id itself if it is not known).
export function labelName(snapshot, id) {
  const label = snapshot.labels.find((entry) => entry.id === id);
  return label ? label.name : id;
}

// A selector of labels. The digits 1 to 9 choose the labels in this order,
// so each option shows its digit.
export function LabelSelect({ snapshot, value, onChoose, disabled }) {
  return html`<select
    aria-label="Label"
    value=${value ?? ""}
    disabled=${disabled}
    onChange=${(event) => onChoose(event.target.value)}
  >
    ${value == null && html`<option value="">choose a label</option>`}
    ${snapshot.labels.map(
      (label, index) => html`<option key=${label.id} value=${label.id}>
        ${index < 9 ? `${index + 1}. ` : ""}${label.name}
      </option>`,
    )}
  </select>`;
}

// Calls `choose(labelId)` when a digit key picks one of the labels.
export function useLabelKeys(shortcuts, snapshot, choose) {
  useEffect(
    () =>
      shortcuts.on("label", (digit) => {
        const label = snapshot.labels[digit - 1];
        if (label) choose(label.id);
      }),
    [shortcuts, snapshot.labels, choose],
  );
}

// The path image of a sample (a PNG made by the server).
export function pathImage(id, mode = "path") {
  return `/api/samples/${encodeURIComponent(id)}/image?mode=${mode}`;
}
