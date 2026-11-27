"""A small synthetic dataset on disk, for tests that need a data folder.

The gestures are distinct shapes (a circle, a line and a zigzag) with noise,
spread over several authors and sessions. Deterministic for a given seed.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from wand_core.dataset import (
    DatasetStore,
    Handedness,
    PositionColumns,
    SampleRecord,
    SampleStatus,
)

SHAPES = ("circle", "line", "zigzag")
FRAME_SIZE = (640, 480)
EPOCH = datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc)


def shape_path(shape: str, count: int) -> np.ndarray:
    """Unit-sized path of ``count`` points, shape (count, 2)."""
    t = np.linspace(0.0, 1.0, count)
    if shape == "circle":
        angle = 2 * math.pi * t
        return np.column_stack([0.1 * np.cos(angle), 0.1 * np.sin(angle)])
    if shape == "line":
        return np.column_stack([0.3 * t, 0.0 * t])
    if shape == "zigzag":
        return np.column_stack([0.3 * t, 0.08 * np.abs(((4 * t) % 2) - 1)])
    raise ValueError(f"unknown shape {shape!r}")


def write_synthetic_dataset(
    folder: Path,
    authors: tuple[str, ...] = ("ann",),
    sessions_per_author: int = 2,
    samples_per_shape: int = 4,
    seed: int = 0,
    shapes: tuple[str, ...] = SHAPES,
) -> DatasetStore:
    """Create a data folder with synthetic sessions and samples.

    Each author gets ``sessions_per_author`` ended sessions holding
    ``samples_per_shape`` samples of every shape, labelled with the shape's
    name. Every ninth sample is rejected.
    """
    generator = np.random.default_rng(seed)
    clock = {"now": EPOCH}

    def tick() -> datetime:
        clock["now"] += timedelta(minutes=1)
        return clock["now"]

    store = DatasetStore.open(Path(folder), create=True, clock=tick)
    counter = 0
    for author in authors:
        for _ in range(sessions_per_author):
            session = store.create_session(author, Handedness.RIGHT)
            for _ in range(samples_per_shape):
                for shape in shapes:
                    counter += 1
                    count = int(generator.integers(25, 45))
                    duration = float(generator.uniform(0.6, 1.6))
                    origin = generator.uniform(0.3, 0.6, size=2)
                    path = origin + shape_path(shape, count)
                    path += generator.normal(0, 0.002, size=path.shape)
                    status = (
                        SampleStatus.REJECTED
                        if counter % 9 == 0
                        else SampleStatus.ACCEPTED
                    )
                    now = tick()
                    store.add_sample(
                        SampleRecord(
                            sample_id=store.new_sample_id(session.session_id),
                            session_id=session.session_id,
                            captured_at=now,
                            updated_at=now,
                            label=shape,
                            status=status,
                            handedness=Handedness.RIGHT,
                            frame_size=FRAME_SIZE,
                            positions=PositionColumns(
                                time_s=list(np.linspace(0, duration, count)),
                                horizontal=list(path[:, 0]),
                                vertical=list(path[:, 1]),
                            ),
                        )
                    )
            store.end_session(session.session_id)
    return store
