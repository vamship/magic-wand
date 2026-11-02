// Small form controls used by the calibrate page. Each shows the value from
// the state and sends changes to the server; a slider keeps the value being
// dragged on screen until the state catches up.

import { useMemo, useRef, useState } from "preact/hooks";

import { html } from "./html.js";
import { throttle } from "./throttle.js";

const SEND_EVERY_MS = 100; // about 10 requests a second while dragging
const SETTLE_MS = 300;

export function Slider(props) {
  const { label, value, min, max, step, onSend, disabled, format } = props;
  const [drag, setDrag] = useState(null);
  const latest = useRef(onSend);
  latest.current = onSend;
  const send = useMemo(
    () => throttle((v) => latest.current(v), SEND_EVERY_MS),
    [],
  );

  const finish = async (v) => {
    send.cancel();
    try {
      await latest.current(v);
    } finally {
      setTimeout(() => setDrag(null), SETTLE_MS);
    }
  };

  const shown = drag === null ? value : drag;
  return html`<label class="control">
    <span class="name">${label}</span>
    <input
      type="range"
      min=${min}
      max=${max}
      step=${step}
      value=${shown}
      disabled=${disabled}
      onInput=${(event) => {
        const v = Number(event.target.value);
        setDrag(v);
        send(v);
      }}
      onChange=${(event) => finish(Number(event.target.value))}
    />
    <output>${format ? format(shown) : shown}</output>
  </label>`;
}

export function NumberField(props) {
  const { label, value, min, max, step, onSend, disabled } = props;
  const [draft, setDraft] = useState(null);
  const shown = draft === null ? value : draft;
  const commit = async (text) => {
    const v = Number(text);
    if (Number.isFinite(v) && v !== value) await onSend(v);
    setDraft(null);
  };
  return html`<label class="control">
    <span class="name">${label}</span>
    <input
      type="number"
      min=${min}
      max=${max}
      step=${step}
      value=${shown}
      disabled=${disabled}
      onInput=${(event) => setDraft(event.target.value)}
      onChange=${(event) => commit(event.target.value)}
    />
  </label>`;
}
