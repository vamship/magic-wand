# Glossary

> **Version** 1 | **Updated** 2026-11-01 | **Draft**

## Overview

This document defines the terms that the project's documents use in a shared
sense. After reading it you will know what each term means everywhere in the
project. Documents link here instead of redefining these terms. Terms that
belong to one component are defined in that component's documents.

## Terms

- **Calibration**: choosing and testing the camera, the vision settings and
  the motion settings against a live view, before a data collection session.
- **Dataset**: the stored sessions and samples recorded by data collection.
- **Gesture**: one deliberate motion of the tip, bounded by idle at the start
  and end.
- **Idle**: the state in which the tip is not moving, or moves below the speed
  threshold, so that natural hand tremor is ignored.
- **Label**: the name of a spell.
- **Motion**: the state in which the tip moves at or above the speed
  threshold.
- **Sample**: a recorded gesture stored in a dataset, with its label and
  status.
- **Session**: one run of data collection by one person with fixed settings.
  Capturing can be paused and resumed within a session. A session stays open
  until the user ends it; an ended session can be reviewed but not resumed.
- **Status**: whether a stored sample is `accepted` or `rejected`. Rejected
  samples stay in the dataset. Deleting a sample is different: it removes the
  sample from the dataset entirely.
- **Tip**: the approximate center of the ping pong ball on the wand. It is the
  point whose motion the system tracks.
