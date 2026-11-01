# Data Collection Application - Requirements

Status: v3, reviewed and confirmed. Delivery phases: **P1** = needed for the
first usable release, **P2** = later phase.

## 1. Purpose

Record and label wand gestures to build the training dataset for the gesture
classifier (target: ~1,000 samples per gesture). The app must make high-volume
recording fast and must use the same vision and motion-detection code as the
inference pipeline so training and inference data are consistent.

## 2. Definitions

- **Gesture / label**: a named spell the classifier must recognize.
- **Sample**: one recorded gesture, bounded by idle at start and end.
- **Session**: one run of the app by one author, with settings locked at start.
- **Calibration**: the phase before a session where vision and motion settings
  are tuned against the live view.
- **Tip position**: midpoint of the ping pong ball in a frame, with the frame
  timestamp (output of the vision system).
- **Status**: each stored sample is either `accepted` or `rejected`.
  **Delete** is different: it removes the sample from the dataset entirely.

## 3. Functional Requirements

### R1. Calibration (P1)
- R1.1 Before starting a session, the user can enter a calibration view that
  shows the live camera feed, the vision mask/detection, and the detected tip.
- R1.2 The user can adjust vision settings (color filter range, etc.) and the
  motion-detection settings (idle/motion speed threshold, valid time window,
  minimum gesture size) and see the effect live.
- R1.3 A calibration can be saved as a named profile and reloaded later, so
  the user need not recalibrate from scratch (e.g. same room, same wand).
- R1.4 Calibration must cope with different lighting, backgrounds, small
  color differences between wands, and different laptop cameras.

### R2. Session management (P1)
- R2.1 Starting a session captures metadata: author, handedness
  (left/right), start timestamp, camera/device identifier, requested and
  *actual* frame resolution and frame rate, the full vision settings, and the
  full motion-detection settings (including time window and minimum size
  thresholds), and optional free-text notes (lighting, background, etc.).
- R2.2 **Settings are locked once the session starts.** To change any vision or
  motion setting the user must end the session and start a new one (via
  calibration). This guarantees every sample in a session was captured with
  identical settings, and lets us detect setting changes across sessions.
- R2.3 Session metadata is stored in its own file; each sample references it
  by session ID. It must be possible to consolidate all samples (with their
  session data) into a single file/dataset on demand.
- R2.4 Handedness is stored with the session and with each sample. Stored
  positions are never mirrored; any handling of handedness is deferred to
  training.

### R3. Gesture label management (P1)
- R3.1 The label set is user-editable: defined in a label list (config file)
  read at startup, and editable in the app (add, rename, remove). Exact UI is
  a design decision.
- R3.2 Labels are picked from the list; they cannot be free-typed at record
  time.
- R3.3 The initial list is dummy entries for development; the real spell list
  will be supplied later.

### R4. Recording and labeling (P1)
- R4.1 Two workflows:
  - **Label-first**: select a label, then record multiple samples, each
    automatically tagged with it.
  - **Record-then-label**: record a sample unlabeled, then assign a label
    during review.
- R4.2 Capture is automatic: the shared motion-detection subsystem segments
  samples using idle -> motion -> idle, with no key press. Segments that
  exceed the valid time window or are too small are **thrown away, not stored**;
  the user is notified that one was discarded.
- R4.3 The live view shows the camera feed, the detected tip, the current state
  (idle / motion), the active label, and a running count of accepted samples
  for that label.

### R5. Review of a captured sample (P1)
- R5.1 After each capture the app shows the wand path with direction cues
  (start/end markers or a color gradient). The user can switch between:
  - path only (color on black), and
  - path overlaid on one camera frame (e.g. the first frame of the sample).
- R5.2 The user marks the sample **accepted** or **rejected**. Rejected
  samples are kept in the dataset, with status `rejected`.
- R5.3 Accept/reject is available via keyboard shortcuts (usable one-handed)
  and on-screen buttons; shortcut keys are shown on the buttons.
- R5.4 The user can undo the most recent decision immediately.

### R6. Storage (P1 unless noted)
- R6.1 Each sample stores raw timestamped positions `(x, y, t)` per frame.
  Derived motion vectors are not stored; they are computed on load by the
  shared code.
- R6.2 Each sample also stores: label (or unlabeled), status, session ID,
  sample ID, capture timestamp, handedness, and frame resolution. Positions
  are stored in normalized coordinates (0 to 1) so different cameras are
  comparable; resolution is recorded as well. Real timestamps are always
  kept, because actual frame rates vary.
- R6.3 The output directory is user-specified (default provided). The file
  format and layout are defined in `design.md`; they must be directly loadable
  by the classification subsystem (Python/NumPy/PyTorch).
- R6.4 Writes are crash-safe: an accepted/rejected sample is on disk before the
  next capture starts, and a partial write never corrupts existing data. The
  same applies to later edits.
- R6.5 Path preview images are generated on demand, not stored in the dataset,
  and generation is fast. Thumbnails for browsing may be cached (derived data
  only, safe to delete).
- R6.6 **Video snippets (capture: P1, viewing: P2).** For each stored sample
  the app also saves the relevant video clip, from a few seconds before to a
  few seconds after the gesture, in a separate directory linked from the sample
  metadata. This is for debugging motion detection and classification.
  Capturing needs a rolling pre-roll buffer and a short post-roll. The pre/post
  duration is configurable. 
- R6.7 Camera defaults: request a common mode (**640x480 at 30 fps**,
  configurable) and record the actual mode obtained in the session metadata.
  Warn the user if the actual mode differs from the request. Motion thresholds
  are expressed in resolution-independent units.
- R6.8 Delete removes the sample record and its video clip.

### R7. Load and review existing data (P1 unless noted)
- R7.1 The user can open a data directory and browse existing samples,
  filtered by label, session, author, date, and status (accepted/rejected).
- R7.2 Samples are shown in a table with a small path-preview thumbnail per
  row, with the ability to select one for a larger detail view (path image,
  metadata).
- R7.3 The user can change a sample's label (including labeling unlabeled
  ones), change its status (accepted <-> rejected, at any time, including
  after the session has closed), and delete it.
- R7.4 Per-label counts of accepted samples are shown (progress toward
  ~1,000 each).
- R7.5 **(P2)** Fullscreen view of a sample with the ability to scrub back and
  forth through its video frames, with the path overlaid.
- R7.6 Edits persist immediately and safely (see R6.4).

## 4. Non-Functional Requirements

- N1. **Shared code**: vision and motion detection live in a shared Python
  package used by both this app and the inference pipeline; the app contains
  no private copy. Repository layout to be decided in `design.md`.
- N2. **Throughput**: record -> review -> accept takes a few seconds, with no
  blocking dialogs beyond the review step.
- N3. **Responsiveness**: the live view runs at the camera's frame rate, with
  no dropped frames severe enough to corrupt tracking.
- N4. **Platform**: macOS and Linux supported. Windows is best effort (e.g.
  via WSL2, noting that WSL2 does not expose webcams by default); not tested.
- N5. **Offline testability**: the shared vision and motion code takes frames
  or position data as input, so it can be tested without a live camera, using
  saved video files or synthetic `(x, y, t)` data (e.g. a synthetic circle
  yields a circular vector sequence; a stationary ball stays idle). Stored
  video snippets can double as regression fixtures.

## 5. Out of Scope (for now)

- Classifier training and evaluation (including any mirroring of
  left-handed samples; stored data is never mirrored).
- Action triggering.
- Multi-user concurrent access to one dataset.
- Storing the *discarded* (too long / too small) segments.

## 6. Design Items Deferred to `design.md`

- App form factor and GUI technology (the R7 table, thumbnails, and the P2
  scrubbing view may influence this).
- Shared code layout in the monorepo (e.g. a top-level `lib/` package).
- File format and directory layout for samples, sessions, labels, calibration
  profiles, and video clips; the single-file consolidation export.
- Time-window and minimum-size thresholds: defaults, config-file keys, units.
- Resampling to a fixed rate and mirroring for left-handed users, both done
  at training/inference time, not in this app.

## 7. Decisions Log

| Topic | Decision |
|---|---|
| Labeling workflows | Both label-first and record-then-label |
| Input | Keyboard shortcuts and on-screen buttons |
| Stored data | Raw timestamped positions; no derived vectors |
| Label set | User-editable list |
| Settings during a session | Locked; new session to change |
| Rejected samples | Kept with status `rejected`; delete is separate |
| Detector-discarded segments | Not stored |
| Handedness | Stored with sample/session; training handles it |
| Platforms | macOS, Linux; Windows best effort |
| Video snippets | Capture in P1; viewer/scrubbing in P2 |
| Spell list | Dummy entries until teammates decide |
| Display mirroring | Dropped; track handedness in metadata only |
| Calibration profiles, thumbnail cache, delete removes clip | Confirmed |
