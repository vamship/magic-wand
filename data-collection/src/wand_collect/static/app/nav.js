// Which page the user should be on, worked out from the state snapshot.

export const PAGES = [
  { id: "setup", title: "Setup" },
  { id: "calibrate", title: "Calibrate" },
  { id: "record", title: "Record" },
  { id: "review", title: "Review" },
  { id: "browse", title: "Browse" },
];

const CAPTURING = ["COUNTDOWN", "READY", "RECORDING"];

// The page the snapshot calls for: Record while capturing, Review when
// capture is paused or a session is loaded for review, Setup otherwise.
export function pageFor(snapshot) {
  if (!snapshot) return "setup";
  const capture = snapshot.capture && snapshot.capture.state;
  if (CAPTURING.includes(capture)) return "record";
  if (capture === "PAUSED") return "review";
  if (snapshot.session && snapshot.session.role === "review") return "review";
  if (!snapshot.session) return "setup";
  return null; // a session is loaded for capture but not capturing
}

// The page to show after a new snapshot. The page changes only when the
// state calls for a different page than before, so the user can still open
// Calibrate or Browse by hand while nothing else changes.
export function pageAfter(current, previousTarget, target) {
  if (target && target !== previousTarget) return target;
  return current;
}
