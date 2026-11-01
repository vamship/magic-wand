# Architecture

> **Version** 3 · **Updated** 2026-11-01 · **Draft**

## 1. Overview

This document describes the architecture of the magic wand system. It covers:

- how data flows through the system when it collects data, trains a classifier
  and recognizes spells;
- the subsystems and what each is responsible for, including the shared
  library;
- the technical decisions, data formats and configuration that every
  component follows;
- how the repository is organized;
- the items still to be filled in before final submission.

After reading it you will understand how the system works end to end and know
where to find the detail for any part of it.

The system recreates the magic wand experience of the Harry Potter area at
Universal Studios. A user waves a wand in front of a camera. The system
recognizes the motion as one of several predefined gestures (spells) and
responds with an action: a visual effect on screen, a sound, or, if time
permits, a physical device.

Terms used throughout:

- **Tip**: the approximate center of the ping pong ball on the wand. It is the
  point whose motion the system tracks.
- **Gesture**: one deliberate motion of the tip, bounded by idle at the start
  and end.
- **Sample**: a recorded gesture stored in a dataset.
- **Session**: one run of data collection by one person with fixed settings.
- **Label**: the name of a spell.

The wand is a brightly colored ping pong ball on a stick, so that OpenCV color
filtering can find it in the video. Four stages turn video into an action:

1. **Vision** finds the tip in each frame.
2. **Motion detection** turns the tip's positions into gestures.
3. **Gesture classification** names the spell a gesture represents.
4. **Action trigger** performs the effect for that spell.

The classifier is a machine learning model, so it must be trained on labeled
examples. The system therefore has two modes that share the first two stages:

- **Inference**: live video goes through all four stages.
- **Data collection**: live video goes through the first two stages, and a
  person labels and stores the resulting gestures as a training dataset
  (about 1,000 samples per gesture).

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

Data collection has two sub flows: calibration, then recording.

#### 2.2.1 Calibration

```text
 Pick camera --> Color calibration --> Motion tuning --> Start session
                 click the tip in      watch live motion   settings are
                 a frozen frame        detection, adjust   locked and
                                       the thresholds      recorded
```

1. The user picks the camera.
2. For color calibration, the app shows a frozen frame and the user clicks the
   tip. The app derives the vision settings (the color range of the ball) from
   the click and shows what it detects.
3. For motion tuning, the app shows the live view with a clear indication of
   motion or idle and the tip's current speed. The user adjusts the thresholds
   until motion triggers as expected.
4. The user can save the result as a profile for the same camera and room.
5. Starting a session locks the settings and records them in the session.

#### 2.2.2 Recording

```text
 +--------+ frame  +--------+ tip position +-----------+
 | Camera |------->| Vision |------------->|  Motion   |
 +--------+        +--------+ + timestamp  | detection |
                                           +-----+-----+
                                                 | gesture (positions)
                                                 v
 +--------+  label, accept or reject    +-----------------+
 |  User  |<--------------------------->| Data collection |
 +--------+                             +--------+--------+
                                                 | sample: positions
                                                 | + label + status
                                                 v
                                        +-----------------+
                                        | Dataset (disk)  |
                                        +-----------------+
```

1. Vision and motion detection run as in inference, with the same code and the
   settings from calibration.
2. The user chooses a label and starts capturing. The app paces the captures
   with a countdown.
3. Motion detection reports a gesture. The app turns it into a sample: the
   tip positions of the gesture, not the vectors.
4. The sample takes the label the user chose and is accepted by default. The
   user reviews it and can reject, relabel or delete it.
5. The sample, with the user's label and status, is written to the dataset as
   part of the current session. Changes the user makes during review update
   the stored sample.

#### 2.2.3 What is stored

A dataset holds sessions, and each session holds samples:

```text
 Dataset
 +-- Session (one per recording run)
     |   name, author, handedness, notes
     |   camera and the mode it delivered
     |   settings used: vision settings, motion settings, clip padding
     |
     +-- Sample (many per session)
         |   label, status (accepted or rejected), handedness
         |   positions: the timestamped tip positions of the gesture
         |
         +-- Video clip (optional): the footage around the gesture
```

- A session belongs to one author and one camera, and has one set of
  settings. Every sample in the session was captured with those settings.
- A sample belongs to one session. It has one label, one status, one sequence
  of positions and at most one video clip.
- Labels are not part of the dataset. A sample refers to its label by
  identifier, and the labels are defined in the shared configuration
  (`config/labels.yaml`).
- The settings in a session start from the defaults in the configuration or a
  saved profile, as described under Configuration.

File formats and layout are in `docs/data-handling.md`.

### 2.3 Training

```text
 Dataset (teammate A) --+
 Dataset (teammate B) --+--> Merge --> Training dataset
 Dataset (teammate C) --+                   |
                                            v
                         Load accepted samples, compute motion vectors
                                            |
                                            v
                              Train --> Trained classifier
                                        (used in inference)
```

Each teammate records sessions on their own machine. The datasets are merged
into one training dataset; merging copies whole sessions and never changes
them (see `docs/data-handling.md`). Training loads the accepted samples,
computes motion vectors from the stored positions with the shared library, and
trains the classifier. The trained classifier is what the inference flow loads.

### 2.4 Shared Implementation

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
gestures, and builds motion vectors. Input: tip positions with timestamps.
Output: gestures, and the live state (moving or idle). Its thresholds and time
window are settings that calibration adjusts.

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

The library (`wand-core`) contains the components that must behave identically
in data collection and inference. Design: `lib/docs/design.md`.

- **Frame sources** deliver camera frames with timestamps, from either a live
  camera or a recorded video file, so the rest of the library runs the same on
  both.
- **Tracker** finds the tip in one frame using the vision settings. It is the
  vision subsystem.
- **Segmenter** watches the tip positions and decides when a gesture starts
  and ends, using the motion settings. It reports finished gestures, discarded
  motion and the live moving or idle state.
- **Vector builder** converts a gesture's positions into motion vectors.
- **Color calibrator** derives vision settings from points the user clicks on
  the tip.
- **Motion calibrator** proposes motion settings from a short measurement of
  the user holding still and then waving.
- **Dataset store** reads, writes, filters, exports and merges datasets in the
  format in `docs/data-handling.md`.
- **Path renderer** draws a gesture's path as an image.

Each application imports the library and supplies what the library does not
have: the camera, the user interface and the application logic. The library
never opens a camera or draws a user interface by itself, so it can be tested
with recorded video and synthetic data.

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

### 4.2 Data across the system

Data collection produces datasets and calibrated settings. This is how each
kind of data is used afterwards.

- **Samples** (timestamped tip positions with a label and status) are the
  training data. Motion vectors are computed from the positions by the shared
  library, the same way inference computes vectors from live positions.
- **Settings** (vision and motion) are recorded in every session so that the
  conditions of each sample are known. At inference the run-time application
  applies settings of the same kind, from a calibration done for the current
  camera and room, to live video. This keeps live gestures comparable to
  training gestures.
- **Labels** are identifiers. The classifier outputs a label identifier and a
  confidence between 0 and 1; the run-time application maps the identifier to
  its display name and the action to perform.
- **Video clips** help debug detection and classification. Inference does not
  use them.

Common formats used by every subsystem:

- **Position**: the tip's horizontal and vertical position as fractions of the
  frame width and height (0 to 1, vertical axis pointing down), with the frame
  size stored beside it.
- **Distance and speed**: in frame-heights and frame-heights per second. The
  horizontal fraction is scaled by the frame's aspect ratio so both axes use
  one unit. Thresholds in these units do not depend on camera resolution.
- **Time**: seconds. Within a gesture, time is measured from its first
  position.

Field-level definitions are in `lib/docs/design.md` and
`docs/data-handling.md`. The rules for handling datasets are in
`docs/data-handling.md`.

### 4.3 Configuration

All configuration is in `config/`.

- `labels.yaml` (in git): the spell labels. Each has an identifier, used in
  stored samples and in classifier output, and a display name shown to users.
  Data collection reads and edits it.
- `vision.yaml` (in git): default values for the vision settings, such as the
  ball's color range and size limits. Calibration starts from these.
- `motion.yaml` (in git): default values for the motion settings, such as the
  speed thresholds, the valid gesture duration and the minimum gesture size.
  Calibration starts from these.
- `data-collection.yaml` (in git): settings of the data collection
  application, such as where datasets are stored, the requested camera mode,
  the countdown length, the video clip padding and the keyboard shortcuts.
- `*.local.yaml` (not in git): a per-machine override. Values in
  `data-collection.local.yaml` replace those in `data-collection.yaml`, for
  example to use a different dataset folder.
- `profiles/` (not in git): calibration profiles that the user saved for a
  particular camera, room and lighting. A profile holds a full set of vision
  and motion settings.

The vision and motion settings used for recording are built up in steps. They
start as the defaults from `vision.yaml` and `motion.yaml`. Loading a profile
replaces them with the profile's values. Adjustments on the calibration
screens then change individual values. When a session starts, the final values
are copied into the session, so the data states the exact settings its samples
were captured with.

## 5. Folder Organization

```text
magic-wand/
  README.md           project introduction and documentation index
  pyproject.toml      uv workspace root; shared tool settings (ruff)
  uv.lock             resolved dependency versions for the workspace
  CLAUDE.md           project and agent instructions
  config/             configuration
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

Components not yet defined (see To Do) are added as further top-level folders
and workspace members, each with its own `pyproject.toml`, `docs/`, `src/` and
`tests/`.

## 6. To Do

Items to fill in before final submission:

- Gesture classification: model, training approach, confidence threshold, and
  where training code lives in the repository.
- Action trigger: the effects for each spell, and physical actuation if time
  permits.
- Run-time application: the component that runs inference end to end, and its
  folder.
- The final list of spells, to replace the placeholder labels.
- Final values for the motion settings, tuned from real recordings.
