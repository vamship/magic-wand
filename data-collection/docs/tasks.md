# Data Collection Application - Tasks

> **Version** 6 | **Updated** 2026-11-04 | **Approved**

## 1. Overview

This document breaks the data collection application into tasks. Each task has
a title, a description, acceptance criteria and implementation notes, and it
gives its type, its dependencies, and the requirements and design sections it
implements. A task is written so that someone who has not seen the rest of the
project can implement it from the task text, going to the referenced documents
for exact definitions.

After reading it you will know what has to be built, how each piece is judged
to be done, the order in which the pieces depend on each other, and where each
piece is specified. Section 4 shows that every part of the approved design is
covered by at least one task.

The work covers the shared library (`wand-core`), which the application and
later the classifier use, and the data collection application itself.

## 2. How to use this document

### 2.1 Task format

Tasks follow the format in `docs/standards.md` section 1.1. Each task here
has a type, status, dependencies, requirements, design references, a
description, acceptance criteria and implementation notes. The description and
the acceptance criteria are binding; the implementation notes are suggestions.

- The **ID** of every task here starts with the component code `DC` (data
  collection), which makes it unique across the repository
  (`docs/standards.md` section 1.1).
- The **branch** of a task is named from its type, ID and title
  (`docs/standards.md` section 1.2). Task DC-L2, "Tracker", of type `feat` is
  developed on `feat/dc-l2-tracker`.
- The **definition of done** (`docs/standards.md` section 1.4) applies to every
  task.
- Each task is written with enough information for an independent agent to
  implement it successfully, using only the task and the documents it
  references (`docs/standards.md` section 1.1).
- Tasks with no dependency between them can be done in parallel.

### 2.2 References

Short names are used for documents:

- **Req**: `data-collection/docs/requirements.md`
- **DC**: `data-collection/docs/design.md`
- **Lib**: `lib/docs/design.md`
- **DH**: `docs/data-handling.md`
- **Arch**: `docs/architecture.md`

### 2.3 Technology and layout (suggested)

- Python 3.11 or later, managed with uv; packages in a `src` layout.
- Shared library `wand-core`, imported as `wand_core`, under `lib/src`. It uses
  `opencv-python-headless`, `numpy`, `pyyaml` and `pydantic`.
- Application `wand-collect`, imported as `wand_collect`, under
  `data-collection/src`. It uses `fastapi`, `uvicorn`, `av` (PyAV),
  `platformdirs` and `ruamel.yaml`, and `httpx` for tests.
- Suggested module layout:

```text
lib/src/wand_core/
  casing.py  settings.py  types.py  sources.py  render.py
  vision/tracker.py
  motion/segmenter.py  motion/vectors.py
  calibration/color.py  calibration/motion.py
  dataset/   models.py  fileio.py  store.py  check.py  export.py  merge.py
  testing/   synthetic.py          (synthetic video and position generators)

data-collection/src/wand_collect/
  cli.py  state.py  server.py  events.py  engine.py  controller.py
  clip_writer.py  services/{calibration,session,library,labels}.py
  static/  (index.html, style.css, app/, vendor/)
```

### 2.4 Shared types

Tasks use these names so independently built parts fit together. In Python the
fields are snake case; in JSON and YAML they are camel case
(`docs/standards.md`).

- **Position**: `time_s`, `horizontal`, `vertical`. Horizontal and vertical are
  fractions of the frame width and height (0 to 1, vertical down). `time_s` is
  seconds from the gesture's first position.
- **TipDetection**: `timestamp_s` (absolute, from the frame), `found`,
  `horizontal`, `vertical`, `radius` (in frame-heights). The last three are
  `None` when not found.
- **Gesture**: `positions` (list of Position), `start_timestamp_s` and
  `end_timestamp_s` (absolute timestamps of the first and last position),
  `frame_width`, `frame_height`.
- **Discard**: `reason` (`too_long`, `too_short`, `too_small` or
  `tracking_lost`) and `timestamp_s`.
- **SegmenterUpdate**: `speed` (frame-heights per second), `moving`, `state`
  (`idle`, `motion` or `waiting`), and `result` (None, a Gesture or a Discard).
- **VisionSettings**: `hue_center`, `hue_half_width`, `sat_min`, `sat_max`,
  `val_min`, `val_max`, `blur_size`, `cleanup_size`, `min_area`, `max_area`,
  `min_roundness` (Lib 6). Hue is in OpenCV units, 0 to 179.
- **MotionSettings**: `start_speed`, `end_speed`, `start_frames`, `end_hold_s`,
  `min_duration_s`, `max_duration_s`, `min_extent`, `lost_timeout_s`,
  `smoothing_frames` (Lib 8.2).
- **Session** and **Sample** records: the fields in DH 5.1 and 5.2.
- **StateSnapshot**: the fields of the Application State in DC 4.3: `session`
  (`id`, `name`, `role` of `capture` or `review`), `settings` (`vision`,
  `motion`, `profile`), `camera` (`device`, `index`, `requested` and `actual`
  modes), `capture` (`state`, and `countdown_ends_at` or `remaining_s`),
  `active_label`, `latest_sample`, `last_discard`, `counts`, `samples_revision`
  and `labels`.

### 2.5 HTTP conventions

- Request and response bodies are JSON with camel case keys. Timestamps are
  ISO 8601 with a UTC offset. Durations are seconds, with an `S` suffix.
- A command that succeeds returns status 200 or 204. Its effect appears in the
  next `state` event (DC 5.2).
- An error returns a non-2xx status and the body
  `{"error": {"code": "...", "message": "..."}}`. Codes: `invalid_request`
  (400), `not_found` (404), `session_active`, `no_session`, `session_ended`,
  `camera_unavailable`, `label_in_use` and `not_capturing` (all 409).

## 3. Summary

| ID | Task | Status |
|---|---|---|
| DC-D0 | Project documents | Completed |
| DC-D1 | Requirements | Completed |
| DC-D2 | Design | Completed |
| DC-D3 | Task list | In progress |
| DC-F1 | Workspace and tooling | Completed |
| DC-F2 | Configuration and settings models | Completed |
| DC-S1 | H.264 encoding spike | Completed |
| DC-S2 | Linux verification | Not started |
| DC-L1 | Frame sources | Completed |
| DC-L2 | Tracker | Completed |
| DC-L3 | Segmenter | Completed |
| DC-L4 | Vector builder | Completed |
| DC-L5 | Path renderer | Completed |
| DC-L6 | Color calibrator | Completed |
| DC-L7 | Motion calibrator | Completed |
| DC-L8 | Dataset store: formats and safe writes | Completed |
| DC-L9 | Dataset store: sessions and samples | Completed |
| DC-L10 | Dataset store: check, export and load | Completed |
| DC-L11 | Dataset store: merge | Completed |
| DC-A1 | Application State | Completed |
| DC-A2 | Application Server | Completed |
| DC-A3 | Capture Engine | Completed |
| DC-A4 | Live video stream | Completed |
| DC-A5 | Calibration Service | Completed |
| DC-A6 | Label Service | Completed |
| DC-A7 | Clip Writer | Completed |
| DC-A8 | Sample Library | Completed |
| DC-A9 | Session Service | Completed |
| DC-A10 | Capture Controller | Completed |
| DC-A11 | Command-line tools | Completed |
| DC-U1 | Web UI shell | Completed |
| DC-U2 | Setup page | Completed |
| DC-U3 | Calibrate page | Completed |
| DC-U4 | Record page | Completed |
| DC-U5 | Review page | Completed |
| DC-U6 | Browse page | Completed |
| DC-U7 | Scrubbing view (P2) | Completed |
| DC-V1 | Whole-application test | Completed |
| DC-V2 | Real-camera testing | In progress |
| DC-V3 | Motion threshold tuning | Not started |

## 4. Coverage of the design

Every part of the approved designs is assigned to at least one task.

**Data collection design (DC)**

| DC section | Tasks |
|---|---|
| 2.1, 2.2 Components | DC-A1 to DC-A11, DC-U1 |
| 3.1 Journey | DC-U1 to DC-U6, DC-A9, DC-A10 |
| 3.2 Session lifecycle | DC-A9, DC-A1, DC-L9 |
| 3.3 Calibration | DC-A5, DC-U3, DC-L6, DC-L7 |
| 3.4 Capture cycle | DC-A10, DC-A3, DC-A7, DC-U4, DC-U5 |
| 4.1 Web UI | DC-U1 to DC-U7 |
| 4.2 Application Server | DC-A2, DC-A4 |
| 4.3 Application State | DC-A1 |
| 4.4 Calibration Service | DC-A5 |
| 4.5 Session Service | DC-A9 |
| 4.6 Capture Engine | DC-A3 |
| 4.7 Capture Controller | DC-A10 |
| 4.8 Clip Writer | DC-A7, DC-S1 |
| 4.9 Sample Library | DC-A8 |
| 4.10 Label Service | DC-A6 |
| 4.11 Dataset Store | DC-L8 to DC-L11 |
| 5.1 Event stream | DC-A2, DC-U1 |
| 5.3 Command line | DC-A2 (serve), DC-A11 |
| 5.4 Application settings | DC-F2 |
| 6 Data | DC-L8, DC-L9, DC-A9, DC-A10 |
| 7 Testing | every task, DC-V1, DC-V2, DC-S2 |

**HTTP interface (DC 5.2)**

| Endpoints | Task |
|---|---|
| `/api/stream` | DC-A4 |
| `/api/events`, `/api/state` | DC-A2 |
| `/api/cameras`, `/api/camera` | DC-A5 |
| `/api/calibration/*`, `/api/settings` | DC-A5 |
| `/api/profiles*` | DC-A5 |
| `/api/sessions*` | DC-A9 |
| `/api/labels*` | DC-A6 |
| `/api/recording/*` | DC-A10 |
| `/api/samples*` except video | DC-A8 |
| `/api/samples/{id}/video` | DC-U7 |

**Library design (Lib) and data handling (DH)**

| Section | Tasks |
|---|---|
| Lib 5 Frame source | DC-L1 |
| Lib 6 Tracker and vision settings | DC-L2, DC-F2 |
| Lib 7 Color calibrator | DC-L6 |
| Lib 8 Segmenter and motion settings | DC-L3, DC-F2 |
| Lib 9 Motion calibrator | DC-L7 |
| Lib 10 Vector builder | DC-L4 |
| Lib 11 Path renderer | DC-L5 |
| Lib 12 Dataset store | DC-L8 to DC-L11 |
| DH 2, 3 Rules, data folder | DC-L8, DC-L9, DC-A8 (delete) |
| DH 4 Identifiers | DC-L9 |
| DH 5 File formats | DC-L8 |
| DH 6 Writing safely | DC-L8 |
| DH 7.1 Consistency check | DC-L10, DC-A11 |
| DH 7.2 Export | DC-L10, DC-A11 |
| DH 7.3 Merge | DC-L11, DC-A11 |
| DH 9 Versioning | DC-L8 |

**Requirements.** Each task lists the requirement IDs it implements. Between
them the tasks cover R1.1 to R7.6 and N1 to N5. R7.5 is P2 (task DC-U7).

## 5. Documentation tasks

### DC-D0 Project documents

- **Type**: docs
- **Status**: Completed
- **Description**: The architecture, data handling, standards, glossary, notes
  and the shared library design.

### DC-D1 Requirements

- **Type**: docs
- **Status**: Completed
- **Description**: `data-collection/docs/requirements.md`, Version 7, approved.

### DC-D2 Design

- **Type**: docs
- **Status**: Completed
- **Description**: `data-collection/docs/design.md`, Version 6, approved.

### DC-D3 Task list

- **Type**: docs
- **Status**: In progress
- **Description**: This document.

## 6. Foundation tasks

### DC-F1 Workspace and tooling

- **Type**: chore
- **Status**: Completed
- **Depends on**: none
- **Requirements**: N1, N4
- **Design**: Arch 5; `docs/standards.md` 2

**Description.** Create the code skeleton so every later task starts from a
working, linted, tested workspace. The repository becomes a single uv
workspace with two packages, `lib` (the shared library) and `data-collection`
(the application). Tooling is configured once at the root.

**Acceptance criteria.**

- [x] On a clean checkout on macOS, `uv sync` succeeds. (Linux is checked
      by DC-S2.)
- [x] `uv run pytest` runs and passes with at least one placeholder test in each
      package.
- [x] `uv run ruff format --check` and `uv run ruff check` pass. Ruff uses a
      line length of 80 and reports lines that are too long.
- [x] `uv run wand-collect --help` prints usage (no commands need to work yet).
- [x] The root `pyproject.toml` lists both packages as workspace members, and a
      single `uv.lock` is committed.
- [x] Each package declares `requires-python` as 3.11 or later and has a `src`
      folder and a `tests` folder.
- [x] `.gitignore` excludes `data/`, `config/profiles/` and
      `config/*.local.yaml`.

**Implementation notes.**

- Root `pyproject.toml`: a uv workspace with members `lib` and
  `data-collection`; `[tool.ruff]` with `line-length = 80`; lint rules including
  `E`, `F`, `I` (import order) and `N` (naming, which checks the snake case and
  constant rules); `[tool.pytest.ini_options]` with the test paths.
- The application depends on the library through the workspace
  (`wand-core = { workspace = true }` under `[tool.uv.sources]`).
- Declare only the dependencies you use now; later tasks add their own. Put
  development tools (`pytest`, `ruff`, `httpx`) in the development dependency
  group of the root.
- Define the `wand-collect` command in the application's `[project.scripts]`
  pointing to a `main` function in `cli.py` built with `argparse`.

### DC-F2 Configuration and settings models

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-F1
- **Requirements**: R3.4, R6.7
- **Design**: Arch 4.3; Lib 4, 6, 8.2; DC 5.4

**Description.** Create the `config/` folder and the code that reads and writes
configuration and settings. The vision settings, motion settings and
application settings are validated models with defaults. YAML and JSON keys are
camel case on disk and snake case in Python; the conversion happens in one
place.

**Acceptance criteria.**

- [x] `config/` contains `labels.yaml` (three dummy labels, each with an `id`
      and a `name`), `vision.yaml`, `motion.yaml` and `data-collection.yaml`,
      with comments explaining each key.
- [x] `vision.yaml` and `motion.yaml` default to the vision settings of Lib 6
      and the starting values in Lib 8.2. `data-collection.yaml` holds the keys
      and defaults of DC 5.4.
- [x] Loading a file returns a validated model with snake case attributes.
      Invalid values (for example a negative speed, or `endSpeed` above
      `startSpeed`) raise a clear error naming the key.
- [x] A local override (`<name>.local.yaml`) replaces keys of the file with the
      same prefix; keys it omits keep their values.
- [x] Saving a model writes camel case keys. Reading a saved file gives back an
      equal model.
- [x] A key conversion helper converts the keys of nested dictionaries and lists
      between camel and snake case, and leaves values untouched.
- [x] A function resolves the working settings in the order of Arch 4.3: the
      defaults and local override, then a profile when given.

**Implementation notes.**

- Use `pydantic` models in `wand_core/settings.py`. The helper lives in
  `wand_core/casing.py` and is reused by the dataset store (DC-L8).
- `hue_center` and `hue_half_width` are in OpenCV hue units (0 to 179) and
  describe an interval on a circle. A suggested default for an orange ball:
  `hue_center` 15, `hue_half_width` 10, `sat_min` 120, `val_min` 120.
- Dummy label ids are lowercase slugs, for example `spell_one`.
- Keep file reading separate from validation so both can be tested alone.

### DC-S1 H.264 encoding spike

- **Type**: chore
- **Status**: Completed
- **Depends on**: DC-F1
- **Requirements**: R6.6, R6.9
- **Design**: DC 4.8

**Description.** Find out whether the planned encoder produces H.264 MP4 files
that browsers play, on macOS, and fast enough to keep up. The result decides
how the Clip Writer (DC-A7) is built. Linux is checked by DC-S2.

**Acceptance criteria.**

- [x] A script encodes 150 frames of 640x480 at 30 fps to an MP4 file with PyAV,
      on macOS. (Linux is checked by DC-S2.)
- [x] The file plays in a `<video>` element in at least two browsers.
- [x] Encoding the 6-second clip takes well under 6 seconds.
- [x] If PyAV cannot encode H.264 on a platform, the fallbacks (the OpenCV
      writer with the `avc1` codec, or MJPEG in an AVI file) are tried and the
      outcome recorded. (PyAV worked on macOS; the fallbacks were tried
      anyway and are recorded.)
- [x] The findings and the chosen approach are written in `docs/notes.md`, which
      is an approved document, so the change goes through a version bump and
      review.

**Implementation notes.**

- Use `libx264`, pixel format `yuv420p`, and the `faststart` option so browsers
  can start playback early.
- Generate frames with random noise or moving shapes so the test reflects real
  compression work.
- Keep the script in the branch under a `spikes` folder; it need not be
  production quality.

**Outcome.** On macOS (Apple Silicon) PyAV `libx264` encoded the clip in 1.1 s
with `faststart`, and the file played in Safari and Chrome. The results,
the fallbacks and the PyAV and OpenCV library clash are in `docs/notes.md`.
The spike script is `data-collection/spikes/h264_spike.py`.

### DC-S2 Linux verification

- **Type**: chore
- **Status**: Not started
- **Depends on**: DC-S1
- **Requirements**: N4, R6.6, R6.9
- **Design**: DC 4.8, DC 7

**Description.** Linux is a supported platform, but the tasks above were
verified on macOS only. This task checks on Linux what was deferred, and
records the results. Steps 1 to 3 can be done any time after DC-S1 when a Linux
machine or container is available; step 4 needs DC-V2.

1. Workspace (DC-F1): on a clean Linux checkout, `uv sync`,
   `uv run ruff format --check`, `uv run ruff check`, `uv run pytest` and
   `uv run wand-collect --help` all succeed.
2. Encoding (DC-S1): run `data-collection/spikes/h264_spike.py` on Linux.
3. Playback (DC-S1): play the produced MP4 in a Linux browser.
4. Cameras (DC-V2): run the DC-V2 checklist with a real camera on Linux, and
   fill in its Linux column.

**Acceptance criteria.**

- [ ] The commands in step 1 succeed on Linux.
- [ ] PyAV's wheel on Linux can encode H.264 with `libx264`, and the 150-frame
      clip encodes in well under 6 seconds. If it cannot, the fallbacks
      named in DC-S1 are tried and the outcome is recorded.
- [ ] The MP4 plays in at least one Linux browser.
- [ ] The DC-V2 checklist has been run on Linux and its results recorded.
- [ ] The findings are written in `docs/notes.md` (a version bump and review),
      and problems found are recorded as follow-up tasks. If the chosen video
      approach does not work on Linux, DC-A7 is changed accordingly.

**Implementation notes.**

- Docker with a `python` or `ubuntu` image is enough for steps 1 and 2.
  Steps 3 and 4 need a Linux desktop with a camera.
- Camera names on Linux come from `/sys/class/video4linux/` (see DC-A5).

## 7. Shared library tasks

### DC-L1 Frame sources

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-F1
- **Requirements**: R1.1, R6.7, N3, N5
- **Design**: Lib 5

**Description.** Provide the objects that deliver video frames with
timestamps, so everything downstream runs the same on a live camera and on a
recorded file. A frame is an image (a NumPy array in BGR order) and a
timestamp in seconds that increases steadily. Also list the cameras on the
machine.

**Acceptance criteria.**

- [x] A video-file source yields every frame of a file in order. Timestamps
      start at 0, increase by the file's frame interval, and are monotonic.
- [x] A camera source takes a requested width, height and frame rate, opens the
      camera, and exposes both the requested mode and the mode the camera
      actually delivers.
- [x] A camera frame's timestamp is taken when the frame is grabbed, from a
      monotonic clock.
- [x] Opening a camera that cannot be opened raises a specific, documented
      error.
- [x] Listing cameras returns, for each one, an index, a name when the operating
      system provides one, a stable device identifier string, and the modes it
      supports when known. With no camera it returns an empty list without
      error.
- [x] All sources can be closed, and closing twice is safe.

**Implementation notes.**

- Define a small interface (open, read, close, frame size, nominal rate) that
  both sources implement, so tests and the Capture Engine (DC-A3) can substitute
  the video-file source for a camera.
- `cv2.VideoCapture` with the default backend. Grab then retrieve, taking the
  timestamp between the two.
- Camera names: on Linux read `/sys/class/video4linux/video<N>/name`; on macOS
  OpenCV gives none, so use the index. The device identifier is the name when
  known, otherwise `index:<N>`; it is what a session stores (DH 5.1).
- List cameras by trying indices 0 to 9. Probing a few common resolutions for
  supported modes is optional.
- Unit tests must not open real cameras: use the file source, and fake
  `VideoCapture` with a stand-in for the camera tests.

### DC-L2 Tracker

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-F2
- **Requirements**: R1.2, R1.7, N1, N5
- **Design**: Lib 6, 13

**Description.** Find the tip of the wand (the center of the colored ball) in a
single frame, given the vision settings. Also provide the generator of
synthetic test videos, which later tasks reuse.

The tracker steps are: smooth the frame; convert to HSV; mark pixels inside the
color range (the hue range is an interval on a circle, applied as two bands
when it crosses the red end); remove specks and fill small holes (open then
close); find connected regions; discard regions outside the allowed area range
or less round than `min_roundness`; pick the best remaining region, preferring
the one nearest the previous tip; report the center of its enclosing circle.

**Acceptance criteria.**

- [x] `process(frame, timestamp_s)` returns a TipDetection with the tip as
      fractions of the frame and the radius in frame-heights, or `found` false.
- [x] A synthetic disk moving along known paths is tracked with an average error
      under 1.5% of the frame height, and found in at least 95% of frames,
      including with noise and varied backgrounds and brightness.
- [x] A disk whose hue lies across the wrap-around (red) is found with a hue
      interval that straddles 0.
- [x] Specks below `min_area`, regions above `max_area`, and non-round regions
      are ignored. With two candidate regions, the one nearest the previous tip
      wins.
- [x] A frame with no ball returns `found` false.
- [x] `mask(frame)` returns the binary mask used for detection, for display.
- [x] Areas in the settings are fractions of the frame area, so the same
      settings work at different resolutions.

**Implementation notes.**

- Roundness is `4 * pi * area / perimeter^2`. `min_area` and `max_area` compare
  to the contour area divided by the frame area.
- Keep the tracker free of camera and file access: it takes a frame. Its
  previous-tip memory is internal state with a reset method.
- The synthetic generator (`wand_core/testing/synthetic.py`) renders a disk of a
  given color, radius and path over a background, with optional noise, and
  returns frames and ground-truth centers. Provide path builders for a circle, a
  line and a figure-eight. DC-L3, DC-L6, DC-V1 and the application tests reuse
  it.

### DC-L3 Segmenter

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-F2
- **Requirements**: R4.5, N1, N5
- **Design**: Lib 8, 13

**Description.** Watch the stream of tip detections and decide when a gesture
starts and ends. It reports, for every detection, the tip's speed and whether it
is moving; when a gesture ends, it reports the finished gesture or the reason it
was discarded. It runs one detection at a time and uses no future data, so the
same class serves live use later.

Behavior:

- Speed is the distance moved between consecutive smoothed positions divided by
  the time between them, in frame-heights per second. The horizontal fraction
  is multiplied by the frame's aspect ratio so both axes share one unit. A
  moving average of `smoothing_frames` positions smooths the stream.
- States: `idle`, `motion`, and `waiting` (after a discard, until the tip is
  idle again). Motion starts when the speed is at least `start_speed` for
  `start_frames` consecutive detections. Motion ends when the speed stays below
  `end_speed` for `end_hold_s`.
- On the end of motion, the gesture is valid if its duration is between
  `min_duration_s` and `max_duration_s` and its path extent (the diagonal of
  the bounding box of its positions, in frame-heights) is at least
  `min_extent`. Otherwise it is discarded as `too_short` or `too_small`.
- If motion lasts longer than `max_duration_s`, discard it as `too_long` at once
  and go to `waiting`. If the tip is not found for longer than
  `lost_timeout_s` during motion, discard it as `tracking_lost`.
- A gesture holds the detected (unsmoothed) positions from the detection just
  before motion began to the end of motion, with the idle-hold tail trimmed.
  Frames where the tip was not found are absent.
- The segmenter can be switched off. When off it still reports speed, `moving`
  and the state for display, but never reports a gesture or a discard, and it
  returns to `idle`.

**Acceptance criteria.**

- [x] A stationary tip stays idle and produces no result.
- [x] Tremor below `start_speed` produces no result.
- [x] A synthetic circle produces one gesture with the expected positions.
- [x] Each discard reason is produced by a matching input: too long, too short,
      too small, and a tip lost for too long.
- [x] A pause shorter than `end_hold_s` in the middle of a gesture does not
      split it.
- [x] After a discard, a new gesture is detected only after the tip is idle
      again.
- [x] Switched off, a moving tip gives speed and `moving` but no result.
- [x] Results do not depend on the camera's resolution or frame rate beyond the
      timestamps.

**Implementation notes.**

- Constructor arguments: the motion settings and the frame aspect ratio. A
  method applies new settings and resets the state.
- Test with generated `(time, horizontal, vertical)` streams, not video.
- Use a small enumeration for states and discard reasons; the reason strings
  are snake case values.

### DC-L4 Vector builder

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-F1
- **Requirements**: R6.1, N1
- **Design**: Lib 10; Arch 4.2

**Description.** Convert a gesture's stored positions into motion vectors: for
each pair of consecutive positions, the displacement (horizontal and vertical),
the time between them, and the speed. Distances are in frame-heights, so the
horizontal difference is scaled by the frame's aspect ratio. Vectors are never
stored; training and inference both call this function.

**Acceptance criteria.**

- [x] For `n` positions it returns `n - 1` vectors.
- [x] Displacements and speed are in frame-heights and frame-heights per second.
- [x] The same positions at different frame sizes with the same aspect ratio
      give the same vectors.
- [x] Fewer than two positions return an empty result; a zero time step does not
      divide by zero.

**Implementation notes.** Return NumPy arrays (one row per step with columns
`dx`, `dy`, `dt`, `speed`). Put it in `wand_core/motion/vectors.py`.

### DC-L5 Path renderer

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-F1
- **Requirements**: R5.2, R6.5
- **Design**: Lib 11

**Description.** Draw a gesture's path as an image, in two modes: the path
alone on a black background, or the path over a supplied camera frame. The path
is a polyline with a color gradient from start to end, with a marker at each
end so direction is clear.

**Acceptance criteria.**

- [x] Given positions, a size and a mode, it returns an image of that size.
- [x] The gradient makes the start and end distinguishable, and the markers are
      visible at thumbnail size (about 96x72) and at large size.
- [x] Overlay mode draws on a copy of the supplied frame, resized to the
      requested size, and never changes the input.
- [x] A one-position or empty gesture draws without error.
- [x] Rendering a typical gesture at 640x480 takes a few milliseconds.
- [x] Stored positions are drawn as they are, never mirrored.

**Implementation notes.** `cv2.polylines` and `cv2.circle` on a NumPy canvas;
build the gradient by drawing short segments with an interpolated color. Add a
helper that encodes an image to PNG bytes for the server.

### DC-L6 Color calibrator

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-L2
- **Requirements**: R1.2, R1.7
- **Design**: Lib 7

**Description.** Derive vision settings from points the user clicked on the
wand tip in a frame. The calibrator keeps the samples from every click, so more
clicks refine the result.

For each click it takes the pixels in a small disc around the point (radius
about 1% of the frame height, at least 3 pixels), converts them to HSV, and
computes: the typical hue as a circular average (hue wraps around), and the
spread of hue, saturation and brightness. Each range is the typical value plus
or minus a margin that is a multiple of the spread (the tolerance, adjustable)
with a minimum margin, so very uniform patches still allow for lighting
changes. It then runs the tracker on the frame with the new settings.

**Acceptance criteria.**

- [x] Given a frame and one or more points, it returns vision settings, the
      detection mask, and the tracker's detection of the tip.
- [x] On synthetic frames, the settings make the tracker find the disk, and find
      little else.
- [x] A red disk (hue near 0 or 179) gives a hue interval that straddles the
      wrap without special input from the caller.
- [x] Adding clicks widens the ranges to cover the new samples.
- [x] It reports how many other regions of the frame the mask also marks, so the
      user can tighten the tolerance or click a more distinctive spot.
- [x] Changing the tolerance changes the margins in the expected direction.
- [x] A click on a spot with no usable color (for example pure black) gives a
      clear error.

**Implementation notes.** Circular mean: average the unit vectors of the hue
angles (hue times 2 degrees). Suggested starting values: tolerance 2.5 times
the spread, minimum margins of about 8 hue units and 40 on saturation and
brightness. Reuse the tracker for the check run so the result is what the live
view will show.

### DC-L7 Motion calibrator

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-L3
- **Requirements**: R1.5
- **Design**: Lib 9

**Description.** Propose motion settings from two short measurements taken in
front of the camera: the tip held still, and the tip waved. The still period
reveals the speed noise from hand tremor and detector jitter. The waving period
shows the speeds of real gestures.

**Acceptance criteria.**

- [x] From still positions it computes the idle ceiling, a high percentile
      (about the 95th) of the measured speeds.
- [x] From waving positions it computes a typical gesture speed.
- [x] It returns `end_speed` as a multiple of the idle ceiling, and
      `start_speed` between that and the typical gesture speed, with
      `start_speed` greater than `end_speed`.
- [x] Synthetic still and waving streams give thresholds in that order, and
      noisier still data gives a higher `end_speed`.
- [x] Too little data, or waving no faster than the noise, gives a clear error.

**Implementation notes.** Compute speeds with the same smoothing as the
segmenter (reuse its function). Suggested: `end_speed` is 3 times the idle
ceiling, at least 0.05; `start_speed` is the geometric mean of `end_speed` and
the typical speed. The values are provisional; DC-V3 tunes them.

### DC-L8 Dataset store: formats and safe writes

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-F2
- **Requirements**: R6.1, R6.2, R6.3, R6.4, R2.3
- **Design**: DH 4, 5, 6, 9; Lib 12

**Description.** The lowest layer of the dataset store: the record models, the
file formats, and the crash-safe write routines. Everything that touches the
data folder uses these.

**Acceptance criteria.**

- [x] Models exist for the session record and the sample record with the fields
      in DH 5.1 and 5.2.
- [x] JSON files and the JSON Lines file are read and written as UTF-8, with
      camel case keys on disk and snake case in Python.
- [x] `dataset.json` carries a `formatVersion`. Opening a folder with a version
      the code does not know fails with a clear error.
- [x] The replace routine writes a temporary file in the same folder, flushes it
      to disk, renames it over the target, then flushes the folder.
- [x] The append routine writes a complete line and its newline in one write and
      flushes it.
- [x] Reading a samples file ignores a last line that lacks its newline or is
      not valid JSON.
- [x] Opening a data folder removes leftover temporary files and truncates an
      incomplete last line. Opening a missing folder creates it only when asked.
- [x] Simulated crashes pass: a leftover temporary file, and a truncated last
      line.
- [x] A round trip of a session and a sample gives equal records.

**Implementation notes.** Put the models in `dataset/models.py` and the file
routines in `dataset/fileio.py`. Use `os.replace` for the rename and `os.fsync`
on the file and on the directory. Position columns are `timeS`, `horizontal`
and `vertical` (DH 5.2). Generate crash tests by writing partial content, not
by killing processes.

### DC-L9 Dataset store: sessions and samples

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-L8
- **Requirements**: R2.1, R2.3, R2.4, R2.7, R6.2, R6.8, R7.3, R7.6
- **Design**: DH 2, 3, 4; Lib 12

**Description.** The operations on sessions and samples, with the identifier
and numbering rules, and change notifications.

Operations: create a session (a new folder under `sessions/` named by a random
UUID, with `session.json`, an empty samples file and a `videos` folder); update
and end a session (set `endedAt`); list sessions; read a session's samples;
add a sample (video clip first, then the sample line, then update
`highestSampleNumber`); update a sample's label or status (rewrite the file and
set `updatedAt`); delete a sample (rewrite the file without it, then remove its
clip); supply the next sample number.

**Acceptance criteria.**

- [x] Session ids are UUID version 4. Sample ids are `<session id>-<number>`
      with the number zero-padded to at least 4 digits.
- [x] The next sample number is one more than the larger of the session's
      `highestSampleNumber` and the highest number in the samples file. After a
      sample with the highest number is deleted, the next number is not reused.
- [x] Adding a sample appends exactly one line and updates
      `highestSampleNumber`. A crash between the two still gives the right next
      number.
- [x] Updating or deleting a sample rewrites the samples file atomically;
      deleting also removes the clip file, and a missing clip is not an error.
- [x] A sample whose `video` is empty, or whose clip file is absent, is read as
      having no clip.
- [x] A label must be a lowercase slug (letters, digits, underscore); anything
      else is rejected.
- [x] Every change (session written, sample added, updated, deleted) is reported
      to subscribers with the kind of change and the ids.
- [x] Ended sessions accept no new samples, but their samples can still be
      updated and deleted.

**Implementation notes.** `dataset/store.py`. Subscribers are plain callbacks
called after the change is on disk. Keep the store single-writer per data
folder (the application is the only writer); no file locking is required.
Samples files are small (about 3 MB per 1,000 samples), so reading a whole file
into memory is fine.

### DC-L10 Dataset store: check, export and load

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-L9
- **Requirements**: R2.3, R6.3
- **Design**: DH 7.1, 7.2

**Description.** Three read-oriented operations. The **consistency check**
reports problems without changing anything: leftover temporary files,
incomplete last lines, video clips with no sample, unsupported format versions,
and samples with an unknown label id (given the label list). Samples whose clip
is missing are listed as information, not errors. The **export** writes one
JSON Lines file in which each line is a sample record with its session record
embedded under `session`, optionally filtered, from one or more data folders,
and without video. The **load** reads either a data folder or an export file
into the same in-memory form, with filters, for the classifier.

**Acceptance criteria.**

- [x] The check returns a report with errors, warnings and information, and
      never writes.
- [x] Each problem listed in DH 7.1 is detected by a test folder built to have
      it.
- [x] Export filters by status, label, session, author and date range, and reads
      several folders.
- [x] Exporting and then loading an export file gives the same samples as
      loading the folders with the same filter.
- [x] Loaded samples expose positions, label, status, handedness and session
      data directly, as plain Python objects.

**Implementation notes.** `dataset/check.py` and `dataset/export.py`. Stream
the export line by line so large datasets do not need to fit in memory.

### DC-L11 Dataset store: merge

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-L9
- **Requirements**: R2.5
- **Design**: DH 7.3

**Description.** Combine one or more source data folders into a target folder.
Session folders the target lacks are copied whole, with their clips, keeping
all ids. A session present in both with identical content is skipped. A session
present in both with different content is a conflict: it is reported and the
target's copy stays, unless the caller asks to replace it with the source's.
Sources are only read. An option skips video clips.

**Acceptance criteria.**

- [x] New sessions are copied in whole; ids are unchanged.
- [x] Identical sessions are skipped; conflicting ones are reported and left
      alone by default, and replaced when asked.
- [x] Source folders are byte-for-byte unchanged after a merge.
- [x] With the skip option, clips are not copied and the merged samples still
      load, with no clip.
- [x] The result lists, per session, whether it was copied, skipped, replaced or
      in conflict.
- [x] No camera or running application is needed.

**Implementation notes.** `dataset/merge.py`. Decide "identical" by comparing
the session file and the samples file contents (a hash of each). Copy to a
temporary folder and rename into place so an interrupted merge leaves no
half-copied session.

## 8. Application tasks

### DC-A1 Application State

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-F1
- **Requirements**: R2.2
- **Design**: DC 4.3

**Description.** The shared record of the application's current state that
every component can read and the Web UI is updated from. It holds immutable
snapshots, has one owner per field, and notifies listeners on every change.

Fields and owners (DC 4.3): session (Session Service); settings, with the
loaded profile name (Calibration Service); camera (Capture Engine); capture
state with the countdown end time or remaining time, active label, latest
sample and last discard (Capture Controller); counts and samples revision
(Sample Library); labels (Label Service). Whether settings are locked is
derived: they are locked while the session is loaded for capture.

**Acceptance criteria.**

- [x] A reader gets a snapshot that is immutable and internally consistent.
      Reading is safe from any thread without the caller taking a lock.
- [x] An update names its owner and the fields; an owner writing a field it does
      not own is rejected.
- [x] An update builds a new snapshot, swaps it in under a lock, and notifies
      all listeners with the new snapshot, in order.
- [x] Concurrent updates from several threads never lose an update or expose a
      half-applied one (tested with threads).
- [x] The snapshot serializes to JSON with camel case keys, ready to send to a
      browser.
- [x] A helper says whether settings are locked for a given snapshot.
- [x] A new instance starts with no session, empty counts and labels, capture
      state `STOPPED`, and default settings.
- [x] Instances are independent: it is created once and passed in, never a
      module global.

**Implementation notes.** Frozen dataclasses for the snapshot and nested
fields; a mutex around the swap; listeners called one at a time in update order
(a small dispatcher keeps ordering if several threads update). `state.py`.
Listener callbacks must not block; the server's listener only enqueues.

### DC-A2 Application Server

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-A1, DC-F2, DC-L8
- **Requirements**: R6.3, N4
- **Design**: DC 4.2, 5.1, 5.3 (`serve`)

**Description.** The web server and the plumbing every service uses: static
files, startup, the event stream, the state endpoint, error handling, and the
`wand-collect serve` command.

**Acceptance criteria.**

- [x] `uv run wand-collect serve` starts the server on the host and port from
      `data-collection.yaml` (default `127.0.0.1:8000`) and serves the Web UI
      files at `/`.
- [x] If the configured host is not a loopback address, startup prints a clear
      warning.
- [x] Startup loads the configuration, opens (creating if needed) the data
      folder with the dataset store, loads the labels, and creates the
      Application State, services and Capture Engine in the right order. The
      engine runs in preview mode when a camera is available, and the server
      still starts when none is.
- [x] `GET /api/state` returns the current snapshot.
- [x] `GET /api/events` is a Server-Sent Events stream. A new connection first
      receives one `state` event with the current snapshot. Every later state
      change sends a `state` event. `motion` events carry the readings the
      Capture Engine publishes. A comment line is sent every 15 seconds as a
      heartbeat.
- [x] Each browser has its own bounded queue. If it falls behind, a waiting
      `state` event is replaced by the newer one (no snapshot is lost in
      effect), and old `motion` events are dropped.
- [x] A disconnected browser's queue is removed.
- [x] Errors follow section 2.5: unknown ids return 404, bad input returns 400,
      rule violations return 409 with a code.
- [x] Each service registers its own routes through a common mechanism, so later
      tasks add endpoints without editing the server core.
- [x] The README has instructions to install and run the application.

**Implementation notes.**

- FastAPI and uvicorn. Events: an async generator returning a streaming
  response with media type `text/event-stream`. The state listener runs on
  other threads, so it hands snapshots to each browser's queue with
  `loop.call_soon_threadsafe`.
- Format each event as `event: <name>` then `data: <json>` then a blank line.
- A router per service module. `create_app` takes the state and the services as
  arguments so tests can pass fakes and a video-file frame source.
- `cli.py` adds a `serve` subcommand with optional `--config` and
  `--data-folder` overrides.
- Test with the FastAPI test client and an event-stream reader.

### DC-A3 Capture Engine

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-A1, DC-L1, DC-L2, DC-L3
- **Requirements**: R4.5, R4.8, R6.6, R6.7, N3
- **Design**: DC 4.6

**Description.** The only owner of the camera. A thread runs a loop that turns
frames into tip detections and gestures, keeps recent frames for clips, and
publishes what the rest of the application needs.

For every frame the loop: reads the settings from the Application State and
applies them if they changed; grabs the frame; runs the Tracker; feeds the
detection to the Segmenter (always, so speed and `moving` are reported; the
Segmenter is armed only when told, so it emits results only then); adds the
frame to the ring buffer; draws the annotated frame; and publishes the frame
and the motion reading.

**Acceptance criteria.**

- [x] Commands arrive on a queue and take effect between frames: arm, disarm,
      open a camera (by index), and close.
- [x] Settings are read from the Application State at the start of each frame,
      and the Tracker and Segmenter are rebuilt when they changed. Segmenter
      state is reset when its settings change.
- [x] The ring buffer keeps JPEG-compressed frames with their timestamps for
      about `clipPadding.preS + maxDurationS + clipPadding.postS` seconds (about
      8 seconds at the defaults, around 10 MB). It returns the frames between
      two timestamps.
- [x] The latest annotated frame (tip marker and the idle or motion state drawn
      on it) and the latest mask frame are available, each with a frame number,
      and a caller can wait for a newer one.
- [x] A motion reading (timestamp, speed, moving, thresholds) is published for
      every frame.
- [x] When the Segmenter reports a gesture or a discard, or motion starts, a
      message is sent to a registered receiver (the Capture Controller).
- [x] After opening a camera, the engine writes the camera to the Application
      State: device, index, the requested mode and the actual mode, with the
      frame rate measured over the first couple of seconds.
- [x] If the camera cannot be opened, the camera field is cleared and the error
      is returned to the caller; the engine keeps running and can open another.
- [x] The engine accepts any frame source, so tests run it on a recorded video.
- [x] A slow consumer of the published frames never delays the camera loop.

**Implementation notes.**

- `engine.py`. One thread; use `queue.Queue` for commands and a
  `threading.Condition` plus a frame counter to publish frames. For the
  server's asynchronous code, expose a method that waits for the next frame in
  a worker thread or via the loop's thread-safe call.
- Annotations with OpenCV: a circle at the tip and a text label for the state.
  The mask view colors the mask white on black.
- Results to the controller: three message kinds (motion started, gesture,
  discard). The Segmenter's state moving from `idle` to `motion` is the
  trigger for motion started.
- Frame timing is measured from the timestamps, not assumed from the requested
  rate.

### DC-A4 Live video stream

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-A2, DC-A3
- **Requirements**: R1.4, R4.8
- **Design**: DC 4.2

**Description.** `GET /api/stream` returns the live video as MJPEG: a
never-ending response whose parts are JPEG images, which a browser shows in an
image element. A query parameter `view` chooses the annotated camera view
(`camera`, the default) or the detection mask (`mask`).

**Acceptance criteria.**

- [x] The response has media type `multipart/x-mixed-replace` with a boundary,
      and each part is a complete JPEG with its content type and length.
- [x] A frame is encoded only while at least one browser is connected, and one
      encoded frame is shared among browsers watching the same view.
- [x] A slow browser skips to the newest frame rather than falling behind.
- [x] Closing the connection stops the generator.
- [x] An unknown `view` returns 400. With no camera, the response sends a
      placeholder image instead of failing.
- [x] A test reads several parts from a stream fed by a recorded video and
      decodes each as an image.

**Implementation notes.** An async generator that waits for a frame newer than
the last one sent, encodes it with `cv2.imencode` at quality about 80, and
yields the multipart bytes. A 640x480 frame is about 30 to 50 KB. Check for a
client disconnect on each loop pass.

### DC-A5 Calibration Service

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-A1, DC-A3, DC-L6, DC-L7, DC-F2
- **Requirements**: R1.1, R1.2, R1.3, R1.4, R1.5, R1.6, R1.7, R2.2
- **Design**: DC 3.3, 4.4

**Description.** Prepares the settings for a session. It owns the Settings
field of the Application State: the working vision and motion settings and the
loaded profile name. It refuses every change while a session is loaded for
capture.

Functions and endpoints (JSON, section 2.5):

- Cameras: `GET /api/cameras` lists them (index, name, device identifier,
  modes) using the library; `PUT /api/camera` with the index asks the Capture
  Engine to open it.
- Settings: `PUT /api/settings` takes a partial change of vision and/or motion
  settings, validates it and writes the state. Manual adjustments use this.
- Color calibration: `POST /api/calibration/freeze` freezes the current frame
  and returns it as a JPEG. `POST /api/calibration/clicks` takes the clicked
  points (as fractions of the frame) and an optional tolerance; it calls the
  color calibrator on the frozen frame, writes the derived vision settings to
  the state, and returns the detection mask as a PNG data URL, the detected
  tip, and the number of other regions marked.
- Motion tuning: nothing extra for the live readings (the Capture Engine
  streams them). The end threshold follows the start threshold at
  `endThresholdRatio` when the Web UI sets only the start threshold: the
  endpoint computes it.
- Guided measurement: `POST /api/calibration/measure` with `phase` set to
  `still` or `wave` collects the tip positions for a fixed time (about 3
  seconds for still, 5 for wave) and returns when done. After both phases it
  calls the motion calibrator and writes the proposed thresholds to the motion
  settings.
- Profiles: `GET /api/profiles`, `PUT /api/profiles/{name}` (save the current
  settings), `POST /api/profiles/{name}/load` (set them from the profile) and
  `DELETE /api/profiles/{name}`, as YAML files in `config/profiles/`.
- Accepting recorded settings from the Session Service on resume (DC-A9), and
  writing them to the state.

**Acceptance criteria.**

- [x] Each endpoint behaves as described. Invalid settings return 400 with the
      key named.
- [x] While the Application State says the session is loaded for capture,
      settings changes, profile loads, color calibration and measurement return
      409 `session_active`.
- [x] Every settings change is visible in the next `state` event and the Capture
      Engine uses it on its next frame.
- [x] A click-based calibration on a synthetic frame makes the live tracker find
      the disk.
- [x] The still and wave measurement on synthetic positions yields settings with
      `start_speed` above `end_speed`.
- [x] Saved profiles survive a restart, contain a full set of vision and motion
      settings, and use camel case keys.
- [x] The working settings start from the resolved defaults (DC-F2), or a loaded
      profile.
- [x] Applying recorded settings from the Session Service works even though the
      session is not yet loaded for capture.

**Implementation notes.** `services/calibration.py`. Keep the frozen frame in
memory only. Run the measurement as a timed collection of the positions the
engine publishes (a short-lived subscription to its detections). The
`clicks` response may be built as JSON with the mask as a base64 PNG.

### DC-A6 Label Service

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-A1, DC-A8, DC-F2
- **Requirements**: R3.1, R3.2, R3.3
- **Design**: DC 4.10

**Description.** Manages the shared list of spell labels in
`config/labels.yaml`. It owns the Labels field of the Application State.

Endpoints: `POST /api/labels` (id and name), `PATCH /api/labels/{id}` (rename:
changes the display name only), `DELETE /api/labels/{id}`. The list itself is
read from the state.

**Acceptance criteria.**

- [x] At startup the labels are read from the file and written to the state.
- [x] Adding a label requires a unique lowercase-slug id and a non-empty name;
      otherwise 400.
- [x] Renaming changes the name only; no sample file is touched.
- [x] Removing a label that samples use returns 409 `label_in_use`; the Sample
      Library supplies the count.
- [x] Changes are written to the file, keeping its comments and the order of
      other entries, and the state is updated.
- [x] When the file changes on disk (for example after a git pull), the list is
      re-read within a few seconds and the state updated, without a restart.
- [x] A malformed file at startup gives a clear error and does not crash a
      running application on a later reload.

**Implementation notes.** `services/labels.py`. `ruamel.yaml` preserves
comments. Poll the file's modification time (about every 2 seconds) rather
than using a file-watching library. Write through the replace routine of DC-L8's
helpers so a crash cannot truncate the file.

### DC-A7 Clip Writer

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-S1
- **Requirements**: R6.6, R6.9
- **Design**: DC 4.8

**Description.** Encodes a list of frames into an H.264 video clip file on a
background thread, without blocking the caller.

**Acceptance criteria.**

- [x] Given frames (JPEG bytes with timestamps), a frame rate and a target path,
      it returns a result that completes later with the path or a failure.
- [x] The video is written to a temporary file in the same folder, then renamed,
      so a clip is complete or absent.
- [x] The frame rate is the measured one; the clip duration matches the frames
      within one frame interval.
- [x] On any failure (encoder missing, bad input, disk error) the result says
      failure, no partial file remains, and nothing is raised on the caller's
      thread.
- [x] The produced file plays in a browser (the format chosen in DC-S1).
- [x] Several clips queued back to back are written one after another.

**Implementation notes.** `clip_writer.py`. Encode with PyAV as decided in
DC-S1, in a separate worker process (design 4.8), so that PyAV and OpenCV never
load in the same process. The caller-side thread queues the clips and talks to
the worker over its standard input and output. The worker must not import
OpenCV: decode the JPEGs with PyAV too. Do not hold the whole clip's decoded
frames in memory at once if it can be avoided.

### DC-A8 Sample Library

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-A1, DC-L5, DC-L9
- **Requirements**: R5.2, R6.5, R6.8, R6.9, R7.1, R7.2, R7.3, R7.4, R7.6
- **Design**: DC 4.9

**Description.** Finds and changes stored samples for both review (one
session) and browsing (the whole dataset), serves images, and keeps the counts.
It owns the Counts and Samples revision fields.

Behavior:

- When the data folder is opened it builds an in-memory index: a summary per
  sample (id, session id and name, author, label, status, capture time, whether
  it has a clip) and accepted counts per label.
- It subscribes to the dataset store's change notifications, whoever made the
  change. After each it updates the index, writes the new counts and an
  increased samples revision to the state.
- `GET /api/samples`: filters `label`, `session`, `author`, `from`, `to`,
  `status`, paging `page` and `pageSize`, and `order` (`capture` or `newest`);
  returns the items and the total. `GET /api/samples/{id}`: the full record
  with a `hasClip` flag. `PATCH /api/samples/{id}`: change `label` and/or
  `status`. `DELETE /api/samples/{id}`: hard delete (record and clip).
- `GET /api/samples/{id}/image?mode=path|overlay` returns a PNG made by the
  path renderer from the stored positions. Overlay decodes one frame from the
  clip at the gesture start. `GET /api/samples/{id}/thumbnail` returns a small
  PNG, cached.

**Acceptance criteria.**

- [x] Queries combine all filters, return stable pages, and are fast for 10,000
      samples (well under 100 ms).
- [x] A new sample written by the Capture Controller appears in queries and in
      the counts without a restart.
- [x] Changing a label or status, and deleting, work in open and ended sessions,
      update the index and the counts, and raise the samples revision.
- [x] A label that does not exist is rejected with 400.
- [x] A label, status or delete change is on disk, written with the safe replace
      routine, before the request returns.
- [x] Overlay or video requests for a sample without a clip, or whose clip file
      is missing, return 404; path images and thumbnails still work.
- [x] Thumbnails are cached in the operating system's cache location (not in the
      data folder), keyed by sample id and a hash of the positions, and can be
      deleted without harm.
- [x] Without a `session` filter, queries cover the whole dataset; the current
      session in the state can be used as the default for review.
- [x] The label-use count is available to the Label Service.

**Implementation notes.** `services/library.py`. Use `platformdirs` for the
cache location. Keep the index in a dictionary plus per-session lists in
capture order. Decode the overlay frame with `cv2.VideoCapture` seeking to the
`gestureStartS` time.

### DC-A9 Session Service

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-A1, DC-A3, DC-A5, DC-L9
- **Requirements**: R2.1, R2.2, R2.4, R2.6, R2.7
- **Design**: DC 3.2, 4.5

**Description.** Owns the session. It owns the Session field of the
Application State.

- `GET /api/sessions` lists the sessions in the data folder (id, name, author,
  start time, sample count, open or ended).
- `POST /api/sessions` starts a session: it takes `author`, `handedness`,
  optional `name` and `notes`. It requires no session loaded for capture
  (409 `session_active` otherwise) and a camera in use (409
  `camera_unavailable`). It reads the final settings and the camera from the
  state, creates the session through the dataset store with the settings, the
  camera device and requested and actual modes, the clip padding, and a highest
  sample number of 0, then records the session in the state as loaded for
  capture, which locks the settings.
- `POST /api/sessions/{id}/load?mode=review|resume`. Review works for any
  session and records it as loaded for review only. Resume works only for open
  sessions: 409 `session_ended` for an ended one. It opens the camera recorded
  in the session by its device identifier; if that device is not among the
  available cameras it returns 409 `camera_unavailable` naming it. It then
  gives the recorded settings to the Calibration Service and records the
  session as loaded for capture. If the camera delivers a different mode than
  recorded, it still resumes and returns a warning in the response.
- `POST /api/sessions/current/end`: for a session loaded for capture it sets
  `endedAt`, tells the Capture Controller to stop, and clears the session in the
  state. For a session loaded for review only it just clears the state and
  changes nothing on disk.
- It supplies the next sample number to the Capture Controller.

**Acceptance criteria.**

- [x] Starting records author, handedness, name, notes, time, camera and
      settings as in DH 5.1, and locks the settings.
- [x] A second start while one is loaded for capture is refused.
- [x] Ending sets `endedAt`, stops capture and unlocks settings. Closing the
      application leaves the session open on disk, and it is listed as open.
- [x] An ended session cannot be resumed, but can be loaded for review and its
      samples edited.
- [x] Resume is refused when the recorded camera is unavailable, and the refusal
      names the camera. It succeeds with the camera present and applies the
      recorded settings, which the Calibrate page then shows.
- [x] Sample numbers continue from the highest number after a delete and after a
      resume.
- [x] A load while another session is loaded for capture is refused.

**Implementation notes.** `services/session.py`. Camera availability comes from
the library's camera listing, matched on the stored device identifier. The
session is only recorded in the state after every earlier step succeeds, so a
failed start or resume leaves the state unchanged.

### DC-A10 Capture Controller

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-A1, DC-A3, DC-A7, DC-A9, DC-L9
- **Requirements**: R4.1, R4.2, R4.3, R4.4, R4.5, R4.6, R4.7, R4.9, R5.6, R6.4
- **Design**: DC 3.4, 4.7

**Description.** Runs the capture cycle: it counts down, makes the Capture
Engine ready, turns each gesture into a saved sample, and handles pause and
resume. It owns the capture state, active label, latest sample and last discard
fields of the Application State.

It is one loop that reads messages from one queue: user commands, results from
the Capture Engine, timer ticks, and save-job completions. It handles one at a
time, so the state machine needs no locks.

States and transitions (DC 3.4): `STOPPED` to `COUNTDOWN` on start;
`COUNTDOWN` to `READY` when the countdown is over and any sample is saved;
`READY` to `RECORDING` when the engine reports motion started; `RECORDING` to
`COUNTDOWN` when a gesture or a discard arrives; pause from `COUNTDOWN` or
`READY` to `PAUSED` at once, and from `RECORDING` after the result is
processed; resume from `PAUSED` to `COUNTDOWN` (the remaining time, or a fresh
countdown if the pause came while `READY`); the end of the session to
`STOPPED`.

Endpoints: `PUT /api/recording/label` (active label, must exist),
`POST /api/recording/start` (requires a session loaded for capture, else 409
`no_session`; requires an active label, else 400), `POST /api/recording/pause`,
`POST /api/recording/resume`.

Building a sample when a gesture arrives: take the active label at that
moment; compute the clip window from `preS` before the gesture start to `postS`
after its end; enter `COUNTDOWN` at once and start a save job in parallel. The
job waits until the engine's frames reach the end of the window, reads the
frames from the ring buffer, passes them to the Clip Writer, asks the Session
Service for the next sample number, builds the sample record (ids, capture
time, label, status `accepted`, the session's handedness, the frame size, the
gesture's positions as columns `timeS`, `horizontal`, `vertical`, and the video
reference with `gestureStartS`), and when the clip finishes writes the record
through the dataset store (with no clip reference if encoding failed). It then
tells the loop it is done.

**Acceptance criteria.**

- [x] Arm and disarm commands are sent to the engine so it is armed only in
      `READY` (and `RECORDING`), and never during the countdown.
- [x] The countdown length comes from the configuration (default 3 seconds). The
      capture state in the state holds the time the countdown ends (or the
      remaining time when paused), and no per-tick updates are written.
- [x] A discard writes the last-discard field, enters `COUNTDOWN` and creates
      nothing on disk.
- [x] A gesture creates exactly one sample, accepted, with the right label,
      positions, handedness, frame size, clip reference and `gestureStartS` (the
      time from the clip start to the gesture start), and the latest-sample
      field shows it as saving, then as saved.
- [x] `READY` is never entered before the countdown is over and the save job is
      done; a sample is on disk before the next capture is ready.
- [x] A clip failure still saves the sample, with no clip.
- [x] Pause from `RECORDING` takes effect only after the result is processed.
      Resume continues the remaining countdown, or restarts it if paused while
      `READY`.
- [x] Review can open only when no sample is being saved.
- [x] Ending the session moves to `STOPPED` from any state and discards no saved
      data.
- [x] Every capture-state change appears in the next `state` event.
- [x] Tests use a fake clock, a scripted engine and a fake Clip Writer to cover
      every state, every transition, the discard path, the pause cases, and the
      clip-failure case.

**Implementation notes.** `controller.py`. Use a monotonic clock abstraction so
tests can advance time. The countdown is a timer message after the remaining
time, not a loop that wakes every tick (the Web UI counts down locally). Active
label changes are allowed in any state and take effect for the next gesture.
The save job runs on a worker thread and posts a message to the loop on
completion.

**Note from DC-L9 (sample numbers).** `DatasetStore.next_sample_number` and
`add_sample` are separate calls, so two writers could be given the same
number. The controller handles one gesture at a time, so this is unlikely, but
the controller must reserve a number and save the sample without another
writer in between (for example by remembering the numbers it has handed out,
or by adding a reserve call to the store). Do not reach into the store's
private lock.

### DC-A11 Command-line tools

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-L10, DC-L11, DC-A2
- **Requirements**: R2.3, R2.5
- **Design**: DC 5.3

**Description.** Three subcommands of `wand-collect` that work without a camera
or a running application: `export`, `merge` and `check`.

- `export <folder>... --output <file>` with filters `--status`, `--label`,
  `--session`, `--author`, `--from` and `--to`.
- `merge <source>... --target <folder>` with `--on-conflict skip|replace`
  (default skip) and `--skip-clips`; prints the per-session result.
- `check <folder>` prints the report; the exit status is non-zero when there are
  errors.

**Acceptance criteria.**

- [x] Each command runs on a test data folder and prints a readable result.
- [x] `export` output matches the library's export; `merge` results match the
      library's merge; `check` detects the problems of DH 7.1.
- [x] A missing folder or bad option gives a clear message and a non-zero exit.
- [x] `--help` documents every option.
- [x] None of the commands opens a camera or starts the server.

**Implementation notes.** Extend `cli.py` with `argparse` subcommands that call
the library functions. Use `subprocess` or the `main` function directly in
tests, with temporary folders.

## 9. Web UI tasks

The Web UI is built with Preact and htm from vendored files, as ES modules
with no build step (DC 4.1). All pages render from the latest state snapshot;
a user action is an HTTP request whose response only says whether it was
accepted (DC 4.1, "Data flow"). JavaScript and CSS are wrapped at 80 columns by
hand.

### DC-U1 Web UI shell

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-A2
- **Requirements**: N2
- **Design**: DC 4.1

**Description.** The page that hosts all others: the vendored libraries, the
client for the event stream and the API, navigation and keyboard shortcuts. It
holds a copy of the latest state snapshot, and the latest `motion` reading, and
re-renders when they change.

**Acceptance criteria.**

- [x] The server's `/` serves `index.html`, which loads the application as ES
      modules with no build step.
- [x] Preact, its hooks, and htm are vendored as exact files under
      `static/vendor/`, and a `VERSIONS.md` lists each file's name, version and
      source URL.
- [x] The page connects to `/api/events`, shows a connection indicator, keeps
      the latest `state` snapshot (as camel case JSON) and the latest `motion`
      reading, and reconnects after a drop. After a reconnect it shows the new
      snapshot.
- [x] Navigation shows Setup, Calibrate, Record, Review and Browse. It moves to
      Record when capture starts, to Review when the capture state is `PAUSED`
      or a session is loaded for review, and to Setup when no session is loaded.
      The user can always open Browse.
- [x] An API helper sends requests and, on an error response, exposes the `code`
      and `message`, which the shell shows as a dismissible notice.
- [x] A shortcut helper registers keys from the application settings, ignores
      keys typed into input fields, and offers each shortcut's key for display
      on its button.
- [x] The countdown helper computes the time left from the end time in the state
      and updates the display locally.
- [x] A test (Python) fails if any file under `static/` outside `vendor/` has a
      line over 80 columns, except HTML.

**Implementation notes.** `static/index.html`, `static/style.css`, `static/app/`
with one module per concern (`main.js`, `state.js`, `api.js`, `shortcuts.js`,
`countdown.js`). Use `EventSource` for the stream. Keep pages as functions of
the state so they stay simple. No Node tooling is used.

### DC-U2 Setup page

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-U1, DC-A5, DC-A9
- **Requirements**: R1.1, R2.1, R2.6, R6.7
- **Design**: DC 3.1, 4.1

**Description.** Where the user chooses the camera, starts a new session, or
opens an existing one.

**Acceptance criteria.**

- [x] Lists the cameras from `GET /api/cameras`, shows the live preview of the
      chosen one using the live video, and lets the user choose a camera.
- [x] Shows the camera in use from the state, including the requested and actual
      mode, with a visible warning when they differ.
- [x] The new session form takes the author, an optional session name, the
      handedness (left or right) and optional notes. Starting is disabled until
      the author and handedness are set. Starting calls the session endpoint and
      the page moves on to Calibrate (or Record if the settings are already
      calibrated and the user chooses so).
- [x] Lists existing sessions (name, author, date, sample count, open or ended)
      with a Review button, and a Resume button for open sessions only.
- [x] A refused resume (ended session or unavailable camera) shows the reason
      from the error. A resume warning about a different camera mode is shown.
- [x] While a session is loaded for capture, the form and Resume are disabled
      and a notice says to end the session first.

**Implementation notes.** `static/app/setup.js`. Sessions come from
`GET /api/sessions` (a query), fetched when the page opens and after any
`session` change in the state.

### DC-U3 Calibrate page

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-U1, DC-A4, DC-A5
- **Requirements**: R1.2, R1.3, R1.4, R1.5, R1.6
- **Design**: DC 3.3, 4.1

**Description.** Calibration of vision and motion for the current camera.

**Acceptance criteria.**

- [x] **Color calibration.** A button freezes the frame and shows it. Clicking
      the tip sends the point (as fractions of the image); the page shows the
      returned detection mask and the detected tip, and says how many other
      regions are also marked. More clicks refine the result. A tolerance
      control re-runs the calibration. A button returns to the live view.
- [x] **Manual adjustment.** Sliders for the vision settings (hue center and
      half-width, saturation and brightness ranges, and the others) send partial
      settings changes and take effect on the live view. A toggle switches the
      live view between the camera and the mask.
- [x] **Motion tuning.** The live view clearly shows motion versus idle (for
      example a colored border and label), the current speed as a number, and a
      short history graph of the speed with the start and end thresholds drawn.
      A slider sets the start threshold, and the end threshold follows at the
      configured ratio. Numeric fields set the valid time window and minimum
      size.
- [x] **Guided measurement.** A guided sequence tells the user to hold still,
      then to wave, calls the measurement endpoint for each phase, and shows
      that the proposed thresholds replaced the motion settings.
- [x] **Profiles.** Save the current settings as a named profile, load, and
      delete from a list.
- [x] Every control shows the current value from the state, and all controls are
      disabled with a notice while a session is loaded for capture.

**Implementation notes.** `static/app/calibrate.js`. The history graph is
drawn on a canvas from the `motion` readings in a ring of the last few seconds.
Throttle slider requests (about 10 per second) while dragging.

### DC-U4 Record page

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-U1, DC-A4, DC-A10
- **Requirements**: R4.1, R4.7, R4.8, R5.6
- **Design**: DC 3.4, 4.1

**Description.** The page used while capturing. It offers no review actions.

**Acceptance criteria.**

- [x] Shows the live view, the capture state (countdown, ready, recording,
      paused), the countdown as a large number counted down locally from the end
      time, the active label, and the accepted count for that label.
- [x] A label selector sets the active label; digits 1 to 9 set it while
      capturing. Start is disabled until a label is chosen.
- [x] When the state says ready, a clear "go" cue is shown.
- [x] The path image of the latest sample is shown as soon as it appears and
      stays during the next countdown; a discard shows its reason as a notice.
- [x] Pressing Escape, or clicking anywhere on the page, pauses capturing. The
      page then moves to Review when it is available.
- [x] No reject, delete or relabel control is offered on this page.
- [x] The latest sample's saving state is shown, so the user knows it is saved.

**Implementation notes.** `static/app/record.js`. The latest sample's image is
`GET /api/samples/{id}/image?mode=path`.

### DC-U5 Review page

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-U1, DC-A8, DC-A10
- **Requirements**: R4.7, R5.1, R5.2, R5.3, R5.4, R5.5
- **Design**: DC 3.4, 4.1

**Description.** Review the samples of the loaded session: reject, restore,
delete and relabel. It opens when capturing is paused or a session is loaded
for review.

**Acceptance criteria.**

- [x] Lists the session's samples in capture order, with the latest selected
      when the page opens. Left and Right (and buttons) step through them.
- [x] Shows the selected sample's path image, with a switch between path only
      and overlay on a camera frame. The overlay choice is unavailable, with the
      reason, for a sample without a clip.
- [x] Shows the sample's label, status, time and whether it has a clip.
- [x] Reject (R, toggles back to accepted), delete (Backspace, with a
      confirmation) and relabel (digits 1 to 9 or a selector) act on the
      selected sample and are sent immediately. The page updates when the
      samples revision changes.
- [x] A selector sets the active label for the next captures.
- [x] Resume (Escape or a button) continues capturing when the session is loaded
      for capture. For a session loaded for review only, Resume is replaced by a
      button that closes the review.
- [x] Every action is also on a button that shows its shortcut key.
- [x] The latest sample is only selectable once it has finished saving.

**Implementation notes.** `static/app/review.js`. Fetch the session's samples
with `GET /api/samples?session=<id>&order=capture` and repeat the query when
the samples revision changes. The selected sample is local page state.

### DC-U6 Browse page

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-U1, DC-A8
- **Requirements**: R6.9, R7.1, R7.2, R7.3, R7.4
- **Design**: DC 4.1

**Description.** Browse every sample in the dataset: filter, inspect, and edit.

**Acceptance criteria.**

- [x] A table shows a thumbnail, label, status, session name, author and date
      for each sample, in pages.
- [x] Filters for label, session (by name), author, date range and status
      (accepted or rejected) apply together.
- [x] Per-label counts of accepted samples are shown, with the progress toward
      about 1,000 each.
- [x] Selecting a row opens a detail view with the path image (path or overlay)
      and the metadata. The overlay and video views are hidden, with a short
      explanation, for a sample without a clip.
- [x] From the detail view the user can change the label, reject or restore, and
      delete (with confirmation), in any session including ended ones.
- [x] The table repeats its query when the samples revision changes.
- [x] It works while no session is loaded.

**Implementation notes.** `static/app/browse.js`. Thumbnails are
`GET /api/samples/{id}/thumbnail`, loaded lazily as rows scroll into view.

### DC-U7 Scrubbing view (P2)

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-U6, DC-A8
- **Requirements**: R7.5
- **Design**: DC 5.2 (video endpoint)

**Description.** A full-screen view of one sample that scrubs through its video
frames with the path drawn over them. Only for samples with a clip.

**Acceptance criteria.**

- [x] `GET /api/samples/{id}/video` serves the clip with support for range
      requests, and returns 404 when there is no clip.
- [x] The view plays the clip and lets the user step frame by frame and scrub
      with a slider.
- [x] The path is drawn over the video, with the part up to the current frame
      highlighted.
- [x] Full screen can be entered and left.
- [x] The view is not offered for a sample without a clip.

**Implementation notes.** `static/app/scrub.js`. Use a `<video>` element and a
canvas on top. Frame positions come from the sample's `positions` and
`gestureStartS`.

## 10. Verification tasks

### DC-V1 Whole-application test

- **Type**: test
- **Status**: Completed
- **Depends on**: DC-A10, DC-A11, DC-U5
- **Requirements**: all P1 requirements, N2
- **Design**: DC 7

**Description.** An automated test that runs the real application with a
recorded video in place of the camera and exercises the whole flow through the
HTTP interface.

**Acceptance criteria.**

- [x] A synthetic video contains a known number of gestures and some motions
      that must be discarded.
- [x] The test calibrates, starts a session, starts capturing, and replays the
      video. It checks the state snapshots after each command and event, that
      the right number of samples exist, and that discards created nothing.
- [x] It pauses, rejects one sample in review, relabels another, resumes with a
      different label, and checks the files on disk.
- [x] It stops the application mid-session, starts it again, resumes the open
      session, and checks that numbering continues and the settings are the
      recorded ones.
- [x] It ends the session and checks that resume is refused but review works.
- [x] A second event-stream client sees the same snapshots as the first.
- [x] A capture cycle takes about the gesture duration plus the countdown (N2).
- [x] The test runs with `uv run pytest` and needs no camera.

**Implementation notes.** Use the synthetic generator (DC-L2) to write a video
file, and inject a video-file frame source into the Capture Engine. Use a short
countdown in the test configuration.

### DC-V2 Real-camera testing

- **Type**: chore
- **Status**: In progress
- **Depends on**: DC-U6
- **Requirements**: R1.7, N3, N4, R6.7
- **Design**: DC 7

**Description.** Check the application with real laptop cameras on macOS,
following a written checklist. Linux is checked by DC-S2, which reuses the
checklist.

**Acceptance criteria.**

- [x] A checklist document exists (a new document with the standard header)
      covering camera selection, calibration under different lighting and
      backgrounds, motion tuning, a capture run, pause and review, resume,
      missing-camera resume refusal, merge, and the missing-clip behavior.
- [ ] It has been run on macOS, and the results are recorded in the document
      with a column left for Linux (filled in by DC-S2).
- [ ] The live view keeps up with the camera, and no dropped frames corrupt
      tracking (N3).
- [ ] Problems found are recorded as follow-up tasks.

**Progress.** The checklist is written
(`data-collection/docs/manual-tests.md`). The macOS run, the recorded
results and any follow-up tasks need a person with the real camera and wand.

**Implementation notes.** `data-collection/docs/manual-tests.md`. Include the
camera permission step on macOS.

### DC-V3 Motion threshold tuning

- **Type**: chore
- **Status**: Not started
- **Depends on**: DC-V2
- **Requirements**: R1.5, R4.5
- **Design**: Lib 8.2

**Description.** Replace the provisional motion defaults with values found from
real recordings.

**Acceptance criteria.**

- [ ] Recordings of the tip held still and of many gestures are made on at least
      two cameras and two people.
- [ ] Chosen values for `start_speed`, `end_speed`, `end_hold_s`,
      `max_duration_s` and `min_extent` give few false gestures and few missed
      real ones on those recordings, and the method and results are written
      down.
- [ ] `config/motion.yaml` has the new defaults.
- [ ] The starting values in `lib/docs/design.md` 8.2 are updated through its
      own branch, with a version bump and review.

**Implementation notes.** Replay the recordings through the Segmenter with
candidate values and count gestures against known counts. The guided
measurement (DC-L7) can supply a starting point for each user.
