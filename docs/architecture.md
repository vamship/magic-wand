# Architecture

> **Version** 10 | **Updated** 2026-11-26 | **Draft**

## 1. Overview

This document describes the architecture of the magic wand system. It covers:

- How data flows through the system when it collects data, trains a classifier
  and recognizes spells;
- The subsystems and the components in them, and what each is responsible
  for, including the shared library;
- The technical decisions, data formats and configuration that every
  subsystem follows;
- How the repository is organized;
- The items still to be filled in before final submission.

After reading it you will understand how the system works end to end and know
where to find the detail for any part of it.

The system recreates the magic wand experience of the Harry Potter area at
Universal Studios. A user waves a wand in front of a camera. The system
recognizes the motion as one of several predefined gestures (spells) and
responds with an action: a visual effect on screen, a sound, or, if time
permits, a physical device.

The system has three **subsystems**: data collection, training and
inference. Each has its own purpose, folder and documents. A **component** is a
building block inside a subsystem, such as vision or the classifier.
Components that more than one subsystem needs live in the shared library.

Terms such as subsystem, component, tip, gesture, sample, session and label
are defined in `docs/glossary.md`.

The wand is a brightly colored ping pong ball on a stick, so that OpenCV color
filtering can find it in the video. The system tracks the center of the ball,
called the tip. Five components turn video into an action:

1. **Vision** finds the tip in each frame.
2. **Motion detection** turns the tip's positions into gestures.
3. **Gesture normalization** gives every gesture the same length and form.
4. **Gesture classification** names the spell a gesture represents.
5. **Action trigger** performs the effect for that spell.

The classifier is a machine learning model, so it must be trained on labeled
examples. The subsystems relate as follows:

- **Data collection**: live video goes through vision and motion detection,
  and a person labels and stores the resulting gestures in a dataset (about
  1,000 samples per gesture across all users). Many users contribute, each
  recording into a dataset of their own, and the datasets are shared through
  git for training.
- **Training**: the datasets are normalized and consolidated into one table,
  the training data, hyperparameters are explored for each classifier family,
  and the best hyperparameter candidate of a family is trained and evaluated.
- **Inference**: live video goes through all five components, in real time,
  using a trained classifier.

## 2. System Flow

### 2.1 Inference

Inference runs in real time. Each frame is processed as it arrives, so vision
and motion detection must keep up with the camera's frame rate, and a gesture
is classified and acted on as soon as it ends.

```text
 +--------+ frame  +--------+ tip position +-----------+
 | Camera |------->| Vision |------------->|  Motion   |
 +--------+        +--------+ + timestamp  | detection |
                                           +-----+-----+
                                                 | gesture (positions)
                                                 v
 +---------+ spell +------------+ fixed-   +---------------+
 | Action  |<------| Gesture    |<---------| Gesture       |
 | trigger | + conf| classifier | length   | normalization |
 +---------+       +------------+ vectors  +---------------+
```

1. The camera delivers frames. Each frame gets a timestamp.
2. Vision finds the tip in the frame and outputs its position with the
   frame's timestamp.
3. Motion detection watches the stream of tip positions. A gesture starts when
   the tip's speed rises above a threshold and ends when it falls below one.
   Motion that lasts too long or covers too little distance is discarded.
4. Gesture normalization converts the gesture's positions into a list of
   motion steps of a fixed length, whatever the gesture's duration or the
   camera's frame rate (section 4.3).
5. The classifier receives the normalized gesture and outputs a spell and a
   confidence score.
6. The action trigger performs the action for the spell. If the confidence is
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

Training has three functions: consolidate the data, explore hyperparameters,
and train and evaluate a model. Each takes inputs and produces outputs:

```text
 +-----------------------------------------------------------------------+
 | 1. CONSOLIDATE                                                        |
 |  In:   datasets (data/<name>/, in git)                                |
 |  Out:  training data (one table, raw + normalized gestures, in git)   |
 +--------------------------------+--------------------------------------+
                                  |
                                  v   split: training set | test set
 +-----------------------------------------------------------------------+
 | 2. EXPLORE                                                            |
 |  In:   training set, experiment definition                            |
 |  Does: k-fold (or similar) validation of every hyperparameter         |
 |        candidate, on the training set only                            |
 |  Out:  ranked hyperparameter candidates (report, results)             |
 +--------------------------------+--------------------------------------+
                                  |
                                  v   test set: not touched so far
 +-----------------------------------------------------------------------+
 | 3. TRAIN AND EVALUATE                                                 |
 |  In:   training set, test set, the chosen hyperparameter candidate    |
 |  Does: train on the whole training set; evaluate on the test set      |
 |  Out:  classifier (in git), metrics, confidence threshold, report     |
 +-----------------------------------------------------------------------+
```

1. **Consolidate.** Every accepted gesture of the datasets is normalized with
   the shared library (section 4.3) and stored with its raw positions and its
   metadata in the training data, one table that holds everything training
   needs. Normalization is fixed, not tuned. The table can be rebuilt from the
   datasets at any time, and it is committed so that every user trains on the
   same data without normalizing again.
2. **Explore.** All gestures are shuffled into one pool and split by percentage
   into a training set (80%) and a test set (20%). An experiment definition
   names a classifier family and the space of hyperparameter values to search.
   The explorer enumerates every hyperparameter candidate in that space and
   evaluates each one by training and validating it on folds of the training
   set. A comparator ranks the hyperparameter candidates. The results are kept
   so they can be analyzed later. The test set is not touched.
3. **Train and evaluate.** The best hyperparameter candidate is trained on the
   whole training set and evaluated once on the test set, which neither the
   exploration nor the training has seen. The test set yields three kinds of
   test case: held-out spells, backward spells (the held-out spells with their
   positions in reverse order) and non-spell recordings. A backward spell
   counts as not a spell. The measures are computed over a range of confidence
   thresholds, and the results choose the confidence threshold. The model is
   saved as a classifier, with the evidence for the choice.

Samples of one session resemble each other, so scores on a random split are
likely to be higher than for a person the classifier has not seen; the
training data can be filtered, for example by author, to test that case.

Non-spell recordings are stored as ordinary samples under a label that
`config/labels.yaml` marks as not a spell. Training does not learn that label
as a class; it uses those samples only as test cases.

### 2.4 Shared Implementation

Vision, motion detection, gesture normalization and the classifiers are
implemented once, in the shared library, and every subsystem runs that
implementation. A gesture seen live therefore has the same form as a gesture
the classifier was trained on. Datasets store positions, not normalized
gestures, so changing how gestures are normalized does not require
re-recording.

## 3. Subsystems

### 3.1 Data collection

An application for recording, labeling and reviewing gestures. It hosts vision
and motion detection, adds calibration, the labeling workflow and review, and
writes datasets. Design: `data-collection/docs/design.md`.

### 3.2 Training

A command-line tool that turns the datasets into trained classifiers. It has
three functions (section 2.3), built from four components:

- **Training data.** The consolidated table of raw and normalized gestures. It
  loads the table, filters it by column, shuffles it, splits it by percentage
  and delivers it whole or in batches.
- **Trainer.** The one interface through which a model of any family is
  trained and evaluated, and its trained model saved. It takes a set of
  hyperparameter values, a set to train on and a set to evaluate on, and
  reports a standard set of metrics. A family may add metrics of its own.
  Each family has a trainer; a family that needs nothing special uses the
  common implementation, and a data scientist can subclass it when one is
  needed. A trainer validates the hyperparameter values it receives.
- **Explorer.** Enumerates the hyperparameter candidates of a space, selects the
  validation folds of the training set, invokes the trainer for each
  hyperparameter candidate on each fold, collects the metrics, ranks the
  hyperparameter candidates with a comparator and stores the results. A stored
  exploration can be loaded to answer questions about its hyperparameter
  candidates. There is one explorer for each way of validating a hyperparameter
  candidate, such as k-fold or a single split.
- **Experiment definitions.** Named files in git, treated as code, that
  state the family, the hyperparameter space, the validation scheme and the
  comparator of an exploration. Each exploration run keeps a copy of the
  definition it used.

The classifier families are open. Examples are a probabilistic model such as
Naive Bayes, a margin-based model such as a support vector machine, an
ensemble such as a random forest, and a neural network such as a multilayer
perceptron. A family is added with a trainer and an experiment definition, and
the workflow does not change. Each family has a design document of its own
that describes its hyperparameters.

Every exploration and every training run writes a report in `reports/`, and
every trained classifier is saved in `models/`, as laid out in section 6.
Design: `training/docs/design.md`.

### 3.3 Inference

The application that recognizes spells live. It runs the pipeline of section
2.1 on the camera's video with a trained classifier and the calibration for
the current camera and room, shows the live view, and hosts the action
trigger. Design: `inference/docs/design.md`.

## 4. Components

### 4.1 Vision

Finds the tip in each frame by filtering for the ball's color and locating the
resulting shape. Input: camera frames. Output: tip position and timestamp (or
"not found") per frame. Its color settings are tuned for each camera and
lighting condition by calibration.

### 4.2 Motion detection

Tracks the tip's speed to separate idle from motion and cuts the stream into
gestures. Input: tip positions with timestamps. Output: gestures, and the live
state (moving or idle). Its thresholds and time window are settings that
calibration adjusts.

### 4.3 Gesture normalization

Gestures differ in duration (a quick flick or a slow circle) and in the number
of positions (cameras deliver different frame rates and drop frames), while
most classifiers need an input of one fixed size. Normalization turns any
gesture into the same form. Input: the timestamped positions of one gesture.
Output: the normalized gesture. It has four steps.

1. **Resample in time.** The gesture's duration is divided into equal time
   intervals, and the position at each interval boundary is read from the
   recorded path by linear interpolation. The result is a fixed number of
   points, spaced equally in time from the first position to the last. The
   points are new positions on the path, not the camera's frames: a gesture
   recorded with fewer frames, or with a dropped frame, gives the same number
   of points as any other. Horizontal positions are scaled by the frame's
   aspect ratio first, so both axes are in frame-heights (section 5.2).
2. **Shift to the origin.** The first point is subtracted from every point, so
   that every gesture starts at (0, 0). Where in the frame the gesture was
   drawn is discarded.
3. **Steps.** Each step runs from one point to the next. It is described by
   three numbers: the horizontal and vertical displacement (dx, dy) in
   frame-heights, and the magnitude of the displacement, the square root of
   dx squared plus dy squared. A step does not depend on the other points or
   on absolute position. The displacement is the magnitude times the cosine
   and the sine of the step's direction, so (dx, dy) carries direction and
   length together. The magnitude is stored as well because a classifier
   cannot easily derive a square root from its inputs. N points give N - 1
   steps.
4. **Duration.** Resampling removes how long the gesture took, so the duration
   in seconds is added as one more value.

The output is one list of numbers: the (dx, dy, magnitude) of every step in
order, followed by the duration. Every classifier reads this list.

Because the points are equally spaced in time, the magnitude of a step shows
how fast that part of the gesture was, relative to the rest, and the
duration gives the absolute speed. The order of the steps keeps the order of
the motion, and the signs of dx and dy keep its direction: a circle drawn
clockwise and one drawn counterclockwise give opposite displacements. Spacing
the points along the path's length instead would erase the speed pattern,
which can tell spells apart.

**Example.** A gesture lasts 1.0 second. The camera dropped a frame between
0.20 and 0.45 seconds, so the recorded frames are unevenly spaced (the
vertical axis points down):

```text
   t      x     y
  0.00   0.30  0.50
  0.10   0.34  0.44
  0.20   0.40  0.38
  0.45   0.52  0.30      <- no frame between 0.20 and 0.45
  0.50   0.54  0.30
  0.80   0.60  0.38
  1.00   0.62  0.46
```

To produce 5 points, the time axis is divided into 4 equal intervals, so the
points are at 0, 0.25, 0.50, 0.75 and 1.00 seconds. At 0.25 the path lies
between the frames at 0.20 and 0.45, one fifth of the way along that gap, so
x = 0.40 + 0.2 * (0.52 - 0.40) = 0.424 and y = 0.38 + 0.2 * (0.30 - 0.38) =
0.364. After the other points are found in the same way and the first is
subtracted from all of them, the points and steps are:

```text
   t     point P (after the shift)       step      dx      dy    magnitude
  0.00   P0 = ( 0.000,  0.000)
  0.25   P1 = ( 0.124, -0.136)           P0 to P1  +0.124  -0.136   0.184
  0.50   P2 = ( 0.240, -0.200)           P1 to P2  +0.116  -0.064   0.132
  0.75   P3 = ( 0.290, -0.133)           P2 to P3  +0.050  +0.067   0.083
  1.00   P4 = ( 0.320, -0.040)           P3 to P4  +0.030  +0.093   0.098
```

The first step equals P1 only because P0 is (0, 0); every other step is the
difference of two consecutive points. The magnitudes show that the gesture
starts fast, slows down and speeds up again. The normalized gesture is the
four triples above followed by the duration, 1.0.

The normalization is fixed: 64 points, which give 63 steps and a list of
190 numbers (63 times 3, plus the duration). It is not a tunable setting. The
number of points is chosen so that resampling changes the shape of a typical
gesture very little. The settings are saved with every classifier, so that
inference can detect a mismatch.

### 4.4 Gesture classification

A model trained on labeled gestures. Input: one normalized gesture. Output: a
spell (a label identifier) and a confidence score between 0 and 1.

- A **classifier** wraps a trained model of one family. Every family
  implements one interface: load, and predict a spell with its confidence.
  Inference uses only this interface. Training a model, and saving it in the
  form the classifier loads, is the work of the training subsystem's
  trainers, so inference needs none of the training code or its
  dependencies.
- The confidence is the probability the model gives to the predicted spell.
- A motion that is not a spell, or a spell drawn backward, is rejected by a low
  confidence, not by a class of its own. The confidence threshold that rejects
  them is chosen in training.
- A saved classifier carries its list of labels, the normalization settings it
  needs, and the recommended confidence threshold.
- The classifier does not decide whether to act on the result; the action
  trigger applies the confidence threshold.

### 4.5 Action trigger

Maps a recognized spell to an effect: an on-screen visual, a sound, or, if
time permits, device control. Input: a spell and its confidence. The effect for
each spell is set in `config/actions.yaml`. The trigger applies the confidence
threshold: below it nothing is performed and the user is told the gesture was
not recognized. The threshold starts at the value saved with the classifier
and can be overridden in configuration.

### 4.6 Shared library

The library (`wand-core`) contains the components that must behave identically
in more than one subsystem. Design: `lib/docs/design.md`.

- **Frame sources** deliver camera frames with timestamps, from either a live
  camera or a recorded video file, so the rest of the library runs the same on
  both.
- **Tracker** finds the tip in one frame using the vision settings. It is the
  vision component.
- **Segmenter** watches the tip positions and decides when a gesture starts
  and ends, using the motion settings. It reports finished gestures, discarded
  motion and the live moving or idle state.
- **Normalizer** implements gesture normalization.
- **Classifiers** hold the classifier interface and the classifier families:
  load and predict. They hold no training code and save nothing. A family with a
  heavy dependency, such as a neural network, makes it optional, so an
  installation without it still runs the other families.
- **Color calibrator** derives vision settings from points the user clicks on
  the tip.
- **Motion calibrator** proposes motion settings from a short measurement of
  the user holding still and then waving.
- **Dataset store** reads, writes, filters, exports and merges datasets in the
  format in `docs/data-handling.md`.
- **Path renderer** draws a gesture's path as an image.

Each subsystem imports the library and supplies what the library does not
have: the camera, the user interface and the application logic. The library
never opens a camera or draws a user interface by itself, so it can be tested
with recorded video and synthetic data.

## 5. Conventions

### 5.1 Technical decisions

| Decision | Reason |
|---|---|
| Single mono-repo | Components share code and evolve together |
| Python 3.11 or later | OpenCV and ML ecosystem |
| OpenCV color filtering | The wand is a brightly colored ball |
| One shared library | Identical processing for training and inference |
| Classifiers in the library | Training and inference load the same code |
| Training code outside it | Inference needs no training dependencies |
| Fixed normalization | One form for every classifier; tuning is on models |
| Training data as parquet | Compact, typed columns, fast to load |
| Random split of all data | The usual practice for a pooled dataset |
| Resampling in time | Keeps the speed profile and order of the motion |
| Split by session | Samples of one session resemble each other |
| uv workspace, ruff | Reproducible environments, one style |
| YAML for configuration | Human-edited, supports comments |
| JSON for recorded data | Small files, readable, safe to edit atomically |
| macOS and Linux | Windows is best effort and untested |

Tooling and workflow rules are in `docs/standards.md`.

### 5.2 Data across the system

Data collection produces datasets and calibrated settings. This is how each
kind of data is used afterwards.

- **Samples** (timestamped tip positions with a label and status) are the
  training data. Normalized gestures are computed from the positions by the
  shared library, the same way inference normalizes live positions.
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

### 5.3 Configuration

All configuration is in `config/`.

- `labels.yaml` (in git): the labels. Each has an identifier, used in stored
  samples and in classifier output, a display name shown to users, and whether
  it is a spell (a label for non-spell recordings is not). Data collection
  reads and edits it.
- `vision.yaml` (in git): default values for the vision settings, such as the
  ball's color range and size limits. Calibration starts from these.
- `motion.yaml` (in git): default values for the motion settings, such as the
  speed thresholds, the valid gesture duration and the minimum gesture size.
  Calibration starts from these.
- `actions.yaml` (in git): the effect for each spell, and the confidence
  threshold override of the action trigger.
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

## 6. Folder Organization

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
  training/           training tool
    docs/             requirements, design, tasks
    experiments/      experiment definitions, by family (in git)
    src/              training code
    tests/
  inference/          inference application
    docs/             requirements, design, tasks
    src/              application code
    tests/
  data/               datasets, one folder per dataset; in git, no video
  training-data/      consolidated raw and normalized gestures; in git
  reports/            exploration and training reports; in git
  models/             trained classifiers; in git
```

`data/` holds several datasets side by side, each a data folder as defined in
`docs/data-handling.md`, for example one for each person who records. The
datasets are shared through git, and video clips are excluded from it.
Training reads all of them, or the ones the user names.

`reports/` and `models/` are organized by classifier family. The results of
explorations, which cover many hyperparameter candidates, and the results of
final training, which cover one model, are kept apart. A model has an identifier
of the form `<family>-<timestamp>`, and the same identifier names its report and
its files:

```text
reports/
  index.md                      every exploration and model, with links
  <family>/
    exploration/<run id>/       definition copy, results, report, figures
    training/<model id>/        metrics, predictions, report, figures
models/
  <family>/<model id>/          the classifier and its metadata
```

An exploration run can be deleted without affecting any model, because a
training report and a saved classifier carry their own hyperparameters.

Each subsystem is a workspace member with its own `pyproject.toml`, `docs/`,
`src/` and `tests/`. The `training/` and `inference/` folders are created when
their tasks start. Inference configuration names the model identifier to
load.

## 7. To Do

Items to fill in before final submission:

- Data collection: recording non-spell samples under a label that is not a
  spell.
- Action trigger: the effects for each spell, and physical actuation if time
  permits.
- Inference application: its user interface and how it applies a calibration
  profile.
- Final values for the motion settings, tuned from real recordings.
