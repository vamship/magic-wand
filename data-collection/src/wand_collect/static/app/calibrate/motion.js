// Motion tuning: a graph of recent speed with the start and end thresholds,
// a slider for the start threshold (the end threshold follows), numeric
// fields for the valid time window and minimum size, and a guided
// measurement that proposes thresholds.

import { useEffect, useRef, useState } from "preact/hooks";

import { api } from "../api.js";
import { Slider, NumberField } from "../controls.js";
import { graphLayout, speedScale, trimReadings } from "../geometry.js";
import { html } from "../html.js";
import { useSelector } from "../state.js";

const WINDOW_S = 5; // seconds of history in the graph
const GRAPH_WIDTH = 600;
const GRAPH_HEIGHT = 120;
const GET_READY_MS = 1500;

// --- The graph ---------------------------------------------------------

function draw(canvas, readings) {
  const context = canvas.getContext("2d");
  if (!context) return;
  context.clearRect(0, 0, canvas.width, canvas.height);
  if (!readings.length) return;
  const newest = readings[readings.length - 1];
  const scale = speedScale(readings, newest.startSpeed);
  const layout = graphLayout(
    readings,
    WINDOW_S,
    canvas.width,
    canvas.height,
    scale,
  );
  const line = (y, color) => {
    context.strokeStyle = color;
    context.beginPath();
    context.moveTo(0, y);
    context.lineTo(canvas.width, y);
    context.stroke();
  };
  context.setLineDash([6, 4]);
  line(layout.startY, "#f0883e");
  line(layout.endY, "#4cc38a");
  context.setLineDash([]);
  context.strokeStyle = "#e8eaee";
  context.lineWidth = 2;
  context.beginPath();
  layout.points.forEach(([x, y], index) =>
    index ? context.lineTo(x, y) : context.moveTo(x, y),
  );
  context.stroke();
  context.lineWidth = 1;
}

export function SpeedGraph({ store }) {
  const canvas = useRef(null);
  useEffect(() => {
    let readings = [];
    let frame = null;
    let last = null;
    const unsubscribe = store.subscribe((all) => {
      if (!all.motion || all.motion === last) return;
      last = all.motion;
      readings = trimReadings([...readings, all.motion], WINDOW_S);
      if (frame === null) {
        frame = requestAnimationFrame(() => {
          frame = null;
          if (canvas.current) draw(canvas.current, readings);
        });
      }
    });
    return () => {
      unsubscribe();
      if (frame !== null) cancelAnimationFrame(frame);
    };
  }, [store]);
  return html`<canvas
    ref=${canvas}
    class="graph"
    width=${GRAPH_WIDTH}
    height=${GRAPH_HEIGHT}
    aria-label="Speed over the last ${WINDOW_S} seconds"
  ></canvas>`;
}

// --- Guided measurement ------------------------------------------------

const STEPS = [
  {
    phase: "still",
    ready: "Get ready to hold the wand still...",
    doing: "Hold the wand still.",
  },
  {
    phase: "wave",
    ready: "Get ready to wave the wand from side to side...",
    doing: "Wave the wand from side to side.",
  },
];

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// The sentence is built as one string: htm drops spaces that sit next to a
// line break, so text and values must not be split across lines in markup.
function appliedText(proposal) {
  const f = (value) => value.toFixed(2);
  return (
    "The proposed thresholds replaced the motion settings: " +
    `start ${f(proposal.startSpeed)}, end ${f(proposal.endSpeed)} ` +
    `(noise ${f(proposal.idleCeiling)}, ` +
    `strokes about ${f(proposal.typicalGestureSpeed)}).`
  );
}

export function GuidedMeasurement({ notices, locked }) {
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [applied, setApplied] = useState(null);

  const start = async () => {
    setBusy(true);
    setApplied(null);
    try {
      for (const step of STEPS) {
        setMessage(step.ready);
        await sleep(GET_READY_MS);
        setMessage(step.doing);
        const reply = await notices.attempt(() =>
          api.post("/api/calibration/measure", { phase: step.phase }),
        );
        if (!reply) return; // the failure is already shown as a notice
        if (reply.complete) setApplied(reply.proposal);
      }
      setMessage("Done.");
    } finally {
      setBusy(false);
    }
  };

  return html`<div class="guided">
    <button disabled=${locked || busy} onClick=${start}>
      Guided measurement
    </button>
    ${message && html`<p class="instruction" role="status">${message}</p>`}
    ${applied && html`<p class="good">${appliedText(applied)}</p>`}
  </div>`;
}

// --- The panel ---------------------------------------------------------

export function MotionTuning({ store, motion, notices, locked }) {
  const reading = useSelector(store, (all) => all.motion);
  const change = (key) => (value) =>
    notices.attempt(() =>
      api.put("/api/settings", { motion: { [key]: value } }),
    );
  return html`<section class="panel">
    <h3>Motion</h3>
    <p class="speed">
      ${"Speed "}<strong>${reading ? reading.speed.toFixed(2) : "-"}</strong>
      ${" frame-heights per second"}
    </p>
    <${SpeedGraph} store=${store} />
    <p class="legend">
      <span class="start">start ${motion.startSpeed.toFixed(2)}</span>
      <span class="end">end ${motion.endSpeed.toFixed(2)}</span>
    </p>
    <${Slider}
      label="Start threshold"
      value=${motion.startSpeed}
      min=${0.05}
      max=${3}
      step=${0.01}
      disabled=${locked}
      format=${(v) => v.toFixed(2)}
      onSend=${change("startSpeed")}
    />
    <${NumberField}
      label="Shortest gesture (s)"
      value=${motion.minDurationS}
      min=${0.1}
      max=${5}
      step=${0.1}
      disabled=${locked}
      onSend=${change("minDurationS")}
    />
    <${NumberField}
      label="Longest gesture (s)"
      value=${motion.maxDurationS}
      min=${0.5}
      max=${10}
      step=${0.5}
      disabled=${locked}
      onSend=${change("maxDurationS")}
    />
    <${NumberField}
      label="Smallest path"
      value=${motion.minExtent}
      min=${0.01}
      max=${1}
      step=${0.01}
      disabled=${locked}
      onSend=${change("minExtent")}
    />
    <${GuidedMeasurement} notices=${notices} locked=${locked} />
  </section>`;
}
