# Training Tool - Requirements

> **Version** 1 | **Updated** 2026-11-25 | **Draft**

## 1. Overview

This document lists what the training tool must do (functional requirements
R1 to R9) and the qualities it must have (N1 to N5). After reading it you
will know what the tool is for, what a user can do with it, and which
requirement IDs the design and task documents refer to.

The tool turns the shared training dataset into a trained gesture classifier.
It compares the classifier families named in `docs/architecture.md` (Naive
Bayes, a support vector machine, a random forest and a neural network for time
series) on the same data and the same measures, so that the project can pick
one and justify the choice. It uses the shared library for gesture
normalization and for the classifiers, so that inference runs the code that
training evaluated.

## 2. Definitions

Terms used across the project (gesture, sample, session, label, status and
others) are defined in `docs/glossary.md`. Terms specific to this document:

- **Experiment**: one configuration file that describes what to train and how
  to evaluate it (R1).
- **Run**: one execution of an experiment, with its own output folder (R7).
- **Fold**: one division of the data into a training side and a test side. An
  experiment has one or more folds.
- **Test case**: one gesture shown to a trained classifier during evaluation,
  with the outcome that counts as correct (R5).
- **Confidence threshold**: the confidence below which a prediction is
  treated as "not recognized" (R6).

## 3. Functional Requirements

### R1. Experiments
- R1.1 One experiment file describes one experiment: the dataset, which
  labels to learn, the treatment of handedness, the normalization settings,
  the split, the classifiers with their settings, and the evaluation
  settings.
- R1.2 Every setting has a documented default, so a minimal experiment file
  names only the classifiers.
- R1.3 The tool rejects an experiment file with an unknown key, a value out
  of range or an unknown classifier family, and says which key is wrong,
  before any training starts.

### R2. Data loading
- R2.1 The tool reads a data folder (by default the shared training data) or
  an export file.
- R2.2 It uses only accepted samples. Samples of labels that are spells are
  training data and test cases; samples of labels that are not spells are
  test cases only.
- R2.3 It reports how many samples each label has, per author and in total,
  and stops with a clear message if a label to be learned has no samples.
- R2.4 Samples whose handedness differs from the experiment's handedness are
  excluded, or mirrored to the experiment's handedness, as the experiment
  chooses.

### R3. Normalization
- R3.1 Every gesture is normalized by the shared library's normalizer with the
  experiment's settings (number of points, context values).
- R3.2 Any scaling of features that a classifier needs is learned from the
  training side only and is saved with the classifier.

### R4. Splitting
- R4.1 Samples are split by session, so that no session has samples on both
  sides of a split.
- R4.2 The experiment chooses between a random split of sessions with a given
  test fraction, and leaving out one author at a time (one fold per author).
- R4.3 A split is determined by the experiment's seed. The same dataset, seed
  and settings give the same split.
- R4.4 Every classifier of an experiment gets the same folds.
- R4.5 The tool stops with a clear message if the training side of a fold has
  no samples of some label to be learned.

### R5. Test cases
- R5.1 The test side of a fold yields three kinds of test case: held-out
  spells (correct outcome: the right label), backward spells and non-spell
  recordings (correct outcome for both: not recognized).
- R5.2 A backward spell is a held-out spell with its positions in reverse
  order.
- R5.3 When the dataset has no non-spell recordings, the tool runs without
  them and says so in its report.

### R6. Training and evaluation
- R6.1 Each classifier of the experiment is trained on the training side of
  every fold through the classifier interface of the shared library; the tool
  contains no code specific to a family.
- R6.2 Evaluation reports, for each classifier and for a range of confidence
  thresholds: the share of held-out spells recognized correctly, the share
  recognized as the wrong spell, the share not recognized, the share of
  backward spells that trigger, and the share of non-spell recordings that
  trigger.
- R6.3 Evaluation also reports the confusion between labels, precision and
  recall per label, and the time a classifier needs per gesture, including
  normalization.
- R6.4 With several folds, the tool reports the measures per fold and over
  all folds together.
- R6.5 The tool recommends a confidence threshold for each classifier: the
  one that recognizes the most held-out spells while keeping the share of
  triggering backward spells, and of triggering non-spell recordings, at or
  below an experiment setting.

### R7. Runs
- R7.1 Each run writes its own folder holding the experiment file as it was
  run, the identity of the dataset, the folds, every prediction of the
  evaluation, the metrics, and the trained classifiers.
- R7.2 The dataset's identity is enough to tell whether two runs used the same
  data.
- R7.3 A run never overwrites another run.
- R7.4 The classifier saved by a run is trained on all samples of the
  learned labels, with the settings that were evaluated, and carries the
  recommended threshold from R6.5.

### R8. Comparison
- R8.1 A report puts the classifiers of one or more runs side by side on the
  measures of R6.2, R6.3 and R6.5, and shows, for each classifier, how
  recognition trades off against false triggering across thresholds.
- R8.2 The report states, for each run, the experiment's key settings and the
  dataset's identity.

### R9. Export for inference
- R9.1 The user can publish one classifier of one run to `models/` under a
  name of their choice, with its metrics summary.
- R9.2 A published classifier holds everything inference needs: the model,
  its labels, its normalization settings and its recommended threshold.

## 4. Non-functional Requirements

- **N1. Reproducible.** A run can be repeated from its folder: the same
  experiment and dataset give the same split and, for the classifiers that
  allow it, the same model.
- **N2. No leakage.** Nothing learned from the test side influences training,
  including feature scaling, early stopping and the choice of settings.
- **N3. Extensible.** Adding a classifier family needs no change to the
  workflow: it implements the library's interface and is named in the
  experiment.
- **N4. Practical speed.** On a laptop, an experiment with the three
  non-neural classifiers on the shared dataset takes minutes, not hours; the
  neural network is allowed longer.
- **N5. Testable.** The tool's tests need no camera and no real dataset;
  they use small synthetic datasets.
