# Data Collection Application - Design

> **Version** 3 | **Updated** 2026-11-01 | **Draft**

## 1. Overview

This document describes how the data collection application is built to meet
`requirements.md`: the technology, the components and their responsibilities,
the system flow, the details of each component, the interfaces, the data it
writes, and how it is tested. After reading it you will know how a gesture
travels from the camera to the dataset, which component does what, how
calibration and review fit in, and how a session is ended, loaded and resumed.
Requirement IDs (R1.1, N1, ...) refer to `requirements.md`. Related documents:
`docs/architecture.md` (system context), `lib/docs/design.md` (the shared
vision and motion components) and `docs/data-handling.md` (the dataset layout
and rules).

Training a gesture classifier needs about 1,000 samples of every gesture,
recorded by several people on different machines. That raises three problems:

- **Recording thousands of samples is tedious.** A paced capture cycle with
  auto-accept yields one gesture every few seconds.
- **Each setup differs: camera, light, background.** Each session is
  calibrated, and the settings are stored in the data.
- **Data must be consistent and combinable.** Vision code is shared, and
  sessions are self-contained so they can be merged.

## 2. The application

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

- **Web UI**: the pages the user sees: Setup, Calibrate, Record, Review and
  Browse. It displays live video and state, and sends the user's commands.
- **Application server**: serves the Web UI, exposes the HTTP interface,
  and pushes events. It routes requests to the services below and holds no
  logic of its own.
- **Capture engine**: the only owner of the camera. For every frame it runs
  the **tracker** (finds the wand tip) and the **segmenter** (decides when a
  gesture starts and ends), both from the shared library. It keeps the most
  recent seconds of frames, and publishes the annotated live image and the
  motion state.
- **Capture controller**: runs the rapid-capture cycle. It owns the countdown,
  decides when the engine is ready for a gesture, handles pause and resume, and
  turns each finished gesture into a saved sample.
- **Clip writer**: encodes the video clip of a sample in the background.
- **Calibration service**: camera listing and selection, color calibration from
  clicks, guided motion measurement, live settings and calibration profiles.
- **Session service**: starts, ends, lists, loads and resumes sessions, records
  their metadata and locks the settings.
- **Library**: lists, filters, edits and deletes samples. Review of a session
  and browsing of the dataset both use it. It also supplies counts and
  thumbnails.
- **Labels**: reads and edits the shared label list.
- **Dataset store**: the shared library component that reads and writes the
  data folder. Every write by any service goes through it.

## 4. System flow

### 4.1 How the components interact

```text
   Browser: Web UI (Setup | Calibrate | Record | Review | Browse)
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
  New session:
    Setup -> Calibrate -> Start session -> Capture <-> Review -> End session
                                              pause / resume

  Existing session (chosen on the Setup page):
    Open session -> Review                     (open or ended sessions)
                 -> Resume -> Capture <-> Review    (open sessions only)

  Browse: filter, inspect and edit samples across the dataset (not capturing)
```

### 4.3 One capture cycle

1. The user picks the active label and starts capturing. The controller starts
   the **countdown** (default 3 seconds) and the engine does not yet respond
   to motion.
2. The countdown reaches zero. The controller makes the engine **ready** and
   the UI tells the user to go. The ready state has no time limit.
3. The user performs the gesture. When the tip starts moving the engine
   reports **recording**; when the motion ends the segmenter reports the
   finished gesture, or a discard reason.
4. If the gesture was discarded the UI shows the reason, and a new countdown
   starts. No sample is created.
5. Otherwise the controller creates the sample: the tip positions, the active
   label, status `accepted`, and a video clip that runs from `preS` seconds
   before the gesture to `postS` seconds after it. A new **countdown starts
   immediately**, and the UI shows the sample's path image.
6. In the background the frames after the gesture are collected, the clip
   writer encodes the clip, and the sample is saved. The engine is not made
   ready until the countdown is over **and** the sample is saved, so a saved
   sample always precedes the next capture.
7. Back to step 2.

Because the countdown overlaps with saving, one cycle takes about the gesture
duration plus the countdown.

**Pause and review.** While capturing runs, the UI shows the latest result but
offers no review actions. Pressing Escape or clicking pauses capturing. If a
gesture is in progress, or its sample is still being saved, the pause takes
effect once that sample is saved, so review only ever sees saved samples.

Review then opens on the samples of the session, with the latest selected. The
user steps through them and can reject, restore, delete or relabel the selected
sample; each change is saved immediately. The user can also choose a different
active label for the next captures. Resuming continues the countdown, or
starts a fresh one if the pause came while the engine was ready.

### 4.4 Capture controller states

```text
             Start                 countdown over
  STOPPED ----------> COUNTDOWN ----and sample saved----> READY
     ^                  ^   |                               |   |
     |                  |   | pause                  pause  |   | motion
     | End session      |   v                               |   | starts
     | (any state)      | PAUSED <--------------------------+   v
     |                  |   |                           RECORDING
     |                  +---+ resume                          |
     |                  ^                                     | gesture ends
     |                  +-------------------------------------+
```

- **STOPPED**: not capturing. This is the state before the first start, after
  the session ends, and after a session is loaded for review. The live view
  still runs, and review is available when a session is loaded.
- **COUNTDOWN**: counting down; the engine ignores motion.
- **READY**: waiting for a gesture.
- **RECORDING**: a gesture is in progress. A pause request is held until the
  gesture ends and its sample is saved, then takes effect.
- **PAUSED**: countdown frozen and review open. Resuming from a pause during
  READY starts a fresh countdown; otherwise the remaining countdown continues.

### 4.5 Session lifecycle

```text
     start                        end
    -------> OPEN -------------------------------> ENDED
              | ^                                   |
              | | app closed, later reopened:       | review only
              +-+ the session stays open            v
```

- **Start** creates a session in the open state.
- A session stays open until the user ends it. Closing the application does not
  end it.
- **Load** lets the user pick a session from the dataset. An open session can
  be reviewed or resumed. An ended session can only be reviewed; it accepts no
  new samples, but its samples can still be edited in review.
- **Resume** continues capturing into the same session with the settings
  recorded in it, which stay locked. Calibration is skipped. The camera
  recorded in the session must be available, or the resume is refused.
- **End** is requested by the user. It records the end time and stops
  capturing.

### 4.6 Calibration flow

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
and keeps a rolling buffer of the latest `preS` + gesture + `postS` seconds of
raw frames for clips. After each frame it publishes:

- the annotated live image (tip marker and motion state drawn on it, or the
  detection mask when the user asks for it);
- the motion state: speed, moving or not, and the active thresholds.

Commands from the controller, calibration service and session service (ready
or not ready, change settings, open a camera) reach the engine through a queue
and take effect between frames. Settings cannot change while a session is
active; on resume, the engine takes its settings from the session record.

### 5.2 Capture controller

Implements the states in 4.4. It also:

- builds the sample from the segmenter's gesture and the buffered frames;
- gets the next sample number from the session service, which continues from
  the session's highest number;
- hands the sample to the clip writer and then the dataset store, in that
  order (a clip is complete before the sample that refers to it);
- holds a pause request until the sample in progress is saved, then opens
  review;
- tracks the count of accepted samples per label for the live view.

### 5.3 Clip writer

Encodes the sample's frames to an H.264 MP4 file on a background thread, using
a temporary file that is renamed when complete. If encoding fails the sample is
still saved, with no clip, and the user is told. Nothing else in the
application depends on a clip existing.

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

- **Start**: validates the author and handedness, records the session name the
  author chose, resolves the settings (see `docs/architecture.md`), and writes
  `session.json` with the camera's identifier and actual mode, the full vision
  and motion settings, the clip padding and a highest sample number of zero. It
  then locks the settings.
- **End**: only when the user asks. It records `endedAt` and stops capturing.
  Closing the application leaves the session open.
- **List**: the sessions in the data folder, with name, author, start time,
  sample count, and whether each is open or ended.
- **Load for review**: any session. It opens review on the session's samples
  and does not start capturing.
- **Resume**: only open sessions. It opens the camera recorded in the session,
  identified by its stored device identifier. If that device is not among the
  available cameras, because it is unplugged or the session was recorded with
  another machine's camera, the resume is refused and the reason is shown. It
  then applies the settings from the session record and locks them. If the
  camera delivers a different mode than the one recorded, the app warns the
  user (R6.7) but continues.
- **Sample numbers**: it supplies each new sample's number as the next one after
  the larger of the session's `highestSampleNumber` and the highest number in
  the samples file, and updates `highestSampleNumber` when the sample is saved.

### 5.6 Library

Keeps an in-memory index of sample summaries, built when a data folder is
opened and updated on every change. It answers filtered and paged queries by
label, session, author, date and status; supplies per-label counts of accepted
samples; and applies label changes, status changes and deletions through the
dataset store. Review is the library's listing for one session in capture
order, with the selected sample tracked by the UI. Edits are allowed in any
session, open or ended. Thumbnails are generated on demand by the shared path
renderer and cached in the operating system's cache location.

A missing clip never blocks listing, filtering or editing. The sample's
details state whether it has a clip. For a sample without one, the detail view
hides the overlay mode and the video view and says why; the path-only image
and thumbnail are unaffected. A clip that has been removed from disk is
treated the same as one that was never recorded.

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

- **Setup**: camera list and previews; the new session form (author, session
  name, handedness, notes); the list of existing sessions, each with Review
  and, for open sessions, Resume.
- **Calibrate**: frozen-frame color calibration; sliders; motion tuning screen.
- **Record**: live view; countdown and state; active label; the latest
  sample's path image; counts. No review actions.
- **Review**: the session's samples with the selected sample's path image
  (path only or overlay) and its details; step, reject, restore, delete and
  relabel actions; a selector for the active label; Resume. Opens when
  capturing is paused or a session is loaded.
- **Browse**: filterable sample table with thumbnails; detail view; label,
  status and delete actions; per-label counts.

**Shortcuts** (defaults, configurable in `config/data-collection.yaml`; each is
also shown on its on-screen button):

| Key | Action |
|---|---|
| Esc | While capturing: pause. In review: resume |
| Left, Right | In review: previous or next sample |
| R | In review: reject the selected sample (again to accept it) |
| Backspace | In review: delete the selected sample |
| P | Switch path-only and overlay views |
| 1 to 9 | Capturing: set the active label. In review: relabel the sample |

While capturing, a mouse click anywhere pauses and opens review.

## 6. Interfaces

### 6.1 Event stream

| Event | Carries |
|---|---|
| `controller` | State, countdown remaining, active label, counts |
| `motion` | Speed, moving or not, thresholds (live, at frame rate) |
| `sample` | The latest sample: id, label, status, saved or saving, has clip |
| `discard` | Reason a gesture was discarded |
| `session` | Session started, loaded, resumed or ended |

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
| `GET /api/sessions` | List sessions, open and ended |
| `POST /api/sessions` | Start a session |
| `POST /api/sessions/{id}/load` | Load a session; `mode=review` or `resume` |
| `POST /api/sessions/current/end` | End the session |
| `GET /api/labels` | List labels |
| `POST /api/labels` | Add a label |
| `PATCH /api/labels/{id}` | Rename a label |
| `DELETE /api/labels/{id}` | Remove a label |
| `PUT /api/recording/label` | Set the active label |
| `POST /api/recording/start` | Start capturing |
| `POST /api/recording/pause` | Pause and open review |
| `POST /api/recording/resume` | Resume |
| `GET /api/samples` | List, with filters and paging |
| `GET /api/samples/{id}` | One sample's details |
| `PATCH /api/samples/{id}` | Change label or status |
| `DELETE /api/samples/{id}` | Delete a sample |
| `GET /api/samples/{id}/image` | Path image; `mode=path` or `overlay` |
| `GET /api/samples/{id}/thumbnail` | Thumbnail |
| `GET /api/samples/{id}/video` | Video clip (P2 viewer) |
| `GET /api/stats` | Accepted counts per label |

Requests that need a clip, namely the video and the overlay image, return
"not found" for a sample without one. A resume request is refused, with the
reason, when the session is ended or its camera is unavailable. The sample
listing filters by label, session, author, date and status.

### 6.3 Command line

| Command | Purpose |
|---|---|
| `wand-collect serve` | Start the application |
| `wand-collect export` | Write a consolidated file from data folders |
| `wand-collect merge` | Merge data folders into a target folder |
| `wand-collect check` | Run the consistency check |

Export, merge and check use the shared dataset store, work without a camera,
and follow the rules in `docs/data-handling.md`.

### 6.4 Application settings

Set in `config/data-collection.yaml`, with camel case keys:

| Key | Meaning | Default |
|---|---|---|
| `dataFolder` | Where datasets are stored | `data` |
| `server.host`, `server.port` | Where the app listens | local only, 8000 |
| `camera.index` | Preferred camera | 0 |
| `camera.width`, `.height`, `.fps` | Requested mode | 640, 480, 30 |
| `countdownS` | Countdown length | 3.0 |
| `clipPadding.preS`, `.postS` | Clip padding | 2.0, 2.0 |
| `endThresholdRatio` | End threshold as a fraction of start | 0.6 |
| `shortcuts` | Key bindings | as in 5.8 |

## 7. Data

Everything is stored as defined in `docs/data-handling.md`. The application
writes:

- `session.json` when a session starts, with `highestSampleNumber` updated each
  time a sample is saved and `endedAt` set when the user ends the session;
- one line in the session's sample file per captured gesture, and its clip,
  when it is saved; a resumed session keeps adding lines to the same file;
- a rewrite of the sample file for each label or status change; a deleted
  sample is removed from the file and its clip is deleted.

## 8. Testing

- **Capture controller**: driven by a fake clock and scripted gestures. Checks
  the sequence of states, auto-accept, discards, that a pause during a gesture
  or a save takes effect only once the sample is saved, resume in each state,
  and that the engine is never ready before the sample is saved.
- **Session service**: start, end, list and load; an ended session cannot be
  resumed but can be reviewed and edited; closing the application leaves a
  session open; resume is refused when the recorded camera is unavailable;
  sample numbers continue after a delete and after a resume.
- **Services**: against a temporary data folder, including settings locking,
  label rules, library queries, and samples whose clip is missing or removed.
- **Whole application**: the HTTP interface exercised with a recorded video in
  place of the camera: calibrate, start a session, replay a clip of gestures,
  pause, reject one in review, resume with another label, restart the
  application, resume the open session, and check the files on disk.
- **Manual**: a checklist for real cameras on macOS and Linux, including
  camera selection, the motion tuning screen and resuming a session.
- The shared library's tests are described in `lib/docs/design.md`.

## 9. Requirement coverage

| Requirement | Where addressed |
|---|---|
| R1 Setup and calibration | 4.6, 5.4, 6.2 |
| R2 Session management | 4.5, 5.5, 7, `docs/data-handling.md` |
| R2.6, R2.7 Load, resume, end | 4.5, 5.5, 6.2 |
| R2.5 Merge | 6.3, `docs/data-handling.md` |
| R3 Labels | 5.7 |
| R4 Recording | 4.3, 4.4, 5.1, 5.2 |
| R5 Review | 4.3, 5.6, 5.8 |
| R6 Storage | 5.3, 7, `docs/data-handling.md` |
| R7 Browse and review | 5.6, 5.8, 6.2 |
| N1 Shared code | 3, `lib/docs/design.md` |
| N2 Throughput | 4.3 |
| N3 Responsiveness | 5.1 |
| N4 Platform | `docs/notes.md` |
| N5 Offline testability | 8, `lib/docs/design.md` |
