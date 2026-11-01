# Notes

Assumptions and constraints that need no action now but affect decisions.
Items that need work become tasks in the owning component's `tasks.md`.

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
- WSL2 does not expose webcams by default, so Windows users may not be able
  to capture from a camera there.

## Wands

- The wands are expected to be identical, but small color differences exist.
  Calibration, not the wand, absorbs these differences.

## Handedness

- Left-handed users' gestures may be mirrored versions of right-handed ones.
  Data collection only records handedness; training decides what to do.
