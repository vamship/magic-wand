# Data Collection Application - Tasks

> **Version** 32 | **Updated** 2026-11-26 | **Approved**

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
  `camera_unavailable`, `label_in_use`, `not_capturing`, `camera_check` and
  `no_camera_check` (all 409).

## 3. Summary

| ID | Task | Status |
|---|---|---|
| DC-D0 | Project documents | Completed |
| DC-D1 | Requirements | Completed |
| DC-D2 | Design | Completed |
| DC-D3 | Task list | Completed |
| DC-F1 | Workspace and tooling | Completed |
| DC-F2 | Configuration and settings models | Completed |
| DC-F3 | Data layout migration | Not started |
| DC-S1 | H.264 encoding spike | Completed |
| DC-S2 | Linux verification | In progress |
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
| DC-L12 | Dataset discovery | Not started |
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
| DC-A12 | Session deletion | Completed |
| DC-A13 | Session name and notes | Completed |
| DC-A14 | Frame-rate measurement | Completed |
| DC-A15 | Camera check on resume | Completed |
| DC-A16 | Put a session on hold | Completed |
| DC-A17 | Camera list cache | Completed |
| DC-A18 | Dataset settings and command line | Not started |
| DC-A19 | Dataset service | Not started |
| DC-A20 | End any open session | Not started |
| DC-U15 | Wording, hover and resume-flow polish | Completed |
| DC-U16 | Accepted and rejected markers | Completed |
| DC-U17 | Browse grid layout | Completed |
| DC-U18 | Infinite scroll and the Review workspace | Completed |
| DC-U19 | Point counts and one page width | Completed |
| DC-U20 | Dataset selection and merge | Not started |
| DC-U21 | End a session from Record, Review and Setup | Not started |
| DC-U1 | Web UI shell | Completed |
| DC-U2 | Setup page | Completed |
| DC-U3 | Calibrate page | Completed |
| DC-U4 | Record page | Completed |
| DC-U5 | Review page | Completed |
| DC-U6 | Browse page | Completed |
| DC-U7 | Scrubbing view (P2) | Completed |
| DC-U8 | No-camera message | Completed |
| DC-U9 | Delete without an error notice | Completed |
| DC-U10 | Review grid and Space key | Completed |
| DC-U11 | Notices and page polish | Completed |
| DC-U12 | Save to the loaded profile | Completed |
| DC-U13 | Keyboard scrubbing | Completed |
| DC-U14 | Scrubbing without a clip | Completed |
| DC-V1 | Whole-application test | Completed |
| DC-V2 | Real-camera testing | Completed |
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
| 4.1 Web UI | DC-U1 to DC-U19 |
| 4.2 Application Server | DC-A2, DC-A4 |
| 4.3 Application State | DC-A1 |
| 4.4 Calibration Service | DC-A5, DC-A17 |
| 4.5 Session Service | DC-A9, DC-A13, DC-A15, DC-A16 |
| 4.6 Capture Engine | DC-A3, DC-A14 |
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
| Lib 10 Normalizer | TR-L1 (replaces DC-L4) |
| Lib 11 Path renderer | DC-L5 |
| Lib 12 Dataset store | DC-L8 to DC-L12 |
| DH 2, 3, 3.1 Rules, data folder, sharing | DC-L8, DC-L9, DC-L12, DC-F3, DC-A8 (delete) |
| DH 4 Identifiers | DC-L9 |
| DH 5 File formats | DC-L8 |
| DH 6 Writing safely | DC-L8 |
| DH 7.1 Consistency check | DC-L10, DC-L12, DC-A11 |
| DC 4.3, 4.5, 4.11, 5.2, 5.4 Datasets | DC-A18, DC-A19, DC-U20 |
| DC 3.2, 4.1, 4.5, 5.2 Ending a session anywhere | DC-A20, DC-U21 |
| DH 7.2 Export | DC-L10, DC-A11 |
| DH 7.3 Merge | DC-L11, DC-A11 |
| DH 9 Versioning | DC-L8 |

**Requirements.** Each task lists the requirement IDs it implements. Between
them the tasks cover R1.1 to R7.6 (including R2.10) and N1 to N5. R7.5 is P2
(task DC-U7).

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
- **Status**: Completed
- **Description**: This document.

The list is complete: every task in it is completed or explicitly parked, and
section 4 maps every part of the design to a task. The document goes on being
updated as the remaining tasks are done (DC-V3, which is deferred until real
recordings exist, and step 4 of DC-S2, which needs a Linux machine with a
camera); that upkeep is not part of this task.

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
- Label ids are lowercase slugs (the placeholder ids were `spell_one` and so
  on; the real spells replaced them in DC-U18's change to `config/labels.yaml`).
- Keep file reading separate from validation so both can be tested alone.

### DC-F3 Data layout migration

- **Type**: chore
- **Status**: Not started
- **Depends on**: DC-A18
- **Requirements**: R2.10
- **Design**: DH 2, 3, 3.1; Arch 6

**Description.** Move to the layout of `docs/data-handling.md` version 7:
datasets live side by side in `data/`, one folder for each dataset, in git,
with video clips ignored. Today the shared sessions are in `training-data/`
(in git), and each person's own `data/` is a single local dataset that git
ignores.

1. **Split the shared sessions by author.** For every session folder in
   `training-data/sessions/`, read the `author` in its `session.json`, make
   the lowercase slug of it (letters and digits; for example `Mrunal` gives
   `mrunal`), and move the folder with `git mv` to
   `data/<author>/sessions/<session id>`. Every `data/<author>/` gets a
   `dataset.json` with the same content as the old `training-data/dataset.json`.
   Then remove the old `training-data/` content, so that the folder can be
   reused for the training data (TR-A1).
2. **Update `.gitignore`.** Remove the lines `data/` and
   `training-data/**/videos/`, and add `data/**/videos/`.
3. **Merge a person's local dataset.** The local `data/` of a person who
   recorded before this change holds `dataset.json` and `sessions/` and is not
   in git. Before step 1, move those two items out of `data/` to a temporary
   folder outside the repository, and after step 1 merge that folder into
   `data/<their dataset>` with `wand-collect merge` (sessions already present
   are skipped as identical, and video clips are copied and stay ignored by
   git). Keep the temporary folder until the result has been checked. This step
   is done on the machine of the person who owns the data, who also sets
   `dataset: <their dataset>` in `config/data-collection.local.yaml`. For this
   repository's owner the dataset is `vamship`.
4. Run the consistency check on every dataset.

**Acceptance criteria.**

- [ ] After the move, `data/` holds one dataset folder for each author in the
      shared sessions, and `training-data/` holds no sessions.
- [ ] Every shared session appears exactly once, in the dataset of its author,
      and the number of accepted samples per label over all datasets equals the
      number in `training-data/` before the move (4,821 in total at the time of
      writing).
- [ ] `git status` shows renames for the session files, not deletions and
      additions of changed files; session and sample files are byte-identical
      to before.
- [ ] `.gitignore` ignores `data/**/videos/` and no longer ignores the rest of
      `data/`; a video clip placed in a dataset is not tracked.
- [ ] `uv run wand-collect check data/<author>` reports no errors for every
      dataset, and given all of them reports no session in conflict.
- [ ] The owner's local sessions are in `data/vamship` with their video clips,
      and the temporary folder was kept until this was confirmed.
- [ ] `uv run wand-collect serve --dataset vamship` opens that dataset and
      lists its sessions.

**Implementation notes.** A small script run once is enough; do not commit it
unless it is worth keeping. Do the move in one commit and the `.gitignore`
change in another. Because part of the work touches files that are not in git,
confirm each destructive step with the owner before doing it.

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
- **Status**: In progress
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
3. Playback (DC-S1): open the MP4 produced on Linux in a browser. The file
   can be shared out of the container to a browser on another machine (a
   decision of 2026-11-15: the Linux-specific part is the encoding, and a
   browser decodes the same H.264 on any system).
4. Cameras (DC-V2): run the DC-V2 checklist with a real camera on Linux, and
   fill in its Linux column.

**Acceptance criteria.**

- [x] The commands in step 1 succeed on Linux.
- [x] PyAV's wheel on Linux can encode H.264 with `libx264`, and the 150-frame
      clip encodes in well under 6 seconds. If it cannot, the fallbacks
      named in DC-S1 are tried and the outcome is recorded.
- [x] The MP4 encoded on Linux plays in a browser (Chrome on macOS, with the
      file shared from the container).
- [ ] The DC-V2 checklist has been run on Linux and its results recorded.
- [ ] The findings are written in `docs/notes.md` (a version bump and review),
      and problems found are recorded as follow-up tasks. If the chosen video
      approach does not work on Linux, DC-A7 is changed accordingly.

**Progress (2026-11-15).** Steps 1 to 3 were run in Docker, on a clean checkout
made with `git archive`, on Debian 13 with Python 3.12 and uv 0.13: on ARM
(aarch64) and on x86_64 (emulated). On both, `uv sync`, `ruff format --check`,
`ruff check`, `pytest` (558 passed) and `wand-collect --help` succeed, and the
spike encodes with PyAV `libx264` in 1.0 s (ARM) and 1.7 s (x86_64), as H.264
with `faststart`. The findings are in `docs/notes.md` (platforms, and video
clips). No problems were found, so no follow-up tasks. Step 3 was done by
sharing the MP4s out of the containers and opening them in Chrome on the Mac:
both load, are 640x480 and 5 s long, and a decoded frame shows the ball where
it was drawn. Still to do: step 4 (the checklist with a real camera on Linux),
which needs a Linux desktop. The findings criterion is met for what was
run so far.

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
- **Note**: Superseded by TR-L1 (`training/docs/tasks.md`), which replaces the
  vector builder with the normalizer and removes it.
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
is a polyline with a color gradient from green at the start to red at the end,
with a small marker at each end (a circle at the start, a square at the end) so
direction is clear.

**Acceptance criteria.**

- [x] Given positions, a size and a mode, it returns an image of that size.
- [x] The gradient makes the start and end distinguishable, and the markers are
      visible at thumbnail size (about 96x72) and at large size.
- [x] Overlay mode draws on a copy of the supplied frame, resized to the
      requested size, and never changes the input.
- [x] A one-position or empty gesture draws without error.
- [x] Rendering a typical gesture at 640x480 takes a few milliseconds.
- [x] Positions are drawn as given. The caller mirrors them for display (see
      DC-A8); the renderer never changes what is stored.

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

### DC-L12 Dataset discovery

- **Type**: feat
- **Status**: Not started
- **Depends on**: DC-L11
- **Requirements**: R2.5, R2.10
- **Design**: DH 3, 3.1, 7.1; Lib 12

**Description.** Let the library work with several datasets side by side in a
data location (a folder such as `data/` whose subfolders are data folders), as
`docs/data-handling.md` version 7 describes.

- `find_datasets(location)` returns the datasets in the location: the
  subfolders that contain a `dataset.json`, sorted by name. For each: its name
  (the folder name), its path, its format version, and its number of sessions
  and samples. Other files and folders are ignored. An unreadable
  `dataset.json` is reported, not fatal.
- `create_dataset(location, name)` creates a new data folder
  `<location>/<name>` with `dataset.json` and `sessions/`, as an ordinary data
  folder. The name must be a lowercase slug (letters, digits, hyphen and
  underscore); an invalid or existing name is refused with a clear error.
- Reading several data folders at once: the load and export functions of
  DC-L10 accept several folders. A session present in more than one folder is
  used once; if its copies differ (the session file and the samples file
  contents), they are reported as a conflict, and the loader raises a clear
  error naming the session unless told to skip such sessions.
- The consistency check (DC-L10) accepts several folders. It also lists
  sessions that are still open (as information), and reports a session present
  in more than one folder with different content as an error.

**Acceptance criteria.**

- [ ] A location with three datasets, a stray file and a folder without
      `dataset.json` lists exactly the three, with the right counts.
- [ ] `create_dataset` makes a folder that opens and passes the check; invalid
      names (uppercase, spaces, slashes, empty) and existing names are refused.
- [ ] Loading two folders that share a session loads it once; with different
      copies it fails naming the session, or skips it when asked.
- [ ] The check on several folders reports open sessions as information and a
      conflicting duplicate as an error, and never writes.
- [ ] Existing single-folder behavior and tests are unchanged.
- [ ] No camera or running application is needed.

**Implementation notes.** Add `dataset/discovery.py`; extend `dataset/check.py`
and the load code. Reuse the content comparison of the merge operation
(DC-L11) to decide whether two copies of a session are identical.

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
- [x] Static files are sent with `Cache-Control: no-cache`, so a browser
      rechecks them and never shows a stale page after an update.
- [x] Ctrl+C stops the server within a few seconds even while a browser tab
      holds the live view or the event stream open; open connections get 2
      seconds and are then closed.
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
- `GET /api/samples/{id}/image?mode=path|overlay` returns a PNG made by the path
  renderer from the stored positions. Overlay decodes one frame from the clip at
  the gesture start. When `mirrorPreview` is on (the default), the shown images
  (path, overlay, thumbnail) are mirrored left to right to match the live view;
  the stored data is never mirrored. The sample details carry a `mirrored` flag
  for the scrubbing view. `GET /api/samples/{id}/thumbnail` returns a small PNG,
  cached.

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
- [x] With `mirrorPreview` on, path images, overlays and thumbnails are
      mirrored (thumbnails are cached per mirror setting), the sample details
      say `mirrored: true`, and the stored positions are unchanged.

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
  sessions: 409 `session_ended` for an ended one. It opens the camera that best
  matches the recorded one (DC-A15) and returns 409 `camera_unavailable` only
  when there is no camera at all. It then gives the recorded settings to the
  Calibration Service and records the session as loaded for capture with a
  camera check pending (DC-A15). If the camera delivers a different mode than
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
- [x] Resume succeeds with the camera present and applies the recorded
      settings, which the Calibrate page then shows. (Changed by DC-A15: it is
      no longer refused when the recorded camera is missing, but it is refused
      with no camera at all.)
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

### DC-A12 Session deletion

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-A8, DC-A9, DC-U2
- **Requirements**: R2.8
- **Design**: DC 4.5, 5.2; DH 2, 6

**Description.** Delete a whole session with its samples and clips.
`DELETE /api/sessions/{id}` returns 204; 404 for an unknown session; 409
`session_loaded` when the session is loaded in any role. The Dataset Store
renames the session folder out of `sessions/` and removes it, and notifies its
subscribers; the Sample Library drops the session's samples from its index,
counts and thumbnail cache and raises the samples revision. The Setup page
shows a Delete button for each session, disabled for the loaded one, that asks
for confirmation and names the session and its sample count.

**Acceptance criteria.**

- [x] A session that is not loaded is deleted with its samples and clips, and
      leaves the session list, the sample queries and the counts.
- [x] A loaded session (capture or review) is refused with 409.
- [x] A crash cannot leave a half-deleted session; a leftover temporary folder
      is removed when the data folder opens.
- [x] The Setup page asks before deleting and refreshes its list.

**Implementation notes.** `DatasetStore.delete_session`,
`SessionService.delete`, and the sessions list in `static/app/setup.js`.

### DC-A13 Session name and notes

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-A9, DC-A8, DC-L9, DC-U2
- **Requirements**: R2.9
- **Design**: DC 4.5, 5.2

**Description.** Change the name and notes of any session, also after it has
ended. `PATCH /api/sessions/{id}` takes `name`, `notes` or both and returns the
session's id, name and notes. A field that is left out stays as it is; an empty
text clears it; the text is trimmed. It answers 400 when neither field is
given and 404 for an unknown session. It works while the session is capturing,
open for review or ended, because the name and notes are not settings. The
Dataset Store writes `session.json`; the Sample Library updates the session
name shown with its samples; for the loaded session the name in the
Application State changes. `GET /api/sessions` also returns each session's
notes. The Setup page shows the notes under each session's name and an Edit
button that opens a small form with the name and the notes, with Save and
Cancel.

**Acceptance criteria.**

- [x] The name and notes change for the loaded session, and the state shows
      the new name.
- [x] They change after the session has ended, and the session stays ended.
- [x] A field that is left out is unchanged; an empty text clears the field.
- [x] An empty request is rejected with 400 and an unknown session with 404.
- [x] The session list returns the notes and shows the change after saving.
- [x] The Setup page offers Edit for every session, also while one is
      capturing and for ended sessions.

**Implementation notes.** `SessionService.patch` uses
`DatasetStore.update_session`; `DetailsEditor` in `static/app/setup.js`.

### DC-A14 Frame-rate measurement

- **Type**: fix
- **Status**: Completed
- **Depends on**: DC-A3
- **Requirements**: R6.7
- **Design**: DC 4.6

**Description.** Found in manual test 1.4 (`manual-tests.md`, section 4). The
Capture Engine measures the camera's actual frame rate once, over the first 2
seconds after the camera opens, and keeps the result until the camera is
reopened. A camera that stalls while it starts gives a wrong number: an
external webcam with a smooth live view showed 3.1 and then 0.4 fps, and the
built-in camera 18.2 and then about 24 fps. The number is shown on the Setup
page, drives the mode warning, and is recorded in `session.json` as the actual
mode. Measure the rate so that a startup stall cannot spoil it, and keep the
measurement up to date while the camera runs.

**Acceptance criteria.**

- [x] The measurement ignores the frames of a warm-up period after the camera
      opens, and is then taken from a window of the most recent frames.
- [x] The rate is the inverse of the median interval between frames in the
      window, so a few long gaps do not change it.
- [x] The window keeps moving while the camera runs, and the rate in the
      Application State is updated when it changes by more than 5%, not on
      every frame.
- [x] No rate is published until the window holds enough frames to be
      meaningful, and until then the state shows the rate as not yet measured.
- [x] A test feeds frame timestamps with a long stall at the start and then a
      steady 30 fps, and expects about 30 fps. A second test uses a steady
      10 fps and expects about 10. A third test uses a video file, whose
      source ends, and expects no rate or error from the end of the file.
- [x] The Setup page shows "measuring" while there is no rate, and the mode
      warning is not shown until there is one.
- [x] A session records the rate at the moment it starts. If there is none
      yet, it records the rate the camera reported when it opened.

**Implementation notes.** `CaptureEngine._measure_fps` and
`_finish_fps_measurement` in `engine.py`. A deque of the last 30 or so frame
timestamps is enough. The clip writer already uses each frame's capture time, so
clips and positions are not affected by this task; the clip's nominal rate is.

### DC-A15 Camera check on resume

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-A9, DC-U2, DC-U3
- **Requirements**: R2.6
- **Design**: DC 3.2, 4.5

**Description.** Found in manual test 6.4 (`manual-tests.md`, section 4). A
session records its camera as a device identifier, which on macOS is only
`index:<n>`, the position in the list. The position changes when a camera is
unplugged, so a resumed session opened the built-in camera in place of the
external one, silently, with settings calibrated for the other camera. Naming
cameras by the system's names was tried and dropped: macOS reorders the camera
list as cameras are opened, so a position cannot reliably be matched with a
name (the Setup page showed one camera twice), and the fix would have needed
macOS-only code. Instead the user checks the camera by sight after every
resume. The app opens the best match, shows the Calibrate page with all
settings read-only except the camera, and waits for the user to continue.

**Acceptance criteria.**

- [x] Resume opens the recorded camera when it is found by its device
      identifier, otherwise the one at the recorded position, otherwise the
      camera in use, otherwise the first one. It is refused only when there is
      no camera at all, and the message names the recorded camera.
- [x] After a resume the state's session has `cameraCheck` true and the
      `recordedCamera`. While it is set, the camera can be changed (Setup and
      Calibrate), settings and profiles stay locked, and `POST /api/recording/
      start` is refused with 409 `camera_check`.
- [x] `POST /api/sessions/current/camera/confirm` clears the check and writes
      the camera in use (device, index, requested and actual mode) to the
      session record, so a changed camera is recorded from then on. It is
      refused with 409 `no_camera_check` when no check is due, and with
      `camera_unavailable` when there is no camera in use. Editing the
      session's name or notes does not clear the check.
- [x] Resume (from the session list, or of the loaded session) opens the
      Calibrate page, which shows a "Check the camera" panel with the session's
      name and the wording in DC-U15, the camera selector, "Continue to Record"
      (disabled without a camera) and "End session". The live view and mask are
      those of the Calibrate page.
- [x] The Record page's Start is disabled with an explanation while the check
      is due.
- [x] Tests cover each of these, and the requirement, design and earlier
      tasks that said resume is refused now say what happens.

**Implementation notes.** `SessionService._find_camera`, `confirm_camera` and
`_resume`; `SessionInfo.camera_check` and `recorded_camera` in `state.py`;
`CaptureController.post_start`; `CalibrationService._require_camera_changeable`;
`CameraCheck` in `static/app/calibrate/index.js`; `cameraLocked` in
`static/app/setup.js`. The session keeps one camera in its record: a session
that is continued on a different camera has the later camera recorded, and the
earlier samples keep the position data, which is normalized and so unaffected.

### DC-A16 Put a session on hold

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-A9, DC-A15, DC-U2, DC-U3, DC-U4, DC-U5
- **Requirements**: R2.7
- **Design**: DC 3.2, 4.5

**Description.** Once a session is loaded for capture, the only way to start or
resume another one was to end it for good, or to stop and start the
application. Add a way to put the loaded session on hold: capturing stops and
the session is unloaded, but it stays open on disk (as when the application is
closed), so it can be resumed later and another session can be started or
loaded meanwhile. `POST /api/sessions/current/hold` does it. It is the same as
ending a session without writing `endedAt`.

**Acceptance criteria.**

- [x] `POST /api/sessions/current/hold` stops the Capture Controller (waiting
      for a sample being saved), clears the session in the state and leaves
      `endedAt` empty. It answers 409 `no_session` when no session is loaded.
      For a session loaded only for review it just closes it.
- [x] After a hold, settings and the camera can change again, a new session can
      be started, another session can be loaded, and the held session is listed
      as open and can be resumed (with the camera check, DC-A15).
- [x] The working settings keep the values of the held session; nothing is
      reset.
- [x] The UI offers "Pause" (renamed from "Put on hold (resume later)") next to
  "End session (final)" on the Setup page (current session), the Calibrate page
  (locked, and the camera check), and by itself on the Record page and, while
  capturing, the Review page. A held session leaves the user on Setup. Pressing
  the button on the Record page does not also pause (the page's click-to-pause
  ignores buttons).
- [x] Tests cover each of these.

**Implementation notes.** `SessionService.hold` and `end` share `_leave`;
`HoldButton` in `static/app/hold.js`. A review-only session keeps its "Close
review" button.

### DC-A17 Camera list cache

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-A5, DC-A9, DC-U2
- **Requirements**: R1.1
- **Design**: DC 4.4

**Description.** Finding the cameras opens every camera number from 0 to 9, one
after another: it is slow, it switches each camera on (a phone's included),
and it can disturb a camera that is running. It was done every time the Setup
page loaded and every time the camera changed, and on every resume. Read the
list once and keep it, and read it again only when the user asks.

**Acceptance criteria.**

- [x] A catalog (`wand_collect/cameras.py`) reads the cameras the first time
      they are asked for and keeps them; the Calibration Service and the
      Session Service share one, and a plain lister given to a service (as in
      the tests) is wrapped in its own.
- [x] `GET /api/cameras` answers from the kept list;
      `GET /api/cameras?refresh=true` looks again and keeps the new list. The
      camera in use is still added to the answer when it was not found.
- [x] The Setup page loads the list without a refresh when it opens and when
      the camera changes, and with `refresh=true` only for the Refresh list
      and Retry buttons.
- [x] Resume uses the kept list. It looks again once, before falling back, when
      the recorded camera is not in it (it may have been plugged in since).
- [x] Tests cover the catalog, the endpoint with and without `refresh`, that a
      camera change causes no new scan, and the resume cases.

**Implementation notes.** `CameraCatalog` and `as_catalog`;
`CalibrationService.get_cameras(refresh)`; `SessionService._find_camera`;
`CameraPanel` in `static/app/setup.js`. The list is kept in memory only, so a
restart of the application scans again.

### DC-A18 Dataset settings and command line

- **Type**: feat
- **Status**: Not started
- **Depends on**: DC-L12, DC-A11
- **Requirements**: R2.10
- **Design**: DC 5.3, 5.4; DH 3

**Description.** Replace the single data folder setting by a data location and
a dataset name, and add the matching command-line options and command.

- In `config/data-collection.yaml` the key `dataFolder` is replaced by
  `dataLocation` (the folder that holds the datasets, default `data`) and
  `dataset` (the name of the dataset to record into, default `default`). The
  application records into `<dataLocation>/<dataset>`, creating the dataset
  (DC-L12) if it does not exist. The old key is no longer accepted, and a
  settings file that has it gets an error that names the new keys.
- `wand-collect serve` takes `--data-location <folder>` and `--dataset <name>`
  in place of `--data-folder`, overriding the settings.
- `wand-collect datasets [--data-location <folder>]` lists the datasets in the
  location with their session and sample counts.
- `export`, `merge` and `check` keep taking data folder paths; `check` and
  `export` accept several (DC-L12).
- The comments in `config/data-collection.yaml`, `README.md` and
  `data-collection/docs/manual-tests.md` are updated to the new names.

**Acceptance criteria.**

- [ ] The new keys and options work, and the app opens
      `<dataLocation>/<dataset>`; a missing dataset is created.
- [ ] The old key and the old option are rejected with a message naming the new
      ones.
- [ ] An invalid dataset name is rejected at startup with a clear message.
- [ ] `wand-collect datasets` lists the datasets of a test location.
- [ ] The existing settings, startup and command-line tests are updated and
      pass, and ruff passes.

**Implementation notes.** Touch `settings.py`, `app.py` and `cli.py` in
`wand_collect`, and the tests `test_app_settings.py` and `test_startup.py`.

### DC-A19 Dataset service

- **Type**: feat
- **Status**: Not started
- **Depends on**: DC-A18, DC-A9, DC-A8, DC-L11
- **Requirements**: R2.5, R2.10
- **Design**: DC 4.3, 4.5, 4.11, 5.2

**Description.** Let the application list, choose, create and merge datasets,
as the Session Service of `DC` 4.5 describes.

- The Application State gets a field `dataset`, the name of the dataset in use,
  owned by the Session Service (`DC` 4.3). It appears in the state snapshot.
- `GET /api/datasets` lists the datasets in the data location: `name`,
  `sessions` and `samples` counts, and whether it is the dataset in use.
- `POST /api/datasets` with `{"name": ...}` creates a dataset (DC-L12).
- `PUT /api/dataset` with `{"name": ...}` chooses the dataset in use: it opens
  it through the Dataset Store (with the cleanup at open), updates the state and
  tells the Sample Library to reindex, so that the session and sample lists show
  that dataset.
- `POST /api/datasets/merge` with `{"sources": [...], "target": ...,
  "onConflict": "skip" | "replace", "skipClips": bool}` runs the merge of
  DC-L11 into the target dataset, which may be new (it is created), and returns
  the per-session result.
- Creating, choosing and merging are refused with the error code
  `session_active` (409) while a session is loaded. An unknown or invalid name
  gives `invalid_request` or `not_found`. Merging a dataset into itself is
  refused.
- If the dataset in use is the merge target, the Sample Library reindexes after
  the merge.

**Acceptance criteria.**

- [ ] Each endpoint works on a temporary data location, and the response and the
      next state snapshot show the result.
- [ ] After choosing another dataset, the session list and the sample list show
      only that dataset's contents, and the state's `dataset` changes.
- [ ] Creating, choosing and merging are refused while a session is loaded, and
      allowed after it is ended or put on hold.
- [ ] A merge into a new dataset creates it; a conflict is skipped or replaced
      as asked; source datasets are unchanged.
- [ ] Merging into the dataset in use updates the lists.
- [ ] Invalid and duplicate names are refused with clear errors.
- [ ] The application settings' `dataset` is the one in use at startup.

**Implementation notes.** Extend `services/session.py`, `state.py` and
`server.py`. Add the endpoints to the table in `DC` 5.2 if they are not there.

### DC-A20 End any open session

- **Type**: feat
- **Status**: Not started
- **Depends on**: DC-A9
- **Requirements**: R2.7
- **Design**: DC 3.2, 4.5, 5.2

**Description.** Today only the loaded session can be ended
(`POST /api/sessions/current/end`), so ending a session that is on hold means
loading it first. Add `POST /api/sessions/{id}/end`, which ends any open
session by its id, as the Session Service of `DC` 4.5 describes:

- It records `endedAt` in the session through the Dataset Store.
- If the session is the loaded one, in either role (capture or review), it
  also tells the Capture Controller to stop and clears the session in the
  Application State, exactly as ending the loaded session does today.
- If another session is loaded, that session and the state are left alone.
- An already ended session gives `session_ended` (409); an unknown id gives
  `not_found` (404).
- `POST /api/sessions/current/end` keeps working and uses the same code path
  for the loaded session (`no_session`, 409, when none is loaded).

**Acceptance criteria.**

- [ ] Ending an open session that is not loaded writes its `endedAt`, leaves the
      state unchanged, and the next `GET /api/sessions` shows it as ended.
- [ ] Ending the session loaded for capture stops capturing (the capture state
      becomes STOPPED), clears the session in the state and records `endedAt`.
- [ ] Ending the session loaded for review unloads it and records `endedAt`.
- [ ] Ending a session while a different one is loaded leaves the loaded one and
      the capture state unchanged.
- [ ] An ended or unknown session returns the stated errors and changes nothing.
- [ ] An ended session cannot be resumed (the existing refusal) and its samples
      can still be reviewed and edited.
- [ ] `POST /api/sessions/current/end` behaves as before.
- [ ] No camera is needed to end a session that is not loaded.

**Implementation notes.** Extend `services/session.py` so that End takes a
session id, with the current-session endpoint as a shortcut; add the route in
`server.py`.

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
      handedness (left or right) and optional notes. Continuing is disabled
      until the author and handedness are set. It starts no session: it keeps
      the details and moves on to Calibrate.
- [x] Lists existing sessions (name, author, date, sample count, open or ended)
      with a Review button, and a Resume button for open sessions only.
- [x] Each session has an Edit button that opens a form for its name and
      notes (DC-A13), enabled for every session, and the notes are shown under
      the name.
- [x] A refused resume (an ended session, or no camera at all) shows the reason
      from the error. A resume warning about a different camera mode is shown.
      A resume that succeeds opens the Calibrate page for the camera check
      (DC-A15), not Record.
- [x] While a session is loaded for capture, the form and the Resume of other
      sessions are disabled and a notice says to end the session first. The
      Resume of the loaded session stays enabled: it resumes a paused capture
      (fresh countdown) and opens Record.

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
- [x] A Start session button creates the session from the details given on
      Setup and opens Record. It is disabled, with a pointer back to Setup,
      until those details exist. While a session is loaded for capture the
      panel instead names the session and offers End session, so the user is
      never left without a way to calibrate.

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
- [x] The detail view stays in the window while the list scrolls (sticky, and
      scrollable itself when taller than the window), so the selected sample
      is always visible beside the list. On a narrow window, where the two
      stack, it scrolls with the page. (Replaced by DC-U17: the list is a grid
      of thumbnails in a scrolling pane, and the detail stays beside or above
      it.)

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
      highlighted. When the sample details say `mirrored`, the video and the
      path are flipped together to match the live view.
- [x] Full screen can be entered and left.
- [x] The video is hidden by default, so only the path movement is shown on a
      black background. A Show video / Hide video button toggles it. The
      video keeps playing underneath and the highlighting and controls work
      as before. The choice carries over to the next sample scrubbed, and is
      forgotten when the page is reloaded (it is not stored).
- [x] The view is offered only for a sample with a clip. (Changed by DC-U14:
      it is now offered for every sample, and without a clip it replays the
      path.)

**Implementation notes.** `static/app/scrub.js`. Use a `<video>` element and a
canvas on top. Frame positions come from the sample's `positions` and
`gestureStartS`.

### DC-U8 No-camera message

- **Type**: fix
- **Status**: Completed
- **Depends on**: DC-U2
- **Requirements**: R1.1
- **Design**: DC 4.1

**Description.** Found in manual test 0.3 (`manual-tests.md`, section 4). When
no camera can be opened, the Setup page says only "No cameras were found." and
the state says "No camera is in use". On macOS the usual cause is that camera
access was denied to the terminal app, and the page does not say so. Replace
the message with one that names the likely causes and how to fix each, so the
user does not have to read the terminal output to find out.

**Acceptance criteria.**

- [x] When the camera list is empty, the Setup page shows a message that names
      the likely causes: the camera is unplugged, another application is using
      it, and camera access is denied to the application that runs this one.
- [x] On macOS the message gives the place to fix the permission (System
      Settings, Privacy and Security, Camera) and says that the terminal app
      may have to be restarted afterwards. On other systems the permission
      sentence is left out.
- [x] The message offers a Retry button that fetches the camera list again, so
      the user does not have to reload the page after fixing the problem.
- [x] The message is not shown while the list is still loading, and it is
      replaced by the camera list as soon as a camera is found.
- [x] A test covers the empty list, the list with cameras and the Retry.

**Implementation notes.** `static/app/setup.js` (the hint at the empty list).
Detecting a denied permission for certain needs a macOS framework call
(AVFoundation through pyobjc), which is not a dependency, so name the causes
rather than claim one. The OpenCV message that repeats in the terminal, once
per probed camera index, comes from native code and is not part of this task;
it can be reduced later by stopping the scan after the first denied index if
that proves possible.

### DC-U9 Delete without an error notice

- **Type**: fix
- **Status**: Completed
- **Depends on**: DC-U5
- **Requirements**: R5.3
- **Design**: DC 4.1

**Description.** Found in manual test 5.3 (`manual-tests.md`, section 4).
Deleting a sample on the Review page works, but a notice then shows "no sample
<id>" with the code `not_found`. The likely cause is that the delete changes
the samples revision in the state, and the page then asks for the details of
the selected sample, which is the one just deleted, before the selection has
moved to a neighbour. Find the cause, and make the delete leave no notice.

**Acceptance criteria.**

- [x] The cause is found and written in the implementation notes, after
      reproducing the notice (a test or a recorded run).
- [x] Deleting the selected sample moves the selection to the next sample, or
      to the previous one at the end of the list, and shows no notice.
- [x] Deleting a sample from another browser tab, or by the command line,
      while a page has it selected, also leaves no notice, and the selection
      moves on.
- [x] A real failure of a request (for example the server is down) still
      shows a notice.
- [x] A test covers the delete of the selected, the last and the only sample.

**Implementation notes.** `static/app/review.js`: the effect that fetches the
details of the selected sample runs on `selected` and `samplesRevision`, and
`load` moves the selection. Compare `DC-U5`'s `nextSelection`. A 404 for a
sample that is no longer in the list can be ignored, but only for the sample
that was deleted, not for all requests.

**Cause (confirmed).** Reproduced with a fake server in a browser-like test:
after the delete the new revision reaches the page first, the effect asks for
the details of the selected sample, which is already gone, and the 404 became a
notice, while the list reload moved the selection on a moment later. The
details request now treats a 404 as "gone" and shows nothing; other failures
still show a notice.

### DC-U10 Review grid and Space key

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-U5, DC-U9
- **Requirements**: R5.1, R5.3
- **Design**: DC 4.1

**Description.** Two changes to the Review page, from manual testing. The path
images (tiles) form a horizontal strip, so the user has to scroll sideways to
see them. Show them as a grid that wraps at the page width, so many samples
are visible at once. Also, reject and restore move to the Space key, which is
easy to reach next to the arrow keys.

**Acceptance criteria.**

- [x] The tiles wrap onto new rows at the page width, with no horizontal
      scroll at any window width, and the page scrolls vertically when there
      are more tiles than fit.
- [x] The selected tile is always scrolled into view, also after stepping with
      the arrow keys, and is clearly marked. A rejected tile is shown dimmed as
      before.
- [x] Left and Right still select the previous and next sample in capture
      order, across rows. Up and Down move the selection by one row.
- [x] Space rejects the selected sample if it is accepted, and restores it if
      it is rejected. The letter `r` still does the same.
- [x] A shortcut can be bound to more than one key: the `reject` setting takes
      a single key or a list of keys, the default is `[" ", "r"]`, and the
      buttons show the first key.
- [x] Space does not scroll the page, and does nothing while a button, a field
      or a dialog has the focus, so it never acts twice.
- [x] Tests cover wrapping, the selection by row, Space and `r`, and the focus
      guard.

**Implementation notes.** `static/app/review.js` (the `.strip` element and its
CSS in `static/style.css`), `static/app/shortcuts.js` (`isTyping` already
ignores fields; extend it to buttons for Space), `Shortcuts` in `settings.py`
and `config/data-collection.yaml`. Page size for the sample list may have to
change if the grid is large (DC-A8).

### DC-U11 Notices and page polish

- **Type**: fix
- **Status**: Completed
- **Depends on**: DC-U1, DC-U2
- **Requirements**: none (usability)
- **Design**: DC 4.1

**Description.** Three small problems found in manual testing. A "Loading..."
text shows at the bottom of every page: `index.html` puts it inside the
element the page is drawn into, and drawing adds to that element and does not
replace what is in it. Notices at the top of the page stay until the user
dismisses them, so they pile up. The camera selector and the refresh button on
the Setup page are not aligned.

**Acceptance criteria.**

- [x] The "Loading..." text is gone from every page once the application has
      started. It may still show before the scripts run, and then disappears
      when the first page is drawn.
- [x] A notice dismisses itself after 6 seconds, and shows a thin bar that
      shrinks to show the time left. Pausing the pointer over a notice stops
      the timer, and it restarts when the pointer leaves. Clicking dismiss
      still removes it at once.
- [x] A notice for an error that is repeated (the same message and code)
      shown while the first is visible restarts the timer of the first and
      does not add another.
- [x] The camera selector and the refresh button on the Setup page have the
      same height and share a baseline, at any window width.
- [x] The shrinking bar respects the reduced motion setting of the browser:
      the notice still disappears, and the bar is not animated.
- [x] Tests cover the timer, the pause and the repeat.

**Implementation notes.** `static/index.html`, `static/app/notices.js` (an
`expiresAt` per item, and a timer owned by the component in `main.js`), CSS in
`static/style.css`, and the selector row in `static/app/setup.js`.

### DC-U12 Save to the loaded profile

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-U3
- **Requirements**: R1.6
- **Design**: DC 3.3, 4.1

**Description.** On the Calibrate page the user can only save the settings
under a name typed into a field. To update the profile that is already loaded,
the user has to type its name again. Add a button that saves the current
settings over the loaded profile.

**Acceptance criteria.**

- [x] When a profile is loaded, the Profiles panel shows a button "Save to
      <name>", beside the name field, that saves the current settings under
      that name with the same request as the existing save.
- [x] Saving over a profile replaces it, so the button asks for no
      confirmation, and shows a short "Saved to <name>." next to the button (an
      inline confirmation, because the notices at the top are for errors).
      (The name field still asks nothing for a new name.)
- [x] The button is not shown when no profile is loaded, and is disabled while
      the settings are locked by a session.
- [x] After the settings differ from the loaded profile, the panel says so
      ("changed since loaded"), so the user knows a save would change it.
      After a save, or a load of a profile, it does not.
- [x] Typing a name that already exists in the name field and pressing Save
      overwrites it as before.
- [x] Tests cover the button, its absence without a loaded profile, and the
      changed marker.

**Implementation notes.** `static/app/calibrate/profiles.js` (`loaded` comes
from `snapshot.settings.profile`). For the changed marker compare the state's
vision and motion settings with the profile as returned by the server; if
there is no endpoint that returns the profile's settings, add one in DC-A5.

**Done as.** `GET /api/profiles/{name}` returns the stored vision and motion
settings, and the panel compares them with the state. Saving a profile (under
any name) also makes it the loaded profile, unless a session has locked the
settings, so "Save to <name>" and the changed marker follow what was saved.

### DC-U13 Keyboard scrubbing

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-U7
- **Requirements**: R7.5
- **Design**: DC 4.1

**Description.** The scrubbing view can only be used with the mouse. Add
keyboard control, so a sample can be examined with the hands on the keyboard.

**Acceptance criteria.**

- [x] Left and Right step one frame back and forward, and Shift with an arrow
      steps ten frames.
- [x] Space plays and pauses, and does not scroll the page or press a focused
      button.
- [x] Home and End go to the first and the last frame.
- [x] F enters and leaves full screen, and V shows and hides the video.
- [x] Escape leaves full screen first (as the browser does) and, pressed again,
      closes the view.
- [x] The controls show their keys, for example `Space`, as the Review page
      does, and the keys are listed in a short line under the view.
- [x] The keys do not act while a field has the focus. The keys of the Review
      page are not active while the view is open.
- [x] Tests cover each key, the guard and the closing of the view.

**Implementation notes.** `static/app/scrub.js` has no key handling today. Use
`createShortcuts` so keys come from the settings (new actions `scrubPlay`,
`scrubBack`, `scrubForward` and so on), with the defaults above. A full-screen
request must come from a key or click event handler.

### DC-U14 Scrubbing without a clip

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-U7, DC-U13
- **Requirements**: R6.9, R7.5
- **Design**: DC 4.1

**Description.** A sample without a clip cannot be scrubbed today. The sample
still has its positions, with a time for each, so its path can be replayed on a
black background without any video. This changes the criterion of DC-U7 that
says the view is not offered for a sample without a clip: it is now offered
always, and only the video is missing.

**Acceptance criteria.**

- [x] The scrubbing view opens for a sample without a clip, from the Review
      and Browse pages, and shows its path on a black background, with the part
      up to the current position highlighted.
- [x] Playback follows the positions' times: it runs from the first position to
      the last in the time the gesture took, and a gap where the tip was not
      found shows as a pause.
- [x] Stepping goes from one stored position to the next. The slider covers the
      gesture's duration, and the keys of DC-U13 work.
- [x] The Show video button is disabled and says that there is no clip. V does
      nothing.
- [x] For a sample with a clip the view is as before.
- [x] DC-U7's criterion is updated to say that the view is offered for every
      sample, and `manual-tests.md` step 7.4 expects the scrubbing view to work
      without video.
- [x] Tests cover playback timing with a gap, stepping, and the disabled
      button.

**Layout fix.** Found by the user: without a video the view showed only the
controls, with a zero-height picture. The box that holds the path sized itself
to its content, which was empty, and the surface inside it used a percentage
width, which resolves to nothing there (measured in Chrome: 0 by 0). The box
now has a definite width (`min(100%, 640px, 80vh` scaled by the frame's
shape`)`), measured in Chrome at three window sizes and two frame shapes.

**Implementation notes.** `static/app/scrub.js`: for a sample with a clip the
video's time drives the display (`countUpTo`); without one, a timer driven by
`requestAnimationFrame` plays the same role. Keep one code path for drawing.

### DC-U15 Wording, hover and resume-flow polish

- **Type**: fix
- **Status**: Completed
- **Depends on**: DC-U2, DC-U5, DC-A15
- **Requirements**: none (usability)
- **Design**: DC 4.1

**Description.** Four things found while testing. The camera line on Setup was
one long sentence ("In use: index:0, asked for ..."). The text of the camera
check read badly. Buttons gave no sign that they could be pressed. And on the
Review page of a resumed session, the "Resume capturing" button failed with
"Capture is not paused", because the camera had not been checked yet.

**Acceptance criteria.**

- [x] The Setup page shows two lines for the camera: "Requested: <mode>" and
      "Actual: <mode>". The actual mode is green when it is what was asked for,
      amber when it is not, and plain while the frame rate is being measured.
      The warning about a different mode stays.
- [x] The camera check text reads: "You are resuming session <name>. All
      settings are locked to those used during the original recording, except
      for the camera. Please select the same camera you used previously to
      ensure consistent tracking. If unsure, end this session and start a new
      one with the desired camera with appropriate calibration settings." It has
      no other paragraph.
- [x] Every enabled button changes its border and background when the pointer
      is over it, and moves a pixel when pressed. Disabled buttons do not. The
      dismiss cross on a notice changes only its colour.
- [x] On the Review page of a session loaded for capture, the top button reads
      "Check the camera first" and goes to Calibrate while the camera is
      unchecked, reads "Go to Record" and goes to Record when capture has not
      started, and reads "Resume capturing" only when capture is paused. The
      server refuses `POST /api/recording/resume` with 409 `camera_check` and
      the same message as for start while the check is due.
- [x] Tests cover each of these.

**Implementation notes.** `CameraPanel` in `static/app/setup.js`,
`CameraCheck` in `static/app/calibrate/index.js`, the `button` rules in
`static/style.css`, `Review` and `CaptureController.post_resume`.

### DC-U16 Accepted and rejected markers

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-U5, DC-U6
- **Requirements**: R5.1
- **Design**: DC 4.1

**Description.** The thumbnails of the Review page showed a rejected sample only
by dimming it. Mark both states plainly, with colour and a symbol so that it
does not rely on colour alone.

**Acceptance criteria.**

- [x] Each tile on the Review page has a green border and a green "✓" in its
      corner when the sample is accepted, and a red border, a red "✕" and a
      dimmed picture when it is rejected. The selected tile keeps its own
      border colour. The tile's label still gives the status in words.
- [x] The thumbnails in the Browse table have the same marker and border.
- [x] The marker stays inside the tile (checked in Chrome).

**Implementation notes.** `statusMark` in `static/app/review.js`; `.mark`,
`.thumbwrap` and `.strip .thumb.accepted|rejected` in `static/style.css`.

### DC-U17 Browse grid layout

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-U6, DC-U10, DC-U16
- **Requirements**: R7.1, R7.2, R7.3, R7.4
- **Design**: DC 4.1

**Description.** The Browse page listed samples in a table, and the selected
sample's detail scrolled out of sight (or was cramped beside it). Show the
samples as a grid of thumbnails in a pane of their own, with the selected
sample in a panel that stays put: the picture, the buttons that change what it
shows, the details, and the actions pinned at the bottom. Build the grid and
the panel as shared pieces (`static/app/sampleview.js`), so that the Review
page can use them next (DC-U18, to be written).

**Acceptance criteria.**

- [x] Workspace pages (Browse, so far) use the whole height of the window: the
      page does not scroll, and the grid pane does. Above the grid are the
      per-label progress (one row) and the filters (one row, which scrolls
      sideways in a narrow window).
- [x] The grid shows each sample as a tile: thumbnail, accepted or rejected
      marker and border (DC-U16), and the label's name. (It was in pages of 100;
      DC-U18 replaced the pages with infinite scrolling.)
- [x] The selected sample is shown in a panel beside the grid, about 40% of the
  width: the picture (path or overlay), the buttons Path only, Overlay (or the
  disabled "Video unavailable") and Scrub, the details, and, pinned at the
  bottom, Relabel, Reject or Restore, and Delete. The picture leaves room for
  the details, which scroll if they are tall.
- [x] In a window narrower than 900 px the panel sits above the grid, and only
      the grid scrolls. In a window that is also shorter than 640 px the page
      scrolls instead, and the panel stays stuck to the top of it.
- [x] The first sample is selected when the grid loads. Browse has the keys of
  Review: Left and Right, Up and Down by a row, Space or `r` to reject or
  restore, Backspace to delete, `v` for the overlay, `s` to scrub, and the
  digits to relabel. Left and Right past the end of a page go to the next or the
  previous page.
- [x] Scrub video or path replaces the workspace and takes over the keys, as on
      the Review page. Deleting a sample leaves no notice and selects the next
      one.
- [x] The layout was checked in Chrome at 1400x800, 1000x700, 700x800 and
      700x500, with the real page and made-up data, and with six labels: the
      per-label progress is a row of small cells (name and count above, the bar
      below) that wraps as needed.
- [x] Tests cover the grid, selection, the keys, paging, filters, delete and
      scrub.

**Implementation notes.** `SampleGrid`, `SampleDetail`, `useSampleDetails`,
`columnsOf` and `nextSelection` in `sampleview.js`; `Browse` in `browse.js`;
the `.shell.fill`, `.workspace`, `.tiles` and `.detail-pane` rules in
`style.css`. A page asks for the full-height frame with `fill: true` in `PAGES`
(`nav.js`).

### DC-U18 Infinite scroll and the Review workspace

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-U17, DC-U5, DC-U15
- **Requirements**: R5.1, R5.2, R5.3, R5.4, R7.1
- **Design**: DC 3.4, 4.1

**Description.** Replace the pages of the Browse grid with infinite scrolling,
and rebuild the Review page on the same workspace, so the two pages share one
set of code. Also replace the placeholder spells with the real list.

**Acceptance criteria.**

- [x] The sample workspace (`static/app/workspace.js`) loads a chunk of 100
      samples at first, and the next chunk when the end of the grid comes
      within about 600 px of the part that can be seen, whether the grid pane
      scrolls or (in a narrow, short window) the page does. It asks for nothing
      past the last sample. The text above the grid says how many match, and how
      many are shown while more remain. There are no paging controls.
- [x] When the samples revision changes, the part already loaded is read again
      (in as few requests as the server's page size allows), so the list stays
      what it is on the server and keeps its place. A change of filter starts
      the list again.
- [x] Left, Right, Up and Down go on past the end of what is loaded: the next
      chunk is loaded and the move continues in it. Keys that repeat faster than
      the page draws each move from where the last one went.
- [x] The Review page is the workspace limited to the loaded session, newest
  first, with the newest sample selected. Above the grid it has: Resume
  capturing (or Close review, "Check the camera first", "Go to Record", as in
  DC-U15), Pause, and the selector of the label for the next captures; and the
  notice that the last gesture is still saving. A sample captured while Review
  is open appears at the top and the selection stays where it was. A session
  with no samples says so; with no session loaded the page says that.
- [x] The panel shows the sample's number in its session ("#42").
- [x] `config/labels.yaml` lists the real spells in this order: Alohamora,
      Aparecum, Herbivicus, Silencio, Revelio, Expelliarmus, Reparo (ids
      `alohamora`, `aparecum`, `herbivicus`, `silencio`, `revelio`,
      `expelliarmus`, `reparo`). The tests that used the placeholder spells use
      their own labels, so they do not depend on this file.
- [x] The infinite scroll was checked in Chrome with 450 made-up samples: the
      grid loaded 100, 200, 300, 400 and then the last 50 as it was scrolled,
      and the page itself did not scroll.
- [x] Tests cover the loading, the keys, the refresh, the Review controls and
      the resume flows.

**Implementation notes.** `SampleWorkspace`, `useSampleList` and `queryFor` in
`workspace.js`; `Browse` in `browse.js`; `Review` in `review.js`. The old Review
layout (the strip of thumbnails above or below a panel) is gone. The new Review
shows the newest sample first (it used to be in capture order, with the latest
last).

**Fix after testing.** Deleting a second sample failed with "query.pageSize:
Input should be a valid integer". The list is read again after every change,
asking for as many samples as are loaded; I had assumed that to be a whole
number of chunks of 100, but a few deletes make it 116, and 116 / 100 * 100
is 115.99999999999999 in floating point, which the server refuses. The amount is
now rounded up to whole chunks with integer arithmetic, and the next page is
computed the same way. A scratch test deletes five samples in a row from a list
of 117.

### DC-U19 Point counts and one page width

- **Type**: feat
- **Status**: Completed
- **Depends on**: DC-U17, DC-U7
- **Requirements**: R7.2, R7.5
- **Design**: DC 4.1

**Description.** Two requests from testing. Show how many points are tracked in
each sample, so that very short or very long gestures stand out: on each
thumbnail, and in the scrubbing view as the current point out of the total.
And give every page the same width, the one that Browse and Review already had.

**Acceptance criteria.**

- [x] Each entry of the sample list has `points`, the number of tracked points
      of the gesture (the positions in the sample; a frame where the tip was not
      found has none).
- [x] Each thumbnail shows its number of points in the top left corner, and the
      tile's label says it ("... 26 points"). The details panel shows the same
      number as "Points".
- [x] The scrubbing view shows "Point <n> / <total> · <time> s", where n counts
      the points up to the current time of the video or of the path replay. With
      a clip it is 0 before the gesture and the total after it.
- [x] Every page is as wide as Browse and Review were (1700 px at most), instead
      of 1100 px for Setup, Calibrate and Record. Checked in Chrome at 1600 px
      for Setup and Calibrate.
- [x] Tests cover the list field, the badge and the readout.

**Implementation notes.** `SampleSummary.points` in `services/library.py`;
`SampleGrid` in `sampleview.js`; `pointReadout` in `scrub.js`; `.shell` in
`style.css`. The readout is built as one string, because the template engine
drops the space around a line break. A point is one tracked frame, so the count
can be lower than the number of video frames of the gesture; the clip's own
frame count is not stored.

### DC-U20 Dataset selection and merge

- **Type**: feat
- **Status**: Not started
- **Depends on**: DC-U2, DC-A19
- **Requirements**: R2.5, R2.10
- **Design**: DC 4.1, 5.2

**Description.** On the Setup page, show the dataset in use and let the user
choose another, create one, or merge datasets.

**Acceptance criteria.**

- [ ] The Setup page shows the dataset in use (from the state) and a list of the
      datasets from `GET /api/datasets` with their session and sample counts;
      choosing one uses `PUT /api/dataset`, and the session list updates.
- [ ] A New dataset form takes a name, shows the error for an invalid or
      existing name, and creates the dataset.
- [ ] A Merge dialog lets the user select source datasets and a target (an
      existing dataset or a new name), choose whether conflicts are skipped or
      replaced and whether clips are skipped, and shows the per-session result
      afterwards.
- [ ] While a session is loaded, these controls are disabled and a notice says
      to end or hold the session first.
- [ ] The dataset in use is visible in the page header on every page.

**Implementation notes.** `static/app/setup.js` and the shell of DC-U1.
Merging replaces data, so ask for a confirmation before a merge with the
replace option.

### DC-U21 End a session from Record, Review and Setup

- **Type**: feat
- **Status**: Not started
- **Depends on**: DC-A20, DC-U2, DC-U4, DC-U5
- **Requirements**: R2.7
- **Design**: DC 3.2, 4.1

**Description.** Let the user end a session where they are, without going to
the Calibrate page or selecting the session first.

- **Record and Review pages**: an End session button beside Pause (the Record
  page gets both buttons; the Review page already has Pause).
- **Setup page**: an End session button on every open session in the list,
  loaded or not.
- Ending is final, so every button first asks for confirmation. The dialog
  names the session and says that it cannot be resumed afterwards, though its
  samples can still be reviewed and edited.
- On confirmation the page calls `POST /api/sessions/{id}/end` (or
  `POST /api/sessions/current/end` for the loaded session). From Record and
  Review it then opens Setup, as Pause does. On Setup the list is fetched again
  and the session shows as ended, without Resume or End.
- The button is a normal button: no keyboard shortcut ends a session.

**Acceptance criteria.**

- [ ] Record shows Pause and End session; Review shows End session beside
      Pause.
- [ ] On the Record page, clicking End session does not also pause capturing
      (the page's click-to-pause ignores buttons).
- [ ] Each button opens the confirmation; cancelling changes nothing;
      confirming ends the session.
- [ ] After ending from Record or Review, the user is on Setup and the session
      is listed as ended.
- [ ] On Setup, every open session, loaded or not, has End session; ended
      sessions do not. Ending one updates the list at once.
- [ ] Ending a session that is on hold works without loading it.
- [ ] A failed request shows its error message and leaves the page as it was.

**Implementation notes.** `static/app/record.js`, `review.js` and `setup.js`;
reuse the confirmation used by the Calibrate page's End session button and by
session deletion if there is one.

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
- **Status**: Completed
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
      camera check on resume, merge, and the missing-clip behavior.
- [x] It has been run on macOS, and the results are recorded in the document
      with a column left for Linux (filled in by DC-S2).
- [x] The live view keeps up with the camera, and no dropped frames corrupt
      tracking (N3).
- [x] Problems found are recorded as follow-up tasks.

**Progress.** The checklist is written and was run on macOS with Chrome, a
built-in camera, an external webcam and a phone camera
(`data-collection/docs/manual-tests.md`). Most steps passed in a step-by-step
pass. The failure it found (step 6.4) and the smaller problems became tasks
DC-U8 to DC-U19, DC-A14 to DC-A17, all implemented. The steps added afterwards
were checked informally, by repeated use of the application with the changes
in place, not step by step (marked `pass*`). Not run: conditions B and C of the
calibration steps and step 6.5, for lack of a setup. The Linux column is left
for DC-S2.

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

**Deferred (2026-11-15).** Not started on purpose: the tuning needs real
gestures of the real spells, and none are recorded yet (the test data was
deleted when the placeholder spells were replaced). The plan, for when a first
batch exists (about 30 to 50 gestures per spell):

1. Build a replay-and-sweep tool that runs the stored clips of a data folder
   through the Tracker and the Segmenter with different motion settings. A
   sample's clip holds the gesture and 2 seconds either side of it, so the tool
   can count the gestures it finds against the known one.
2. Add a few continuous recordings of the wand held still (any camera
   application will do, played back through the video file source) to count
   false gestures, because saved samples only hold accepted gestures.
3. Score missed and spurious gestures for a grid of values and propose new
   defaults, with the method and results written down as the criteria say.

Until then the provisional defaults stand, and each session can use the guided
measurement on the Calibrate page, which records the settings it used.
