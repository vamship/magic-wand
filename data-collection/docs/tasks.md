# Data Collection Application - Tasks

> **Version** 1 | **Updated** 2026-11-01 | **Draft**

## 1. Overview

This document breaks the data collection application into tasks. Each task
names its branch, its status, the tasks it depends on, and the requirements and
design sections it implements. After reading it you will know what has to be
built, in what order the pieces depend on each other, and where each piece is
specified.

The work covers the shared library (`wand-core`), which the application and
later the classifier use, and the data collection application itself.

## 2. How to read this document

**Status values.** Each task is `Not started`, `In progress` or `Completed`.

**Branches.** Each task is done on its own branch, named as shown, and merged
after review (`docs/standards.md`).

**Definition of done.** Every task is complete only when:

- `uv run ruff format` and `uv run ruff check` report nothing to fix;
- the task's tests pass with `uv run pytest`;
- every new dependency is declared in the relevant `pyproject.toml`, and
  `uv.lock` is up to date;
- lines in code and text are within 80 columns, and names follow the naming
  standards;
- the behavior matches the approved design. A needed change to the design is
  made on a branch of its own first.

**References.** Short names are used for documents:

- **Req**: `data-collection/docs/requirements.md`
- **DC**: `data-collection/docs/design.md`
- **Lib**: `lib/docs/design.md`
- **DH**: `docs/data-handling.md`
- **Arch**: `docs/architecture.md`

**Order.** A task can start when the tasks it depends on are complete. Tasks
with no dependency between them can be done in parallel. A sensible order is
the foundation and spike tasks first, then the library, then the application,
then the Web UI, then verification.

## 3. Summary

| ID | Task | Status |
|---|---|---|
| D0 | Project documents | Completed |
| D1 | Requirements | Completed |
| D2 | Design | Completed |
| D3 | Task list | In progress |
| F1 | Workspace and tooling | Not started |
| F2 | Configuration and settings models | Not started |
| S1 | H.264 encoding spike | Not started |
| L1 | Frame sources | Not started |
| L2 | Tracker | Not started |
| L3 | Segmenter | Not started |
| L4 | Vector builder | Not started |
| L5 | Path renderer | Not started |
| L6 | Color calibrator | Not started |
| L7 | Motion calibrator | Not started |
| L8 | Dataset store: formats and safe writes | Not started |
| L9 | Dataset store: sessions and samples | Not started |
| L10 | Dataset store: check, export and load | Not started |
| L11 | Dataset store: merge | Not started |
| A1 | Application State | Not started |
| A2 | Application Server | Not started |
| A3 | Capture Engine | Not started |
| A4 | Live video stream | Not started |
| A5 | Calibration Service | Not started |
| A6 | Label Service | Not started |
| A7 | Clip Writer | Not started |
| A8 | Sample Library | Not started |
| A9 | Session Service | Not started |
| A10 | Capture Controller | Not started |
| A11 | Command-line tools | Not started |
| U1 | Web UI shell | Not started |
| U2 | Setup page | Not started |
| U3 | Calibrate page | Not started |
| U4 | Record page | Not started |
| U5 | Review page | Not started |
| U6 | Browse page | Not started |
| U7 | Scrubbing view (P2) | Not started |
| V1 | Whole-application test | Not started |
| V2 | Real-camera testing | Not started |
| V3 | Motion threshold tuning | Not started |

## 4. Documentation tasks

### D0 Project documents

- **Branch**: merged (`docs/*`)
- **Status**: Completed
- **Work**: Architecture, data handling, standards, glossary, notes, and the
  shared library design.

### D1 Requirements

- **Branch**: merged (`docs/requirements`)
- **Status**: Completed
- **Work**: `data-collection/docs/requirements.md`, Version 7, approved.

### D2 Design

- **Branch**: merged
- **Status**: Completed
- **Work**: `data-collection/docs/design.md`, Version 6, approved.

### D3 Task list

- **Branch**: `docs/tasks`
- **Status**: In progress
- **Work**: This document.

## 5. Foundation tasks

### F1 Workspace and tooling

- **Branch**: `chore/workspace`
- **Status**: Not started
- **Depends on**: none
- **Requirements**: N1, N4
- **Design**: Arch 5; `docs/standards.md` 2
- **Work**: Create the root `pyproject.toml` as a uv workspace with `lib` and
  `data-collection` as members, and the root lock file. Configure ruff (line
  length 80, line-length rule on) and pytest once at the root. Create both
  packages with their own `pyproject.toml`, `src` and `tests` folders. The
  application declares the shared library as a workspace dependency and a
  `wand-collect` command. Add the `.gitignore` entries for `data/`,
  `config/profiles/` and `config/*.local.yaml`.
- **Done when**: `uv sync`, `uv run pytest` and both ruff commands succeed on a
  clean checkout, on macOS and Linux.

### F2 Configuration and settings models

- **Branch**: `feat/config`
- **Status**: Not started
- **Depends on**: F1
- **Requirements**: R3.4, R6.7
- **Design**: Arch 4.3; Lib 6, 8.2; DC 5.4
- **Work**: Create the `config/` folder with `labels.yaml` (dummy labels),
  `vision.yaml`, `motion.yaml` and `data-collection.yaml`. Build the vision,
  motion and application settings models with the defaults in the designs and
  validation. Build the loader: read YAML, convert camel case keys to snake
  case, apply the local override, and write YAML back with the reverse
  conversion. Provide the same key conversion for JSON, for the dataset store.

### S1 H.264 encoding spike

- **Branch**: `chore/h264-spike`
- **Status**: Not started
- **Depends on**: F1
- **Requirements**: R6.6, R6.9
- **Design**: DC 4.8
- **Work**: Confirm that the chosen encoder produces H.264 MP4 files on macOS
  and Linux and that a browser plays them. If not, evaluate the fallbacks (the
  OpenCV writer, or MJPEG in AVI) and record the decision and any design change
  in `docs/notes.md` through its own branch.
- **Done when**: a script encodes a sample list of frames on both platforms and
  the findings are written down.

## 6. Shared library tasks

### L1 Frame sources

- **Branch**: `feat/frame-sources`
- **Status**: Not started
- **Depends on**: F1
- **Requirements**: R1.1, R6.7, N3, N5
- **Design**: Lib 5
- **Work**: A video-file source with the file's own timestamps and a camera
  source that requests a mode, timestamps frames at grab time, and reports the
  mode it actually got. Camera listing with index, name when available, and
  supported modes when known.
- **Done when**: a recorded clip replays with the expected timestamps.

### L2 Tracker

- **Branch**: `feat/tracker`
- **Status**: Not started
- **Depends on**: F2
- **Requirements**: R1.2, R1.7, N1, N5
- **Design**: Lib 6, 13
- **Work**: The tracker pipeline and the vision settings, including the hue
  range on a circle so red and orange work. Build the synthetic-video
  generator (a colored disk moving along known paths, with noise and varied
  backgrounds) and use it in the tests.
- **Done when**: recovered centers match the generated paths within a small
  tolerance, including colors that cross the hue wrap-around.

### L3 Segmenter

- **Branch**: `feat/segmenter`
- **Status**: Not started
- **Depends on**: F2
- **Requirements**: R4.5, N1, N5
- **Design**: Lib 8, 13
- **Work**: The segmenter state machine and motion settings: smoothing,
  hysteresis, hold time, valid window, minimum size, tracking loss, the on and
  off switch, and the per-frame speed and moving output.
- **Done when**: synthetic position streams give one gesture for a circle,
  nothing for a still tip or for tremor, each discard reason where expected,
  and no split when a pause is shorter than the hold time.

### L4 Vector builder

- **Branch**: `feat/vectors`
- **Status**: Not started
- **Depends on**: F1
- **Requirements**: R6.1, N1
- **Design**: Lib 10; Arch 4.2
- **Work**: Convert a gesture's positions to displacement, elapsed time and
  speed per step, in frame-heights.

### L5 Path renderer

- **Branch**: `feat/path-renderer`
- **Status**: Not started
- **Depends on**: F1
- **Requirements**: R5.2, R6.5
- **Design**: Lib 11
- **Work**: Draw a gesture's path with a start-to-end color gradient and end
  markers, on black or over a supplied frame.
- **Done when**: both modes render a sample path quickly, with a basic image
  comparison test.

### L6 Color calibrator

- **Branch**: `feat/color-calibrator`
- **Status**: Not started
- **Depends on**: L2
- **Requirements**: R1.2, R1.7
- **Design**: Lib 7
- **Work**: Derive vision settings from clicked points: circular hue average,
  spread, margins, tolerance, extra clicks, and the report of other regions
  the settings also match.
- **Done when**: on synthetic frames the derived settings let the tracker find
  the disk and little else.

### L7 Motion calibrator

- **Branch**: `feat/motion-calibrator`
- **Status**: Not started
- **Depends on**: L3
- **Requirements**: R1.5
- **Design**: Lib 9
- **Work**: Propose motion thresholds from a still period and a waving period.
- **Done when**: synthetic still and waving streams give thresholds in a
  sensible order.

### L8 Dataset store: formats and safe writes

- **Branch**: `feat/dataset-formats`
- **Status**: Not started
- **Depends on**: F2
- **Requirements**: R6.1 to R6.4, R2.3
- **Design**: DH 4 to 6, 9; Lib 12
- **Work**: Session and sample models, identifiers, JSON and JSON Lines
  reading and writing with the key conversion, the replace, append and delete
  write routines, the handling of an incomplete last line, and the cleanup of
  leftover files at open.
- **Done when**: round trips pass, and simulated crashes (a leftover temporary
  file, a truncated last line) recover as described.

### L9 Dataset store: sessions and samples

- **Branch**: `feat/dataset-operations`
- **Status**: Not started
- **Depends on**: L8
- **Requirements**: R2.1, R2.3, R2.4, R2.7, R6.2, R6.8, R7.3
- **Design**: DH 2 to 4; Lib 12
- **Work**: Create, update and end sessions; add, update and delete samples
  and their clips; the highest sample number and next-number rule; label id
  checks; and change notifications to subscribers.
- **Done when**: numbers continue after a delete and after reopening, and
  subscribers hear every change.

### L10 Dataset store: check, export and load

- **Branch**: `feat/dataset-export`
- **Status**: Not started
- **Depends on**: L9
- **Requirements**: R2.3, R6.3
- **Design**: DH 7.1, 7.2
- **Work**: The consistency check, the consolidated export with filters and
  several data folders, and loading a data folder or an export file into the
  same in-memory form.

### L11 Dataset store: merge

- **Branch**: `feat/dataset-merge`
- **Status**: Not started
- **Depends on**: L9
- **Requirements**: R2.5
- **Design**: DH 7.3
- **Work**: Merge source folders into a target: copy new sessions whole with
  their clips, skip identical ones, report conflicts, offer replace, never
  change a source, and an option to skip clips.
- **Done when**: tests cover new, identical and conflicting sessions.

## 7. Application tasks

### A1 Application State

- **Branch**: `feat/app-state`
- **Status**: Not started
- **Depends on**: F1
- **Requirements**: R2.2
- **Design**: DC 4.3
- **Work**: The state object with immutable snapshots, one owner per field,
  update under a lock, and listeners notified on change.
- **Done when**: tests show consistent snapshots under concurrent updates, one
  writer per field, and listener notification.

### A2 Application Server

- **Branch**: `feat/app-server`
- **Status**: Not started
- **Depends on**: A1, F2, L8
- **Requirements**: R6.3, N4
- **Design**: DC 4.2, 5.1, 5.3 (`serve`)
- **Work**: The web server on this computer only, static serving of the Web UI,
  startup (configuration, data folder, Capture Engine in preview), the event
  stream with per-browser queues (state snapshots and `motion` readings) and
  the `GET /api/state` endpoint, and the `wand-collect serve` command. Add the
  run instructions to the README.

### A3 Capture Engine

- **Branch**: `feat/capture-engine`
- **Status**: Not started
- **Depends on**: A1, L1, L2, L3
- **Requirements**: R4.5, R4.8, R6.6, R6.7, N3
- **Design**: DC 4.6
- **Work**: The camera thread: read settings from the state each frame, track,
  segment when armed, keep the JPEG ring buffer with range reads, publish the
  annotated and mask frames and the motion readings, accept arm, disarm and
  open-camera commands, and write the camera in use to the state.

### A4 Live video stream

- **Branch**: `feat/live-stream`
- **Status**: Not started
- **Depends on**: A2, A3
- **Requirements**: R1.4, R4.8
- **Design**: DC 4.2
- **Work**: `GET /api/stream` with the camera and mask views: encode a frame
  only while a browser is watching, share one encoded frame between browsers,
  and skip to the newest frame for a slow browser.

### A5 Calibration Service

- **Branch**: `feat/calibration-service`
- **Status**: Not started
- **Depends on**: A1, A3, L6, L7, F2
- **Requirements**: R1.1 to R1.7, R2.2
- **Design**: DC 3.3, 4.4
- **Work**: The settings field of the state, camera listing and choice, frozen
  frame and click-based color calibration, manual changes, the motion tuning
  support, the guided measurement writing its proposal to the settings,
  profiles on disk, the refusal while a session is loaded for capture, and the
  endpoints in DC 5.2.

### A6 Label Service

- **Branch**: `feat/label-service`
- **Status**: Not started
- **Depends on**: A1, A8, F2
- **Requirements**: R3.1 to R3.3
- **Design**: DC 4.10
- **Work**: Read and write the label file keeping comments, write the labels
  to the state, validation, refusal to remove a label in use, re-reading when
  the file changes, and the label endpoints.

### A7 Clip Writer

- **Branch**: `feat/clip-writer`
- **Status**: Not started
- **Depends on**: S1
- **Requirements**: R6.6, R6.9
- **Design**: DC 4.8
- **Work**: Background H.264 encoding to a temporary file then rename, with a
  clear failure result.
- **Done when**: a failure leaves no partial clip.

### A8 Sample Library

- **Branch**: `feat/sample-library`
- **Status**: Not started
- **Depends on**: A1, L5, L9
- **Requirements**: R5.2, R6.5, R6.8, R6.9, R7.1 to R7.4
- **Design**: DC 4.9
- **Work**: The in-memory index, filtered and paged queries, edits and
  deletions through the dataset store, counts and samples revision written to
  the state, change notifications from the dataset store, path images,
  thumbnails with the cache outside the dataset, the overlay frame, handling
  of missing clips, and the sample endpoints.

### A9 Session Service

- **Branch**: `feat/session-service`
- **Status**: Not started
- **Depends on**: A1, A3, A5, L9
- **Requirements**: R2.1, R2.2, R2.6, R2.7
- **Design**: DC 3.2, 4.5
- **Work**: Start, end, list, load for review and resume. Resume checks the
  recorded camera and refuses if it is unavailable, hands the recorded settings
  to the Calibration Service and records the session in the state. Supply
  sample numbers. The session endpoints.
- **Done when**: an ended session cannot be resumed, closing the app leaves a
  session open, and numbering continues after a resume.

### A10 Capture Controller

- **Branch**: `feat/capture-controller`
- **Status**: Not started
- **Depends on**: A1, A3, A7, A9, L9
- **Requirements**: R4.1 to R4.7, R4.9, R5.6, R6.4
- **Design**: DC 3.4, 4.7
- **Work**: The state machine and its single message loop, the countdown, the
  arm and disarm commands, building a sample with a parallel save job (clip
  window, number, record, clip, write), discards, pause and resume with the
  pause held during a gesture, writing the capture state, countdown end time,
  active label, latest sample and last discard, and the recording endpoints.
- **Done when**: tests with a fake clock and scripted gestures cover the states
  in DC 7.

### A11 Command-line tools

- **Branch**: `feat/cli-tools`
- **Status**: Not started
- **Depends on**: L10, L11, A2
- **Requirements**: R2.3, R2.5
- **Design**: DC 5.3
- **Work**: The `export`, `merge` and `check` commands on top of the dataset
  store, working without a camera.

## 8. Web UI tasks

### U1 Web UI shell

- **Branch**: `feat/ui-shell`
- **Status**: Not started
- **Depends on**: A2
- **Requirements**: N2
- **Design**: DC 4.1
- **Work**: Vendor Preact and htm with a `VERSIONS.md`, the event stream
  client that keeps the latest state snapshot, the API client, page switching,
  the shortcut handling, and the 80-column rule for JavaScript and CSS.

### U2 Setup page

- **Branch**: `feat/ui-setup`
- **Status**: Not started
- **Depends on**: U1, A5, A9
- **Requirements**: R1.1, R2.1, R2.6
- **Design**: DC 4.1
- **Work**: Camera list and previews, the new session form, and the list of
  sessions with Review and Resume.

### U3 Calibrate page

- **Branch**: `feat/ui-calibrate`
- **Status**: Not started
- **Depends on**: U1, A4, A5
- **Requirements**: R1.2 to R1.6
- **Design**: DC 3.3, 4.1
- **Work**: The frozen frame with click-to-calibrate and the mask, vision
  sliders, the motion tuning screen (indicator, speed, history graph,
  threshold slider, numeric fields, guided measurement), and profiles.

### U4 Record page

- **Branch**: `feat/ui-record`
- **Status**: Not started
- **Depends on**: U1, A4, A10
- **Requirements**: R4.1, R4.8, R5.6
- **Design**: DC 4.1
- **Work**: Live view, state, local countdown from the end time, active label,
  the latest path image, discard notices, counts, and the pause behavior.

### U5 Review page

- **Branch**: `feat/ui-review`
- **Status**: Not started
- **Depends on**: U1, A8, A10
- **Requirements**: R4.7, R5.1 to R5.5
- **Design**: DC 3.4, 4.1
- **Work**: Step through the session's samples, path and overlay views,
  reject, restore, delete and relabel, the active label selector, Resume, the
  shortcuts and buttons, and the missing-clip behavior.

### U6 Browse page

- **Branch**: `feat/ui-browse`
- **Status**: Not started
- **Depends on**: U1, A8
- **Requirements**: R7.1 to R7.4, R6.9
- **Design**: DC 4.1
- **Work**: Filterable table with thumbnails, a detail view, actions, and
  counts, repeating queries when the samples revision changes.

### U7 Scrubbing view (P2)

- **Branch**: `feat/ui-scrubbing`
- **Status**: Not started
- **Depends on**: U6, A8
- **Requirements**: R7.5
- **Design**: DC 5.2 (video endpoint)
- **Work**: The video endpoint and a full-screen view that scrubs through a
  sample's frames with the path overlaid, available only when a clip exists.

## 9. Verification tasks

### V1 Whole-application test

- **Branch**: `feat/e2e-test`
- **Status**: Not started
- **Depends on**: A10, A11, U5
- **Requirements**: all P1 requirements, N2
- **Design**: DC 7
- **Work**: The scenario in DC 7: a recorded video in place of the camera;
  calibrate, start a session, replay gestures, pause, reject one in review,
  resume with another label, restart the application, resume the open session,
  and check the files and the state snapshots.

### V2 Real-camera testing

- **Branch**: `chore/camera-testing`
- **Status**: Not started
- **Depends on**: U6
- **Requirements**: N3, N4, R6.7
- **Design**: DC 7
- **Work**: Write the manual checklist (camera selection, calibration, motion
  tuning, a capture run, pause and review, resume, merge) and run it on macOS
  and Linux with real laptop cameras.

### V3 Motion threshold tuning

- **Branch**: `chore/tune-thresholds`
- **Status**: Not started
- **Depends on**: V2
- **Requirements**: R1.5, R4.5
- **Design**: Lib 8.2
- **Work**: Use real recordings to find good default values for the motion
  settings, update the defaults in `config/motion.yaml`, and update the
  starting values in the library design through its own branch.
