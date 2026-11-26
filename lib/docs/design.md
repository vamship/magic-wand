# Shared Library - Design

> **Version** 3 | **Updated** 2026-11-26 | **Draft**

## 1. Overview

The shared library, installed as `wand-core`, is the single implementation of
vision, motion detection, the dataset format, gesture normalization and the
classifiers. Data collection, training and inference use it. This document
describes its components, how they work together, the settings that control
them, and how they are tested. After reading it you will know what the
library does, what each component is responsible for, and what each setting
means. System context is in `docs/architecture.md`; the dataset layout is in
`docs/data-handling.md`.

A gesture classifier is trained on recorded data and then fed live data. If
the two are produced by different code, or by differently tuned code, the
classifier sees input unlike what it learned. The library removes that risk by
being the only place where a camera frame becomes a gesture. It must also work
with many cameras and lighting conditions, and be testable without a camera.

## 2. Components

- **Frame source**: delivers camera frames with timestamps. Variants are a live
  camera and a recorded video file, so everything downstream runs identically
  on either. It can list the cameras on the machine.
- **Tracker**: examines one frame and reports where the tip is, or that it was
  not found. It finds the ball by its color.
- **Segmenter**: watches the stream of tip positions and decides when a
  gesture starts and ends. It reports each finished gesture, or a reason the
  motion was discarded, and continuously reports whether the tip is moving.
- **Normalizer**: converts a gesture's positions into the fixed-length form
  that classifiers read.
- **Classifiers**: load a trained model and predict a spell and a confidence
  from a normalized gesture. They contain no training code and never write a
  model.
- **Color calibrator**: derives vision settings from points the user clicks on
  the wand tip in a frame.
- **Motion calibrator**: proposes motion settings from a short guided
  measurement of the user's stillness and gesture speed.
- **Path renderer**: draws a gesture's path as an image.
- **Dataset store**: reads, writes, filters, exports and merges recorded data
  as defined in `docs/data-handling.md`.

## 3. How the components work together

```text
 Frame source --frame--> Tracker --tip position--> Segmenter
 (camera or file)        (vision settings)         (motion settings)
                                                      |
                          +---------------------------+-----------+
                          | gesture (positions)       | live state|
                          v                           v           v
                    Dataset store              speed, moving?   discard
                    Normalizer                 (for tuning UIs) reasons
                    Path renderer
```

The normalizer's output is what the classifiers read, in training and in
inference.

Calibration uses the same pieces:

```text
 Color calibration:   frame + clicked points --> Color calibrator
                      --> vision settings --> Tracker shows the result

 Motion calibration:  tip positions while the user holds still, then waves
                      --> Motion calibrator --> proposed motion settings
```

The Tracker and Segmenter never open a camera or read a file themselves; they
are given frames or positions. As a result the same code runs on live video,
on recorded clips and on synthetic test data.

## 4. Conventions

Positions, time, distances and speeds follow `docs/architecture.md`: positions
are fractions of the frame, vertical axis down; distances are in frame-heights;
speeds in frame-heights per second; time in seconds.

Setting names in this document are written as they appear in configuration and
JSON files, in camel case. In Python code they are snake case, per
`docs/standards.md`.

## 5. Frame source

- A frame is delivered with a timestamp in seconds that increases steadily.
  For a camera it is taken when the frame is grabbed; for a video file it is
  the file's own timeline.
- A camera source requests a resolution and frame rate (default 640x480 at
  30 fps) and reports the mode it actually received.
- Listing cameras returns the devices found, each with an index, a name when
  the operating system provides one, and the modes it supports when that can
  be determined. Names are often unavailable on macOS, so the index and a
  preview identify a camera there.

## 6. Tracker and vision settings

For each frame the tracker follows these steps:

1. Smooth the frame to reduce sensor noise.
2. Mark the pixels whose color lies within the configured color range.
3. Remove specks and fill small holes in the marked area.
4. Find the connected marked regions and discard those outside the allowed
   size range or too far from round.
5. Choose the best remaining region, preferring one near the previous tip
   position, and report the center of its enclosing circle as the tip.

The result holds the timestamp, the tip position and radius, and whether a tip
was found. The tracker can also produce the marked-pixel mask for display.

**Vision settings**

| Key | Meaning |
|---|---|
| `hueCenter`, `hueHalfWidth` | Color range on the hue circle |
| `satMin`, `satMax` | Saturation range |
| `valMin`, `valMax` | Brightness range |
| `blurSize` | Smoothing strength |
| `cleanupSize` | Speck removal and hole filling strength |
| `minArea`, `maxArea` | Allowed region size, as fractions of the frame |
| `minRoundness` | How close to circular a region must be (0 to 1) |

The hue range is a center and half-width on a circle, so colors that straddle
the red end of the spectrum, such as orange and red, need no special handling
by the user. Internally such a range is applied as two bands.

## 7. Color calibrator

Input is a frame and one or more points the user clicked on the wand tip.

1. Take the pixels in a small disc around each click.
2. Compute the typical hue (a circular average, since hue wraps around) and
   the spread of hue, saturation and brightness.
3. Set each range to the typical value plus a margin proportional to the
   spread, with a minimum margin so very uniform patches still tolerate
   lighting changes. The margin scale is a tolerance setting the user can
   change.
4. Run the tracker on the frame and return the settings with the resulting
   mask.

Further clicks add samples and widen the ranges. If the mask also marks other
regions of the frame, the calibrator reports how many, so the user can tighten
the tolerance or sample a more distinctive part of the ball.

## 8. Segmenter and motion settings

### 8.1 Behavior

The segmenter receives one tip detection at a time and keeps a short history.

- It computes the tip's speed from a lightly smoothed position stream, which
  suppresses hand tremor and detector jitter.
- Three states describe the stream:

```text
         speed >= startSpeed             speed < endSpeed for endHoldS
 IDLE ------------------------> MOTION ---------------------------> report
   ^    (for startFrames frames)   |                              gesture
   |                                | too long, or tip lost too long
   |                                v
   +<------ speed < endSpeed ---- DISCARD (wait for idle)
```

- Two thresholds give hysteresis: motion starts above `startSpeed` and ends
  only when speed stays below the lower `endSpeed` for `endHoldS`, so a
  brief pause inside a gesture does not end it.
- When motion ends, the gesture is reported if its duration is within the valid
  window and its path is large enough. Otherwise it is discarded with a
  reason: `too_long`, `too_short`, `too_small` or `tracking_lost`.
- A gesture consists of the detected positions from just before motion began
  until motion ended; the trailing idle period is trimmed. Frames with no
  detection are absent, and the timestamps show the gap.
- After every detection the segmenter also reports the current speed, the state
  and whether the tip counts as moving. Tuning screens use this.
- The segmenter can be switched off and on, so an application can ignore
  motion at chosen times.

### 8.2 Motion settings

Speeds are in frame-heights per second, durations in seconds, distances in
frame-heights.

| Key | Meaning | Starting value |
|---|---|---|
| `startSpeed` | Speed above which motion starts | 0.25 |
| `endSpeed` | Speed below which motion may end | 0.15 |
| `startFrames` | Frames above start speed needed | 2 |
| `endHoldS` | Time below end speed needed | 0.3 |
| `minDurationS` | Shortest valid gesture | 0.3 |
| `maxDurationS` | Longest valid gesture (the valid window) | 4.0 |
| `minExtent` | Smallest valid path size (bounding box diagonal) | 0.10 |
| `lostTimeoutS` | Longest tolerated gap with no tip | 0.25 |
| `smoothingFrames` | Frames in the smoothing average | 3 |

The starting values are provisional. A task tunes them against real
recordings; thereafter they are set per machine through calibration and stored
with every session.

## 9. Motion calibrator

A guided measurement in two steps, run while the user is in front of the
camera:

1. **Hold still** for a few seconds. The calibrator records the speed the
   detector reports for a motionless tip (tremor and jitter) and takes a high
   percentile as the idle ceiling.
2. **Wave** the wand a few times. It records the typical peak speeds.

It then proposes `endSpeed` as a multiple of the idle ceiling, and
`startSpeed` between that and the typical gesture speed. The user checks and
adjusts the proposal on the motion tuning screen of the application.

## 10. Normalizer

The normalizer implements gesture normalization as specified in
`docs/architecture.md`, section 4.3: resample in time to a fixed number of
points, shift to the origin, describe each step by its horizontal and vertical
displacement and its magnitude, and add the duration.

- **Input**: the positions of one gesture (times in seconds from the first
  position, horizontal and vertical as fractions of the frame) and the frame
  size. Horizontal positions are scaled by the aspect ratio so that both axes
  are in frame-heights.
- **Output**: the normalized gesture, one list of numbers: the (dx, dy,
  magnitude) of every step in order, then the duration. With the fixed 64
  points it has 190 numbers.
- **Settings**: the number of points (64), recorded in every saved classifier
  and in the training data. The normalizer also has a version number that
  increases whenever a change alters its output.
- **Edge cases**: a gesture needs at least two positions and a duration above
  zero; otherwise it is rejected with a message. Positions with equal
  timestamps are merged before interpolation. A gesture with fewer positions
  than points is interpolated up; one with more is interpolated down.
- It works on one gesture at a time and on many at once, with the same result.
  It is computed on demand from stored positions and never stored in a
  dataset.

## 11. Path renderer

Draws a gesture's path with a color gradient from green at the start to red at
the end and small markers at both ends. It draws the positions it is given;
mirroring for display is the caller's choice. Two modes: the path alone on a
black background, or the path over a supplied camera frame. Rendering is a
small drawing operation, fast enough to generate on demand.

## 12. Dataset store

Implements `docs/data-handling.md`:

- Create and open data folders; create sessions; write, update and delete
  samples and their clips, treating a missing or removed clip as "no clip"
  and never as an error;
- List and filter samples by label, session, author, date and status;
- Atomic writes and the startup cleanup of leftovers;
- Consistency check, export to a single file, and merge of data folders;
- Find the datasets in a data location, where each folder holding a dataset
  file is one dataset, and open one or several of them;
- Load data folders or an export file into the same in-memory form for
  training.

## 13. Classifiers

A classifier wraps a trained model of one family and has one interface:

- **Load**: read a classifier from a folder. Loading rejects an unknown format
  version, and rejects a classifier whose normalization settings or version
  differ from the library's.
- **Predict**: for a normalized gesture, return the probability of every
  label. The predicted spell is the label with the highest probability, and
  its probability is the confidence. A batch of gestures can be predicted at
  once, with the same results as one at a time.

The library only loads. Training and saving belong to the training
subsystem: a trainer trains the model and writes it in the form below. The
library specifies that form, because the library has to read it.

A classifier is a folder holding the model in the family's own form, and a
`classifier.json` file with `formatVersion`, the family, the label ids in the
order of the probabilities, and the normalization settings and version.
Training adds further fields (the model id,
the hyperparameters, a summary of the metrics, the training data fingerprint
and the report path); the library ignores them.

The library implements the prediction side of each family that has a trainer.
A family with a heavy dependency, such as a neural network, declares it as
optional, and loading such a classifier without the dependency fails with a
message that says what to install. Model files come from this repository and
are trusted; a loader must not be given files from elsewhere.

## 14. Testing

- **Tracker**: synthetic videos of a colored disk moving along known paths,
  with noise and varied background and brightness; recovered centers are
  compared with the truth. Colors that straddle the hue wrap-around are
  included.
- **Color calibrator**: clicks on synthetic frames produce settings under
  which the tracker finds the disk and little else.
- **Segmenter**: synthetic position streams. A still tip stays idle; a circle
  gives one gesture; each discard reason is triggered; tremor below the
  threshold gives nothing; a pause shorter than `endHoldS` does not split a
  gesture.
- **Motion calibrator**: synthetic still and waving streams give thresholds in
  a sensible order.
- **Dataset store**: write and read round trips, filters, export, merge
  (new, identical and conflicting sessions) and simulated crashes such as a
  leftover temporary file.
- **Frame source**: a recorded clip replays with the expected timestamps.
- **Normalizer**: the example in `docs/architecture.md`, section 4.3,
  reproduces its points and steps; the same shape drawn in 1 and in 2
  seconds, or elsewhere in the frame, gives the same steps; a gesture with a
  dropped frame gives the same number of points; too few positions, a zero
  duration and equal timestamps behave as in section 10; batch and single
  results agree.
- **Classifiers**: a small model is built directly with each family's own
  library and written in the form of section 13; it loads and predicts
  probabilities that sum to 1, and batch and single predictions agree; a
  changed format version, normalization setting or normalization version is
  rejected; a missing optional dependency gives the message of section 13.
- Real recordings from data collection can be added later as regression
  fixtures.
