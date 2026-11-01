# Data Collection Application - Requirements

Status: v4. Updated after the design review: rapid-capture workflow with
auto-accept, click-to-calibrate, motion tuning, camera selection, shared label
configuration, and dataset merging. Delivery phases: **P1** = needed for the
first usable release, **P2** = later phase.

## 1. Overview

This document lists what the data collection application must do (functional
requirements R1 to R7), the qualities it must have (N1 to N5), what is out of
scope, and the decisions made so far. After reading it you will know what the
application is for, what the user can do with it, and which requirement IDs the
design and task documents refer to.

The application records and labels wand gestures to build the training dataset
for the gesture classifier (target: about 1,000 samples per gesture). It must
make high-volume recording fast, and it must use the same vision and
motion-detection code as the inference pipeline so training and inference data
are consistent.

## 2. Definitions

- **Gesture / label**: a named spell the classifier must recognize.
- **Sample**: one recorded gesture, bounded by idle at start and end.
- **Session**: one run of the app by one author, with settings locked at start.
- **Calibration**: the phase before a session where the camera, vision
  settings and motion settings are chosen and tested against the live view.
- **Tip position**: midpoint of the ping pong ball in a frame, with the frame
  timestamp (output of the vision system).
- **Status**: each stored sample is either `accepted` or `rejected`.
  **Delete** is different: it removes the sample from the dataset entirely.
- **Rapid capture**: the recording workflow in R4, a repeating cycle of
  countdown, gesture and result.

## 3. Functional Requirements

### R1. Setup and calibration (P1)
- R1.1 **Camera selection.** The user can see the cameras available on the
  machine, preview each, and choose one. The choice is recorded in the session.
- R1.2 **Color calibration by click.** The user is shown a frozen camera image
  and clicks the tip of the wand. The app derives the vision settings from the
  click and shows the detection result (mask and detected tip). The user can
  click more points to refine the result. Colors that wrap around the hue
  scale (e.g. red/orange) work without any extra user steps.
- R1.3 **Manual vision adjustment.** The user can also adjust the vision
  settings by hand (e.g. with sliders) and see the effect live.
- R1.4 **Motion tuning.** A screen shows the live camera feed and clearly
  distinguishes motion from no motion, shows the current tip speed, and has a
  slider for the motion threshold. The user tunes the threshold by watching
  when motion triggers. The other motion settings (valid time window, minimum
  gesture size) can also be adjusted there.
- R1.5 **Guided motion measurement.** The app can propose initial motion
  thresholds from a short guided step: hold the wand still, then wave it.
- R1.6 A calibration can be saved as a named profile and reloaded later.
  Profiles are local to the machine.
- R1.7 Calibration must cope with different lighting, backgrounds, small color
  differences between wands, and different laptop cameras.

### R2. Session management (P1)
- R2.1 Starting a session captures metadata: author, an optional session name
  chosen by the author so teammates can refer to the session, handedness
  (left/right), start timestamp, camera/device identifier, requested and
  *actual* frame resolution and frame rate, the full vision settings, and the
  full motion-detection settings (including time window and minimum size
  thresholds), and optional free-text notes (lighting, background, etc.).
- R2.2 **Settings are locked once the session starts.** To change any vision or
  motion setting the user must end the session and start a new one (via
  calibration). This guarantees every sample in a session was captured with
  identical settings, and lets us detect setting changes across sessions.
- R2.3 Each session is stored as a self-contained unit with its metadata in
  its own file; each sample references its session. It must be possible to
  consolidate all samples (with their session data) into a single file on
  demand.
- R2.4 Handedness is stored with the session and with each sample. Stored
  positions are never mirrored; any handling of handedness is deferred to
  training.
- R2.5 **Merge.** Data recorded in parallel (for example by different teammates
  on different machines) can be merged into one dataset. Merging never alters
  a session, and reports any conflict instead of silently overwriting.

### R3. Gesture label management (P1)
- R3.1 The label set is a project configuration file shared by all teammates,
  and is editable from within the app (add, rename, remove).
- R3.2 Each label has a stable identifier and a display name. Samples refer to
  the identifier, so renaming a label does not alter any sample. A label that
  has samples cannot be removed.
- R3.3 Labels are picked from the list; they cannot be free-typed at record
  time.
- R3.4 The initial list is dummy entries for development; the real spell list
  will be supplied later.

### R4. Recording (P1)
- R4.1 The user chooses an **active label** before capturing, and can change
  it at any time. Each captured sample is tagged with the active label.
- R4.2 **Rapid capture cycle.** After the user starts capturing, the app
  repeats:
  1. a **countdown** that tells the user when to get ready;
  2. the app becomes **ready**, and the user performs the gesture;
  3. the **result** (the path image) is shown while the next countdown runs.
- R4.3 The countdown length is configurable in the application config. The
  default is 3 seconds.
- R4.4 After the countdown ends, the app is ready for the next gesture, with no
  timeout, until a gesture is captured or the user pauses.
- R4.5 Gesture capture is automatic: the shared motion-detection subsystem
  segments each sample using idle -> motion -> idle, with no key press.
  Segments that exceed the valid time window or are too small are **thrown
  away, not stored**; the user is notified that one was discarded.
- R4.6 **Auto-accept.** A captured sample is saved as `accepted` without any
  user action. The user intervenes only to reject (or otherwise change) it.
- R4.7 **Pause.** Pressing Escape or clicking any mouse button pauses the
  countdown so the user can review the latest sample (R5). Resuming continues
  the countdown.
- R4.8 The live view shows the camera feed, the detected tip, the current state
  (countdown, ready, recording, paused), the countdown, the active label, and a
  running count of accepted samples for that label.
- R4.9 There is no separate record-then-label workflow. Unlabeled samples are
  not created; a sample's label can be changed during review (R5.2) or later
  (R7.3).

### R5. Review of the latest sample (P1)
- R5.1 After each capture the app shows the wand path with direction cues
  (start/end markers or a color gradient). The user can switch between:
  - path only (color on black), and
  - path overlaid on one camera frame (e.g. the first frame of the sample).
- R5.2 While reviewing the latest sample (during the countdown or while
  paused), the user can **reject** it (or accept it again), **delete** it, and
  **change its label**. Changes are saved immediately.
- R5.3 These actions are available via keyboard shortcuts (usable one-handed)
  and on-screen buttons; shortcut keys are shown on the buttons.
- R5.4 Rejecting or deleting the most recent sample needs a single action.

### R6. Storage (P1 unless noted)
- R6.1 Each sample stores raw timestamped positions `(x, y, t)` per frame.
  Derived motion vectors are not stored; they are computed on load by the
  shared code.
- R6.2 Each sample also stores: label, status, session ID, sample ID, capture
  and last-update timestamps, handedness, and frame resolution. Positions are
  stored in normalized coordinates (0 to 1) so different cameras are
  comparable; resolution is recorded as well. Real timestamps are always
  kept, because actual frame rates vary.
- R6.3 The data directory is user-specified. The default is outside version
  control. The file format and layout are defined in `docs/data-storage.md` and
  must be directly loadable by the classification subsystem (Python/NumPy/
  PyTorch).
- R6.4 Writes are crash-safe: a sample is on disk before the next capture is
  ready, and a partial write never corrupts existing data. The same applies to
  later edits.
- R6.5 Path preview images are generated on demand, not stored in the dataset,
  and generation is fast. Thumbnails for browsing may be cached outside the
  dataset (derived data only, safe to delete).
- R6.6 **Video snippets (capture: P1, viewing: P2).** For each stored sample
  the app also saves the relevant video clip, from a few seconds before to a
  few seconds after the gesture, linked from the sample metadata. This is for
  debugging motion detection and classification. The padding duration is
  configurable.
- R6.7 Camera defaults: request a common mode (**640x480 at 30 fps**,
  configurable) and record the actual mode obtained in the session metadata.
  Warn the user if the actual mode differs from the request. Motion thresholds
  are expressed in resolution-independent units.
- R6.8 Delete removes the sample record and its video clip.

### R7. Load and review existing data (P1 unless noted)
- R7.1 The user can open a data directory and browse existing samples,
  filtered by label, session (by name), author, date, and status
  (accepted/rejected).
- R7.2 Samples are shown in a table with a small path-preview thumbnail per
  row, with the ability to select one for a larger detail view (path image,
  metadata).
- R7.3 The user can change a sample's label, change its status
  (accepted <-> rejected, at any time, including after the session has closed),
  and delete it.
- R7.4 Per-label counts of accepted samples are shown (progress toward
  ~1,000 each).
- R7.5 **(P2)** Fullscreen view of a sample with the ability to scrub back and
  forth through its video frames, with the path overlaid.
- R7.6 Edits persist immediately and safely (see R6.4).

## 4. Non-Functional Requirements

- N1. **Shared code**: vision and motion detection live in a shared Python
  package used by both this app and the inference pipeline; the app contains
  no private copy.
- N2. **Throughput**: a capture cycle takes about the gesture duration plus the
  countdown, with no blocking dialogs.
- N3. **Responsiveness**: the live view runs at the camera's frame rate, with
  no dropped frames severe enough to corrupt tracking.
- N4. **Platform**: macOS and Linux supported. Windows is best effort (e.g.
  via WSL2, noting that WSL2 does not expose webcams by default); not tested.
- N5. **Offline testability**: the shared vision and motion code takes frames
  or position data as input, so it can be tested without a live camera, using
  saved video files or synthetic `(x, y, t)` data. Stored video snippets can
  double as regression fixtures.

## 5. Out of Scope (for now)

- Classifier training and evaluation (including any mirroring of
  left-handed samples; stored data is never mirrored).
- Action triggering.
- Multi-user concurrent access to one dataset.
- Storing the *discarded* (too long / too small) segments.
- A separate record-then-label workflow.

## 6. Decisions Log

| Topic | Decision |
|---|---|
| Labeling workflow | Label-first rapid capture only; relabel in review |
| Capture pacing | Countdown (default 3 s, configurable), then ready |
| Acceptance | Auto-accept; the user intervenes to reject |
| Pause | Escape or mouse click; resume continues the countdown |
| Input | Keyboard shortcuts and on-screen buttons |
| Stored data | Raw timestamped positions; no derived vectors |
| Label set | Shared project config, editable in the app |
| Settings during a session | Locked; new session to change |
| Calibration | Click the tip; manual sliders; motion tuning screen |
| Rejected samples | Kept with status `rejected`; delete is separate |
| Detector-discarded segments | Not stored |
| Handedness | Stored with sample/session; training handles it |
| Platforms | macOS, Linux; Windows best effort |
| Video snippets | Capture in P1; viewer/scrubbing in P2 |
| Data sharing | Self-contained sessions; merge command |
| Spell list | Dummy entries until teammates decide |
| Display mirroring | Dropped; track handedness in metadata only |
