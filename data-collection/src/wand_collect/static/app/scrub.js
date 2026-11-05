// The scrubbing view: one sample's video with its path drawn over it. The
// part of the path up to the current frame is highlighted. Only for samples
// that have a clip. Frame positions come from the sample's `positions` and
// the clip's `gestureStartS`.

import { useEffect, useRef, useState } from "preact/hooks";

import { html } from "./html.js";

const FRAME_S = 1 / 30; // one step; the clip's rate is about 30 fps
const PATH_COLOR = "rgba(255, 255, 255, 0.35)";
const DONE_COLOR = "#f0883e";
const MARKER_COLOR = "#4cc38a";

// How many positions are at or before video time `videoS`. Position times
// are seconds from the gesture start, which is `gestureStartS` into the clip.
export function countUpTo(timeS, gestureStartS, videoS) {
  const into = videoS - gestureStartS;
  let count = 0;
  while (count < timeS.length && timeS[count] <= into + 1e-9) count += 1;
  return count;
}

// Draws the whole path faintly and the part up to `count` in colour.
export function drawPath(context, positions, count, width, height) {
  const { horizontal, vertical } = positions;
  const at = (i) => [horizontal[i] * width, vertical[i] * height];
  context.clearRect(0, 0, width, height);
  context.lineWidth = Math.max(2, height / 120);
  context.lineJoin = "round";
  const trace = (from, to, color) => {
    if (to - from < 1) return;
    context.beginPath();
    context.strokeStyle = color;
    context.moveTo(...at(from));
    for (let i = from + 1; i <= to; i += 1) context.lineTo(...at(i));
    context.stroke();
  };
  trace(0, horizontal.length - 1, PATH_COLOR);
  trace(0, count - 1, DONE_COLOR);
  if (count > 0) {
    const [x, y] = at(count - 1);
    context.beginPath();
    context.fillStyle = MARKER_COLOR;
    context.arc(x, y, Math.max(4, height / 60), 0, 2 * Math.PI);
    context.fill();
  }
}

export function Scrub({ id, details, onClose }) {
  const stage = useRef(null);
  const video = useRef(null);
  const canvas = useRef(null);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [full, setFull] = useState(false);

  const positions = details.positions;
  const start = details.video ? details.video.gestureStartS : 0;
  const draw = () => {
    const element = canvas.current;
    const player = video.current;
    if (!element || !player) return;
    element.width = player.clientWidth || 640;
    element.height = player.clientHeight || 480;
    const context = element.getContext("2d");
    if (!context) return;
    const count = countUpTo(positions.timeS, start, player.currentTime);
    drawPath(context, positions, count, element.width, element.height);
  };

  useEffect(() => {
    const player = video.current;
    const update = () => {
      setTime(player.currentTime);
      draw();
    };
    const meta = () => {
      setDuration(player.duration || 0);
      player.currentTime = Math.max(0, start);
      update();
    };
    player.addEventListener("timeupdate", update);
    player.addEventListener("seeked", update);
    player.addEventListener("loadedmetadata", meta);
    player.addEventListener("play", () => setPlaying(true));
    player.addEventListener("pause", () => setPlaying(false));
    // While playing, follow the video every animation frame.
    let frame = 0;
    const follow = () => {
      if (!player.paused) update();
      frame = requestAnimationFrame(follow);
    };
    frame = requestAnimationFrame(follow);
    return () => cancelAnimationFrame(frame);
  }, [id]);

  useEffect(() => {
    const changed = () => setFull(document.fullscreenElement === stage.current);
    document.addEventListener("fullscreenchange", changed);
    return () => document.removeEventListener("fullscreenchange", changed);
  }, []);

  const seek = (seconds) => {
    const player = video.current;
    const next = Math.min(Math.max(0, seconds), duration || seconds);
    player.currentTime = next;
    setTime(next);
  };
  // A step starts from where the player is now, so quick clicks add up.
  const step = (frames) => seek(video.current.currentTime + frames * FRAME_S);
  const toggle = () => {
    const player = video.current;
    if (player.paused) player.play();
    else player.pause();
  };
  const toggleFull = () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else if (stage.current.requestFullscreen) stage.current.requestFullscreen();
  };

  return html`<section class="scrub" ref=${stage}>
    <div class="frame">
      <div class="box">
        <video
          ref=${video}
          src=${`/api/samples/${encodeURIComponent(id)}/video`}
          preload="auto"
          muted
          playsinline
        ></video>
        <canvas ref=${canvas}></canvas>
      </div>
    </div>
    <div class="row controls">
      <button onClick=${toggle}>${playing ? "Pause" : "Play"}</button>
      <button aria-label="Back one frame" onClick=${() => step(-1)}>
        ◀ Frame
      </button>
      <button aria-label="Forward one frame" onClick=${() => step(1)}>
        Frame ▶
      </button>
      <input
        type="range"
        aria-label="Position in the clip"
        min="0"
        max=${duration}
        step="0.01"
        value=${time}
        onInput=${(event) => seek(Number(event.target.value))}
      />
      <span class="hint">${time.toFixed(2)} s</span>
      <button onClick=${toggleFull}>
        ${full ? "Leave full screen" : "Full screen"}
      </button>
      <button onClick=${onClose}>Close</button>
    </div>
  </section>`;
}
