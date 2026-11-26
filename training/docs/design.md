# Training Subsystem - Design

> **Version** 4 | **Updated** 2026-11-26 | **Draft**

## 1. Overview

This document describes how the training subsystem consolidates the recorded
datasets into training data, explores the hyperparameters of each classifier
family, and trains, evaluates and saves classifiers. After reading it you will
know the components and the classes behind them, how a run flows through them,
the formats of the training data, the experiment definitions, the reports and
the saved models, and the commands that drive it. Requirements are in
`training/docs/requirements.md`; the system context is in
`docs/architecture.md`; the layout of the recorded datasets is in
`docs/data-handling.md`.

The subsystem has to produce, for each classifier family, the best model the
data supports, and to show how that was found. The design addresses this in
three steps. Training data puts everything training needs in one table, so
every family trains on the same inputs. A single explorer, composed with a
family's trainer, searches the hyperparameter space the same way for every
family. A final step evaluates the chosen hyperparameter candidate on test
gestures that no earlier step has seen.

The classifier families are open. This document names some as examples
(Naive Bayes, a support vector machine, a random forest, an MLP) and defines
nothing that is specific to one. A family's hyperparameters and defaults are
described in a design document of its own, written when the family is added.

## 2. Components

- **Training data builder**: Reads datasets through the shared library,
  normalizes each accepted gesture and writes the training data.
- **Training data access**: Loads the training data and provides selecting,
  shuffling, splitting and reading in whole or in batches.
- **Trainer**: Trains a model of one family on a set it is given, evaluates it
  on another set it is given, and saves the trained model (section 6). Each
  family has one.
- **Experiment definition**: A named file that states an exploration
  (section 7).
- **Explorer**: Enumerates the hyperparameter candidates of a space, selects the
  validation folds from the training set, has the trainer train and validate
  each hyperparameter candidate on them, ranks the hyperparameter candidates
  with a comparator and stores the results (section 8). One explorer exists for
  each validation scheme.
- **Evaluator**: Builds the test cases and computes the measures and the
  threshold recommendation (section 9).
- **Reporter**: Writes the reports, the figures and the index (section 10).
- **Model store**: Saves and lists the trained models (section 10).

Normalization and the classifiers come from the shared library
(`docs/architecture.md`, sections 4.3 and 4.4). A classifier loads a trained
model of one family and predicts with it; it has no training code and does not
save. A trainer holds the training code of the family and writes the model in
the form the classifier loads.

## 3. Classes

The key classes and what each is responsible for. Their attributes and
methods are decided when the code is written.

```text
 DATA
 +----------------------+     +----------------------------------+
 | TrainingDataBuilder  |---->| GestureSet                       |
 | Builds the training  |     | A view of rows of the training   |
 | data from datasets   |     | data: select, shuffle, split,    |
 +----------------------+     | read in whole or in batches      |
                              +----------------^-----------------+
                                               | reads
 EXPLORATION                                   |
 +----------------------+     +----------------+-----------------+
 | ExplorerFactory      |---->| Explorer  (abstract)             |
 | Builds an explorer   |     | Enumerates hyperparameter        |
 | from a definition or |     | candidates, runs each over the   |
 | from a stored run    |     | folds, aggregates, sorts, stores |
 +----------------------+     +----^----------------------^------+
                                   |                      |
                        +----------+-------+    +---------+--------+
                        | KFoldExplorer    |    | SingleSplit-     |
                        | k folds          |    | Explorer         |
                        +------------------+    +------------------+
                                   | uses
              +--------------------+--------------------+
              v                                         v
 +----------------------------+     +--------------------------------+
 | Comparator  (abstract)     |     | Trainer  (abstract)            |
 | Says which of two          |     | Trains on a set it is given,   |
 | candidate results is       |     | evaluates on another, saves    |
 | better                     |     | the model                      |
 +-------------^--------------+     +---------------+----------------+
               | e.g. ByMetric                      | writes what the
                                                    | classifier loads
                                                    v
                                    +--------------------------------+
                                    | Classifier  (library)          |
                                    | Loads a saved model, predicts  |
                                    +--------------------------------+
 OUTPUT
 +------------------+  +------------------+  +------------------------+
 | Evaluator        |  | Reporter         |  | ModelStore             |
 | Builds test      |  | Writes reports,  |  | Saves and lists        |
 | cases, measures  |  | figures, index   |  | trained models         |
 +------------------+  +------------------+  +------------------------+
```

- **GestureSet** is a view of rows of the training data. Selecting, shuffling
  and splitting return new views and copy nothing.
- **Trainer** is the base class. It is given a training set and an evaluation
  set explicitly and knows nothing about folds. A family uses the common
  implementation or a subclass of it.
- **Explorer** is the base class. It enumerates the hyperparameter candidates
  from the space in the experiment definition, owns the loop over them and the
  aggregation of metrics, and leaves the choice of folds to its subclasses.
- **Comparator** is the interface for ranking. It compares the results of two
  hyperparameter candidates; `ByMetric` is one implementation.
- **ExplorerFactory** builds an explorer from an experiment definition, or
  from a stored exploration run.
- **Classifier** is the library's class (`lib/docs/design.md`). A trainer
  writes what it loads.
- The experiment definition and an exploration run are plain records, not
  classes with behavior.

## 4. System flow

Training has three phases. Each has inputs, steps and outputs:

```text
 +-----------------------------------------------------------------------+
 | PHASE 1  BUILD                                                        |
 |  Input:   datasets in data/<name>/                                    |
 |  Steps:   read accepted samples; normalize every gesture              |
 |  Output:  training-data/  (table of raw + normalized gestures)        |
 +-----------------------------------------+-----------------------------+
                                           |
                                           v
 +-----------------------------------------------------------------------+
 | PHASE 2  EXPLORE                                                      |
 |  Input:   training-data/, experiment definition, seed, test fraction  |
 |  Steps:   1. split into training set and test set; set the test set   |
 |              aside                                                    |
 |           2. enumerate the hyperparameter candidates                  |
 |           3. for each candidate and each fold of the training set:    |
 |                trainer trains on the training folds, evaluates on     |
 |                the validation fold                                    |
 |           4. aggregate over folds; comparator ranks the candidates    |
 |  Output:  exploration run: definition copy, results, report           |
 +-----------------------------------------+-----------------------------+
                                           |
                                           v
 +-----------------------------------------------------------------------+
 | PHASE 3  TRAIN AND EVALUATE                                           |
 |  Input:   training-data/, exploration run + candidate (default: the   |
 |           best) or hyperparameter values, seed, test fraction         |
 |  Steps:   1. make the same split                                      |
 |           2. trainer trains on the whole training set                 |
 |           3. evaluator tests the model once on the test set           |
 |           4. choose the confidence threshold                          |
 |  Output:  model (models/<family>/<model id>/), training report        |
 +-----------------------------------------------------------------------+
```

The test set is not used in phase 2, and not used to train in phase 3. Its
only use is the evaluation in phase 3.

How the pieces connect in phase 2:

```text
 experiment definition --> ExplorerFactory --> Explorer
 training set ------------------------------>    |  for each candidate,
                                                 |  for each fold:
                                                 |    training folds,
                                                 v    validation fold
                                              Trainer --> metrics
                                                 |
                              Explorer aggregates, Comparator sorts
                                                 |
                                                 v
                                          exploration run (folder)
```

## 5. Training data

### 5.1 Normalization

Normalization is the library's, described in `docs/architecture.md`, section
4.3, with fixed settings: 64 points. A gesture becomes 63 steps of
(dx, dy, magnitude) and a duration, which is 63 times 3 plus 1, or 190
numbers. A classifier receives this list, with every step in order and the
duration last.

The settings are fixed because tuning is about the models, and one form for
every family keeps their results comparable. On the datasets recorded so far,
a path resampled to 64 points stays within 0.003 frame-heights of the original
for the median gesture and within 0.008 for the 95th percentile.

### 5.2 Format

Training data is a folder `training-data/` holding two files.

`gestures.parquet` has one row per accepted sample, with these columns:

| Column | Content |
|---|---|
| `sampleId`, `sessionId` | Identifiers from the dataset |
| `author`, `handedness` | From the session |
| `label` | Label id |
| `isSpell` | Whether the label is a spell |
| `durationS` | Gesture duration in seconds |
| `frameWidth`, `frameHeight` | Frame size in pixels |
| `rawTimeS`, `rawX`, `rawY` | Raw positions, as lists |
| `steps` | 189 numbers: dx, dy, magnitude of each step in order |

The input to a classifier is `steps` followed by `durationS`.

`gestures.json` describes the file:

```json
{
  "formatVersion": 1,
  "builtAt": "2026-11-26T14:15:02-04:00",
  "datasets": ["data/mrunal", "data/vamship", "data/wen"],
  "sourceCommit": "0813bf3",
  "sessionIds": ["3f8c1d2e-9a4b-4c7e-8f10-5b6d7e8f9a0b"],
  "sampleCount": 4821,
  "fingerprint": "9c1f...",
  "normalization": {"points": 64, "version": 1}
}
```

- The **fingerprint** is a SHA-256 hash over the sorted sample ids, each with
  its label and status. Two training data files cover the same samples when
  their fingerprints match. `sourceCommit` is the git commit of the
  repository when the datasets were built, and is empty outside git.
- The `normalization.version` is the library's normalization version. A
  trainer or a classifier that records a different version is reported as a
  mismatch.
- Training data is derived from the datasets and is rebuilt, not merged, when
  sessions are added. Rebuilding is deterministic, so a conflict in git is
  resolved by rebuilding. Comparing contents, and not file bytes, tells
  whether two builds agree.
- Only accepted samples are included. Rejected samples are left out.
- A session that appears in more than one dataset, for example after a merge,
  is used once. If its copies differ, the build stops and names the session.
- Building reads every dataset in `data/` unless the user names some.

### 5.3 Access and splitting

Loading gives a set that covers the whole table. A set offers:

- **Select** rows by the values of columns, for example one author, one
  label or spells only. The result is a set.
- **Shuffle** with a seed, and **split** by percentage into two or more sets.
  A split can be stratified so every side keeps the label shares.
- **Read** the whole set or batches of a size, as arrays of the normalized
  gestures with their labels.
- **Count** the samples per label and per author.

A set is a view of the loaded table (a list of row positions), so selecting
and splitting copy nothing.

The training set and the test set come from one operation: the rows of labels
that are not spells all go to the test set, and the remaining rows are
shuffled with the seed and split by label-stratified percentage, 80 training
and 20 test by default. The split depends only on the training data, the seed
and the percentage, and is made again, not stored, when a run needs it. A run
records those three values, so phase 3 reproduces the split of phase 2
exactly.

Samples of one session resemble each other, so a random split rates a
classifier more favorably than a person it has not seen would. Selecting
by author gives that stricter test when it is wanted.

## 6. Trainers

A trainer is the one interface through which a family is trained and
evaluated. It is given its sets explicitly and does not choose them:

- **Train** on a training set, given the values of the family's
  hyperparameters, and evaluate on an evaluation set, returning the standard
  metrics and, on request, the predicted label and confidence of every
  gesture of the evaluation set.
- **Save** the trained model in the form that the library's classifier loads,
  with the files described in `lib/docs/design.md`.
- **Validate** the hyperparameter values it is given before training: an
  unknown name, a value of the wrong kind or a value out of range is an error
  that names the hyperparameter.

During exploration the explorer gives the trainer the training folds and a
validation fold. In phase 3 the training set and the test set are given
instead. The trainer cannot tell the difference.

Metrics are reported as named numbers. Every trainer reports the **standard
metrics**:

| Metric | Meaning |
|---|---|
| `accuracy` | Share of gestures given the right label |
| `macroF1` | F1 averaged over labels |
| `logLoss` | Log loss of the predicted probabilities |
| `timePerGestureMs` | Mean time to classify one gesture |
| `trainSeconds` | Time to train |

A family may add metrics of its own, for example the number of epochs an MLP
ran or the number of support vectors of an SVM. They are stored with the
others.

Rules for every family:

- **Features.** A trainer receives the normalized gesture of section 5.2, a
  list of 190 numbers.
- **Confidence.** It is the probability the model gives to the predicted
  label.
- **Learning from data.** Anything a trainer learns from data, such as the
  scaling of features or the stopping point of a neural network, comes from
  the training set it is given, and is saved with the model.
- **Randomness.** Random choices use the seed of the run.

Each family has a trainer. The common implementation serves a family that
needs nothing special, and a subclass adds what a family needs. Families are
not fixed here. Examples are Naive Bayes, a support vector machine, a random
forest and an MLP. A family's hyperparameters, their defaults and any special
behavior are described in a design document of that family, written when the
family is added.

## 7. Experiment definitions

A definition is a JSON file in `training/experiments/<family>/<name>.json`,
with camel case keys. It is kept in git and changed like code. This example is
for an SVM, as an illustration:

```json
{
  "formatVersion": 1,
  "name": "svm-coarse",
  "family": "svm",
  "validation": {"scheme": "kFold", "folds": 5},
  "comparator": {
    "name": "byMetric",
    "settings": {"metric": "accuracy", "direction": "max"}
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
| `family` | The classifier family |
| `validation.scheme` | `kFold` or `singleSplit` |
| `validation.folds` | Folds, for `kFold` (default 5) |
| `validation.fraction` | Validation share, for `singleSplit` (0.2) |
| `comparator.name` | The comparator to use |
| `comparator.settings` | Settings of that comparator |
| `hyperparameters` | The space (below) |

The comparator `byMetric` is one comparator; its settings name a metric and a
direction (`max` or `min`: which value is better). Other comparators can be
added, each with its own settings.

A hyperparameter that is not in `hyperparameters` takes the family's default.
Each entry in the space is one of:

- A **range**: `{"min": 0.0001, "max": 0.01, "count": 10, "type": "linear"}`
  gives 10 values spaced evenly from min to max; `"type": "log"` spaces them
  evenly on a logarithmic scale. Adding `"integer": true` rounds the values
  to whole numbers and removes duplicates.
- A **list** of values: `[100, 120, 150]` gives those three values.

For example, these entries give 3 x 3 x 5 = 45 hyperparameter candidates:

```json
"hyperparameters": {
  "hiddenLayers": [1, 2, 3],
  "hiddenUnits": [100, 120, 150],
  "learningRate": {"min": 0.0001, "max": 0.01, "count": 5, "type": "log"}
}
```

The hyperparameter candidates are all combinations of one value from each
entry, so their number is the product of the entries' value counts. The tool
prints that number before it starts.

The tool rejects a definition with an unknown key, an invalid range (min above
max, a count below 1, or a log range that includes zero or less) or a
hyperparameter that the family's trainer does not accept.

## 8. Explorer

The explorer is composed of a trainer, a hyperparameter space, a validation
scheme and a comparator, all taken from the definition. A factory builds it
from a definition and, later, from a stored run.

For a run, the explorer does this:

1. It enumerates the hyperparameter candidates and numbers them in a fixed
   order.
2. It makes the folds of the training set, once, so that every hyperparameter
   candidate is validated on the same folds.
3. For each hyperparameter candidate, and for each fold, it gives the trainer
   the training folds to train on and the validation fold to evaluate on, and
   appends the metrics to the results.
4. When all hyperparameter candidates are done, it aggregates each metric of a
   hyperparameter candidate over its folds, as the mean and the standard
   deviation, and sorts the hyperparameter candidates with the comparator.

A hyperparameter candidate's score is the average over its folds. The best
single fold is never used, because it only shows which fold was easiest. The
standard deviation shows whether two hyperparameter candidates differ by more
than the variation between folds.

**Validation schemes.** One explorer exists for each scheme and all share the
rest of the logic. A scheme decides how the training set is divided into
folds:

- `kFold` shuffles the training set with the seed, splits it into `folds`
  parts of equal label shares, and uses each part once for validation, with
  the other parts as the training folds.
- `singleSplit` makes one label-stratified split of the training set, 1 minus
  `fraction` to train and `fraction` to validate.

The test set is never part of a fold.

**Stored runs.** An exploration run writes
`reports/<family>/exploration/<run id>/`, where the run id is
`<timestamp>-<definition name>`:

```text
<run id>/
  definition.json    copy of the definition as it was run
  run.json           seed, test fraction, training data fingerprint,
                     master definition name, times, candidate count
  results.csv        one row per candidate and fold
  report.md          the report (section 10)
  figures/
```

`results.csv` has the columns `candidate` and `fold`, then one column per
hyperparameter and one per metric. Rows are appended as hyperparameter
candidates finish, so an interrupted run keeps what it measured.

An explorer can be built from a stored run (`definition.json` and `run.json`)
and then answers questions about it without training anything: the best
hyperparameter candidate, the best n, the metrics of one hyperparameter
candidate, and, for one hyperparameter, the mean of a metric at each of its
values. The ranking is computed from the results each time, so a changed
comparator in a later version of the code reranks old results instead of
breaking them. The user is responsible for keeping the comparator the same when
a comparison between runs matters.

## 9. Final training and evaluation

### 9.1 Training

Phase 3 reads the hyperparameters from a hyperparameter candidate of an
exploration run (the best one unless another is named) or from a file of values.
It makes the split with the run's seed and test fraction, and stops if the
training data no longer has the fingerprint that the exploration recorded. It
then:

1. Trains the model on the whole training set.
2. Evaluates it on the test set (section 9.2) and chooses the threshold
   (section 9.3).
3. Writes the report and saves the model with the threshold (section 10).

The model that is saved is the one that was evaluated. The test set is never
used to train it.

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
The threshold is chosen from the test results, so the rates reported at it are
slightly optimistic, and the report says so. The recommendation is a starting
value, which the action trigger can override (`docs/architecture.md`, section
4.5).

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

- `source.json` holds the exploration run id and hyperparameter candidate number
  (or null for values given directly), the hyperparameter values used, the seed,
  the test fraction and the training data fingerprint. Because it holds the
  values, a training report does not depend on the exploration run staying.
- `classifier.json` holds `formatVersion`, the model id, the family, the label
  ids, the normalization settings, the recommended threshold, the
  hyperparameter values, a summary of the test metrics, the training data
  fingerprint and the path of the training report. Its fields are specified in
  `lib/docs/design.md`.
- `predictions.parquet` has, for each test case, its sample id, kind, correct
  label (or null), predicted label, confidence and the time to classify it,
  so the measures can be recomputed without training.

### 10.3 Reports

An exploration report has the definition's key settings and the training data
fingerprint, a table of the hyperparameter candidates in rank order with their
metrics and the spread over folds, and, for each hyperparameter, a chart of a
metric against its values.

A training report has the split sizes, the hyperparameters, the measures of
section 9.2 as tables and charts, the threshold and its reason, the
confusion matrix, and the timing. Charts are PNG files in `figures/`,
referenced from the Markdown.

`index.md` lists every exploration run and every model, by family, with the
date, a summary and links. The reporter rebuilds it from the folders each time
a report is written. Reports and models stay valid when exploration runs are
deleted; only the index entries of deleted runs disappear.

## 11. Commands

The commands start with `wand-train`:

| Command | What it does |
|---|---|
| `training-data build [datasets]` | Builds `training-data/` |
| `training-data check [datasets]` | Compares it with the datasets |
| `training-data summary` | Prints counts per label and author |
| `explore <definition>` | Runs an exploration |
| `show <run id>` | Prints the best, top n and parameter effects |
| `train <run id>` | Trains the best candidate of a run |
| `train --family <f> --values <file>` | Trains from given values |
| `index` | Rebuilds `reports/index.md` |

Without names, `training-data build` and `training-data check` use every dataset
in `data/`. Common options: `--seed` (default 42), `--test-fraction` (default
0.2), `--top` for `show`, `--candidate` for `train` to choose another
hyperparameter candidate, and `--max-false-trigger` for `train`. `explore` and
`train` write their reports and the index as they finish.

## 12. Testing

- **Training data**: A small synthetic dataset gives rows with the right
  columns, normalized values equal to the library's, and a fingerprint that
  changes when a label or status changes; building twice gives the same
  content; a session present in two datasets is used once, and differing
  copies stop the build; a file of an unknown format version is refused.
- **Access**: Selecting by column, seeded shuffles, stratified splits and
  batches give the expected rows and shapes, and the non-spell rows land in
  the test set.
- **Definitions**: A valid file and each kind of invalid one give the expected
  outcome or message; ranges and lists enumerate the expected values
  (linear, log, integer with duplicates).
- **Trainers**: A fake family checks that a trainer is given exactly the two
  sets it must use, reports the standard metrics and rejects an unknown or
  out-of-range hyperparameter. Each real family is tested on a small synthetic
  set of simple shapes: it beats chance, and the model it saves loads in the
  library without the training code.
- **Explorer**: A fake trainer with known metrics gives the expected ranking,
  aggregates, partial results after an interruption and answers to queries; with
  k-fold every training row is validated exactly once, and the test set never
  appears in a fold; every hyperparameter candidate sees the same folds; a
  stored run reloads to the same answers.
- **Evaluator**: Measures from small hand-made predictions match
  hand-computed values, including the threshold rule and the case where no
  threshold meets the limit; reversing a gesture reverses its positions with
  re-timed times.
- **Whole run**: Build, explore and train on a synthetic dataset leave every
  file of section 10, and the saved model predicts the same labels and
  confidences when loaded by the library alone.
- Real data is not used in tests; the tool is run on the real datasets by hand
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
| N2 | 5.3, 8, 9 |
| N3 | 3, 6, 8 |
| N4 | 8 |
| N5 | 12 |
| N6 | 2, 6 |

## 14. To Do

Items to fill in before this document is approved:

- Family designs: A design document for each family that is implemented,
  with its hyperparameters, defaults and special behavior.
- Data collection: Recording non-spell samples under a label that is not a
  spell, and the `isSpell` mark in `config/labels.yaml` (a label without the
  mark is a spell).
