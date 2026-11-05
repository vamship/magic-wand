# Data Collection Application - Design

> **Version** 14 | **Updated** 2026-11-05 | **Approved**

## 1. Overview

This document describes how the data collection application works. It starts
with the system and its components, then shows the flows through them (a
session, a calibration, a capture cycle), then describes how each component
works and what it exchanges with the others. It ends with the interfaces, the
data written, and how the application is tested. After reading it you will know
how a gesture travels from the camera to the dataset, which component does what,
and how sessions are started, paused, reviewed, ended and resumed.

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

## 2. System Architecture

### 2.1 The system at a glance

The data collection application runs on the user's machine. The user works in a
browser; the application reads the camera, records samples into a data folder,
and reads shared configuration.

```text
 +------+ commands, clicks +-------------------+ frames +--------+
 | User |----------------->|                   |<-------| Camera |
 |      |<-----------------|  Data Collection  |        +--------+
 +------+ live video,      |        App        |
          events, images   |                   | samples, clips
 +---------+ labels,       |                   |--------------+
 | config/ |-------------->|                   |              v
 +---------+ defaults      +-------------------+      +-------------+
                                                      | Data folder |
                                                      +-------------+
```

### 2.2 Components

The application is a single Python program with a browser front end. It is
built from eleven components:

```text
 +-------------------------------- Browser -------------------------------+
 |                                 Web UI                                 |
 +------------+---------------------^----------------------^--------------+
              | HTTP requests       | live video           | events
 +------------v---------------------+----------------------+--------------+
 |                          Application Server                            |
 +-----+------------+------------+------------+------------+--------------+
       |            |            |            |            |
       v            v            v            v            v
 +-----------+ +---------+ +------------+ +---------+ +---------+
 |Calibration| | Session | |  Capture   | | Sample  | |  Label  |
 | Service   | | Service | | Controller | | Library | | Service |
 +-----+-----+ +----+----+ +--+------+--+ +----+----+ +----+----+
       |            |         |      |         |           |
       v            |         |      v         |           v
 +-----------+      |         |  +--------+    |     config/labels.yaml
 |  Capture  |<-----+---------+  |  Clip  |    |
 |  Engine   |                   | Writer |    |
 | (Tracker, |                   +---+----+    |
 | Segmenter)|                       |         |
 +-----+-----+                       v         v
       |                        +---------------------+
    Camera                      |    Dataset Store    |
                                +----------+----------+
                                           v
                                      Data folder

 +------------------------------------------------------------------------+
 |  Application State (shared by all components; drives the Web UI; 4.3)  |
 +------------------------------------------------------------------------+
```

- **Web UI**: the pages the user sees and uses, in the browser.
- **Application Server**: the web server; connects the Web UI to the services.
- **Application State**: the single record of what the application is doing
  now (session, settings, camera, capture state, counts and more). Every
  component can read it, each field has one writer, and the Web UI is updated
  from it.
- **Calibration Service**: camera choice, color calibration, motion tuning and
  calibration profiles.
- **Session Service**: starting, ending, listing, loading and resuming
  sessions.
- **Capture Controller**: runs the capture cycle and turns gestures into
  samples.
- **Capture Engine**: owns the camera; finds the wand and detects gestures
  using the shared **Tracker** and **Segmenter**.
- **Clip Writer**: encodes the video clip of a sample.
- **Sample Library**: lists, filters, edits and deletes stored samples, for
  review and browsing.
- **Label Service**: reads and edits the shared label list.
- **Dataset Store**: the shared library component that reads and writes the
  data folder. Every write goes through it.

## 3. System Flow

### 3.1 The user's journey

```text
  New session:
    Setup -> Calibrate -> Start session -> Capture <-> Review -> End session
                                              pause / resume

  Existing session (chosen on the Setup page):
    Open session -> Review                     (open or ended sessions)
                 -> Resume -> Capture <-> Review    (open sessions only)

  Browse: filter, inspect and edit samples across the dataset (not capturing)
```

### 3.2 Session lifecycle

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

### 3.3 Calibration

```text
  Pick camera -> Color calibration -> Motion tuning -> Save profile -> Session
                 freeze a frame,       live feed with    (optional)     start
                 click the tip,        motion indicator,
                 see mask; add more    speed, threshold
                 clicks or adjust      slider; optional
                 sliders               guided measurement
```

### 3.4 The capture cycle

The Capture Controller is a state machine. Its states and transitions are:

```text
      STOPPED
         | start
         v
      COUNTDOWN <-----------------------------+
         | countdown over                     | gesture discarded,
         | and any sample saved               | or sample created
         v                                    |
       READY                                  |
         | motion starts                      |
         v                                    |
      RECORDING ------------------------------+

  pause:       from COUNTDOWN or READY, to PAUSED at once. From RECORDING, held
               until the gesture ends, then to PAUSED.
  resume:      PAUSED to COUNTDOWN (the remaining time, or a fresh countdown
               if the pause came while READY).
  end session: any state to STOPPED.
```

- **STOPPED**: not capturing. This is the state before the first start, after
  the session ends, and after a session is loaded for review. The live view
  still runs, and review is available when a session is loaded.
- **COUNTDOWN**: counting down (default 3 seconds); the Capture Engine ignores
  motion.
- **READY**: waiting for a gesture, with no time limit.
- **RECORDING**: a gesture is in progress.
- **PAUSED**: the countdown is frozen and review is open.

One pass through the cycle:

1. The user picks the active label and starts capturing. The Capture
   Controller enters COUNTDOWN.
2. The countdown reaches zero and any sample being saved is done. The Capture
   Controller enters READY and the Web UI tells the user to go.
3. The user performs the gesture. When the tip's speed rises above the start
   threshold, the Capture Engine reports that motion has started and the
   Capture Controller enters RECORDING.
4. The Segmenter ends the motion and reports the result: either a finished
   gesture, or a discard reason (too long, too short, too small, or the tip was
   lost).
5. **If the result is a discard**, the Web UI shows the reason, the Capture
   Controller enters COUNTDOWN, and nothing is created or written.
6. **If the result is a finished gesture**, the Capture Controller creates the
   sample: the tip positions, the active label, status `accepted`, and a video
   clip that runs from the configured padding before the gesture (default 2
   seconds) to the same padding after it. It enters COUNTDOWN immediately, and
   the Web UI shows the sample's path image.
7. In the background, the frames after the gesture are collected, the Clip
   Writer encodes the clip, and the sample is saved. READY is not entered until
   the countdown is over and the sample is saved, so a saved sample always
   precedes the next capture.
8. Back to step 2.

Because the countdown overlaps with saving, one cycle takes about the gesture
duration plus the countdown.

**Pause and review.** While capturing runs, the Web UI shows the latest result
but offers no review actions. Pressing Escape or clicking pauses capturing.
Review opens on the samples of the session with the latest selected, as soon as
any sample still being saved is saved, so review only ever sees saved samples.
The user steps through the samples and can reject, restore, delete or relabel
the selected one; each change is saved immediately. The user can also choose a
different active label for the next captures, and then resumes.

## 4. Component Details

Each component is described by what it does, how it works, and what it
exchanges with other components.

### 4.1 Web UI

**What it does.** It is everything the user sees and touches: the pages, the
live video, the countdown, the path images and the review controls. It holds no
rules of its own. It sends the user's commands to the Application Server and
shows what the Application State says.

**How it works.**

- It is a single-page application, built with Preact and htm from vendored
  files as ES modules, with no build step. The vendored files, with versions
  and sources, are listed in a `VERSIONS.md` beside them. JavaScript and CSS
  follow the 80-column rule in `docs/standards.md`.
- **Data flow.** The Web UI keeps a copy of the latest Application State
  snapshot and renders every page from it. A user action is an HTTP request;
  its response says only whether the request was accepted. The effect shows up
  when the next snapshot arrives. The Web UI never edits its own copy, so
  several browser windows always show the same thing.
- **Outside the state.** Two things reach the Web UI directly: the live video,
  which is an image element whose source is the live video stream, and the
  `motion` readings (speed, moving or idle) used by the motion tuning screen.
  Both are streams, not state.
- **Queries.** Lists of samples and sessions, profiles, cameras, images and
  thumbnails are requests made when a page opens or a filter changes. A page
  repeats its query when the samples revision in the state changes.
- **Countdown.** The state holds the time at which the countdown ends. The page
  counts down locally from it, so no ticks are sent.
- Pages:
  - **Setup**: camera list and previews; the form for the new session's
    details (author, session name, handedness, notes), which the page keeps
    until the session starts and which only leads on to Calibrate; the list of
    existing sessions, each with Review, Delete and, for open sessions, Resume.
    A session cannot be started from Setup.
  - **Calibrate**: frozen-frame color calibration, vision sliders, the motion
    tuning screen, and the Start session button, which creates the session
    from the details given on Setup and opens Record. Settings are final
    once it is pressed (R2.2).
  - **Record**: live view, countdown and state, active label, the latest
    sample's path image, and counts. It has no review actions.
  - **Review**: the session's samples, with the selected sample's path image
    (path only or overlay) and details; step, reject, restore, delete and
    relabel actions; a selector for the active label; Resume. It opens when
    capturing is paused or a session is loaded.
  - **Browse**: filterable sample table with thumbnails, a detail view, label,
    status and delete actions, and per-label counts.
- Keyboard shortcuts are read by a listener on the page. Defaults are below,
  are configurable in `config/data-collection.yaml`, and each is shown on its
  on-screen button.

| Key | Action |
|---|---|
| Esc | While capturing: pause. In review: resume |
| Left, Right | In review: previous or next sample |
| R | In review: reject the selected sample (again to accept it) |
| Backspace | In review: delete the selected sample |
| P | Switch path-only and overlay views |
| 1 to 9 | Capturing: set the active label. In review: relabel the sample |

While capturing, a mouse click anywhere pauses and opens review.

**Interactions.** Sends HTTP requests to the Application Server. Receives state
snapshots, `motion` readings and live video from it. Nothing else.

### 4.2 Application Server

**What it does.** It is the only door into the application. It serves the Web
UI, accepts the user's requests, hands them to the right service, streams live
video, and sends the Application State and the motion readings to the browsers.

**How it works.**

- It is a FastAPI application served by uvicorn, listening only on this
  computer (`127.0.0.1`). The Web UI files are served as static files.
- Each HTTP endpoint (section 5.2) checks its input and calls one method of
  one service. It contains no capture or storage logic.
- The live video endpoint takes the Capture Engine's latest annotated frame,
  encodes it as a JPEG, and sends it as a continuous multipart stream (MJPEG).
  It encodes frames only while a browser is connected.
- The event endpoint is a Server-Sent Events stream: a one-way channel on which
  the server pushes small messages to the browser as things happen. When a
  browser connects, the server first sends the current Application State
  snapshot. After that it sends a new snapshot every time the state changes,
  and the `motion` readings as they arrive.
- Each connected browser has its own bounded queue. Every snapshot is complete,
  so if a browser falls behind, a waiting snapshot is replaced by the newer one
  and nothing is lost. Old `motion` readings are dropped.
- At startup it loads the configuration, opens the data folder (removing any
  leftover temporary files, per `docs/data-handling.md`) and starts the
  Capture Engine in preview mode.

**Interactions.** Receives requests from the Web UI. Calls the Calibration
Service, Session Service, Capture Controller, Sample Library and Label
Service. Reads frames from the Capture Engine and snapshots from the
Application State.

### 4.3 Application State

**What it is.** The single record of what the running application is doing
right now. Components read the facts they need from it instead of asking each
other, and the Web UI is updated from it. It is not saved to disk: when the
application starts it holds only the defaults (no session), and the sessions
on disk remain the lasting record.

**What it holds.** Every field has one owner, the only component that writes
it.

- **Session**: none, or the session's id and name and whether it is loaded for
  capture or for review only. Owner: Session Service.
- **Settings**: the working vision and motion settings, and the name of the
  loaded profile, if any. Owner: Calibration Service.
- **Camera**: the camera in use and the mode it delivers. Owner: Capture
  Engine.
- **Capture state**: STOPPED, COUNTDOWN, READY, RECORDING or PAUSED, and the
  time at which the countdown ends (or the time remaining, when paused).
  Owner: Capture Controller.
- **Active label**: the label new samples receive. Owner: Capture Controller.
- **Latest sample**: the id, label, status and clip availability of the sample
  just captured, and whether it is still being saved. Owner: Capture
  Controller.
- **Last discard**: the reason for the most recent discard, and when it
  happened. The Web UI shows a notice when it changes. Owner: Capture
  Controller.
- **Counts**: accepted samples per label. Owner: Sample Library.
- **Samples revision**: a number that increases whenever a stored sample is
  added, changed or deleted, so pages know to repeat their queries. Owner:
  Sample Library.
- **Labels**: the list of labels. Owner: Label Service.

Whether the settings are locked is not a field. The settings are locked while
the session is loaded for capture, and readers work that out from the Session
field.

**What is not in it.** Anything streamed to the browser, and anything that is a
query:

- the live video and the detection mask view;
- the `motion` readings (speed, moving or idle), which arrive at frame rate;
- the results of queries: pages of samples, the list of sessions, profiles and
  cameras, images, thumbnails and clips;
- the frozen calibration frame.

**How updates reach the screen.** Commands go in through the Application
Server to a service. The service changes the state. The new snapshot goes back
out to every browser:

```text
  Web UI --- request ---> Application Server ---> service
    ^                                               |
    |                                           updates its
    |                                           fields in
    |                                               v
    +---- state snapshot ---- Application Server <- Application State
          (event stream)
```

**Who writes and who reads.**

```text
  Owner                   Fields it writes
  Session Service         session
  Calibration Service     settings
  Capture Engine          camera
  Capture Controller      capture state, active label, latest sample,
                          last discard
  Sample Library          counts, samples revision
  Label Service           labels
          |
          v
  +-------------------+   readers: every component, as needed
  | Application State |-----------------------------------------+
  +---------+---------+                                         |
            | a snapshot on every change                        |
            v                                                   v
   Application Server --- event stream ---> Web UI     Capture Engine reads
                                                      the settings each frame
```

- The **Calibration Service** reads the session before it changes the
  settings, loads a profile or runs a color calibration. While the session is
  loaded for capture it refuses the request.
- The **Capture Engine** reads the settings at the start of every frame and
  applies them if they changed.
- The **Session Service** reads the session to refuse starting or loading a
  session while one is loaded for capture, and reads the settings when it
  starts a session.
- The **Capture Controller** reads the session to accept a start only when a
  session is loaded for capture.
- The **Sample Library** reads the session to open review on it by default.
- The **Application Server** reads the whole state to send it to browsers.

**How it works.**

- One Application State object is created when the application starts and is
  passed to every component. It is not a module-level global, so a test can
  create a fresh one.
- It holds one immutable **snapshot**. A reader gets the current snapshot,
  which is a plain read that is safe from any thread and always internally
  consistent. A reader never sees half of an update.
- Only a field's owner writes it. To change a field the owner calls an update;
  the Application State takes a lock, builds a new snapshot equal to the old
  one with that change, replaces the old snapshot, and notifies its listeners.
  The Application Server is the listener that sends the snapshot to browsers.
  Updates from different owners are applied one at a time.
- Facts live in the state; actions remain calls. Starting a capture, arming the
  Capture Engine and saving a sample are commands to a component. What they
  change is then written to the state by the component that owns it.
- Session transitions:
  - Start, or resume of an open session: none to loaded for capture.
  - Load for review: none, or another review, to loaded for review only.
  - End: loaded for capture to none. Closing a review: loaded for review to
    none.
- A component applies a rule by reading the state at the moment it acts. The
  Calibration Service and the Session Service both run on the Application
  Server's event loop, and neither pauses between reading the state and acting
  on it. A settings change and a session start therefore cannot interleave.
- The snapshot is small (the settings, the labels, a few counts), and changes a
  few times a second at most, so every change sends the whole snapshot.

### 4.4 Calibration Service

**What it does.** It prepares the settings for a session: chooses the camera,
derives the vision settings from a click, tunes the motion settings, and saves
and loads profiles.

**How it works.**

- It owns the **Settings** field of the Application State: the working vision
  and motion settings. They start as the defaults from `config/vision.yaml` and
  `config/motion.yaml`, or from a loaded profile (see `docs/architecture.md`
  for how settings are resolved). Every change updates the state, so the
  Capture Engine and the Web UI see it at once.
- **Cameras**: it asks the Capture Engine's frame source to list the cameras
  and to open one for a preview. Names may be unavailable (notably on macOS),
  so previews identify a camera.
- **Color calibration**: on request it freezes the current frame and keeps it
  in memory. For each batch of clicked points it calls the shared color
  calibrator with the frozen frame and the points, receives vision settings,
  runs the Tracker on the frozen frame, writes the derived settings to the
  state, and returns the detection mask. Manual adjustments overwrite
  individual settings.
- **Motion tuning**: the Capture Engine already streams the tip's speed and
  moving state on every frame. The Web UI draws the indicator, the speed and a
  short history graph with the start and end thresholds. A slider sets the start
  threshold; the end threshold follows at a fixed ratio (configurable). Numeric
  fields set the valid time window and minimum size. For the guided
  measurement, it collects the tip positions while the user holds still and then
  waves, passes them to the shared motion calibrator, and writes the proposed
  thresholds to the settings for the user to adjust.
- **Profiles**: saved as YAML files under `config/profiles/` on this machine.
- Before it changes the settings, loads a profile or runs a color
  calibration, it reads the session from the Application State. While a
  session is loaded for capture it refuses the request.
- When the Session Service resumes a session, it hands the recorded settings
  to the Calibration Service, which writes them to the state. This is the one
  way settings change while no session is being calibrated, and the Session
  Service does it before recording the session as loaded for capture.

**Interactions.** Receives requests from the Application Server and the
recorded settings from the Session Service. Writes the Settings to the
Application State and reads the session from it. Sends camera commands to the
Capture Engine and receives frames, tip detections and motion readings from it.
Reads and writes `config/profiles/`.

### 4.5 Session Service

**What it does.** It owns the session: starting, ending, listing, loading and
resuming, and the numbering of samples.

**How it works.**

- **Start**: validates the author and handedness, records the session name,
  reads the final settings from the Application State, and writes
  `session.json` through the Dataset Store with the camera's identifier and
  actual mode, the full vision and motion settings, the clip padding, and a
  highest sample number of zero. It then records the session in the
  Application State as loaded for capture, which locks the settings.
- **End**: only when the user asks. It records `endedAt`, tells the Capture
  Controller to stop, and clears the session in the Application State. Closing
  the application leaves the session open.
- **List**: the sessions in the data folder, with name, author, start time,
  sample count, and whether each is open or ended.
- **Load for review**: any session. It records it in the Application State as
  loaded for review only, and opens review on the session's samples without
  starting capture.
- **Resume**: only open sessions. It opens the camera recorded in the session,
  identified by its stored device identifier. If that device is not among the
  available cameras, because it is unplugged or the session was recorded with
  another machine's camera, the resume is refused and the reason is shown. It
  then hands the settings from the session record to the Calibration Service,
  and records the session in the Application State as loaded for capture,
  which locks them. If the camera delivers a different mode than the one
  recorded, the app warns the user (R6.7) but continues.
- **Edit details**: the name and the notes of any session, loaded or not, open
  or ended (R2.9). They are descriptions, not settings, so they stay editable
  when settings are locked. The new values are written to `session.json`
  through the Dataset Store, which notifies the Sample Library so that the
  samples show the new session name. If the session is the loaded one, the
  name in the Application State changes too. An empty text clears the field.
- **Delete**: only a session that is not loaded, in any role. The Dataset Store
  removes the whole session folder, and the Sample Library drops its samples
  from its index and counts.
- **Sample numbers**: the next sample's number is one more than the larger of
  the session's `highestSampleNumber` and the highest number in the samples
  file. When the sample is saved, `highestSampleNumber` is updated.

**Interactions.** Receives requests from the Application Server. Sends camera
commands to the Capture Engine, recorded settings to the Calibration Service,
and start and stop commands to the Capture Controller. Gives the Capture
Controller each new sample number. Writes the session to, and reads the session
and settings from, the Application State. Reads and writes session files
through the Dataset Store.

### 4.6 Capture Engine

**What it does.** It is the only owner of the camera. It turns frames into tip
positions, detects gestures, and keeps recent frames for video clips.

**How it works.**

- It runs one thread with a loop. For every frame it:
  1. reads the settings from the Application State and applies them if they
     changed;
  2. grabs the frame from the shared frame source, with a timestamp taken at
     grab time;
  3. runs the **Tracker** on it, producing a tip detection (position and
     timestamp, or "not found");
  4. if armed, feeds the detection to the **Segmenter**, which reports whether
     the tip is moving, and when a gesture ends, either the finished gesture or
     a discard reason;
  5. adds the frame to a ring buffer of recent frames;
  6. draws the annotations (tip marker and motion state, or the detection
     mask when the user asks for it) and publishes the annotated frame as the
     latest frame. By default the published picture is mirrored left to right,
     so the user sees it as in a mirror (`mirrorPreview`). Only the picture
     shown is mirrored: the tip positions, the buffered frames and so the
     clips stay as the camera saw them, as `docs/data-handling.md` requires.
- The ring buffer holds enough frames for the padding before a gesture, the
  longest valid gesture and the padding after it: about 8 seconds at the
  defaults. Frames are stored JPEG-compressed, which keeps the buffer near
  10 MB. It can return the frames between two timestamps.
- The Segmenter is armed only when the Capture Controller says the engine is
  ready, so motion during the countdown is ignored.
- Commands arrive on a queue and take effect between frames: arm or disarm and
  open a camera. Settings are not commands; the engine reads them from the
  state. Settings cannot change while a session is loaded for capture.
- After opening a camera it writes the device and the mode it delivers to the
  Application State.
- Frame timing is measured, not assumed: the actual frame rate is reported and
  written to the session.

**Interactions.** Receives commands from the Calibration Service, Session
Service and Capture Controller. Reads the Settings from the Application State
and writes the Camera to it. Sends the latest annotated frame to the
Application Server, the motion readings to the Application Server for streaming
to the browser, and gesture and discard results to the Capture Controller. Lets
the Capture Controller read frames from its buffer.

### 4.7 Capture Controller

**What it does.** It runs the capture cycle (section 3.4): it counts down,
decides when the engine is ready, creates a sample from each gesture, and
handles pause and resume.

**How it works.**

- It is a single loop that reads messages from one queue: the user's commands,
  the Capture Engine's results, and timer ticks for the countdown. It handles
  one message at a time, so the state machine needs no locks.
- Inputs and outputs:

```text
  Web UI, via the Application Server        Capture Engine
  start, pause, resume, active label        motion started, gesture, discard
                  |                                     |
                  v                                     v
          +-------------------------------------------------+
          |                Capture Controller               |
          | STOPPED, COUNTDOWN, READY, RECORDING, PAUSED    |
          +----+-----------+------------+------------+------+
               |           |            |            |
               v           v            v            v
         Capture Engine  Clip Writer  Dataset    Application State
         arm or disarm   frames       Store      capture state, active
                         to encode    sample     label, latest sample,
                                      record     last discard
  Session Service: next sample number, in
```

- **Writing the state.** On each change of state it writes the capture state to
  the Application State. When COUNTDOWN starts it writes the time at which the
  countdown ends; when it pauses it writes the time remaining. It writes the
  active label when the user changes it, the latest sample when one is created
  and again when it is saved, and the last discard when a gesture is discarded.
- **Building a sample.** When a finished gesture arrives, the Capture
  Controller:
  1. takes the active label as it is at that moment;
  2. works out the clip window, from the configured padding before the gesture
     starts to the same padding after it ends;
  3. enters COUNTDOWN straight away, and starts a **save job** that runs in
     parallel;
  4. in the save job, waits until the Capture Engine's frames reach the end of
     the window, then reads the frames in the window from the ring buffer and
     gives them to the Clip Writer;
  5. gets the next sample number from the Session Service;
  6. builds the sample record: ids, capture time, label, status `accepted`,
     the session's handedness, the frame size, and the gesture's positions as
     columns of time (seconds from the first position), horizontal and
     vertical fractions of the frame;
  7. when the Clip Writer finishes, adds the clip reference (or none, if
     encoding failed), writes the record through the Dataset Store, and
     updates the latest sample in the state to saved.
- The save job reports completion to the main loop as a message. The loop
  enters READY only when the countdown is over and the save job is done.
- A pause request during RECORDING is held until the gesture ends and the
  state machine has processed the result.

**Interactions.** Receives commands from the Application Server and results
from the Capture Engine. Sends arm and disarm commands to the Capture Engine,
frames to the Clip Writer and sample records to the Dataset Store. Gets sample
numbers from the Session Service. Reads the session from the Application State
and writes the capture state, active label, latest sample and last discard to
it.

### 4.8 Clip Writer

**What it does.** It turns a list of frames into a video clip file.

**How it works.** It takes the frames with their capture times, the measured
frame rate and a target path. Each frame is placed in the clip at its capture
time, so a moment in the clip is the same moment as in the recorded positions
even when the camera's rate varies. A separate worker process, started by the
application and used for one clip after another, encodes the frames as H.264
into a temporary file in the session's `videos` folder, then renames it to the
final name, so a clip is either complete or absent. The encoding runs in its own
process because the video libraries it needs clash, on some platforms, with the
camera libraries used by the rest of the application (see `docs/notes.md`); the
caller never waits for it. If the worker stops unexpectedly, the clip being
written is reported as failed and a new worker is started for the next one. If
encoding fails it reports failure and the Capture Controller saves the sample
with no clip. Nothing else in the application depends on a clip existing.

**Interactions.** Receives frames from the Capture Controller. Returns the clip
path, or failure, to it. Writes the clip file.

### 4.9 Sample Library

**What it does.** It finds and changes stored samples, for both review (the
samples of one session) and browsing (the whole dataset), and keeps the sample
counts.

**How it works.**

- When a data folder is opened it scans the sessions once and builds an
  in-memory index: one summary per sample (id, session, author, label, status,
  capture time, whether it has a clip), plus accepted counts per label.
- The Dataset Store notifies the Sample Library of every change to a stored
  sample, whoever made it: a new sample from the Capture Controller, or an
  edit or deletion made through the Sample Library. The Sample Library updates
  the index, then writes the new Counts and an increased Samples revision to
  the Application State.
- Queries filter the index by label, session, author, date and status, and
  return a page. Review is the query for one session in capture order; the Web
  UI keeps track of which sample is selected.
- Edits (label, status) and deletions are applied through the Dataset Store:
  the session's samples file is rewritten atomically, and for a deletion the
  clip is removed. Edits are allowed in any session, open or ended.
- Images are made on demand by the shared path renderer from the stored
  positions. Thumbnails are cached in the operating system's cache location,
  keyed by sample id and a hash of the positions and the mirror setting. The
  overlay view decodes one frame from the sample's clip. When `mirrorPreview`
  is on, the images are mirrored left to right to match the live view, and
  the sample details carry `mirrored` so the scrubbing view flips the video
  and path together. The stored data is never mirrored.
- A missing clip never blocks listing, filtering or editing. The sample's
  details state whether it has a clip. Without one, the Web UI hides the
  overlay and video views and says why. A clip removed from disk is treated the
  same as one that was never recorded.

**Interactions.** Receives requests from the Application Server and change
notifications from the Dataset Store. Reads and writes samples through the
Dataset Store. Writes the Counts and Samples revision to the Application State
and reads the session from it. Answers the Label Service's question of how many
samples use a label.

### 4.10 Label Service

**What it does.** It manages the shared list of spell labels.

**How it works.** It reads `config/labels.yaml` at startup, writes the list to
the Labels field of the Application State, and updates the field whenever the
list changes. It writes changes back to the file, keeping its comments. Each
label has an identifier and a display name; renaming changes only the display
name. Adding checks that the identifier is unique and well formed. Removing is
refused if the Sample Library reports samples using the label. It checks the
file's modification time and re-reads it when it changes, so labels pulled from
git appear without a restart.

**Interactions.** Receives requests from the Application Server. Asks the
Sample Library for label use counts. Writes the Labels to the Application State.
Reads and writes `config/labels.yaml`.

### 4.11 Dataset Store

**What it does.** It is the one component that reads and writes the data
folder. It is part of the shared library, so the classifier reads data with the
same code that wrote it.

**How it works.** It implements `docs/data-handling.md`: the folder layout, the
file formats, the three crash-safe write routines (replace, append and delete),
the export, merge and consistency check operations, and the cleanup at open.
It notifies its subscribers of every change it makes: a sample added, updated
or deleted, and a session written. See `lib/docs/design.md`.

**Interactions.** Called by the Session Service, Capture Controller and Sample
Library. Notifies the Sample Library of changes. Reads and writes the data
folder.

## 5. Interfaces

### 5.1 Event stream

| Event | Carries |
|---|---|
| `state` | The whole Application State snapshot, on connect and on change |
| `motion` | Speed, moving or not, thresholds (a stream, at frame rate) |

The `motion` readings are not part of the Application State. Everything else
the Web UI shows about the current state comes from `state`.

### 5.2 HTTP interface

| Endpoint | Purpose |
|---|---|
| `GET /api/stream` | Live video; `view=camera` or `view=mask` |
| `GET /api/events` | The event stream (`state` and `motion`) |
| `GET /api/state` | The current Application State snapshot |
| `GET /api/cameras` | List cameras |
| `PUT /api/camera` | Choose the camera |
| `POST /api/calibration/freeze` | Freeze a frame |
| `POST /api/calibration/clicks` | Add clicked points; returns the mask |
| `POST /api/calibration/measure` | Run the guided motion measurement |
| `PUT /api/settings` | Change settings (refused during a session) |
| `GET /api/profiles` | List profiles |
| `PUT /api/profiles/{name}` | Save a profile |
| `POST /api/profiles/{name}/load` | Load a profile |
| `DELETE /api/profiles/{name}` | Delete a profile |
| `GET /api/sessions` | List sessions, open and ended |
| `POST /api/sessions` | Start a session |
| `POST /api/sessions/{id}/load` | Load a session; `mode=review` or `resume` |
| `POST /api/sessions/current/end` | End the session |
| `PATCH /api/sessions/{id}` | Change the name and/or notes of any session |
| `DELETE /api/sessions/{id}` | Delete a session that is not loaded |
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

Responses to commands report only success or error; the result appears in the
next `state` event. Requests that need a clip, namely the video and the overlay
image, return "not found" for a sample without one. A resume request is
refused, with the reason, when the session is ended or its camera is
unavailable. The sample listing filters by label, session, author, date and
status.

### 5.3 Command line

| Command | Purpose |
|---|---|
| `wand-collect serve` | Start the application |
| `wand-collect export` | Write a consolidated file from data folders |
| `wand-collect merge` | Merge data folders into a target folder |
| `wand-collect check` | Run the consistency check |

Export, merge and check use the Dataset Store, work without a camera, and follow
the rules in `docs/data-handling.md`.

### 5.4 Application settings

Set in `config/data-collection.yaml`, with camel case keys:

| Key | Meaning | Default |
|---|---|---|
| `dataFolder` | Where datasets are stored | `data` |
| `server.host`, `server.port` | Where the app listens | local only, 8000 |
| `camera.index` | Preferred camera | 0 |
| `camera.width`, `.height`, `.fps` | Requested mode | 640, 480, 30 |
| `countdownS` | Countdown length in seconds | 3.0 |
| `clipPadding.preS`, `.postS` | Clip padding in seconds | 2.0, 2.0 |
| `endThresholdRatio` | End threshold as a fraction of start | 0.6 |
| `mirrorPreview` | Show the live view mirrored, like a mirror | true |
| `shortcuts` | Key bindings | as in 4.1 |

## 6. Data

Everything is stored as defined in `docs/data-handling.md`. The application
writes:

- `session.json` when a session starts, with `highestSampleNumber` updated each
  time a sample is saved and `endedAt` set when the user ends the session;
- one line in the session's sample file per captured gesture, and its clip,
  when it is saved; a resumed session keeps adding lines to the same file;
- a rewrite of the sample file for each label or status change; a deleted
  sample is removed from the file and its clip is deleted.

## 7. Testing

- **Capture Controller**: driven by a fake clock and scripted gestures. Checks
  the sequence of states, auto-accept, discards, that a pause during a gesture
  is held until the gesture ends, that review opens only once a sample is saved,
  resume in each state, and that READY is never entered before the sample is
  saved.
- **Application State**: each field is written only by its owner; readers
  always get a consistent snapshot while writers update from several threads;
  every update notifies the listeners; the Calibration Service refuses
  settings changes, profile loads and color calibration while a session is
  loaded for capture; a settings change and a session start never interleave;
  the Capture Engine picks up changed settings on its next frame.
- **Session Service**: start, end, list and load; an ended session cannot be
  resumed but can be reviewed and edited; closing the application leaves a
  session open; resume is refused when the recorded camera is unavailable;
  sample numbers continue after a delete and after a resume.
- **Other services**: against a temporary data folder, including settings
  locking, label rules, Sample Library queries, and samples whose clip is
  missing or removed.
- **Whole application**: the HTTP interface exercised with a recorded video in
  place of the camera: calibrate, start a session, replay a clip of gestures,
  pause, reject one in review, resume with another label, restart the
  application, resume the open session, and check the files on disk. A client
  on the event stream checks the snapshot after each command, and a second
  client sees the same snapshots.
- **Manual**: a checklist for real cameras on macOS and Linux, including
  camera selection, the motion tuning screen and resuming a session. Only the
  macOS run is done as part of the main work; the Linux run, and the Linux
  checks of the build and the video encoding, are deferred (requirement N4)
  and tracked as task DC-S2 in `tasks.md`. The design is meant to work
  unchanged on Linux, but that is unverified until then.
- The shared library's tests are described in `lib/docs/design.md`.

## 8. Requirement coverage

| Requirement | Where addressed |
|---|---|
| R1 Setup and calibration | 3.3, 4.4, 5.2 |
| R2 Session management | 3.2, 4.3, 4.5, 6, `docs/data-handling.md` |
| R2.5 Merge | 5.3, `docs/data-handling.md` |
| R2.6, R2.7 Load, resume, end | 3.2, 4.3, 4.5, 5.2 |
| R2.9 Name and notes | 4.5, 5.2 |
| R3 Labels | 4.10 |
| R4 Recording | 3.4, 4.6, 4.7 |
| R5 Review | 3.4, 4.1, 4.9 |
| R6 Storage | 4.8, 4.11, 6, `docs/data-handling.md` |
| R7 Browse and review | 4.1, 4.9, 5.2 |
| N1 Shared code | 2.2, `lib/docs/design.md` |
| N2 Throughput | 3.4 |
| N3 Responsiveness | 4.6 |
| N4 Platform | `docs/notes.md` |
| N5 Offline testability | 7, `lib/docs/design.md` |
