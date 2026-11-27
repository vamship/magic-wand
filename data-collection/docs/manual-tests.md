# Data Collection Application - Manual Tests

> **Version** 3 | **Updated** 2026-11-15 | **Draft**

## Overview

This document is the checklist for testing the data collection application
with real cameras. It lists the steps, what to expect from each, and a table
to record the result on macOS and on Linux. The automated tests use a recorded
video; this checklist covers what they cannot: a real camera, real lighting, a
real wand and a real person. The macOS run belongs to task DC-V2. The Linux
column is filled in by task DC-S2.

## 1. How to use this checklist

- Run the application from the repository root with
  `uv run wand-collect serve` and open the printed address in a browser.
- Use a dataset you can throw away: `--data-location /tmp/wand-check
  --dataset check`.
- Record each result in section 3 as `pass`, `fail` or `n/a`. Put a note under
  the table for anything that is not a plain pass. Each failure becomes a
  follow-up task in `tasks.md`.
- Repeat the calibration steps (2.1 to 2.4) in three conditions: usual
  lighting on a plain wall (A), dim light on a plain wall (B), and bright mixed
  light with a cluttered desk behind (C). Record each as 2.1A, 2.1B and so on.

| Run | Computer and OS | Camera | Browser | Date |
|---|---|---|---|---|
| macOS | macOS (Darwin 25.6.0) | Built-in, external webcam and iPhone | Chrome | 2026-11-14 |
| Linux | | | | |

## 2. Steps

### Before the first run

- **0.1** On macOS, allow camera access for the terminal app that runs the
  application (System Settings, Privacy and Security, Camera).
  Expect: The first start asks for permission once; later starts do not.

- **0.2** Start the application.
  Expect: One line with the address, and no Objective-C `libavdevice` warning.

- **0.3** Start it with the camera unplugged or blocked.
  Expect: It starts and says no camera is available. The Setup page shows no
  live view.

### Setup and camera

- **1.1** Open the Setup page.
  Expect: The cameras are listed and the live view shows the chosen one.

- **1.2** Choose another camera, if there is one.
  Expect: The live view switches. The mode line shows the mode asked for and the
  mode delivered.

- **1.2b** Reload the Setup page, and switch between cameras a few times.
  Expect: No camera switches on by itself, apart from the one you choose (the
  phone's camera stays off). The list does not change. Then plug in or remove a
  camera and press Refresh list.
  Expect: Only then are the cameras scanned (the cameras flicker once) and the
  list updates.

- **1.3** Move a hand in front of the camera.
  Expect: The live view keeps up, with no visible lag or stutter (N3).

- **1.4** Read the mode line.
  Expect: It shows 640x480 at about 30 fps (R6.7), or a warning says the mode
  differs.

### Calibration

- **2.1** On the Calibrate page, press Freeze, then click the wand tip.
  Expect: The mask marks the tip and says how many other regions are marked.

- **2.2** Click the tip in other places, then return to the live view.
  Expect: More clicks refine the mask. The live view tracks the tip.

- **2.3** Switch the live view to the mask and wave the wand across the picture.
  Expect: The tip stays marked everywhere. Few or no other objects are marked.

- **2.4** Move a slider (hue width) while watching the live view.
  Expect: The change shows at once.

### Motion tuning

- **3.1** Hold the wand still.
  Expect: The page shows idle, and the speed stays below the start threshold.

- **3.2** Draw a gesture.
  Expect: The page shows motion during the gesture and idle after it. The graph
  shows the speed crossing the thresholds.

- **3.3** Run the guided measurement: hold still, then wave.
  Expect: The proposed thresholds replace the motion settings, in a sensible
  order.

- **3.4** Save a profile, change a slider, then load the profile.
  Expect: The saved values return.

### A capture run

- **4.1** On Setup, enter an author and a hand, then press Start and record.
  Expect: The session starts and the Record page opens.

- **4.2** Choose a label and press Start.
  Expect: A large countdown, then Go.

- **4.3** Draw ten gestures of one label.
  Expect: Each ends the motion, shows a path image and raises the accepted count
  by one. Saving finishes before the next Go.

- **4.4** Make a quick flick and a tiny movement.
  Expect: Each shows a discard reason, and the count does not change.

- **4.5** Press a digit key during a countdown.
  Expect: The active label changes for the next gesture.

- **4.6** Time a cycle with a stopwatch.
  Expect: A cycle takes about the gesture time plus the countdown (N2).

### Pause and review

- **5.1** Press Escape while Go is shown.
  Expect: Capture pauses and Review opens with the newest sample (the first
  tile) selected.

- **5.2** Step through the samples with the arrow keys (Left and Right by
  tile, Up and Down by row) and switch to the overlay.
  Expect: Each sample shows its path. The overlay shows the camera frame at the
  start of the gesture. With many samples, scroll the grid down: more load as
  you near the end, and the selected sample stays where it is.

- **5.3** Reject a sample, restore it and reject it again. Relabel another with
  a digit key. Delete a third after confirming.
  Expect: Each change shows at once, and the Browse counts follow.

- **5.4** Scrub the video of a sample.
  Expect: The video plays and steps by frame, with the path drawn on it.

- **5.5** Press Escape again.
  Expect: Capture resumes with a countdown.

### Resume and ending

- **6.1** Stop the application with Ctrl+C in the middle of a session and start
  it again.
  Expect: The session is listed as open, with its sample count.

- **6.2** Resume it on the Setup page.
  Expect: The Calibrate page opens with "Check the camera": the settings show
  the recorded values and are read-only, and only the camera can be changed.
  After Continue to Record, the next sample is numbered after the last one.

- **6.3** End the session, then try Resume.
  Expect: The session has no Resume button (R2.6, DC-U2); the server also refuses it with a reason. Review works and edits are saved.

- **6.4** Start a session, stop the application, unplug the camera, start again
  and resume.
  Expect: Resume goes ahead on the camera that is available and opens the
  Calibrate page for the camera check, which says that every setting is locked
  except the camera. Starting capture is not possible before Continue to
  Record.
  Then open Review and press the button at the top.
  Expect: It reads "Check the camera first" and takes you back to Calibrate,
  with no error.

- **6.5** Resume with a camera that delivers another mode, if one is available.
  Expect: The session resumes and a warning names both modes.

- **6.6** Resume, then choose a different camera on the Calibrate page and
  continue.
  Expect: Capture works with that camera, and the session's `camera` in
  `session.json` is the new one.

- **6.7** Start a session and record a sample. Press Pause. Start a new
  session, record a sample, and pause it too. Resume the first one.
  Expect: Both sessions are listed as open. The first resumes with the camera
  check, its next sample number follows its last, and the second is
  unchanged.

### Check, merge, export and missing clips

- **6.8** Open Browse with a few hundred samples. Resize the window wide,
  then narrow, then short.
  Expect: The thumbnails are a grid in their own scrolling pane, the page does
  not scroll, and the selected sample (picture, buttons, details, and the
  actions at the bottom) stays beside the grid. In a narrow window it sits
  above the grid; in a narrow and short one the page scrolls and the sample
  sticks to the top. The arrow keys, Space, Backspace, P and the digits work as
  on Review, and the arrows go on to the next page at the end of a page.

- **6.9** Look at the thumbnails on Browse, then open the scrubbing view
  (S) of a sample and step through it.
  Expect: Each thumbnail shows its number of tracked points in the top left.
  The scrubbing view shows "Point n / total", which goes up as you step, and
  the total matches the number on the thumbnail. Setup, Calibrate, Record,
  Review and Browse all have the same width.

- **7.1** Run `uv run wand-collect check <folder>`.
  Expect: No errors.

- **7.2** Run `merge` into a new folder, then again.
  Expect: The sessions are reported as copied, then as skipped.

- **7.3** Run `export` with `--status accepted`.
  Expect: One line per accepted sample, with no video.

- **7.4** Delete one clip file by hand. Open Browse and Review.
  Expect: The sample is listed and editable. Overlay and video are unavailable
  and say why. The scrubbing view still opens and replays the path. `check` lists a note, not an error.

## 3. Results

| Step | macOS | Linux |
|---|---|---|
| 0.1 | pass | n/a |
| 0.2 | pass |  |
| 0.3 | pass |  |
| 1.1 | pass |  |
| 1.2 | pass |  |
| 1.2b | pass* |  |
| 1.3 | pass |  |
| 1.4 | pass |  |
| 2.1 | pass |  |
| 2.2 | pass |  |
| 2.3 | pass |  |
| 2.4 | pass |  |
| 3.1 | pass |  |
| 3.2 | pass |  |
| 3.3 | pass |  |
| 3.4 | pass |  |
| 4.1 | pass |  |
| 4.2 | pass |  |
| 4.3 | pass |  |
| 4.4 | pass |  |
| 4.5 | pass |  |
| 4.6 | pass |  |
| 5.1 | pass |  |
| 5.2 | pass |  |
| 5.3 | pass |  |
| 5.4 | pass |  |
| 5.5 | pass |  |
| 6.1 | pass |  |
| 6.2 | pass |  |
| 6.3 | pass |  |
| 6.4 | fail, then pass* |  |
| 6.5 | n/a |  |
| 6.6 | pass* |  |
| 6.7 | pass* |  |
| 6.8 | pass* |  |
| 6.9 | pass* |  |
| 7.1 | pass |  |
| 7.2 | pass |  |
| 7.3 | pass |  |
| 7.4 | pass |  |
| 2.1A, 2.1B, 2.1C | A pass, B and C n/a | |
| 2.2A, 2.2B, 2.2C | A pass, B and C n/a | |
| 2.3A, 2.3B, 2.3C | A pass, B and C n/a | |
| 2.4A, 2.4B, 2.4C | A pass, B and C n/a | |

Notes on the macOS results:

- A result marked `pass*` was not checked step by step. The person who ran the
  first pass used the application repeatedly afterwards, with the changes in
  place, and found these working. Step 6.4 failed in the first pass (the wrong
  camera was reopened, with no warning); the camera check on resume (DC-A15)
  replaced that behaviour, and it was found working in the same way.
- Conditions B and C of the calibration steps (dim light, mixed light with a
  cluttered desk) and step 6.5 (a camera with another mode) were not run: there
  was no setup for them. They stay open for a later run.
- Run on macOS with Chrome, a built-in camera, an external webcam and a phone
  camera. The Linux column is for DC-S2.

## 4. Follow-up tasks

| Problem found | Task |
|---|---|
| 0.3: with camera access denied, the terminal repeats the OpenCV "camera access has been denied" message about ten times (once per probed camera), and the UI says only "No cameras were found" without naming the permission. Minor. | DC-U8 |
| 1.4: the measured rate is far below 30 fps and varies between measurements: built-in 18.2 then about 24, iPhone 17.6 then about 24, external 3.1 then 0.4, although the external feed looks smooth. The rate is measured once, over the first 2 seconds after the camera opens, so a startup stall gives a wrong number that stays until the camera is reopened. The step passes because the warning is shown. | DC-A14 |
| 5.3: deleting a sample works, but a toast then shows "no sample <id> not_found". Probably the page asks for the details of the sample it has just deleted, because the samples revision changes before the selection moves on. Not reproduced yet. | DC-U9 |
| 6.4: Resume after unplugging the external camera succeeded on the built-in camera, and tracking then failed because the calibration belonged to the other camera. On macOS the camera is identified by its index, which changes when a camera is unplugged. Both sessions in the test folder record `index:0`. The camera list reorders as cameras are opened, so cameras cannot be matched by name reliably. | DC-A15 (camera check by sight); step 6.4 and the new 6.6 need to be run again |
| 6.3: the original step expected a refused Resume, but the page offers no Resume for an ended session, as designed. The step now says so. | none |
| 6.5: not tested, no second camera that delivers a different mode. | none |
