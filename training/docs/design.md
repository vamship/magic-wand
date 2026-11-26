# Training Subsystem - Design

> **Version** 2 | **Updated** 2026-11-26 | **Draft**

## 1. Overview

This document describes how the training subsystem consolidates the training
data, explores the hyperparameters of each classifier family, and trains,
evaluates and saves classifiers. After reading it you will know the
components and their responsibilities, how a run flows through them, the
formats of the gesture data, the experiment definitions, the reports and the
saved models, and the commands that drive it. Requirements are in
`training/docs/requirements.md`; the system context is in
`docs/architecture.md`; the shape of the stored sessions is in
`docs/data-handling.md`.

The subsystem has to produce, for each classifier family, the best model the
data supports, and to show how that was found. The design addresses this in
three steps. Gesture data puts everything training needs in one table, so
every family trains on the same inputs. A single explorer, composed with a
family's trainer, searches the hyperparameter space the same way for every
family. A final step evaluates the chosen candidate on gestures that no step
before it has seen.

## 2. The data it works on

The shared training data holds 4,821 accepted samples from 29 sessions and
three authors, all right-handed.

- Five spells have about 760 samples each, and two have about 500.
- A median gesture has 50 positions and lasts 1.7 seconds; the middle 80
  percent last 1.2 to 2.4 seconds. The longest has 108 positions.
- There are no non-spell recordings yet. They will be added under a label that
  `config/labels.yaml` marks as not a spell; a label without the mark is a
  spell.

## 3. Components

- **Gesture data builder**: reads a data folder through the shared library,
  normalizes each accepted gesture and writes the gesture data.
- **Gesture data access**: loads the gesture data and provides selecting,
  shuffling, splitting and reading in whole or in batches.
- **Trainer**: trains, evaluates, saves and loads a model of one family
  (section 6). Each family has one.
- **Experiment definition**: a named file that states an exploration
  (section 7).
- **Explorer**: enumerates the candidates of a hyperparameter space, has the
  trainer train and validate each, ranks them with a comparator and stores the
  results (section 8). One explorer exists for each validation scheme.
- **Evaluator**: builds the test cases and computes the measures and the
  threshold recommendation (section 9).
- **Reporter**: writes the reports, the figures and the index (section 10).
- **Model store**: saves and lists the trained classifiers (section 10).

Normalization and the classifiers come from the shared library
(`docs/architecture.md`, sections 4.3 and 4.4). A classifier holds a trained
model of one family and can predict, save and load; it has no training code.
A trainer holds the training code of the family and produces a classifier.

## 4. System flow

```text
 1. build                  training data (sessions)
                                    |
                                    v
                            Gesture data builder
                                    |
                                    v
                            gesture-data/ (table)

 2. explore                 experiment definition
                                    |
                                    v
 gesture-data/ --> split --> tuning set     test set (kept aside)
                                |
                                v
         Explorer: for each candidate, for each validation fold
                   Trainer fits on one part, validates on the other
                                |
                                v  metrics, ranking
                      reports/<family>/exploration/<run id>/

 3. train       exploration run + candidate (or hyperparameters)
                                |
                                v
         Trainer fits on the tuning set --> Evaluator on the test set
                                |           measures, threshold
                                v
         Trainer fits on all data --> models/<family>/<model id>/
                                      reports/<family>/training/<model id>/
```

1. **Build.** The builder writes the gesture data. This is done when the
   training data changes, and the result is committed.
2. **Explore.** The run splits the gesture data into a tuning set and a test
   set (section 5.3) and uses only the tuning set. The explorer runs the
   candidates and writes the results as it goes.
3. **Train.** The run uses the same split. The trainer fits the chosen
   candidate on the tuning set and the evaluator measures it on the test
   set. The trainer then fits it again on all the data, and the result is
   saved with the threshold the evaluator recommended.

## 5. Gesture data

### 5.1 Normalization

Normalization is the library's (`docs/architecture.md`, section 4.3) with
fixed settings: 64 points, and the duration and the start position as
context values. A gesture becomes 63 motion vectors of two numbers each, plus
the duration in seconds and the start position, which is 129 numbers in the
flat form. The sequence form is the same 63 vectors as 63 steps of two
channels, with the three context values given separately.

The settings are fixed because tuning is about the models, and one form for
every family keeps their results comparable. 64 points lose little: on the
training data a resampled path stays within 0.003 frame-heights of the
original for the median gesture and within 0.008 for the 95th percentile.

### 5.2 Format

Gesture data is a folder `gesture-data/` holding two files.

`gestures.parquet` has one row per accepted sample, with these columns:

| Column | Content |
|---|---|
| `sampleId`, `sessionId` | Identifiers from the training data |
| `author`, `handedness` | From the session |
| `label` | Label id |
| `isSpell` | Whether the label is a spell |
| `durationS` | Gesture duration in seconds |
| `frameWidth`, `frameHeight` | Frame size in pixels |
| `rawTimeS`, `rawX`, `rawY` | Raw positions, as lists |
| `vectors` | 126 numbers: horizontal and vertical of each vector |
| `startX`, `startY` | Start position, in frame-heights |

`gestures.json` describes the file:

```json
{
  "formatVersion": 1,
  "builtAt": "2026-11-26T14:15:02-04:00",
  "source": "training-data",
  "sourceCommit": "0813bf3",
  "sessionIds": ["3f8c1d2e-9a4b-4c7e-8f10-5b6d7e8f9a0b"],
  "sampleCount": 4821,
  "fingerprint": "9c1f...",
  "normalization": {
    "points": 64,
    "context": ["duration", "startPosition"],
    "version": 1
  }
}
```

- The **fingerprint** is a SHA-256 hash over the sorted sample ids, each with
  its label and status. Two gesture data files cover the same samples when
  their fingerprints match. `sourceCommit` is the git commit of the
  repository when the source was `training-data`, and is empty otherwise.
- The `normalization.version` is the library's normalization version. A
  trainer or a classifier that records a different version is reported as a
  mismatch.
- Gesture data is derived from the training data and is rebuilt, not merged,
  when sessions are added. Rebuilding is deterministic, so a conflict in git
  is resolved by rebuilding. Comparing contents, and not file bytes, tells
  whether two builds agree.
- Only accepted samples are included. Rejected samples are left out.

### 5.3 Access and splitting

Loading gives a set that covers the whole table. A set offers:

- **Select** rows by the values of columns, for example one author, one
  label or spells only. The result is a set.
- **Shuffle** with a seed, and **split** by percentage into two or more sets.
  A split can be stratified so every side keeps the label shares.
- **Read** the whole set or batches of a size, as arrays in the flat form or
  the sequence form with the context values, and the labels.
- **Count** the samples per label and per author.

A set is a view of the loaded table (a list of row positions), so selecting
and splitting copy nothing.

The tuning and test sets come from one operation: the rows of labels that are
not spells all go to the test set, and the remaining rows are shuffled with
the seed and split by label-stratified percentage, 85 tuning and 15 test by
default. The split depends only on the gesture data, the seed and the
percentage, and is made again, not stored, when a run needs it. A run
records those three values, so training reproduces the split of an
exploration exactly.

Samples of one session resemble each other, so a random split rates a
classifier more favorably than a person it has not seen would. Selecting
by author gives that stricter test when it is wanted.

## 6. Trainers

A trainer is the one interface through which a family is trained and
evaluated. It does the following:

- **Train** on a set, given the values of the family's hyperparameters.
- **Evaluate** on a set, returning the standard metrics and, on request, the
  predicted label and confidence of every gesture.
- **Save and load** its trained model.
- **Produce a classifier** from the trained model for the shared library, to
  save in `models/`.
- **Validate** the hyperparameter values it is given before training: an
  unknown name, a value of the wrong kind or a value out of range is an error
  that names the hyperparameter.

Metrics are reported as named numbers. Every trainer reports the **standard
metrics**:

| Metric | Meaning |
|---|---|
| `accuracy` | Share of gestures given the right label |
| `macroF1` | F1 averaged over labels |
| `logLoss` | Log loss of the predicted probabilities |
| `timePerGestureMs` | Mean time to classify one gesture |
| `trainSeconds` | Time to train |

A family may add metrics of its own, for example the number of epochs the
neural network ran or the number of support vectors of the SVM. They are
stored with the others and are never used to compare families.

Each family has a trainer. The common implementation serves a family that
needs nothing special, and a subclass adds what a family needs.

| Family | Hyperparameters and defaults |
|---|---|
| `naiveBayes` | `varSmoothing` 1e-9 |
| `svm` | `kernel` rbf, `c` 10, `gamma` scale |
| `randomForest` | `trees` 300, `maxDepth` none, `minSamplesLeaf` 1 |
| `neuralNet` | `learningRate` 0.001, `batchSize` 64, `filters` 32, |
| | `hiddenUnits` 64, `dropout` 0.2, `maxEpochs` 60, `patience` 8 |

- **Features.** Naive Bayes, the SVM and the forest read the flat form. The
  neural network reads the sequence form: a small one-dimensional
  convolutional network, with the context values joined to its learned summary
  before the output layer.
- **Confidence.** For every family it is the probability given to the
  predicted label: the class probability of Naive Bayes, the share of trees
  voting for the label, probability estimates fitted on the training set for
  the SVM, and the softmax output of the network.
- **Scaling.** The SVM and the network standardize their features with the mean
  and spread of the set they are trained on; the values are saved with the
  classifier. Naive Bayes and the forest need none.
- **Stopping.** The network trains until `patience` epochs pass without
  improvement on a validation part taken from the set it is trained on (15
  percent), and keeps the best epoch.
- Random choices use the seed of the run.

## 7. Experiment definitions

A definition is a JSON file in `training/experiments/<family>/<name>.json`,
with camel case keys. It is kept in git and changed like code.

```json
{
  "formatVersion": 1,
  "name": "svm-coarse",
  "family": "svm",
  "validation": {"scheme": "kFold", "folds": 5},
  "comparator": {
    "metric": "accuracy",
    "direction": "max",
    "tieBreaker": {"metric": "timePerGestureMs", "direction": "min"}
  },
  "hyperparameters": {
    "kernel": ["rbf"],
    "c": {"min": 0.1, "max": 100, "count": 4, "type": "log"},
    "gamma": ["scale", "auto"]
  }
}
```

| Key | Meaning |
|---|---|
| `name` | Name of the definition; also its file name |
| `family` | One of the families of section 6 |
| `validation.scheme` | `kFold` or `singleSplit` |
| `validation.folds` | Folds, for `kFold` (default 5) |
| `validation.fraction` | Validation share, for `singleSplit` (0.2) |
| `comparator.metric` | A metric the trainer reports |
| `comparator.direction` | `max` or `min`: which value is better |
| `comparator.tieBreaker` | Optional second metric and direction |
| `hyperparameters` | The space (below) |

A hyperparameter that is not in `hyperparameters` takes the family's default.
Each entry in the space is one of:

- a **range**: `{"min": 0.0001, "max": 0.01, "count": 10, "type": "linear"}`
  gives 10 values spaced evenly from min to max; `"type": "log"` spaces them
  evenly on a logarithmic scale. Adding `"integer": true` rounds the values
  to whole numbers and removes duplicates;
- a **list** of values: `[100, 120, 150]` gives those three values.

The candidates are all combinations of one value from each entry, so their
number is the product of the entries' value counts. The tool prints that
number before it starts.

The tool rejects a definition with an unknown key, an invalid range (min above
max, a count below 1, or a log range that includes zero or less) or a
hyperparameter that the family's trainer does not accept.

## 8. Explorer

The explorer is composed of a trainer, a hyperparameter space, a validation
scheme and a comparator, all taken from the definition. A factory builds it
from a definition and, later, from a stored run.

For a run, the explorer does this:

1. It enumerates the candidates and numbers them in a fixed order.
2. For each candidate, and for each validation fold of the tuning set, it
   has the trainer train on the training part and evaluate on the validation
   part, and appends the metrics to the results.
3. When all candidates are done, it aggregates each metric of a candidate over
   its folds, as the mean and the standard deviation, and the comparator
   ranks the candidates by the mean of its metric, with the tie-breaker's
   metric for equal values.

**Validation schemes.** One explorer exists for each scheme and all share the
rest of the logic:

- `kFold` shuffles the tuning set with the seed, splits it into `folds`
  parts of equal label shares, and uses each part once for validation.
- `singleSplit` makes one label-stratified split of the tuning set, 1 minus
  `fraction` to train and `fraction` to validate.

A fold's training part is also the set a trainer learns scaling and stopping
from (N2), and the test set is never part of either.

**Stored runs.** An exploration run writes
`reports/<family>/exploration/<run id>/`, where the run id is
`<timestamp>-<definition name>`:

```text
<run id>/
  definition.json    copy of the definition as it was run
  run.json           seed, test fraction, gesture data fingerprint,
                     master definition name, times, candidate count
  results.csv        one row per candidate and fold
  report.md          the report (section 10)
  figures/
```

`results.csv` has the columns `candidate` and `fold`, then one column per
hyperparameter and one per metric. Rows are appended as candidates finish, so
an interrupted run keeps what it measured.

An explorer can be built from a stored run (`definition.json` and
`run.json`) and then answers questions about it without training anything:
the best candidate, the best n, the metrics of one candidate, and, for one
hyperparameter, the mean of a metric at each of its values. The ranking is
computed from the results each time, so a changed comparator in a later
version of the code reranks old results instead of breaking them. The user is
responsible for keeping the comparator the same when a comparison between runs
matters.

## 9. Final training and evaluation

### 9.1 Training

The training run reads the hyperparameters from a candidate of an exploration
run (the best one unless another is named) or from a file of values. It makes
the split with the run's seed and test fraction, and stops if the gesture data
no longer has the fingerprint that the exploration recorded. It then:

1. trains the candidate on the tuning set;
2. evaluates it on the test set (section 9.2) and chooses the threshold
   (section 9.3);
3. trains the candidate again on all the gesture data, which gives the
   classifier to save;
4. writes the report and saves the classifier (section 10).

### 9.2 Test cases and measures

| Kind | Source | Correct outcome |
|---|---|---|
| Spell | Test set samples of spells | The sample's label |
| Backward | The spell samples, reversed | Not recognized |
| Non-spell | Test set samples of non-spells | Not recognized |

A reversed gesture visits the positions from last to first, with times
measured from the new first position, so a backward spell lasts as long as the
original and moves at the same speeds. A classifier cannot reject it by
duration or speed, only by direction.

A prediction is **recognized** when its confidence is at or above the
threshold. The measures are computed for every threshold from 0 to 1 in
steps of 0.01:

| Measure | Share of ... that ... |
|---|---|
| Recognition rate | spell cases recognized, right label |
| Misrecognition rate | spell cases recognized, wrong label |
| Missed rate | spell cases not recognized |
| Backward false trigger rate | backward cases recognized as a spell |
| Non-spell false trigger rate | non-spell cases recognized as a spell |

At threshold 0 the recognition rate is the plain accuracy. Also reported are
the confusion matrix and the precision and recall of each label at threshold
0 and at the recommended threshold, and the time to classify one gesture, as
the mean and the 95th percentile, measured one gesture at a time as inference
runs. When the data has no non-spell samples the report says so.

### 9.3 Threshold

The recommended threshold is the lowest one at which the backward false
trigger rate and, when non-spell cases exist, the non-spell false trigger rate
are both at or below a limit (default 0.05, set with `--max-false-trigger`).
The false trigger rates fall and the missed rate rises as the threshold rises,
so the lowest threshold that meets the limit gives the highest recognition
rate. If none meets the limit, the recommendation is 1 and the report says so.
The recommendation is a starting value, which the action trigger can override
(`docs/architecture.md`, section 4.5).

## 10. Reports and models

### 10.1 Layout

```text
reports/
  index.md
  <family>/
    exploration/<run id>/          section 8
    training/<model id>/
      source.json                  where the candidate came from
      metrics.csv                  the measures of section 9.2 per threshold
      predictions.parquet          one row per test case
      report.md
      figures/
models/
  <family>/<model id>/
    classifier                     the model, in the family's own form
    classifier.json                metadata
```

The model id is `<family>-<timestamp>`, for example `svm-20261126-141502`. It
names the training folder and the model folder, and is never reused.

### 10.2 Files

- `source.json` holds the exploration run id and candidate number (or null
  for values given directly), the hyperparameter values used, the seed, the
  test fraction and the gesture data fingerprint. Because it holds the values,
  a training report does not depend on the exploration run staying.
- `classifier.json` holds `formatVersion`, the model id, the family, the label
  ids, the normalization settings, the recommended threshold, the
  hyperparameter values, a summary of the test metrics, the gesture data
  fingerprint and the path of the training report.
- `predictions.parquet` has, for each test case, its sample id, kind, correct
  label (or null), predicted label, confidence and the time to classify it,
  so the measures can be recomputed without training.

### 10.3 Reports

An exploration report has the definition's key settings and the gesture data
fingerprint, a table of the candidates in rank order with the compared metric
and its spread, and, for each hyperparameter, a chart of the compared metric
against its values.

A training report has the split sizes, the hyperparameters, the measures of
section 9.2 as tables and charts, the threshold and its reason, the
confusion matrix, and the timing. Charts are PNG files in `figures/`,
referenced from the Markdown.

`index.md` lists every exploration run and every model, by family, with the
date, the compared metric or the test summary, and links. The reporter
rebuilds it from the folders each time a report is written. Reports and
models stay valid when exploration runs are deleted; only the index entries
of deleted runs disappear.

## 11. Commands

The commands start with `wand-train`:

| Command | What it does |
|---|---|
| `gesture-data build [source]` | Builds `gesture-data/` |
| `gesture-data check [source]` | Compares it with a data folder |
| `gesture-data summary` | Prints counts per label and author |
| `explore <definition>` | Runs an exploration |
| `show <run id>` | Prints the best, top n and parameter effects |
| `train <run id>` | Trains the best candidate of a run |
| `train --family <f> --values <file>` | Trains from given values |
| `index` | Rebuilds `reports/index.md` |

Common options: `--seed` (default 42), `--test-fraction` (default 0.15),
`--top` for `show`, `--candidate` for `train` to choose another candidate,
and `--max-false-trigger` for `train`. `explore` and `train` write their
reports and the index as they finish.

## 12. Testing

- **Gesture data**: a small synthetic data folder gives rows with the right
  columns, normalized values equal to the library's, and a fingerprint that
  changes when a label or status changes; building twice gives the same
  content; a file of an unknown format version is refused.
- **Access**: selecting by column, seeded shuffles, stratified splits and
  batches give the expected rows and shapes, and the non-spell rows land in
  the test set.
- **Definitions**: a valid file and each kind of invalid one give the expected
  outcome or message; ranges and lists enumerate the expected values
  (linear, log, integer with duplicates).
- **Trainers**: each family on a small synthetic set of simple shapes beats
  chance, reports the standard metrics, rejects an unknown or out-of-range
  hyperparameter, and its classifier loads without the training code.
- **Explorer**: a fake trainer with known metrics gives the expected ranking,
  aggregates, partial results after an interruption and answers to queries;
  with k-fold every training row is validated exactly once; a stored run
  reloads to the same answers.
- **Evaluator**: measures from small hand-made predictions match hand-computed
  values, including the threshold rule and the case where no threshold meets
  the limit; reversing a gesture reverses its positions with re-timed
  times.
- **Whole run**: build, explore and train on a synthetic data folder leave
  every file of section 10, and the saved classifier predicts the same labels
  and confidences when loaded by the library alone.
- Real data is not used in tests; the tool is run on the shared data by hand
  when its tasks are verified.

## 13. Requirement coverage

| Requirement | Design |
|---|---|
| R1 | 5.1, 5.2 |
| R2 | 5.3 |
| R3 | 6 |
| R4 | 7 |
| R5 | 8 |
| R6 | 9 |
| R7 | 10 |
| N1 | 5.3, 8 |
| N2 | 5.3, 6, 8 |
| N3 | 6, 8 |
| N4 | 6, 8 |
| N5 | 12 |
| N6 | 3, 6 |

## 14. To Do

Items to fill in before this document is approved:

- Library design: `lib/docs/design.md` must gain the normalizer and the
  classifier interface and families, and its vector builder must hand the
  resampling to the normalizer, as `docs/architecture.md` now specifies.
- Data collection: recording non-spell samples under a label that is not a
  spell, and the `isSpell` mark in `config/labels.yaml` (a label without the
  mark is a spell).
