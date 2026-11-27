# Training Subsystem - Tasks

> **Version** 1 | **Updated** 2026-11-26 | **Approved**

## 1. Overview

This document breaks the training subsystem into tasks. Each task has a title,
a description, acceptance criteria and implementation notes, and it gives its
type, its dependencies, and the requirements and design sections it
implements. A task is written so that someone who has not seen the rest of the
project can implement it from the task text, going to the referenced documents
for exact definitions.

After reading it you will know what has to be built, how each piece is judged
to be done, the order in which the pieces depend on each other, and where each
piece is specified. Section 4 shows that every part of the approved design is
covered by at least one task.

The work covers the shared library's normalizer and classifier loading
(`wand-core`), and the training tool (`wand-train`). The tasks for the dataset
layout and the dataset discovery that training needs are in
`data-collection/docs/tasks.md` (DC-F3 and DC-L12).

**Families are not tasked yet.** The classifier families are open
(`docs/architecture.md`, section 3.2). The tasks here build the framework,
and test it with a fake family. Before a real family such as Naive Bayes, an
SVM, a random forest or an MLP is implemented, it needs a design document of
its own (`training/docs/design.md`, section 14), and then tasks for its
trainer, its classifier and its experiment definition. Those documents and
tasks are added when the families are brought in, and they are needed before
exploration and training can be run on real data (TR-V2).

## 2. How to use this document

### 2.1 Task format

Tasks follow the format in `docs/standards.md` section 1.1. Each task here
has a type, status, dependencies, requirements, design references, a
description, acceptance criteria and implementation notes. The description and
the acceptance criteria are binding; the implementation notes are suggestions.

- The **ID** of every task here starts with the component code `TR`
  (training), which makes it unique across the repository
  (`docs/standards.md` section 1.1).
- The **branch** of a task is named from its type, ID and title
  (`docs/standards.md` section 1.2). Task TR-L1, "Normalizer", of type `feat`
  is developed on `feat/tr-l1-normalizer`.
- The **definition of done** (`docs/standards.md` section 1.4) applies to every
  task.
- Each task is written with enough information for an independent agent to
  implement it successfully, using only the task and the documents it
  references (`docs/standards.md` section 1.1).
- Tasks with no dependency between them can be done in parallel.

### 2.2 References

Short names are used for documents:

- **Req**: `training/docs/requirements.md`
- **TD**: `training/docs/design.md`
- **Lib**: `lib/docs/design.md`
- **DH**: `docs/data-handling.md`
- **Arch**: `docs/architecture.md`

### 2.3 Technology and layout (suggested)

- Python 3.11 or later, managed with uv; packages in a `src` layout.
- The shared library `wand-core` (imported as `wand_core`, under `lib/src`)
  gets the normalizer and classifier loading. It already uses `numpy`.
- The training tool `wand-train` (imported as `wand_train`, under
  `training/src`) is a new workspace member. It uses `numpy`, `pandas`,
  `pyarrow` (parquet), `scikit-learn` (metrics and splitting helpers),
  `matplotlib` (figures, with the non-interactive `Agg` backend) and
  `pyyaml`. Each task adds the dependencies it uses.
- Suggested module layout:

```text
lib/src/wand_core/
  normalize.py                       (the normalizer)
  classifiers/  base.py  registry.py  files.py

training/
  CLAUDE.md
  experiments/<family>/<name>.json   (experiment definitions)
  src/wand_train/
    cli.py  definitions.py  evaluate.py  models.py
    data/       builder.py  format.py  gestureset.py
    trainers/   base.py  metrics.py  registry.py  fake.py
    explore/    enumerate.py  comparator.py  explorer.py  runs.py
    reports/    exploration.py  training.py  figures.py  index.py
  tests/
```

### 2.4 Names used across tasks

Tasks use these names so independently built parts fit together. In Python the
fields are snake case; in JSON and YAML they are camel case
(`docs/standards.md`).

- **Normalized gesture**: a one-dimensional array of floats: the
  `(dx, dy, magnitude)` of each of the 63 steps in order, then the duration in
  seconds. It has 190 numbers (`Arch` 4.3, `TD` 5.1).
- **Prediction**: `label` (a label id), `confidence` (the probability of that
  label) and `probabilities` (an array with one probability per label, in the
  classifier's label order).
- **Training data**: the files in `training-data/` (`TD` 5.2): the table
  `gestures.parquet` and the description `gestures.json`.
- **Gesture set**: a view of rows of the training data (`TD` 5.3).
- **Metrics**: a dictionary of named numbers. The standard names are
  `accuracy`, `macro_f1`, `log_loss`, `time_per_gesture_ms` and
  `train_seconds` (`camelCase` in files: `macroF1`, `logLoss`,
  `timePerGestureMs`, `trainSeconds`).
- **Hyperparameter candidate**: a dictionary from hyperparameter name to
  value. Candidates are numbered from 1 in their enumeration order.
- **Candidate result**: a candidate with its metrics on each fold and the
  mean and standard deviation of each metric over the folds.
- **Run id** of an exploration: `<yyyymmdd-HHMMSS>-<definition name>`.
  **Model id**: `<family>-<yyyymmdd-HHMMSS>`.

## 3. Summary

| ID | Task | Status |
|---|---|---|
| TR-D1 | Requirements | Completed |
| TR-D2 | Design | Completed |
| TR-D3 | Task list | In progress |
| TR-F1 | Training package and tooling | Completed |
| TR-L1 | Normalizer | Not started |
| TR-L2 | Classifier loading | Not started |
| TR-A1 | Training data builder | Not started |
| TR-A2 | Gesture sets | Not started |
| TR-A3 | Trainer base and metrics | Not started |
| TR-A4 | Experiment definitions | Not started |
| TR-A5 | Explorer | Not started |
| TR-A6 | Stored explorations | Not started |
| TR-A7 | Evaluator | Not started |
| TR-A8 | Final training and models | Not started |
| TR-A9 | Reporter | Not started |
| TR-V1 | End-to-end test | Not started |
| TR-V2 | Real datasets | Not started |

Dependencies, in the order work can start:

```text
 DC-L12 (dataset discovery)       DC-F3 (data layout, after DC-A18)
 TR-F1 ----+-------------------+---- TR-A4
 TR-L1 ----+--- TR-L2          |
           |                   v
           +-----------> TR-A1 --> TR-A2 --> TR-A3 --+--> TR-A5 --> TR-A6
                                              |      |        |
                                              |      +--> TR-A7
                                              v               v
                                          TR-A8 <-------------+
                                              v
                                          TR-A9 --> TR-V1 --> TR-V2
```

## 4. Coverage of the design

Every part of the approved design is assigned to at least one task.

| TD section | Tasks |
|---|---|
| 2 Components | TR-A1 to TR-A9 |
| 3 Classes | TR-A2, TR-A3, TR-A5, TR-A7, TR-L2 |
| 4 System flow | TR-A6, TR-A8, TR-V1 |
| 5.1 Normalization | TR-L1 |
| 5.2 Format | TR-A1 |
| 5.3 Access and splitting | TR-A2 |
| 6 Trainers | TR-A3, and the family tasks to come |
| 7 Experiment definitions | TR-A4 |
| 8 Explorer | TR-A5, TR-A6 |
| 9 Final training and evaluation | TR-A7, TR-A8 |
| 10 Reports and models | TR-A8, TR-A9 |
| 11 Commands | TR-A1, TR-A6, TR-A8, TR-A9 |
| 12 Testing | each task, TR-V1 |

| Requirement | Tasks |
|---|---|
| R1 Training data | TR-L1, TR-A1 |
| R2 Access | TR-A2 |
| R3 Trainers | TR-A3, TR-L2 |
| R4 Experiment definitions | TR-A4 |
| R5 Exploration | TR-A5, TR-A6 |
| R6 Training and evaluation | TR-A7, TR-A8 |
| R7 Reports and models | TR-A8, TR-A9 |
| N1 to N6 | TR-A1 to TR-A9, TR-V1 |

## 5. Documentation tasks

### TR-D1 Requirements

- **Type**: docs
- **Status**: Completed
- **Description**: `training/docs/requirements.md`.

### TR-D2 Design

- **Type**: docs
- **Status**: Completed
- **Description**: `training/docs/design.md`.

### TR-D3 Task list

- **Type**: docs
- **Status**: In progress
- **Description**: This document. Family designs and the tasks for the
  families are added later, as described in section 1.

## 6. Foundation tasks

### TR-F1 Training package and tooling

- **Type**: chore
- **Status**: Completed
- **Depends on**: none
- **Requirements**: N5
- **Design**: TD 11; Arch 6; `docs/standards.md` 2

**Description.** Create the training package so every later task starts from a
working, linted, tested workspace. `training` becomes a member of the uv
workspace with the package name `wand-train`, the import name `wand_train` and
the command `wand-train`. The command prints usage and has the sub-commands of
`TD` 11 (`training-data`, `explore`, `show`, `train`, `index`) as shells that
print "not implemented yet" and exit with status 2. The component also gets its
own instructions file.

**Acceptance criteria.**

- [x] `uv sync` succeeds, and `uv.lock` is up to date and committed.
- [x] The root `pyproject.toml` lists `training` as a workspace member, adds
      `wand_train` to the first-party packages of the import sorting rule and
      `training/tests` to the test paths.
- [x] `training/pyproject.toml` declares `requires-python` as 3.11 or later and
      depends on `wand-core` through the workspace.
- [x] `uv run wand-train --help` lists the five sub-commands; each one's
      `--help` works.
- [x] `uv run pytest`, `uv run ruff format --check` and `uv run ruff check`
      pass, with at least one placeholder test in `training/tests`.
- [x] `training/CLAUDE.md` exists. Like the other components' instructions
      files, it states the role, the task and the process, and points to
      `training/docs/` and the root documents.
- [x] The folder `training/experiments/` exists and is tracked in git (add a
      `.gitkeep`).

**Implementation notes.**

- Declare only the dependencies you use now; later tasks add their own.
- Use `argparse` with sub-parsers in `cli.py`; `main()` is the entry point in
  `[project.scripts]`.
- Model `training/CLAUDE.md` on `data-collection/CLAUDE.md`.

## 7. Shared library tasks

### TR-L1 Normalizer

- **Type**: feat
- **Status**: Not started
- **Depends on**: none
- **Requirements**: R1.2, N6
- **Design**: Lib 10; Arch 4.3; TD 5.1

**Description.** Implement gesture normalization in `wand-core` as specified
in `Arch` 4.3 and `Lib` 10. Input: the positions of one gesture (`time_s`,
`horizontal` and `vertical` as fractions of the frame, with `time_s` from the
first position) and the frame size in pixels. Output: the normalized gesture
(section 2.4). Steps:

1. Scale the horizontal positions by the frame's aspect ratio (width divided
   by height), so both axes are in frame-heights.
2. Choose 64 moments at equal time intervals from the first time to the last
   (the `k`-th is `k * duration / 63`, `k` from 0 to 63) and read the position
   at each by linear interpolation.
3. Subtract the first point from every point.
4. For each pair of consecutive points compute `dx`, `dy` and
   `magnitude = sqrt(dx**2 + dy**2)`.
5. Output the 63 `(dx, dy, magnitude)` triples in order, then the duration in
   seconds (the last time minus the first).

The number of points is a parameter with the default 64 (so tests can use
fewer), recorded with the result's metadata. The module also exposes
`NORMALIZATION_VERSION = 1` and the settings `points`. A batch function
normalizes many gestures. The old vector builder (`DC-L4`) is removed.

**Acceptance criteria.**

- [ ] For 5 points, the gesture of the worked example in `Arch` 4.3 (positions
      `(0.30, 0.50)`, `(0.34, 0.44)`, `(0.40, 0.38)`, `(0.52, 0.30)`,
      `(0.54, 0.30)`, `(0.60, 0.38)`, `(0.62, 0.46)` at times 0, 0.10, 0.20,
      0.45, 0.50, 0.80, 1.00 seconds, with a square frame so no scaling) gives
      the steps and the duration of that example, to 3 decimals.
- [ ] With the default settings, any gesture of at least 2 positions gives 190
      numbers.
- [ ] The same shape drawn in 1 second and in 2 seconds gives identical steps
      and durations 1.0 and 2.0.
- [ ] The same shape drawn in another part of the frame gives identical
      results.
- [ ] A gesture recorded with fewer frames, or with a dropped frame, gives the
      same number of points, and the same steps up to the interpolation error
      on a smooth path.
- [ ] The same positions at two frame sizes with the same aspect ratio give
      identical results; at a different aspect ratio the horizontal values are
      scaled.
- [ ] Fewer than 2 positions, a duration of zero or less, and mismatched array
      lengths are rejected with a clear error. Positions with equal timestamps
      are merged (their average is used) before interpolation.
- [ ] Normalizing a batch gives the same result as normalizing one by one.
- [ ] The vector builder module, its tests and its exports are removed, and
      nothing else in the repository imports it.

**Implementation notes.** `wand_core/normalize.py`; use `numpy.interp`. Delete
`wand_core/motion/vectors.py` and `lib/tests/test_vectors.py`, and update
`__init__` exports. Add a note to DC-L4 in `data-collection/docs/tasks.md`
that TR-L1 supersedes it. Return a small result object or a plain array plus
the settings, as you prefer, but keep the batch function's output a 2-D array
with one row per gesture.

### TR-L2 Classifier loading

- **Type**: feat
- **Status**: Not started
- **Depends on**: TR-L1
- **Requirements**: R3.5, R6.8, N6
- **Design**: Lib 13; Arch 4.4; TD 10.2

**Description.** Implement the classifier interface of `Lib` 13 in `wand-core`.
A classifier is a folder with a `classifier.json` file and the model in the
family's own form. The library only loads and predicts; training and saving
belong to the training tool.

- `load(folder)` reads `classifier.json` and returns a classifier of the right
  family. `classifier.json` has `formatVersion` (1), `family`, `labels` (label
  ids in the order of the probabilities), `normalization` (`points` and
  `version`), and may have more fields, which are ignored. Loading rejects an
  unknown format version, and rejects a classifier whose normalization points
  or version differ from the library's, each with a clear error.
- A classifier predicts from normalized gestures (section 2.4): one gesture or
  a batch, returning Predictions (section 2.4). The probabilities sum to 1.
- A **registry** maps a family name to a function that loads that family's
  model from a folder. A family's task registers its loader. An unknown family
  is a clear error. A loader may need an optional dependency; if it is
  missing, loading fails with a message that names what to install.

**Acceptance criteria.**

- [ ] With a fake family registered by the test, a folder with a valid
      `classifier.json` loads, and `predict` returns Predictions whose
      probabilities sum to 1, whose label is the most probable one, and whose
      confidence is its probability.
- [ ] Batch and single predictions agree.
- [ ] An unknown `formatVersion`, a different normalization `points` or
      `version`, an unknown family and a missing `classifier.json` are each
      rejected with a distinct, clear error.
- [ ] A loader that raises an import error for an optional dependency results
      in an error that names the dependency.
- [ ] Extra fields in `classifier.json` are ignored.
- [ ] Nothing in the library imports `wand_train`, and loading needs no
      training code.

**Implementation notes.** `wand_core/classifiers/base.py` (the interface),
`registry.py`, `files.py` (reading `classifier.json`). The fake family used in
tests can predict from a stored array of class means. Keep the heavy imports
inside the family loaders.

## 8. Application tasks

### TR-A1 Training data builder

- **Type**: feat
- **Status**: Not started
- **Depends on**: TR-F1, TR-L1, DC-L12
- **Requirements**: R1, N1, N4, N5
- **Design**: TD 5.1, 5.2, 11; DH 3, 3.1, 5

**Description.** Build the training data from datasets and provide the three
`training-data` commands.

- `wand-train training-data build [dataset...] [--output <folder>]` reads the
  named datasets, or every dataset in the data location (`data/`) when none are
  named (using the dataset discovery of DC-L12). It keeps the accepted
  samples, normalizes each gesture with the library's normalizer, and writes
  `gestures.parquet` and `gestures.json` to `training-data/` (or the output
  folder), as in `TD` 5.2: the columns and their meaning, and the JSON fields
  `formatVersion` (1), `builtAt`, `datasets`, `sourceCommit`, `sessionIds`,
  `sampleCount`, `fingerprint` and `normalization`.
- Rows are ordered by session id and then sample id, and the parquet content
  does not depend on the order the datasets were given. `steps` holds the 189
  numbers of the normalized gesture without the duration, and `durationS`
  holds the duration. The raw positions are stored as they are in the dataset
  (the horizontal and vertical fractions, as lists), with the frame size.
- The **fingerprint** is the hex SHA-256 of the text made by sorting the
  samples by sample id and writing one line `<sampleId>\t<label>\t<status>\n`
  for each.
- A session that appears in more than one dataset is used once; if its copies
  differ (compare the session file and the samples file contents), the build
  stops and names the session.
- `training-data check [dataset...]` rebuilds the fingerprint and normalization
  settings from the datasets without writing, compares them with the committed
  `gestures.json`, prints what differs and exits with a non-zero status when
  they do not match.
- `training-data summary` prints the counts per label and per author from the
  committed table.

**Acceptance criteria.**

- [ ] A synthetic dataset gives a table with every column of `TD` 5.2, and the
      normalized values equal the library normalizer's output.
- [ ] Rejected samples are left out; labels are copied as they are.
- [ ] Building twice gives identical content (compare the data frames, not the
      file bytes), and the order of the dataset arguments does not matter.
- [ ] The fingerprint changes when a label or a status changes, and not when
      only `builtAt` changes.
- [ ] A session present in two datasets is used once; differing copies stop the
      build with a message naming the session.
- [ ] `check` exits 0 on matching data and non-zero, with a message, on a
      changed dataset.
- [ ] A `gestures.json` with an unknown `formatVersion` is refused by `check`
      and `summary`, and by the loader of TR-A2.
- [ ] `gestures.json` records `sourceCommit` as the short git commit when the
      repository has one, and an empty string otherwise.
- [ ] Building the shared datasets (about 4,800 samples) takes seconds.
- [ ] A helper that writes a small synthetic dataset folder with distinct
      shapes (for example a circle, a line and a zigzag, with noise, several
      authors and sessions) exists for the tests of this and later tasks.

**Implementation notes.** `wand_train/data/builder.py` and `format.py`. Read
data with the library's dataset store (DC-L12 and the existing load
functions). Use `pyarrow` list columns for the raw positions and the steps;
`pandas` for the in-memory table. Put the synthetic dataset helper where the
tests of several tasks can import it (for example `training/tests/synthetic`
or `wand_core/testing`).

### TR-A2 Gesture sets

- **Type**: feat
- **Status**: Not started
- **Depends on**: TR-A1
- **Requirements**: R2, N1, N5
- **Design**: TD 3, 5.3

**Description.** Load the training data and provide a gesture set, a view of
rows of the table, with these operations (`TD` 5.3):

- `load(folder)` reads `training-data/` and returns a gesture set covering all
  rows; it refuses an unknown format version.
- `select(...)` keeps the rows whose column has a given value or one of a list
  of values (for example `author` or `label`), and returns a new set.
- `shuffle(seed)` returns a new set with the rows in a random order that
  depends only on the seed.
- `split(fractions, seed, stratify=True)` returns one set for each fraction
  (for example `[0.8, 0.2]`); with `stratify` every set keeps the label shares
  as closely as the sizes allow. The same table, seed and fractions give the
  same sets. Every row is in exactly one set.
- `concat(sets)` returns the set holding the rows of the given sets (used to
  join the training folds).
- `batches(size)` yields batches of the normalized gestures and labels. The
  set also returns all its normalized gestures (rows of 190 numbers) and
  labels at once, and gives access to the raw positions of a row, for the
  evaluator.
- `counts()` returns the number of rows per label and per author; `len` works.
- A **train and test split** helper: `train_test_split(fraction=0.2, seed)`
  returns the training set and the test set of `TD` 5.3 (a stratified split
  of all rows).

Sets are views: they keep row positions into the loaded table and copy no
data.

**Acceptance criteria.**

- [ ] Each operation gives the expected rows and shapes on a small table.
- [ ] `shuffle` and `split` are deterministic for a seed and differ for another
      seed; the union of the parts of `split` equals the input, with no row
      twice.
- [ ] With `stratify`, the label shares of every part are within one row of
      the proportional share.
- [ ] `select` then `split` keeps only the selected rows.
- [ ] `batches(size)` covers every row once, and the last batch may be smaller.
- [ ] Creating views does not copy the table (check that the underlying arrays
      are shared).
- [ ] The default train and test split is 80 and 20 percent.

**Implementation notes.** `wand_train/data/gestureset.py`. Hold the table once
and a NumPy array of row indices in each set. For the stratified split, shuffle
within each label with a seeded generator and cut each label's rows by the
fractions.

### TR-A3 Trainer base and metrics

- **Type**: feat
- **Status**: Not started
- **Depends on**: TR-A2, TR-L2
- **Requirements**: R3, N3, N5
- **Design**: TD 3, 6

**Description.** The trainer base, the standard metrics and a fake family for
tests.

A **trainer** trains a model of one family on a gesture set it is given and
evaluates it on another set it is given. It knows nothing about folds. Its
interface:

- `family`: the family name.
- A declaration of the hyperparameters it accepts: for each its name, its kind
  (integer, float, string choice or boolean), its default and, where it
  applies, its range or choices. `validate(hyperparameters)` fills in
  defaults, and rejects an unknown name, a value of the wrong kind and a value
  out of range, with an error that names the hyperparameter.
- `train(training_set, evaluation_set, hyperparameters, seed)` validates the
  hyperparameters, trains the model on the training set and returns a result
  holding the metrics on the evaluation set and, on request, the predictions
  (a Prediction for every gesture of the evaluation set). Anything learned from
  data (for example feature scaling) uses the training set only.
- `save(folder, extra_fields=None)` writes the trained model in the form the
  library's classifier loads (TR-L2): the model file and `classifier.json`
  with `formatVersion`, `family`, `labels` (the label ids in probability
  order), `normalization` (`points` and `version` from the library), and any
  extra fields given.

The **base class** does the common work: it validates, calls the subclass to
fit and to give probabilities, computes the standard metrics and the
predictions, and writes `classifier.json`. Subclasses only fit the model,
give probabilities for gestures and write their model file. A subclass may
report further metrics. The standard metrics (`TD` 6): `accuracy`,
`macro_f1`, `log_loss`, `time_per_gesture_ms` (the mean time to predict one
gesture, measured one gesture at a time over up to 200 evaluation gestures)
and `train_seconds`. The confidence of a prediction is the probability of the
predicted label.

A **registry** maps a family name to its trainer. A **fake family**, used by
tests, trains by computing the mean normalized gesture of each label and
predicting from the distances (convert distances to probabilities with a
softmax), accepts one float hyperparameter (for example `sharpness`) and
registers a loader in the library's registry (TR-L2).

**Acceptance criteria.**

- [ ] The standard metrics are computed correctly on hand-made predictions
      (accuracy, macro F1 and log loss against hand-computed values).
- [ ] An unknown hyperparameter, a wrong kind and an out-of-range value each
      raise an error naming the hyperparameter; missing ones take their
      defaults.
- [ ] The fake family beats chance on a synthetic set of distinct shapes.
- [ ] A trainer uses exactly the two sets it is given: a test shows that data
      outside them never reaches the model.
- [ ] Scaling or any other learned value comes from the training set only (a
      test with a fake that records the data it saw).
- [ ] The result can include the predictions, with label, confidence and
      probabilities for every evaluation gesture.
- [ ] A model saved by the fake family loads with the library's `load`, and its
      predictions equal those made at training time.
- [ ] A subclass can add its own metrics, and they are returned beside the
      standard ones.
- [ ] A family can be added by writing a subclass and registering it, with no
      change to the base or to other families.

**Implementation notes.** `wand_train/trainers/base.py`, `metrics.py`,
`registry.py`, `fake.py`. Use `scikit-learn`'s metric functions or your own;
handle labels absent from the evaluation set in the macro average (skip
them) and clip probabilities in the log loss.

### TR-A4 Experiment definitions

- **Type**: feat
- **Status**: Not started
- **Depends on**: TR-F1
- **Requirements**: R4, N5
- **Design**: TD 7

**Description.** Load, validate and enumerate experiment definitions
(`TD` 7).

- `load(path)` reads a JSON definition with camel case keys (converted to snake
  case in Python) with `formatVersion`, `name`, `family`, `validation`,
  `comparator` and `hyperparameters`.
- Validation errors name the key: an unknown key at any level, a missing
  required key, `name` different from the file name without `.json`, a
  `validation.scheme` other than `kFold` or `singleSplit`, `folds` below 2,
  `fraction` outside 0 to 1 (exclusive), and an invalid hyperparameter entry.
  `validation.folds` defaults to 5 and `validation.fraction` to 0.2.
- A hyperparameter entry is a **range** `{min, max, count, type}` with
  `type` `linear` or `log` and an optional `integer` flag, or a **list** of
  values. A range is invalid when `min` is above `max`, `count` is below 1, or
  the type is `log` and `min` is zero or less. A list must not be empty.
- `enumerate_candidates(definition)` returns the hyperparameter candidates in
  a fixed order: the hyperparameters in the order they appear in the file, all
  combinations, with the last hyperparameter changing fastest. A range gives
  `count` values from `min` to `max` inclusive, spaced evenly (`linear`) or
  evenly in logarithm (`log`); `count` 1 gives `[min]`. With `integer`, values
  are rounded to whole numbers and duplicates are removed, keeping the first.
  A list gives its values as they are. The number of candidates is the product
  of the numbers of values.
- The `comparator` entry is kept as a name and a dictionary of settings; the
  explorer (TR-A5) interprets it.

**Acceptance criteria.**

- [ ] The example definitions of `TD` 7 load, and the 3 x 3 x 5 example
      enumerates 45 candidates.
- [ ] Linear, log, integer-with-duplicates, single-count and list entries give
      the expected values (compare with hand-computed lists).
- [ ] The enumeration order is the one stated, and repeating it gives the same
      list.
- [ ] Each kind of invalid definition is rejected with a message that names the
      key (one test each).
- [ ] The camel case to snake case conversion uses the library's casing
      helpers.

**Implementation notes.** `wand_train/definitions.py` and
`explore/enumerate.py`. Use `pydantic` models (already a dependency of the
library) or hand-written checks. Use `itertools.product`. Write definitions to
and read them from `training/experiments/<family>/<name>.json`; a family's
example definition is added by its own task.

### TR-A5 Explorer

- **Type**: feat
- **Status**: Not started
- **Depends on**: TR-A3, TR-A4
- **Requirements**: R5.1 to R5.4, R5.8, N1, N2, N3, N5
- **Design**: TD 3, 8

**Description.** The explorer, the comparator and the validation schemes.

- A **comparator** decides which of two candidate results (section 2.4) is
  better. The interface compares two results and says which ranks first, or
  that they tie. `ByMetric` is the first implementation: its settings are
  `metric` (a metric name) and `direction` (`max` or `min`), and it compares
  the mean of that metric. A **comparator registry** maps the name used in the
  definition (`byMetric`) to the comparator and builds it from the settings;
  an unknown name or invalid settings are errors.
- The **explorer** base class is given a trainer, the experiment definition
  and a comparator. `explore(training_set, seed, progress=None,
  on_candidate=None)`:
  1. Enumerates the candidates (TR-A4) and checks every one with the trainer's
     validation, before any training, so a bad value fails at once;
  2. Asks its subclass for the folds of the training set, once, so that every
     candidate is validated on the same folds (the folds are pairs of a
     training part, which is the union of the other parts, and a validation
     part);
  3. For each candidate and each fold, calls the trainer with the training
     part and the validation part, and collects the metrics;
  4. After each candidate's folds, builds its candidate result (the mean and
     the standard deviation of each metric over the folds) and calls
     `on_candidate` with the candidate number, the per-fold metrics and the
     result, so the caller can store it;
  5. When all are done, sorts the candidate results with the comparator (stable:
     equal candidates keep their enumeration order) and returns them.
  `progress` is called after each fold with the counts done and total.
- The explorer never sees the test set: it is given only the training set.
- Subclasses: `KFoldExplorer` shuffles the training set with the seed and splits
  it into `folds` stratified parts of equal share, using each part once for
  validation; `SingleSplitExplorer` makes one stratified split with
  `1 - fraction` for training and `fraction` for validation.
- An **explorer factory** builds the explorer for a definition: the trainer
  from the trainer registry (TR-A3), the comparator from the comparator
  registry, and the subclass for the validation scheme.

**Acceptance criteria.**

- [ ] With a fake trainer that returns known metrics for each candidate and
      fold, the results, aggregates (mean and standard deviation) and ranking
      match hand-computed values, for `max` and for `min`.
- [ ] With k-fold, every training row is a validation row in exactly one fold,
      and training and validation parts never overlap.
- [ ] Every candidate is evaluated on the same folds (the fake trainer records
      the folds it was given).
- [ ] A test set passed in by mistake is impossible: `explore` takes only the
      training set, and a test confirms rows of a held-out set never reach a
      trainer.
- [ ] A candidate with an invalid hyperparameter fails before any training, and
      the error names the hyperparameter and the candidate.
- [ ] Equal candidates keep their enumeration order.
- [ ] `on_candidate` is called once per candidate, in order, as each finishes,
      and `progress` counts every fold.
- [ ] An unknown comparator name or invalid comparator settings are rejected.
- [ ] A new validation scheme or comparator can be added without changes to the
      explorer base.

**Implementation notes.** `wand_train/explore/explorer.py` and
`comparator.py`. Use `functools.cmp_to_key` with the comparator. Seed the
fold shuffling with the run's seed. Pass the seed to the trainer as well.

### TR-A6 Stored explorations

- **Type**: feat
- **Status**: Not started
- **Depends on**: TR-A5
- **Requirements**: R5.5 to R5.7, R5.8, N1
- **Design**: TD 8, 11

**Description.** Store explorations on disk, reload them and answer questions
about them, and provide the `explore` and `show` commands.

- `wand-train explore <definition> [--seed 42] [--test-fraction 0.2]
  [--training-data <folder>] [--reports <folder>]` loads the training data,
  makes the training and test split (`train_test_split` of TR-A2, with the
  seed and the fraction), checks the definition (TR-A4), prints the number of
  candidates, runs the explorer on the training set only, and stores the run
  in `<reports>/<family>/exploration/<run id>/` (default reports folder:
  `reports/`). It prints progress and the best candidates at the end.
- The run folder (`TD` 8) holds `definition.json` (a copy of the definition as
  it was run), `run.json` (the seed, the test fraction, the training data
  fingerprint, the definition's name, the start and end times, the number of
  candidates and the tool version), and `results.csv` with one row for each
  candidate and fold: the columns `candidate` and `fold`, then one column for
  each hyperparameter and one for each metric (snake case in the file header).
  Rows are appended and flushed as each candidate finishes, so an interrupted
  run keeps what was measured. A run folder is never overwritten: a folder that
  exists is an error.
- **Reloading.** `ExplorerFactory.from_run(folder)` rebuilds the explorer from
  `definition.json` and `run.json`, and loads `results.csv`, with no training.
  The ranking is computed from the results each time. It supports:
  `best()`, `top(n)`, `metrics(candidate)` (per fold and aggregated) and
  `effect(hyperparameter, metric)` (the mean of the metric at each value of the
  hyperparameter). For an interrupted run, only candidates with all their folds
  are ranked, and the answer says the run is incomplete.
- `wand-train show <run id or folder> [--top 5] [--effect <hyperparameter>
  --metric <name>]` prints these answers. The run id is looked up under the
  reports folder.

**Acceptance criteria.**

- [ ] A run on a synthetic training set with the fake family leaves
      `definition.json`, `run.json` and `results.csv` with the stated columns
      and one row per candidate and fold.
- [ ] `run.json` records the seed, the test fraction and the training data
      fingerprint.
- [ ] Killing a run half way leaves a `results.csv` with the finished
      candidates; `show` works on it and says it is incomplete.
- [ ] Reloading a finished run gives the same ranking, best candidate, metrics
      and effects as the run printed.
- [ ] A changed comparator setting in a copy of `definition.json` re-ranks the
      stored results without error.
- [ ] A second run never overwrites the first: a run id whose folder already
      exists stops the command with a clear message.
- [ ] `explore` never loads or touches the test set rows beyond making the
      split.
- [ ] A definition that does not validate stops the command before any training
      and prints the reason; the exit status is non-zero.
- [ ] `show --effect` prints the mean of the metric for each value of the
      hyperparameter.

**Implementation notes.** `wand_train/explore/runs.py`. Use the `csv` module or
`pandas` for `results.csv`. Format the run id time in local time as
`yyyymmdd-HHMMSS`. The report that `explore` writes at the end is added by
TR-A9.

### TR-A7 Evaluator

- **Type**: feat
- **Status**: Not started
- **Depends on**: TR-A3
- **Requirements**: R6.3 to R6.6, N5
- **Design**: TD 9.2, 9.3

**Description.** The evaluator builds the test cases from the test set, runs a
trained model over them and computes every measure of `TD` 9.2 and 9.3.

- **Test cases.** For each row of the test set: a **spell** case (its
  normalized gesture and label), and a **backward** case: the same raw
  positions in reverse order, with times measured from the new first position
  (`t' = last_time - t`, listed from the last position to the first), and the
  `horizontal` and `vertical` lists reversed. The backward gesture is
  normalized with the library's normalizer, using the row's frame size. The
  correct outcome of a spell case is its label; of a backward case, "not
  recognized".
- **Input.** A function that returns the probability of every label for a batch
  of normalized gestures (the trained model's), the label order, and the test
  set. The evaluator is given no data beyond the test set.
- **Output.** A table of predictions, one row for each test case: `sampleId`,
  `kind` (`spell` or `backward`), `correctLabel` (null for backward),
  `predictedLabel`, `confidence`, the `probabilities` (a list in label order)
  and `timeMs` (the time to predict that one gesture, measured one gesture at a
  time). And the measures:
  - On the spell cases, without a threshold: `accuracy`, `macro_f1`,
    `log_loss`; the **label AUC** of each label against the others (computed
    from that label's probability, skipping a label with no positives or no
    negatives and listing it as skipped) and their mean; the confusion matrix;
    the precision and recall of each label;
  - The **rejection AUC**: the area under the ROC curve for telling spell cases
    (positive) from backward cases (negative), with the confidence as the
    score;
  - The mean and 95th percentile of `timeMs`;
  - The **curve data**, for every threshold from 0 to 1 in steps of 0.01 (101
    values): the recognition rate (spell cases recognized with the right
    label), misrecognition rate (recognized with a wrong label), missed rate
    (not recognized) and backward false trigger rate (backward cases
    recognized), where a case is recognized when its confidence is at or above
    the threshold;
  - The **threshold information**: the lowest threshold in the curve at which
    the backward false trigger rate is at or below a limit (default 0.05), or
    none if no threshold meets it.

**Acceptance criteria.**

- [ ] Reversing a gesture reverses the positions and re-times them as stated; a
      test with known positions checks the result.
- [ ] Every measure matches a hand-computed value on small hand-made
      predictions (a perfect classifier, a random one, a mix), including the
      label AUC, the rejection AUC (1.0 for perfect separation, 0.5 for equal
      scores), the confusion matrix and the curve data.
- [ ] At threshold 0 the recognition rate equals the accuracy, and every
      backward case is recognized; at threshold 1 only cases with confidence 1
      are recognized.
- [ ] The threshold information is the lowest qualifying threshold, and is
      reported as none when the limit cannot be met.
- [ ] A label with no spell cases or with all of them is skipped for its AUC
      without failing.
- [ ] The predictions table has the stated columns, and every measure can be
      recomputed from it alone (a test recomputes accuracy, the curve data and
      the rejection AUC from the table).
- [ ] The evaluator uses only the test set it is given.

**Implementation notes.** `wand_train/evaluate.py`. `scikit-learn`'s
`roc_auc_score` is fine for the AUC values. The time per gesture is measured by
calling the prediction function for one gesture at a time.

### TR-A8 Final training and models

- **Type**: feat
- **Status**: Not started
- **Depends on**: TR-A6, TR-A7, TR-L2
- **Requirements**: R6.1, R6.2, R6.6 to R6.8, R7.4, R7.6, R7.7, N1, N2
- **Design**: TD 9, 10

**Description.** Train the chosen hyperparameter candidate on the whole
training set, evaluate it once on the test set, and save the model and the
results.

`wand-train train <run id> [--candidate <n>]` or `wand-train train --family
<family> --values <file>`, with `[--seed] [--test-fraction]
[--training-data <folder>] [--reports <folder>] [--models <folder>]
[--max-false-trigger 0.05]`:

1. Reads the hyperparameter candidate: the stated candidate of the exploration
   run (default: the best, by the stored ranking), whose run folder provides
   the seed, the test fraction and the training data fingerprint; or the values
   in a JSON file. It stops with a clear message if the training data's
   fingerprint differs from the one the exploration recorded.
2. Makes the same training and test split as the exploration (TR-A2, with the
   same seed and fraction).
3. Trains the model with the trainer on the whole training set, evaluating on
   the test set (TR-A3), and runs the evaluator (TR-A7) with the trained
   model's prediction function.
4. Allocates a model id `<family>-<yyyymmdd-HHMMSS>`; neither folder below may
   exist already.
5. Writes `<reports>/<family>/training/<model id>/` with `source.json` (the
   exploration run id and candidate number, or null; the hyperparameter values
   used; the seed; the test fraction; the training data fingerprint),
   `metrics.csv` (the measures without a threshold, and the curve data, one
   row per threshold), and `predictions.parquet` (the table of TR-A7).
6. Saves the trained model to `<models>/<family>/<model id>/` with the trainer's
   `save`, and adds to `classifier.json` the fields `modelId`,
   `hyperparameters`, `metrics` (a summary: accuracy, macro F1, log loss, label
   AUC mean, rejection AUC), `trainingDataFingerprint` and `reportPath`. The
   classifier carries no threshold.
7. Loads the saved classifier with the library's `load` and checks that its
   predictions for the test set equal those of the evaluation; stops with an
   error if not.

The test set is never used to train: the saved model is the one that was
evaluated.

**Acceptance criteria.**

- [ ] On a synthetic dataset with the fake family, `train <run id>` writes every
      file named above and the model folder, and prints their paths.
- [ ] The split used by `train` equals the split of the exploration it follows
      (same sample ids in the test set).
- [ ] The trainer is given the training set to train on and the test set to
      evaluate on, and no row is in both (a test checks).
- [ ] `classifier.json` has the stated fields and no threshold; the model loads
      with the library alone, without importing `wand_train` (check in a
      subprocess or with an import guard).
- [ ] A changed training data fingerprint stops the command before any
      training.
- [ ] Two models never share an id or overwrite files; deleting the exploration
      run folder leaves the training report and the model intact.
- [ ] `--values` with a file of hyperparameter values works without an
      exploration run, and `source.json` then records the values and a null
      exploration run.
- [ ] An unknown candidate number, an unknown run id and a family without a
      registered trainer give clear errors.

**Implementation notes.** `wand_train/models.py` and the `train` command in
`cli.py`. The seed of a run without an exploration is `--seed` (default 42).
Writing the report that goes with the training run is added by TR-A9.

### TR-A9 Reporter

- **Type**: feat
- **Status**: Not started
- **Depends on**: TR-A6, TR-A8
- **Requirements**: R7.1 to R7.5, N5
- **Design**: TD 10.3, 11

**Description.** Write Markdown reports with figures, and the index, for
explorations and training runs.

- The **exploration report** (`report.md` and `figures/` in the run folder): the
  definition's key settings (family, validation scheme, comparator), the
  training data fingerprint, the seed, a table of the hyperparameter
  candidates in rank order with their hyperparameter values, the compared
  metric's mean and standard deviation and the other metrics' means, and for
  each hyperparameter that has more than one value a chart of the compared
  metric (mean, with the spread as error bars) against its values.
- The **training report** (`report.md` and `figures/` in the training folder):
  the split sizes, the hyperparameters, the model id and its source, the
  threshold-free measures as a table, the label AUC per label, the confusion
  matrix (as a table), the precision and recall per label, the timing, a chart
  of the recognition, misrecognition and missed rates and the backward false
  trigger rate against the threshold, the ROC curve of the rejection AUC, and
  the threshold information with a sentence that training chooses no
  threshold.
- Figures are PNG files referenced by relative links, drawn with `matplotlib`
  with the `Agg` backend so no display is needed.
- The **index** (`reports/index.md`): for each family, the explorations (run id,
  date, the best candidate's compared metric) and the models (model id, date,
  accuracy, rejection AUC), each with a relative link to its report. It is
  rebuilt from the folders each time any report is written and by
  `wand-train index`. A deleted exploration folder disappears from the index.
- `explore` and `train` call the reporter when they finish.

**Acceptance criteria.**

- [ ] After an exploration and a training run on synthetic data, the reports,
      figures and index exist; every relative link in them points to an
      existing file.
- [ ] The exploration report lists candidates in rank order with the stated
      columns; the training report shows every item listed.
- [ ] The index lists every exploration and model by family, and updates after
      a new run and after a run folder is deleted.
- [ ] Reports are generated without a display (headless).
- [ ] Reports use only the stored files (`results.csv`, `metrics.csv`,
      `predictions.parquet`, `source.json`, `definition.json`, `run.json`), so
      they can be regenerated later without training.

**Implementation notes.** `wand_train/reports/`. Build Markdown tables with
plain string formatting. Keep every line of generated text reasonable;
generated reports are not subject to the 80 column rule.

## 9. Verification tasks

### TR-V1 End-to-end test

- **Type**: test
- **Status**: Not started
- **Depends on**: TR-A9
- **Requirements**: N1, N2, N5, N6
- **Design**: TD 12

**Description.** One automated test that runs the whole flow on a small
synthetic dataset with the fake family, without a camera: build the training
data, explore, train, report, and load the model.

**Acceptance criteria.**

- [ ] Building, exploring (k-fold and single split, in two runs), training and
      reporting run in sequence through the command line functions, and leave
      every file of `TD` 10.
- [ ] A second exploration with the same seed gives the same folds, results
      and ranking.
- [ ] The test set's sample ids never appear in any fold of the exploration or
      in the training set.
- [ ] The saved model loads with `wand_core` alone and predicts the same labels
      and confidences as in the run.
- [ ] Deleting the exploration folder leaves the model, the training report
      and `wand-train index` working.
- [ ] The test needs no camera, no real dataset and runs in seconds.

**Implementation notes.** Put it in `training/tests/test_end_to_end.py`, using
the synthetic dataset helper of TR-A1.

### TR-V2 Real datasets

- **Type**: test
- **Status**: Not started
- **Depends on**: TR-V1, DC-F3, and the tasks of at least one real family
- **Requirements**: N4
- **Design**: TD 5.2, 8, 9

**Description.** Run the tool by hand on the real datasets in `data/` with each
family that has been implemented, and check the results. This task can start
only when the families are designed and implemented (section 1). Record what
was found in `docs/notes.md` or in the task.

**Acceptance criteria.**

- [ ] `training-data build` on the real datasets takes seconds and its
      `check` passes; the counts in `summary` match the datasets.
- [ ] An exploration and a training run complete for each implemented family;
      reports and models are in `reports/` and `models/`.
- [ ] The exploration times are reasonable on a laptop (N4); slow ones are
      noted.
- [ ] A person reads one exploration report and one training report and
      confirms they are understandable.
- [ ] The committed `training-data/` matches the committed datasets (`check`
      passes) before a pull request merges.
