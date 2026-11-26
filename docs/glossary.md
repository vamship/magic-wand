# Glossary

> **Version** 3 | **Updated** 2026-11-26 | **Draft**

## Overview

This document defines the terms that the project's documents use in a shared
sense. After reading it you will know what each term means everywhere in the
project. Documents link here instead of redefining these terms. Terms that
belong to one component are defined in that component's documents.

## Terms

- **Calibration**: choosing and testing the camera, the vision settings and
  the motion settings against a live view, before a data collection session.
- **Candidate**: one combination of hyperparameter values that an exploration
  evaluates.
- **Classifier**: a trained model of one family, wrapped so that it can
  predict a spell with a confidence, be saved and be loaded. Inference uses
  classifiers; it never trains them.
- **Component**: a building block inside a subsystem, or in the shared
  library, such as vision or the classifier.
- **Confidence threshold**: the confidence below which a prediction is
  treated as not recognized.
- **Dataset**: the stored sessions and samples recorded by data collection.
- **Experiment definition**: a named file, kept in git as code, that states
  the classifier family, the hyperparameter space, the validation scheme and
  the comparator of an exploration.
- **Exploration**: evaluating the candidates of a hyperparameter space for
  one classifier family and ranking them.
- **Gesture**: one deliberate motion of the tip, bounded by idle at the start
  and end.
- **Gesture data**: the consolidated table of all accepted gestures, each with
  its raw positions, its normalized form and its metadata, that training
  reads. It is derived from the training data.
- **Hyperparameter**: a setting of a classifier family that is chosen before
  training, such as a learning rate, and not learned from data.
- **Idle**: the state in which the tip is not moving, or moves below the speed
  threshold, so that natural hand tremor is ignored.
- **Label**: the name of a spell.
- **Model id**: the identifier of a trained classifier, of the form
  `<family>-<timestamp>`. Its report and its files carry the same id.
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
- **Subsystem**: one of the three parts of the system, each with its own
  folder and documents: data collection, training and inference.
- **Tip**: the approximate center of the ping pong ball on the wand. It is the
  point whose motion the system tracks.
