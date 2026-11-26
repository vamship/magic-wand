# Training Subsystem - Requirements

> **Version** 3 | **Updated** 2026-11-26 | **Draft**

## 1. Overview

This document lists what the training subsystem must do (functional
requirements R1 to R7) and the qualities it must have (N1 to N6). After
reading it you will know what the subsystem is for, what a user can do with
it, and which requirement IDs the design and task documents refer to.

The subsystem has three functions:

1. **Consolidation.** It turns the datasets recorded by data collection into
   one table of raw and normalized gestures, the training data, ready for
   training.
2. **Exploration.** It searches the hyperparameter space of each classifier
   family and ranks the candidates.
3. **Training.** It trains the best candidate of a family, evaluates it on
   data it has not seen, chooses a confidence threshold and saves the
   classifier.

The families to compare include, for example, Naive Bayes, a support vector
machine, a random forest and a multilayer perceptron (MLP, a neural network);
the design names the first set. Normalization and the classifiers that
inference loads come from the shared library, so inference runs the code that
training evaluated.

## 2. Definitions

Terms used across the project (gesture, sample, session, label, status,
dataset, training data, hyperparameter, candidate, exploration, experiment
definition, classifier, model id and others) are defined in
`docs/glossary.md`. Terms specific to this document:

- **Tuning set** and **test set**: the two parts of the training data. The
  tuning set is used to explore and to train; the test set is used only to
  evaluate the finished candidate (R6).
- **Validation scheme**: how a candidate is judged inside an exploration, on
  parts of the tuning set (R5).
- **Comparator**: the rule that ranks candidates by their metrics (R5).
- **Test case**: one gesture shown to a trained classifier during final
  evaluation, with the outcome that counts as correct (R6).

## 3. Functional Requirements

### R1. Training data
- R1.1 The tool builds the training data from datasets: by default every
  dataset in the data location, or the datasets the user names, or an export
  file. Each accepted sample becomes one row holding its raw positions, its
  normalized form, and its metadata (sample, session, author, handedness,
  label, whether the label is a spell, and the duration).
- R1.2 Normalization is done by the shared library with fixed settings that
  the user cannot change. The settings and the library's normalization version
  are recorded in the training data.
- R1.3 The training data records where it came from: the datasets and
  sessions it covers and a fingerprint of their samples, so that two copies can
  be compared.
- R1.4 Building is deterministic: the same datasets give the same training
  data.
- R1.5 A session that appears in more than one dataset is used once. If its
  copies differ, the build stops and names the session.
- R1.6 The user can check whether committed training data matches the
  datasets. Training needs only the training data and never the datasets.
- R1.7 The tool refuses training data in a format version it does not know.

### R2. Access to training data
- R2.1 The user can load the training data, and select rows by the values of
  one or more columns to produce a smaller set with the same abilities.
- R2.2 A set can be shuffled with a seed and split by percentage into two or
  more sets. A split can keep the share of each label the same on every side.
- R2.3 A set can be read as a whole or in batches, as arrays of the normalized
  gestures with their labels.
- R2.4 The user can see how many samples a set has, per label and per author.
- R2.5 Selecting, shuffling and splitting do not copy the data.

### R3. Trainers
- R3.1 One interface trains a model of any family on one set, evaluates it on
  another, saves it, loads it, and reports its metrics. The workflow contains
  no code specific to a family.
- R3.2 Every trainer reports the same standard metrics: accuracy, macro F1, log
  loss, the time to classify one gesture and the time to train. A trainer may
  report further metrics of its own.
- R3.3 A trainer can report, for each gesture of the evaluation set, the
  spell it predicts and its confidence.
- R3.4 A trainer accepts values for the hyperparameters of its family, uses a
  documented default for any it is not given, and rejects an unknown
  hyperparameter or a value of the wrong kind or out of range, naming the
  hyperparameter.
- R3.5 A trainer produces a classifier of the shared library that inference
  can load, with no training code or training dependency.
- R3.6 Anything a trainer learns from data, such as feature scaling or the
  stopping point of the MLP, comes from the training set it was given.
- R3.7 There is a trainer for each family of the first set named in the design.
  A new family is added with a trainer and an experiment definition, and
  nothing else changes.

### R4. Experiment definitions
- R4.1 An experiment definition names the family, the hyperparameter space,
  the validation scheme and the comparator of an exploration.
- R4.2 Each hyperparameter in the space is either a range, given by its
  minimum, its maximum, the number of values and whether they are spaced
  linearly or logarithmically, or an explicit list of values.
- R4.3 Experiment definitions are named files kept in the repository by
  family. They are reviewed and changed like code.
- R4.4 The tool rejects a definition with an unknown key, an invalid range or a
  hyperparameter the family does not accept, before any training starts.

### R5. Exploration
- R5.1 The tool enumerates every candidate of the space: one value for each
  hyperparameter, in all combinations. It states the number of candidates
  before starting.
- R5.2 It evaluates each candidate with the definition's validation scheme on
  the tuning set only. Two schemes are available: k-fold and a single split.
- R5.3 For each candidate it collects the trainer's metrics on every
  validation fold and aggregates them over the folds. A candidate's score is
  the average over its folds, never the best fold.
- R5.4 The comparator ranks the candidates by their aggregated metrics. A
  comparator can rank by one metric in either direction, with a second
  metric as tie-breaker.
- R5.5 An exploration run writes its own folder holding a copy of the
  definition, the settings of the run, and the metrics of every candidate and
  fold. A run never overwrites another run.
- R5.6 Results are written as candidates finish, so an interrupted run keeps
  what it measured.
- R5.7 The user can load a finished or interrupted run and ask for the best
  candidate, the best n candidates, the metrics of a candidate, and the effect
  of one hyperparameter on a metric.
- R5.8 The tool shows progress while it runs.

### R6. Training and evaluation
- R6.1 The tool splits the training data into a tuning set and a test set by
  percentage, with a seed. Every sample of a label that is not a spell goes to
  the test set. The same data, seed and percentage always give the same
  split, so an exploration and the training that follows it share one test set.
- R6.2 The tool trains the candidate on the tuning set, taking its
  hyperparameters from a candidate of an exploration run (by default the best
  one) or from values given directly.
- R6.3 The tool evaluates the trained candidate on the test set, with three
  kinds of test case: held-out spells, backward spells (held-out spells with
  their positions in reverse order) and non-spell recordings. When there are no
  non-spell recordings it says so and goes on without them.
- R6.4 Evaluation reports, over a range of confidence thresholds: the share of
  spells recognized with the right label, the share recognized with a wrong
  label, the share not recognized, the share of backward spells that trigger,
  and the share of non-spell recordings that trigger. It also reports the
  confusion between labels, precision and recall per label, and the time per
  gesture.
- R6.5 The tool recommends a confidence threshold: the one that recognizes the
  most spells while the shares of triggering backward spells and of triggering
  non-spell recordings stay at or below a limit that the user can set.
- R6.6 After evaluation the tool trains the candidate again on all the
  training data and saves that classifier with the recommended threshold.
- R6.7 A saved classifier carries its labels, its normalization settings, the
  recommended threshold, its hyperparameters, a summary of its test metrics, a
  reference to its exploration run, and the fingerprint of the training data.

### R7. Reports and models
- R7.1 Every exploration and every training run writes a report in Markdown,
  with its figures and the tables it was made from, so that it can be read
  and shared through git.
- R7.2 An exploration report shows its definition, the ranked candidates and,
  for each hyperparameter, its effect on the compared metric.
- R7.3 A training report shows the split, the measures of R6.4 as tables and
  charts, the recommended threshold and the hyperparameters used.
- R7.4 Reports and models are organized by family. An exploration is kept
  apart from a training run, and every trained classifier has a model id that
  names its report and its files.
- R7.5 An index lists every exploration and every model with a link to its
  report, and is updated whenever one is written.
- R7.6 Deleting an exploration run does not affect any model or training
  report.
- R7.7 A training run or a saved model never overwrites another.

## 4. Non-functional Requirements

- **N1. Reproducible.** The same training data, definition and seed give the
  same split and the same ranking, for the families whose training can be
  repeated exactly.
- **N2. No leakage.** The test set is never seen by exploration or by
  training. Everything learned from data comes from the set being trained on.
- **N3. Extensible.** A new family or a new validation scheme is added without
  changes to the parts that exist.
- **N4. Practical speed.** Building the training data takes seconds. An
  exploration of the families other than the MLP takes minutes on a laptop;
  the MLP may take longer.
- **N5. Testable.** The tests need no camera and no real dataset; they use
  small synthetic data.
- **N6. Light inference.** Using a saved classifier needs only the shared
  library; nothing in training has to be installed.
