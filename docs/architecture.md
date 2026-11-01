# Architecture

Status: Draft v2. Covers the whole system. Component designs are listed in
section 5.3.

## 1. Introduction

### 1.1 System overview

The system recreates the magic wand experience of the Harry Potter area at
Universal Studios. A user waves a wand in front of a camera. The system
recognizes the motion as one of several predefined gestures (spells) and
responds with an action: a visual effect on screen, a sound, or, if time
permits, a physical device.

The wand is a brightly colored ping pong ball on a stick, so that OpenCV color
filtering can find it in the video. Four stages turn video into an action:

1. **Vision** finds the ball in each frame.
2. **Motion detection** turns the ball's positions into gestures.
3. **Gesture classification** names the spell a gesture represents.
4. **Action trigger** performs the effect for that spell.

The classifier is a machine learning model, so it must be trained on labeled
examples. The system therefore has two modes that share the first two stages:

- **Inference**: live video goes through all four stages.
- **Data collection**: live video goes through the first two stages, and a
  person labels and stores the resulting gestures as a training dataset
  (about 1,000 samples per gesture).

The project is the term project for EECE5644 (Machine Learning and Pattern
Recognition).

Terms used throughout:

- **Tip**: the midpoint of the ping pong ball.
- **Gesture**: one deliberate motion of the tip, bounded by idle at the start
  and end.
- **Sample**: a recorded gesture stored in a dataset.
- **Session**: one run of data collection by one person with fixed settings.
- **Label**: the name of a spell.

### 1.2 What this document covers

- Section 2, system flow: how data moves through inference, data collection
  and training.
- Section 3, subsystems: what each subsystem does, and what the shared library
  contains.
- Section 4, conventions: technical decisions, common data structures and
  rules for handling datasets.
- Section 5, folder organization: how the repository is laid out.

## 2. System Flow

### 2.1 Inference

```text
 +--------+ frame  +--------+ tip position +-----------+ gesture +----------+
 | Camera |------->| Vision |------------->|  Motion   |-------->| Gesture  |
 +--------+        +--------+ + timestamp  | detection | vectors |classifier|
                                           +-----------+         +----+-----+
                                                                      |
                                                       spell + confidence
                                                                      v
                                                                 +---------+
                                                                 | Action  |
                                                                 | trigger |
                                                                 +---------+
```

1. The camera delivers frames. Each frame gets a timestamp.
2. Vision finds the tip in the frame and outputs its position with the
   frame's timestamp.
3. Motion detection watches the stream of tip positions. It converts movement
   between consecutive frames into vectors (direction and speed). A gesture
   starts when the tip's speed rises above a threshold and ends when it falls
   below one. Motion that lasts too long or covers too little distance is
   discarded.
4. The classifier receives the vectors of one gesture and outputs a spell and
   a confidence score.
5. The action trigger performs the action for the spell. If the confidence is
   below the minimum threshold, no action is performed and the user is told
   the gesture was not recognized.

### 2.2 Data collection

```text
 +--------+ frame  +--------+ tip position +-----------+ gesture +-----------+
 | Camera |------->| Vision |------------->|  Motion   |-------->|   Data    |
 +--------+        +--------+ + timestamp  | detection |positions|collection |
                                           +-----------+         +--+-----+--+
                                                                    ^     |
                                        calibrate, label, review    |     v
                                        +--------+                  |  +-------+
                                        |  User  |<-----------------+  |Dataset|
                                        +--------+                     +-------+
```

1. Vision and motion detection run exactly as in inference, with the same
   code.
2. Before recording, the user calibrates vision and motion detection for the
   current camera, lighting and background.
3. Each gesture that motion detection reports is turned into a sample with
   the label the user chose. The sample stores the tip positions of the
   gesture, not the vectors.
4. The user reviews samples and can reject, relabel or delete them.
5. Samples are written to the dataset together with the settings used to
   record them.

### 2.3 Training

```text
 Dataset --> load accepted --> compute motion --> train --> Trained classifier
 (disk)      samples           vectors            model     (used in inference)
```

Training reads the dataset, computes motion vectors from the stored positions
with the shared library, and trains the classifier. The trained classifier is
what the inference flow loads.

### 2.4 What the flows share

Vision and motion detection are implemented once, in the shared library, and
both flows run that implementation. A gesture seen live therefore has the same
form as a gesture the classifier was trained on. Vectors are computed from
positions at load time rather than stored, so changing how vectors are built
does not require re-recording.

## 3. Subsystems

### 3.1 Vision

Finds the tip in each frame by filtering for the ball's color and locating the
resulting shape. Input: camera frames. Output: tip position and timestamp (or
"not found") per frame. Its color settings are tuned for each camera and
lighting condition by calibration.

### 3.2 Motion detection

Tracks the tip's speed to separate idle from motion, cuts the stream into
gestures, and builds motion vectors. Input: tip positions. Output: gestures,
and the live state (moving or idle). Its thresholds and time window are
settings that calibration adjusts.

### 3.3 Gesture classification

A model trained on labeled gestures. Input: the motion vectors of one gesture.
Output: a spell and a confidence score. Not yet designed.

### 3.4 Action trigger

Maps a recognized spell to an effect: on-screen visual, sound, or device
control. Applies the confidence threshold. Not yet designed.

### 3.5 Data collection

An application for recording, labeling and reviewing gestures. It hosts vision
and motion detection, adds calibration, the labeling workflow and review, and
writes datasets. Design: `data-collection/docs/design.md`.

### 3.6 Shared library

The library (`wand-core`) holds everything that must be identical in
data collection and inference:

- frame sources: a live camera and a recorded video file;
- the tracker (vision) and its settings;
- the segmenter and vector builder (motion detection) and their settings;
- the color and motion calibrators that derive those settings;
- the dataset store: reading, writing, export and merge of datasets;
- the path renderer, which draws a gesture as an image.

Each application imports the library and supplies what the library does not
have: the camera, the user interface and the application logic. The library
never opens a camera or draws a user interface by itself, so it can be tested
with recorded video and synthetic data. Design: `lib/docs/design.md`.

## 4. Conventions

### 4.1 Technical decisions

| Decision | Reason |
|---|---|
| Single mono-repo | Components share code and evolve together |
| Python 3.11 or later | OpenCV and ML ecosystem |
| OpenCV color filtering | The wand is a brightly colored ball |
| One shared library | Identical processing for training and inference |
| uv workspace, ruff | Reproducible environments, one style |
| YAML for configuration | Human-edited, supports comments |
| JSON for recorded data | Small files, readable, safe to edit atomically |
| macOS and Linux | Windows is best effort and untested |

Tooling and workflow rules are in `docs/standards.md`.

### 4.2 Common data structures

All subsystems use these structures. Field-level definitions are in
`lib/docs/design.md` and `docs/data-storage.md`.

- **Frame**: an image with a timestamp in seconds.
- **Tip detection**: timestamp, tip position, ball radius, and whether the
  ball was found.
- **Position**: horizontal and vertical position as fractions of the frame
  width and height (0 to 1, vertical axis pointing down). The frame size is
  stored beside it.
- **Distance and speed**: in frame-heights, and frame-heights per second. The
  horizontal fraction is scaled by the frame's aspect ratio so both axes use
  one unit. Thresholds in these units do not depend on camera resolution.
- **Gesture**: a sequence of timestamped positions. Time is in seconds from
  the first position.
- **Motion vectors**: for each pair of consecutive positions, the displacement,
  the elapsed time and the speed. Always derived from positions.
- **Label**: a stable identifier and a display name. Everything refers to the
  identifier.
- **Sample and session**: the stored forms of a gesture and of a recording
  run, defined in `docs/data-storage.md`.
- **Classification result**: a label identifier and a confidence between 0
  and 1.

### 4.3 Dataset handling

Rules for handling datasets, and their layout and file formats, are in
`docs/data-storage.md`.

### 4.4 Configuration

All configuration is in `config/`.

| File | Contents | In git |
|---|---|---|
| `labels.yaml` | Spell labels: identifier, display name | Yes |
| `vision.yaml` | Default vision settings | Yes |
| `motion.yaml` | Default motion settings | Yes |
| `data-collection.yaml` | Data collection settings | Yes |
| `*.local.yaml` | Per-machine override of the file with that prefix | No |
| `profiles/` | Saved calibration profiles | No |

Detection settings resolve in this order, later steps overriding earlier ones:
the default file and local override; a loaded calibration profile; adjustments
made during calibration. A session records the resolved settings.

## 5. Folder Organization

### 5.1 Repository layout

```text
magic-wand/
  pyproject.toml      uv workspace root; shared tool settings (ruff)
  uv.lock             resolved dependency versions for the workspace
  CLAUDE.md           project and agent instructions
  config/             configuration (section 4.4)
  docs/               system-wide documentation
  lib/                shared library
    docs/
    src/              library code
    tests/
  data-collection/    data collection application
    docs/             requirements, design, tasks
    src/              application code
    tests/
  data/               default dataset location; not in git
```

Later components, such as the classifier and the run-time application, are
added as further top-level folders and workspace members, each with its own
`pyproject.toml`, `docs/`, `src/` and `tests/`.

### 5.2 Rules

- Shared logic lives in `lib/`, not in a component.
- A component depends on `lib/` through the workspace, never by copying code.
- Each component owns its documentation, tests and package settings.
- System-wide documents and cross-cutting rules live in `docs/`.

### 5.3 Documentation map

- `docs/architecture.md`: this document.
- `docs/data-storage.md`: dataset layout, formats, merge and export.
- `docs/standards.md`: workflow, tooling, formatting and documentation rules.
- `docs/notes.md`: assumptions and constraints.
- `lib/docs/design.md`: shared library design.
- `data-collection/docs/requirements.md`: data collection requirements.
- `data-collection/docs/design.md`: data collection design.
- `data-collection/docs/tasks.md`: data collection work breakdown.
