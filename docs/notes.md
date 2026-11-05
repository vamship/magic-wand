# Notes

> **Version** 3 | **Updated** 2026-11-04 | **Approved**

## Overview

This document records assumptions and constraints that affect decisions but
need no action now: cameras, platforms, wands and handedness. After reading
it you will know what the project takes for granted. Items that need work
are tasks in the owning component's `tasks.md`, not notes.

## Cameras

- Teammates use different laptop cameras. A camera may ignore the requested
  resolution or frame rate, and auto-exposure can lower the frame rate in dim
  light. The application records the mode it actually got and warns when it
  differs from the request.
- Stored positions are normalized and carry real timestamps, so differing
  resolutions and frame rates remain comparable. Resampling to a fixed rate
  is done when training or classifying.
- On macOS the terminal or Python process needs camera permission.

## Platforms

- macOS and Linux are supported. Windows is best effort and untested.
- Everything so far was verified on macOS only. Linux verification is task
  DC-S2.
- WSL2 does not expose webcams by default, so Windows users may not be able
  to capture from a camera there.

## Wands

- The wands are expected to be identical, but small color differences exist.
  Calibration, not the wand, absorbs these differences.

## Handedness

- Left-handed users' gestures may be mirrored versions of right-handed ones.
  Data collection only records handedness; training decides what to do.

## Video clips

Findings of the H.264 encoding spike (task DC-S1), run on macOS (Apple
Silicon) with 150 frames of 640x480 at 30 fps. The frames were random noise
with moving shapes, a worst case for compression.

| Encoder | Time | Result |
|---|---|---|
| PyAV `libx264` (chosen) | 1.1 s | H.264, `yuv420p`, `faststart` set |
| OpenCV `avc1` | 2.6 s | H.264, but no `faststart` |
| OpenCV `MJPG` in AVI | 1.3 s | Works, files almost twice as large |

- The PyAV file played in Safari and Chrome. The clip writer encodes with
  PyAV, using `libx264`, `yuv420p` and `faststart`.
- Importing PyAV and OpenCV in one process on macOS prints an Objective-C
  warning that both bundle their own `libavdevice`, which "may cause spurious
  casting failures and mysterious crashes". Nothing crashed in the spike. To
  avoid it, the application keeps PyAV out of its main process: the clip
  writer encodes in a separate worker process, and the overlay image reads
  its frame with OpenCV.
- Linux has not been tested (task DC-S2).
