# Data Collection Application - Design

Status: Draft v2. Requirement IDs (R1.1, N1, ...) refer to `requirements.md`.
System context is in `docs/architecture.md`; the shared vision and motion
components are in `lib/docs/design.md`; the dataset layout is in
`docs/data-storage.md`.

## 1. The challenge

Training a gesture classifier needs about 1,000 samples of every gesture,
recorded by several people on different machines. That raises three problems:

- **Recording thousands of samples is tedious.** A paced capture cycle with
  auto-accept yields one gesture every few seconds.
- **Each setup differs: camera, light, background.** Each session is
  calibrated, and the settings are stored in the data.
- **Data must be consistent and combinable.** Vision code is shared, and
  sessions are self-contained so they can be merged.

## 2. The application at a glance

A **local web application**. A Python program runs on the user's machine,
owns the camera, and serves a user interface that the user opens in a browser.
Nothing leaves the machine; the server accepts connections from this computer
only.

| Concern | Choice |
|---|---|
| Language | Python 3.11 or later |
| Vision and motion | The shared library (OpenCV, NumPy) |
| Server | FastAPI served by uvicorn |
| Live video | A continuous stream of JPEG images (MJPEG) |
| Live updates | An event stream (Server-Sent Events) |
| Browser UI | Preact with htm, vendored files, no build step |
| Video clips | H.264 in MP4 files |
| Configuration | YAML files, validated on load |
| Tooling | As defined in `docs/standards.md` |

The **event stream** is a one-way channel on which the server pushes small
messages to the browser as things happen, so the browser need not ask
repeatedly.

The camera is read by the Python program, not by the browser, so the same
processing runs for the app, for tests and for later inference.

## 3. Components

- **Web UI**: the pages the user sees: Setup, Calibrate, Record and Browse.
  It displays live video and state, and sends the user's commands.
- **Application server**: serves the Web UI, exposes the HTTP interface,
  and pushes events. It routes requests to the services below and holds no
  logic of its own.
- **Capture engine**: the only owner of the camera. For every frame it runs
  the **tracker** (finds the wand tip) and the **segmenter** (decides when a
  gesture starts and ends), both from the shared library. It keeps the most
  recent seconds of frames, and publishes the annotated live image and the
  motion state.
- **Capture controller**: runs the rapid-capture cycle. It owns the countdown,
  decides when the engine is ready for a gesture, turns each finished gesture
  into a sample, and handles pause and review actions on the latest sample.
- **Clip writer**: encodes the video clip of a sample in the background.
- **Calibration service**: camera listing and selection, color calibration from
  clicks, guided motion measurement, live settings and calibration profiles.
- **Session service**: starts and ends sessions, records their metadata and
  locks the settings.
- **Library**: browses, filters, edits and deletes existing samples, and
  supplies counts and thumbnails.
- **Labels**: reads and edits the shared label list.
- **Dataset store**: the shared library component that reads and writes the
  data folder. Every write by any service goes through it.

## 4. System flow

### 4.1 How the components interact

```text
   Browser: Web UI (Setup | Calibrate | Record | Browse)
        |  commands          ^ live video        ^ events
        v                    |                   |
   +--------------------- Application server ---------------------+
   +-----+-----------+-----------+-----------+-----------+--------+
         |           |           |           |           |
         v           v           v           v           v
   Calibration   Session     Capture      Library     Labels
   service       service     controller      |           |
         |           |           |           |           v
         |           |     +-----+-----+     |      config/labels.yaml
         |           |     |           |     |
         v           |     v           v     |
      +--------------+--+  Clip writer  |     |
      | Capture engine  |      |        |     |
      | tracker +       |      v        v     v
      | segmenter       |   +---------------------+
      +--------+--------+   |    Dataset store    |
               |            |  (shared library)   |
            Camera          +----------+----------+
                                       v
                                  Data folder
```

### 4.2 The user's journey

```text
  Setup --> Calibrate --> Start session --> Record <--> Review --> End session
  pick       click tip,    author, hand-    countdown,   latest      back to
  camera     tune motion   edness, notes;   gesture,     sample      Calibrate
                           settings lock    repeat

  Browse (any time outside a session): filter, inspect, edit, delete
```

### 4.3 One capture cycle

1. The user picks the active label and presses Start. The controller starts the
   **countdown** (default 3 seconds) and the engine does not yet respond to
   motion.
2. The countdown reaches zero. The controller makes the engine **ready** and the
   UI tells the user to go. The ready state has no time limit.
3. The user performs the gesture. When the tip starts moving the engine reports
   **recording**; when the motion ends the segmenter reports the finished
   gesture, or a discard reason.
4. If the gesture was discarded the UI shows the reason, and a new countdown
   starts. No sample is created.
5. Otherwise the controller creates the sample: the tip positions, the active
   label, status `accepted`, and a video clip that runs from `pre_s` seconds
   before the gesture to `post_s` seconds after it. A new **countdown starts
   immediately**, and the UI shows the sample's path image.
6. In the background the frames after the gesture are collected, the clip writer
   encodes the clip, and the sample is saved. The engine is not made ready until
   the countdown is over **and** the sample is saved, so a saved sample always
   precedes the next capture.
7. Back to step 2.

Because the countdown overlaps with saving, one cycle takes about the gesture
duration plus the countdown.

**Review.** At any point in steps 1 to 6 the user may act on the latest
sample: reject it, delete it, or change its label. If the sample is still being
saved, the action is applied as soon as it is saved. **Pausing** freezes the
countdown and keeps the engine from becoming ready, so the user can review
at leisure; resuming continues the countdown.

### 4.4 Capture controller states

```text
             Start                 countdown over
  STOPPED ----------> COUNTDOWN ----and sample saved----> READY
     ^                  ^   |                               |   |
     |                  |   | pause                  pause  |   | motion
     | Stop             |   v                               |   | starts
     | (any state)      | PAUSED <--------------------------+   v
     |                  |   |                           RECORDING
     |                  +---+ resume                          |
     |                  ^                                     | gesture ends
     |                  +-------------------------------------+
```

- **STOPPED**: not capturing. The live view still runs.
- **COUNTDOWN**: counting down; the engine ignores motion.
- **READY**: waiting for a gesture.
- **RECORDING**: a gesture is in progress. A pause request is held until the
  gesture ends and its sample is created, then takes effect.
- **PAUSED**: countdown frozen. Resuming from a pause during READY starts a
  fresh countdown; otherwise the remaining countdown continues.

### 4.5 Calibration flow

```text
  Pick camera -> Color calibration -> Motion tuning -> Save profile -> Session
                 freeze a frame,       live feed with    (optional)     start
                 click the tip,        motion indicator,
                 see mask; add more    speed, threshold
                 clicks or adjust      slider; optional
                 sliders               guided measurement
```

## 5. Component details

### 5.1 Capture engine

Runs on its own thread so slow requests never stall the camera (N3). It takes
frames from the camera at the requested mode, runs the tracker and segmenter,
and keeps a rolling buffer of the latest `pre_s` + gesture + `post_s` seconds of
raw frames for clips. After each frame it publishes:

- the annotated live image (tip marker and motion state drawn on it, or the
  detection mask when the user asks for it);
- the motion state: speed, moving or not, and the active thresholds.

Commands from the controller and calibration service (ready or not ready,
change settings, change camera) reach the engine through a queue and take effect
between frames. Settings cannot change while a session is active.

### 5.2 Capture controller

Implements the states in 4.4. It also:

- builds the sample from the segmenter's gesture and the buffered frames;
- hands the sample to the clip writer and then the dataset store, in that
  order (a clip is complete before the sample that refers to it);
- keeps the latest sample so review actions can be applied to it, queuing an
  action that arrives before the save completes;
- tracks the count of accepted samples per label for the live view.

### 5.3 Clip writer

Encodes the sample's frames to an H.264 MP4 file on a background thread, using
a temporary file that is renamed when complete. If encoding fails the sample is
still saved, with no clip, and the user is told.

### 5.4 Calibration service

- **Cameras**: lists the cameras and lets the user preview each one; the
  chosen camera is used for the session. Names may be unavailable (notably on
  macOS), so previews identify a camera.
- **Color calibration**: freezes a frame, receives clicks, asks the shared
  color calibrator for settings, and returns the result with the detection
  mask. Manual adjustments overwrite individual settings.
- **Motion tuning**: while the user holds the wand in front of the camera, the
  live view shows a clear motion/no-motion indicator, the current speed as a
  value and a short history graph with the start and end thresholds drawn on it.
  A slider moves the start threshold; the end threshold follows it at a fixed
  ratio (configurable). Numeric fields adjust the valid time window and minimum
  size. The guided measurement runs the shared motion calibrator and shows its
  proposal.
- **Profiles**: save, list, load and delete named settings, stored under
  `config/profiles/` on this machine.

### 5.5 Session service

On start it validates the author and handedness, resolves the settings (see
`docs/architecture.md`), and writes `session.json` with the camera's actual
mode, the full vision and motion settings and the clip padding. It then locks
the settings. On end it records `ended_at`.

### 5.6 Library

Keeps an in-memory index of sample summaries, built when a data folder is
opened and updated on every change. It answers filtered and paged queries by
label, session, author, date and status; supplies per-label counts of accepted
samples; and applies label changes, status changes and deletions through the
dataset store. Thumbnails are generated on demand by the shared path renderer
and cached in the operating system's cache location.

### 5.7 Labels

Reads the label list from `config/labels.yaml` and writes changes back to it.
Renaming changes only the display name. Removing a label that has samples is
refused. The list is re-read when the file changes, so teammates' updates
pulled from git appear without a restart.

### 5.8 Browser UI

Built with Preact and htm from vendored files, as ES modules with no build
step. The vendored files, with versions and sources, are listed in a
`VERSIONS.md` beside them. JavaScript and CSS follow the 80-column rule in
`docs/standards.md`.

- **Setup**: camera list and previews; session form (author, handedness,
  notes).
- **Calibrate**: frozen-frame color calibration; sliders; motion tuning screen.
- **Record**: live view; countdown and state; active label; the latest
  sample's path image; review actions; counts.
- **Browse**: filterable sample table with thumbnails; detail view; label,
  status and delete actions; per-label counts.

**Shortcuts** (defaults, configurable in `config/data-collection.yaml`; each is
also shown on its on-screen button):

| Key | Action |
|---|---|
| Esc | Pause or resume |
| R | Reject the latest sample (again to accept it) |
| Backspace | Delete the latest sample |
| P | Switch path-only and overlay views |
| 1 to 9 | Running: set the active label. Paused: relabel the latest sample |

A mouse click anywhere pauses, and a click on a review button also applies its
action.

## 6. Interfaces

### 6.1 Event stream

| Event | Carries |
|---|---|
| `controller` | State, countdown remaining, active label, counts |
| `motion` | Speed, moving or not, thresholds (live, at frame rate) |
| `sample` | The latest sample: id, label, status, saved or saving |
| `discard` | Reason a gesture was discarded |
| `session` | Session started or ended |

### 6.2 HTTP interface

| Endpoint | Purpose |
|---|---|
| `GET /api/stream` | Live video; `view=camera` or `view=mask` |
| `GET /api/events` | The event stream |
| `GET /api/cameras` | List cameras |
| `PUT /api/camera` | Choose the camera |
| `POST /api/calibration/freeze` | Freeze a frame |
| `POST /api/calibration/clicks` | Add clicked points; returns settings |
| `POST /api/calibration/measure` | Run the guided motion measurement |
| `GET /api/settings` | Current vision and motion settings |
| `PUT /api/settings` | Change settings (refused during a session) |
| `GET /api/profiles` | List profiles |
| `PUT /api/profiles/{name}` | Save a profile |
| `POST /api/profiles/{name}/load` | Load a profile |
| `DELETE /api/profiles/{name}` | Delete a profile |
| `POST /api/sessions` | Start a session |
| `POST /api/sessions/current/end` | End the session |
| `GET /api/labels` | List labels |
| `POST /api/labels` | Add a label |
| `PATCH /api/labels/{id}` | Rename a label |
| `DELETE /api/labels/{id}` | Remove a label |
| `PUT /api/recording/label` | Set the active label |
| `POST /api/recording/start` | Start capturing |
| `POST /api/recording/pause` | Pause |
| `POST /api/recording/resume` | Resume |
| `POST /api/recording/stop` | Stop capturing |
| `GET /api/samples` | List, with filters and paging |
| `GET /api/samples/{id}` | One sample's details |
| `PATCH /api/samples/{id}` | Change label or status |
| `DELETE /api/samples/{id}` | Delete a sample |
| `GET /api/samples/{id}/image` | Path image; `mode=path` or `overlay` |
| `GET /api/samples/{id}/thumbnail` | Thumbnail |
| `GET /api/samples/{id}/video` | Video clip (P2 viewer) |
| `GET /api/stats` | Accepted counts per label |

### 6.3 Command line

| Command | Purpose |
|---|---|
| `wand-collect serve` | Start the application |
| `wand-collect export` | Write a consolidated file from data folders |
| `wand-collect merge` | Merge data folders into a target folder |
| `wand-collect check` | Run the consistency check |

Export, merge and check use the shared dataset store, work without a camera,
and follow the rules in `docs/data-storage.md`.

### 6.4 Application settings

Set in `config/data-collection.yaml`:

| Key | Meaning | Default |
|---|---|---|
| `data_folder` | Where datasets are stored | `data` |
| `server.host`, `server.port` | Where the app listens | local only, 8000 |
| `camera.index` | Preferred camera | 0 |
| `camera.width`, `.height`, `.fps` | Requested mode | 640, 480, 30 |
| `countdown_s` | Countdown length | 3.0 |
| `clip_padding.pre_s`, `.post_s` | Clip padding | 2.0, 2.0 |
| `end_threshold_ratio` | End threshold as a fraction of start | 0.6 |
| `shortcuts` | Key bindings | as in 5.8 |

## 7. Data

Everything is stored as defined in `docs/data-storage.md`. The application
writes:

- `session.json` when a session starts, updated when it ends;
- one sample file per captured gesture, and its clip, when it is saved;
- updates to a sample file for each label or status change; the clip is removed
  with a deleted sample.

## 8. Testing

- **Capture controller**: driven by a fake clock and scripted gestures. Checks
  the sequence of states, auto-accept, discards, pause and resume in every
  state, a review action arriving before the save finishes, and that the engine
  is never ready before the sample is saved.
- **Services**: against a temporary data folder, including settings locking,
  label rules and library queries.
- **Whole application**: the HTTP interface exercised with a recorded video in
  place of the camera: calibrate, start a session, replay a clip of gestures,
  reject one, and check the files on disk.
- **Manual**: a checklist for real cameras on macOS and Linux, including
  camera selection and the motion tuning screen.
- The shared library's tests are described in `lib/docs/design.md`.

## 9. Requirement coverage

| Requirement | Where addressed |
|---|---|
| R1 Setup and calibration | 4.5, 5.4, 6.2 |
| R2 Session management | 5.5, 7, `docs/data-storage.md` |
| R3 Labels | 5.7 |
| R4 Recording | 4.3, 4.4, 5.1, 5.2 |
| R5 Review | 4.3, 5.2, 5.8 |
| R6 Storage | 5.3, 7, `docs/data-storage.md` |
| R7 Browse and review | 5.6, 5.8, 6.2 |
| N1 Shared code | 3, `lib/docs/design.md` |
| N2 Throughput | 4.3 |
| N3 Responsiveness | 5.1 |
| N4 Platform | `docs/notes.md` |
| N5 Offline testability | 8, `lib/docs/design.md` |
| R2.5 Merge | 6.3, `docs/data-storage.md` |
