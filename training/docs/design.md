# Training Tool - Design

> **Version** 1 | **Updated** 2026-11-25 | **Draft**

## 1. Overview

This document describes how the training tool turns the shared training
dataset into a trained classifier: the components, the flow of one run, the
experiment file, the settings of each classifier, how classifiers are
evaluated and how a threshold is chosen, and the files a run writes. After
reading it you will know what each part does and how to specify and read an
experiment. Requirements are in `training/docs/requirements.md`; system
context is in `docs/architecture.md`; the dataset layout is in
`docs/data-handling.md`.

The tool must answer one question fairly: which classifier recognizes spells
best for a person and a camera it has not seen, while ignoring backward
spells and everyday motion? Three things make the answer reliable:

- all classifiers see the same split and the same test cases;
- the split is by session or by author, so that near-duplicate samples never
  sit on both sides;
- the confidence threshold is chosen from measured results, not guessed.

## 2. The data it works on

The shared training data (29 sessions, 3 authors, about 4,500 accepted
samples, all right-handed) shapes the defaults below.

- A median gesture has about 50 positions and lasts 1.7 seconds; the middle
  80 percent last 1.2 to 2.4 seconds and have 34 to 73 positions.
- Five spells have about 760 samples from three authors. Two spells have about
  500 samples from two authors.
- There are no non-spell recordings yet. Data collection will add them under a
  label that `config/labels.yaml` marks as not a spell; a label without that
  mark is a spell.

## 3. Components

- **Experiment loader**: reads and validates an experiment file and fills in
  defaults.
- **Data loader**: reads the dataset through the shared library, keeps the
  accepted samples, applies the handedness rule and reports counts.
- **Splitter**: divides the sessions into folds.
- **Test case builder**: turns the test side of a fold into test cases.
- **Trainer**: normalizes the training side, trains each classifier on it and
  runs each classifier over the test cases.
- **Evaluator**: computes the measures from the predictions and recommends a
  threshold.
- **Run writer**: writes the run folder.
- **Reporter**: builds the comparison across classifiers and runs.
- **Publisher**: copies a classifier of a run to `models/`.

The normalizer and the classifiers are not part of the tool; they come from
the shared library (`docs/architecture.md`, sections 4.3 and 4.4), which is
also what inference uses.

## 4. Flow of a run

```text
 experiment file
       |
       v
 Experiment loader --> Data loader --> Splitter --> folds
                                                      |
       +----------------------------------------------+
       | for each fold
       v
 Trainer: normalize training side, train every classifier
       |
       v
 Test case builder: spells, backward spells, non-spells
       |
       v
 Trainer: normalize and classify every test case
       |  (prediction, confidence, time)
       v
 Evaluator (all folds pooled) --> measures, thresholds
       |
       v
 Trainer: train each classifier again on all samples
       |
       v
 Run writer --> runs/<run>/            Reporter, Publisher read it later
```

1. The experiment loader checks the file (R1.3) and the data loader reads
   the dataset. The loader stops if a label to learn has no samples.
2. The splitter makes the folds (section 6). Each fold is a list of training
   sessions and a list of test sessions.
3. For each fold, each classifier is trained on the normalized training side
   and then classifies every test case. The tool records the predicted label,
   its confidence and the time taken, with the test case's kind and correct
   outcome.
4. The evaluator pools the predictions of all folds and computes the measures
   in section 8, for every threshold in a range, and picks the recommended
   threshold (section 9).
5. Each classifier is trained once more on all accepted samples of the learned
   labels. This is the classifier the run saves, because it has seen the most
   data; its threshold comes from the held-out results of step 4.
6. The run writer saves everything (section 10).

## 5. The experiment file

An experiment is one YAML file with camel case keys. Every key has a default;
the minimal file lists only the classifiers.

```yaml
name: baseline
dataset: training-data
seed: 42
labels: all
handedness:
  use: right
  others: exclude
normalization:
  points: 32
  context: [duration, startPosition]
split:
  strategy: author
evaluation:
  maxFalseTriggerRate: 0.05
classifiers:
  - family: naiveBayes
  - family: svm
  - family: randomForest
  - family: neuralNet
```

| Key | Meaning | Default |
|---|---|---|
| `name` | Short name, used in the run folder's name | file name |
| `dataset` | A data folder or an export file | `training-data` |
| `seed` | Seed for the split and for every random choice | 42 |
| `labels` | `all` spells, or a list of label ids | `all` |
| `handedness.use` | Handedness the classifier is for | `right` |
| `handedness.others` | `exclude` or `mirror` samples of the other hand | `exclude` |
| `normalization.points` | Points a gesture is resampled to | 32 |
| `normalization.context` | Context values: `duration`, `startPosition` | both |
| `split.strategy` | `author` or `sessions` | `author` |
| `split.testFraction` | Share of sessions tested (`sessions` only) | 0.25 |
| `evaluation.maxFalseTriggerRate` | Limit for threshold choice | 0.05 |
| `classifiers` | Families with their settings (section 7) | required |

Notes on the choices:

- **Points = 32.** Half of all gestures have fewer than 50 positions, and 10
  percent have fewer than 34, so 32 points keep nearly all of the detail of
  most gestures while rarely interpolating much. A larger number adds
  features without adding information. Other values are tried by running
  another experiment.
- **Both context values** let a classifier use the speed of the gesture and
  where in the frame it was drawn. An experiment can drop either one to test
  whether it helps or only fits the people who recorded.
- **Handedness.** The dataset has only right-handed samples. `mirror` converts
  left-handed samples to right-handed by reversing the horizontal direction of
  the positions before normalization. Any classifier trained for the left
  hand uses `handedness.use: left` in its own experiment.
- **No reject class.** The classifiers learn only the spells. Backward spells
  and non-spell recordings are rejected by low confidence, as the
  architecture specifies; they are used as test cases only, so the classifier
  is never trained on a "not a spell" class whose variety it cannot cover.
- The `author` strategy holds out each author once, so the dataset's three
  authors give three folds. The `sessions` strategy gives one fold.

## 6. Splitting

- Sessions, not samples, are the unit of the split, so that one person's
  session (one camera, one lighting, one set of habits) is never on both
  sides.
- **Author strategy.** One fold per author; the test side holds all of that
  author's sessions and the training side holds everyone else's. It measures
  the case that matters at a demonstration: a person the classifier has not
  seen.
- **Sessions strategy.** The sessions are shuffled with the seed and the
  test fraction of them goes to the test side. Sessions are dealt out so that
  each label keeps sessions on the training side.
- A fold whose training side lacks a label to learn is an error that names
  the fold and label. With the shared data this does not occur, because
  every label has at least two authors.
- Anything the model learns from data, such as feature scaling, a validation
  carve-out for the neural network's stopping point, or a classifier setting
  chosen by a search, uses the training side only (N2). The validation
  carve-out is also made by session.

## 7. Classifiers

Every family implements the interface in `docs/architecture.md`, section 4.4.
Features are the flat form of the normalized gesture for the first three
families and the sequence form for the neural network
(`docs/architecture.md`, section 4.3). With 32 points and both context
values, the flat form has 65 numbers: 31 vectors of two numbers, the
duration, and the two start coordinates.

The confidence of every family is the probability it gives to the label it
predicts. Settings are the keys in the `classifiers` entry of the experiment
file; omitted keys take the default shown.

| Family | Settings and defaults | Confidence from |
|---|---|---|
| `naiveBayes` | `varSmoothing` 1e-9 | Class probability of a Gaussian model |
| `svm` | `kernel` rbf, `c` 10, `gamma` scale | Probability estimates fitted on the training side |
| `randomForest` | `trees` 300, `maxDepth` none, `minSamplesLeaf` 1 | Share of trees voting for the label |
| `neuralNet` | `epochs` 60, `learningRate` 0.001, `batchSize` 64, `patience` 8 | Softmax output |

- **Naive Bayes** is the baseline: it assumes the features are independent
  given the spell.
- **SVM and the neural network** need features of similar scale, so their
  features are standardized with the mean and spread of the training side;
  the values are saved with the classifier. Naive Bayes and the forest do not
  need this.
- **Neural network.** A small one-dimensional convolutional network reads the
  sequence of vectors, with the context values joined to its learned summary
  before the output layer. It trains with early stopping: training ends after
  `patience` epochs without improvement on a validation set, carved from the
  training side by session (15 percent of the sessions), and the best epoch
  is kept. The network is deliberately small, since there are only a few
  thousand samples.
- Random choices use the experiment's seed.
- Settings are fixed in the experiment file. Searching over settings is done
  by running several experiments and comparing them.

## 8. Test cases and measures

### 8.1 Test cases

The test side of a fold gives:

| Kind | Source | Correct outcome |
|---|---|---|
| Spell | Held-out samples of learned labels | The sample's label, with confidence at or above the threshold |
| Backward | Each spell sample, positions in reverse order | Not recognized |
| Non-spell | Held-out samples of labels that are not spells | Not recognized |

A reversed gesture runs through the same positions from last to first, with
times measured from the new first position, so a backward spell lasts as long
as the original and moves at the same speeds. A classifier cannot reject it
by duration or speed, only by direction.

### 8.2 Measures

A prediction counts as **recognized** when its confidence is at or above the
threshold, and as **not recognized** below it. The measures are computed for
every threshold from 0 to 1 in steps of 0.01:

| Measure | Definition |
|---|---|
| Recognition rate | Spell cases recognized with the right label, over all spell cases |
| Misrecognition rate | Spell cases recognized with a wrong label, over all spell cases |
| Missed rate | Spell cases not recognized, over all spell cases |
| Backward false trigger rate | Backward cases recognized as any spell, over all backward cases |
| Non-spell false trigger rate | Non-spell cases recognized as any spell, over all non-spell cases |

At threshold 0 every case is recognized, so recognition rate at 0 is the
plain accuracy of the classifier. Also reported:

- the confusion matrix and the precision and recall of each label at
  threshold 0 and at the recommended threshold;
- accuracy per author (author strategy) so a weak fold is visible;
- the time to normalize and classify one gesture, as the mean and the 95th
  percentile over the test cases, measured one gesture at a time as inference
  runs;
- the number of training samples and test cases of each kind.

With several folds the predictions of all folds are pooled before the
measures are computed, and the per-fold values are reported beside them.

## 9. Threshold recommendation

For each classifier the recommended threshold is the lowest one at which the
backward false trigger rate and, when non-spell cases exist, the non-spell
false trigger rate are both at or below `evaluation.maxFalseTriggerRate`.
The lowest such threshold gives the highest recognition rate that meets the
limit, because the false trigger rates fall and the missed rate rises as the
threshold rises. If no threshold meets the limit, the recommendation is
threshold 1 and the report says the limit could not be met.

The recommendation is a starting value. The action trigger can override it in
configuration (`docs/architecture.md`, section 4.5).

## 10. Run folder

A run writes `runs/<timestamp>-<name>/`, with the timestamp in the form
`20261125-141502`. The folder is never reused (R7.3).

```text
runs/<timestamp>-<name>/
  run.json              identity, timings, tool version, summary
  experiment.yaml       the experiment as run, defaults filled in
  dataset.json          the dataset's identity and counts
  folds.json            session ids of each fold's two sides
  predictions.jsonl     one line per test case and classifier
  metrics.json          every measure of section 8, per threshold
  classifiers/
    <family>/
      classifier.json   metadata of the saved classifier
      model             the trained model
```

- **Dataset identity** (`dataset.json`) holds the dataset's location, the
  git commit of the repository when the dataset is `training-data`, the ids
  of its sessions, and a fingerprint: a SHA-256 hash over the sorted sample
  ids with each sample's label and status. Two runs used the same data when
  their fingerprints match.
- **`predictions.jsonl`** has one line per classifier and test case: fold,
  sample id, kind, correct label (or null), predicted label, confidence and
  time in milliseconds. The measures can be recomputed from it without
  retraining.
- **`classifier.json`** carries `formatVersion`, the family, the label ids,
  the normalization settings, the recommended threshold, the run it came from
  and a summary of its metrics. The model file is the family's own
  serialization.

## 11. Commands

| Command | What it does |
|---|---|
| `wand-train run <experiment>` | Runs the experiment and prints where the run folder is |
| `wand-train data <dataset>` | Prints the counts of section 2 for a dataset without training |
| `wand-train compare <run>...` | Writes a comparison report for the runs |
| `wand-train publish <run> <family> <name>` | Copies the classifier to `models/<name>/` |

`wand-train run` prints progress per fold and classifier and a summary table
at the end. `wand-train compare` writes `report.md` and the images it refers
to into the first run's folder, or into the folder named by `--out`.

### 11.1 Comparison report

The report has one section per run, with the key settings and the dataset
identity, then:

- a table of classifiers with recognition rate, misrecognition rate, missed
  rate, the two false trigger rates at the recommended threshold, and the
  time per gesture;
- a chart per run of recognition rate against backward false trigger rate as
  the threshold varies, one curve per classifier;
- the confusion matrix of each classifier at its recommended threshold;
- the accuracy per author.

When runs of different experiments are compared, the report lists the
settings in which the experiments differ.

## 12. Testing

- **Experiment loader**: a valid file, defaults, an unknown key, an unknown
  family and a value out of range each give the expected result or message.
- **Splitter**: no session has samples on both sides; the same seed gives the
  same folds; the author strategy gives one fold per author; a missing label
  on the training side is reported.
- **Test case builder**: reversing a gesture gives reversed positions with
  re-timed timestamps; non-spell samples are test cases and never training
  data.
- **Evaluator**: measures computed from small hand-made predictions match
  hand-computed values, including the threshold rules and the case where no
  threshold meets the limit.
- **Whole run**: a small synthetic dataset, with spells that are simple
  distinct shapes, run through every family. Every family beats chance, the
  run folder holds every file of section 10, and a second run with the same
  seed gives the same folds and measures.
- **Publish and reload**: a published classifier loaded by the library's
  loader predicts the same labels and confidences as in the run.
- Real data is not used in tests; the tool is also run on the shared dataset
  by hand when its tasks are verified.

## 13. Requirement coverage

| Requirement | Design |
|---|---|
| R1 | 5 |
| R2 | 2, 3, 4 |
| R3 | 4, 7 |
| R4 | 6 |
| R5 | 8.1 |
| R6 | 4, 7, 8, 9 |
| R7 | 4, 10 |
| R8 | 11.1 |
| R9 | 10, 11 |
| N1 | 5, 10 |
| N2 | 6, 7 |
| N3 | 3, 7 |
| N4 | 7 |
| N5 | 12 |

## 14. To Do

Items to fill in before this document is approved:

- Library design: `lib/docs/design.md` must gain the normalizer and the
  classifier interface and families, and its vector builder must hand the
  resampling to the normalizer, as `docs/architecture.md` now specifies.
- Data collection: recording non-spell samples under a label that is not a
  spell, and the `isSpell` mark in `config/labels.yaml` (a label without the
  mark is a spell).
