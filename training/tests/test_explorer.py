import pytest

from wand_core.testing.datasets import write_synthetic_dataset
from wand_train import definitions
from wand_train.data import builder, gestureset
from wand_train.explore.comparator import (
    ByMetric,
    Comparator,
    ComparatorError,
    build_comparator,
    register_comparator,
    unregister_comparator,
)
from wand_train.explore.explorer import (
    Explorer,
    Fold,
    KFoldExplorer,
    SingleSplitExplorer,
    build_explorer,
    register_scheme,
    unregister_scheme,
)
from wand_train.trainers.base import (
    Hyperparameter,
    HyperparameterError,
    Trainer,
    TrainResult,
)
from wand_train.trainers.fake import (
    register_fake_family,
    unregister_fake_family,
)
from wand_train.trainers.registry import register_trainer, unregister_trainer


@pytest.fixture(scope="module")
def full(tmp_path_factory):
    root = tmp_path_factory.mktemp("explorer")
    write_synthetic_dataset(
        root / "data" / "ann", authors=("ann", "bob"), samples_per_shape=10
    )
    builder.build([root / "data" / "ann"], root / "td", root=root)
    return gestureset.load(root / "td")


@pytest.fixture
def sets(full):
    return full.train_test_split(seed=1)


# Known accuracy of each candidate (value of "a") on fold 0 and fold 1.
# The numbers are exact in binary, so means and ties compare exactly.
TABLE = {1: [0.5, 0.75], 2: [1.0, 0.5], 3: [0.25, 0.25], 4: [0.75, 0.75]}


class Scripted(Trainer):
    """Returns known metrics and records every set it is given."""

    family = "scripted"
    hyperparameter_specs = (Hyperparameter("a", "float", 1.0, minimum=0),)

    def __init__(self):
        super().__init__()
        self.calls = []

    def fit(self, features, labels, hyperparameters, seed):
        raise NotImplementedError

    def predict_probabilities(self, features):
        raise NotImplementedError

    def write_model(self, folder):
        raise NotImplementedError

    def train(
        self,
        training_set,
        evaluation_set,
        hyperparameters=None,
        seed=42,
        with_predictions=False,
    ):
        values = self.validate(hyperparameters)
        fold = sum(1 for call in self.calls if call["a"] == values["a"])
        self.calls.append(
            {
                "a": values["a"],
                "seed": seed,
                "training": set(training_set.rows),
                "validation": set(evaluation_set.rows),
            }
        )
        accuracy = TABLE[int(values["a"])][fold]
        return TrainResult(
            {"accuracy": accuracy, "log_loss": 1 - accuracy},
            values,
            (),
        )


def definition(scheme="kFold", direction="max", values=(1, 2, 3, 4), **extra):
    return definitions.parse(
        {
            "formatVersion": 1,
            "name": "scripted",
            "family": "scripted",
            "validation": {"scheme": scheme, "folds": 2, **extra},
            "comparator": {
                "name": "byMetric",
                "settings": {"metric": "accuracy", "direction": direction},
            },
            "hyperparameters": {"a": list(values)},
        }
    )


def make(scheme="kFold", direction="max", **kwargs):
    spec = definition(scheme, direction, **kwargs)
    comparator = build_comparator("byMetric", spec.comparator.settings)
    cls = KFoldExplorer if scheme == "kFold" else SingleSplitExplorer
    trainer = Scripted()
    return cls(trainer, spec, comparator), trainer


def test_aggregates_and_ranking_for_max(sets):
    training, _ = sets
    explorer, _ = make(direction="max")
    ranked = explorer.explore(training, seed=1)
    # Means: 1 -> .625, 2 -> .75, 3 -> .25, 4 -> .75 (ties with 2).
    assert [result.number for result in ranked] == [2, 4, 1, 3]
    by_number = {result.number: result for result in ranked}
    assert by_number[1].mean["accuracy"] == 0.625
    assert by_number[1].std["accuracy"] == 0.125
    assert by_number[2].std["accuracy"] == 0.25
    assert by_number[3].std["accuracy"] == 0.0
    assert by_number[1].fold_metrics == [
        {"accuracy": 0.5, "log_loss": 0.5},
        {"accuracy": 0.75, "log_loss": 0.25},
    ]
    assert by_number[2].hyperparameters == {"a": 2}


def test_ranking_for_min_and_ties_keep_enumeration_order(sets):
    training, _ = sets
    ranked = make(direction="min")[0].explore(training, seed=1)
    assert [result.number for result in ranked] == [3, 1, 2, 4]


def test_kfold_uses_every_row_for_validation_once(sets):
    training, _ = sets
    explorer = make()[0]
    folds = explorer.make_folds(training, seed=3)
    assert len(folds) == 2
    validated = [row for fold in folds for row in fold.validation.rows]
    assert sorted(validated) == sorted(training.rows)
    for fold in folds:
        assert set(fold.training.rows).isdisjoint(fold.validation.rows)
        assert len(fold.training) + len(fold.validation) == len(training)
    five = KFoldExplorer(
        Scripted(),
        definitions.parse(
            {**_raw(), "validation": {"scheme": "kFold", "folds": 5}}
        ),
        build_comparator(
            "byMetric", {"metric": "accuracy", "direction": "max"}
        ),
    ).make_folds(training, seed=3)
    assert sorted(r for f in five for r in f.validation.rows) == sorted(
        training.rows
    )


def _raw():
    return {
        "formatVersion": 1,
        "name": "scripted",
        "family": "scripted",
        "validation": {"scheme": "kFold"},
        "comparator": {
            "name": "byMetric",
            "settings": {"metric": "accuracy", "direction": "max"},
        },
        "hyperparameters": {"a": [1]},
    }


def test_single_split_uses_the_fraction(sets):
    training, _ = sets
    explorer, _ = make("singleSplit", fraction=0.25)
    (fold,) = explorer.make_folds(training, seed=1)
    assert abs(len(fold.validation) - 0.25 * len(training)) <= 3
    assert set(fold.training.rows).isdisjoint(fold.validation.rows)


def test_every_candidate_sees_the_same_folds_and_the_seed(sets):
    training, _ = sets
    explorer, trainer = make()
    explorer.explore(training, seed=11)
    assert len(trainer.calls) == 4 * 2
    by_candidate = {}
    for call in trainer.calls:
        by_candidate.setdefault(call["a"], []).append(
            (call["training"], call["validation"])
        )
    first = by_candidate[1]
    for folds in by_candidate.values():
        assert folds == first
    assert all(call["seed"] == 11 for call in trainer.calls)


def test_held_out_rows_never_reach_a_trainer(sets):
    training, test = sets
    explorer, trainer = make()
    explorer.explore(training, seed=1)
    seen = set().union(
        *(c["training"] | c["validation"] for c in trainer.calls)
    )
    assert seen == set(training.rows)
    assert seen.isdisjoint(test.rows)


def test_invalid_hyperparameter_fails_before_any_training(sets):
    training, _ = sets
    explorer, trainer = make(values=(1, 2, -5))
    with pytest.raises(HyperparameterError, match=r"candidate 3.*'a'"):
        explorer.explore(training, seed=1)
    assert trainer.calls == []


def test_callbacks(sets):
    training, _ = sets
    explorer, _ = make()
    progress, finished = [], []
    explorer.explore(
        training,
        seed=1,
        progress=lambda done, total: progress.append((done, total)),
        on_candidate=lambda number, folds, result: finished.append(
            (number, len(folds), result.number, len(progress))
        ),
    )
    assert progress == [(i, 8) for i in range(1, 9)]
    # Called once per candidate, in order, as each finishes.
    assert finished == [(1, 2, 1, 2), (2, 2, 2, 4), (3, 2, 3, 6), (4, 2, 4, 8)]


def test_comparator_errors():
    with pytest.raises(ComparatorError, match="nope"):
        build_comparator("nope", {})
    for bad in (
        {},
        {"metric": "accuracy"},
        {"metric": "accuracy", "direction": "up"},
        {"metric": "", "direction": "max"},
        {"metric": "accuracy", "direction": "max", "extra": 1},
    ):
        with pytest.raises(ComparatorError):
            build_comparator("byMetric", bad)
    with pytest.raises(ComparatorError, match="speed"):
        from wand_train.explore.results import aggregate

        result = aggregate(1, {}, [{"accuracy": 1.0}])
        ByMetric("speed", "max").compare(result, result)


def test_factory_builds_from_a_definition():
    register_fake_family()
    try:
        spec = definitions.parse(
            {
                **_raw(),
                "family": "fake",
                "hyperparameters": {"sharpness": [1.0]},
            }
        )
        explorer = build_explorer(spec)
        assert isinstance(explorer, KFoldExplorer)
        assert isinstance(explorer.comparator, ByMetric)
        single = definitions.parse(
            {
                **_raw(),
                "family": "fake",
                "validation": {"scheme": "singleSplit"},
                "hyperparameters": {"sharpness": [1.0]},
            }
        )
        assert isinstance(build_explorer(single), SingleSplitExplorer)
    finally:
        unregister_fake_family()


def test_end_to_end_with_the_fake_family(sets):
    training, test = sets
    register_fake_family()
    try:
        spec = definitions.parse(
            {
                **_raw(),
                "family": "fake",
                "hyperparameters": {"sharpness": [0.01, 5.0, 50.0]},
            }
        )
        ranked = build_explorer(spec).explore(training, seed=1)
        assert len(ranked) == 3
        accuracies = [r.mean["accuracy"] for r in ranked]
        assert accuracies == sorted(accuracies, reverse=True)
    finally:
        unregister_fake_family()


def test_new_schemes_and_comparators_need_no_change_to_the_base(sets):
    training, _ = sets

    class Halves(Explorer):
        def make_folds(self, training_set, seed):
            first, second = training_set.split([0.5, 0.5], seed)
            return [Fold(first, second)]

    class Fewest(Comparator):
        def compare(self, first, second):
            return first.number - second.number

    register_scheme("halves", Halves)
    register_comparator("byNumber", lambda settings: Fewest())
    register_trainer(Scripted)
    try:
        spec = definitions.parse(
            {
                **_raw(),
                "family": "scripted",
                "validation": {"scheme": "kFold"},
                "comparator": {"name": "byNumber"},
                "hyperparameters": {"a": [3, 1]},
            }
        )
        spec = definitions.Definition(
            spec.name,
            spec.family,
            definitions.Validation("halves"),
            spec.comparator,
            spec.hyperparameters,
        )
        explorer = build_explorer(spec)
        assert isinstance(explorer, Halves)
        # Scripted has two folds' worth of numbers; one fold uses index 0.
        ranked = explorer.explore(training, seed=1)
        assert [r.number for r in ranked] == [1, 2]
    finally:
        unregister_scheme("halves")
        unregister_comparator("byNumber")
        unregister_trainer("scripted")
