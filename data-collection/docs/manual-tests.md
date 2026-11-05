# Data Collection Application - Manual Tests

> **Version** 1 | **Updated** 2026-11-04 | **Draft**

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
- Use a data folder you can throw away: `--data-folder /tmp/wand-check`.
- Record each result in section 3 as `pass`, `fail` or `n/a`. Put a note under
  the table for anything that is not a plain pass. Each failure becomes a
  follow-up task in `tasks.md`.
- Repeat the calibration steps (2.1 to 2.4) in three conditions: usual
  lighting on a plain wall (A), dim light on a plain wall (B), and bright mixed
  light with a cluttered desk behind (C). Record each as 2.1A, 2.1B and so on.

| Run | Computer and OS | Camera | Browser | Date |
|---|---|---|---|---|
| macOS | | | | |
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
  Expect: Capture pauses and Review opens with the latest sample selected.

- **5.2** Step through the samples with the arrow keys and switch to the
  overlay.
  Expect: Each sample shows its path. The overlay shows the camera frame at the
  start of the gesture.

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
  Expect: Calibrate shows the recorded settings, and the next sample is numbered
  after the last one.

- **6.3** End the session, then try Resume.
  Expect: Resume is refused with a reason. Review works and edits are saved.

- **6.4** Start a session, stop the application, unplug the camera, start again
  and resume.
  Expect: Resume is refused and the message names the camera.

- **6.5** Resume with a camera that delivers another mode, if one is available.
  Expect: The session resumes and a warning names both modes.

### Check, merge, export and missing clips

- **7.1** Run `uv run wand-collect check <folder>`.
  Expect: No errors.

- **7.2** Run `merge` into a new folder, then again.
  Expect: The sessions are reported as copied, then as skipped.

- **7.3** Run `export` with `--status accepted`.
  Expect: One line per accepted sample, with no video.

- **7.4** Delete one clip file by hand. Open Browse and Review.
  Expect: The sample is listed and editable. Overlay and video are unavailable
  and say why. `check` lists a note, not an error.

## 3. Results

| Step | macOS | Linux |
|---|---|---|
| 0.1 | | n/a |
| 0.2 | |  |
| 0.3 | |  |
| 1.1 | |  |
| 1.2 | |  |
| 1.3 | |  |
| 1.4 | |  |
| 2.1 | |  |
| 2.2 | |  |
| 2.3 | |  |
| 2.4 | |  |
| 3.1 | |  |
| 3.2 | |  |
| 3.3 | |  |
| 3.4 | |  |
| 4.1 | |  |
| 4.2 | |  |
| 4.3 | |  |
| 4.4 | |  |
| 4.5 | |  |
| 4.6 | |  |
| 5.1 | |  |
| 5.2 | |  |
| 5.3 | |  |
| 5.4 | |  |
| 5.5 | |  |
| 6.1 | |  |
| 6.2 | |  |
| 6.3 | |  |
| 6.4 | |  |
| 6.5 | |  |
| 7.1 | |  |
| 7.2 | |  |
| 7.3 | |  |
| 7.4 | |  |
| 2.1A, 2.1B, 2.1C | | |
| 2.2A, 2.2B, 2.2C | | |
| 2.3A, 2.3B, 2.3C | | |
| 2.4A, 2.4B, 2.4C | | |

## 4. Follow-up tasks

| Problem found | Task |
|---|---|
| | |
