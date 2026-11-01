# Architecture

Status: Draft v1. This is the system-wide view. Component designs live next to
each component and are listed in section 9.

## 1. The problem and the approach

The system turns the motion of a wand, seen through a webcam, into a spell.
Three things make this hard, and the architecture is shaped by them.

- **Challenge: a classifier only works if live input looks like its training
  data.** Approach: one shared library does the vision and motion work for both
  data collection and run time.
- **Challenge: people, wands, lighting, backgrounds and cameras differ.**
  Approach: each recording session is calibrated, and the settings used are
  stored with the data.
- **Challenge: data comes from several people and machines at different
  times.** Approach: data is stored in self-contained session folders with a
  documented layout, and folders can be merged.

## 2. Components

- **Vision** (shared library): finds the wand tip in each camera frame.
- **Motion detection** (shared library): splits tip positions into gestures
  and builds motion vectors.
- **Dataset format** (shared library): reads, writes, exports and merges
  recorded data.
- **Data collection** (in design): records, labels and reviews gestures into
  a dataset.
- **Gesture classification** (later): maps a gesture's vectors to a spell and
  a confidence.
- **Action trigger** (later): performs the effect for a recognized spell.
- **Configuration**: labels, defaults and settings shared by components, kept
  in files under `config/`.

Terms used throughout:

- **Tip**: the midpoint of the ping pong ball on the wand.
- **Gesture**: one deliberate motion of the tip, bounded by idle at the start
  and end.
- **Sample**: a recorded gesture stored in a dataset.
- **Session**: one run of data collection by one person with fixed settings.
- **Label**: the name of a spell a gesture belongs to.

## 3. System flow

### 3.1 Run time

```text
 +--------+ frames +--------+ tip positions +--------+
 | Camera |------->| Vision |-------------->| Motion |
 +--------+        +--------+               +---+----+
                                                | gesture (motion vectors)
                                                v
 +----------+  spell + confidence  +-----------------------+
 |  Action  |<---------------------| Gesture classification|
 +----------+                      +-----------------------+
```

### 3.2 Data collection

```text
 +--------+ frames +--------+ tip positions +--------+
 | Camera |------->| Vision |-------------->| Motion |
 +--------+        +--------+               +---+----+
                                                | gesture
                                                v
 +-------+   calibrate, label, review   +-----------------+
 | User  |<---------------------------->| Data collection |
 +-------+                              +--------+--------+
                                                 | writes
                                                 v
                                        +-----------------+
                                        | Dataset on disk |
                                        +--------+--------+
                                                 | read offline
                                                 v
                                        Classifier training
```

### 3.3 How the two flows relate

Vision and motion detection are the same code in both flows (the shared
library), run with the same kind of settings. Data collection stores the
tip positions of each gesture rather than derived vectors. The vectors are
computed when the data is loaded, by the same code that run time uses, so a
change to how vectors are built never requires re-recording.

## 4. Shared library

The library is the one place where vision, motion detection and the dataset
format are defined. Neither data collection nor run time keeps a private copy.
It has no knowledge of any user interface and never opens a camera on its own
accord: it is handed frames or positions, which also makes it testable without
hardware. Its design is in `lib/docs/design.md`.

## 5. Conventions

These conventions apply to all components and to stored data.

- **Time**: seconds. Within a sample, time is measured from the first stored
  position.
- **Position**: horizontal and vertical position of the tip as a fraction of
  the frame width and height (0 to 1, vertical axis pointing down). The frame
  size is stored beside it.
- **Distance and speed**: measured in frame-heights, and frame-heights per
  second. The horizontal fraction is scaled by the frame's aspect ratio so both
  axes use the same unit. Thresholds expressed this way do not depend on camera
  resolution.
- **Handedness**: recorded as metadata (left or right). Stored positions are
  never mirrored; any handling is the responsibility of training.
- **Labels**: referenced by a stable identifier, never by display name.

## 6. Repository layout

```text
magic-wand/
  pyproject.toml     uv workspace root; shared tool settings (ruff)
  uv.lock            resolved dependency versions for the whole workspace
  CLAUDE.md          agent instructions; points to docs/
  config/            all configuration (section 7)
  docs/              system-wide documentation
  lib/               the shared library
  data-collection/   the data collection application
  data/              default dataset location; not under version control
```

Each component has its own `pyproject.toml`, `docs/` and tests. Tooling rules
are in `docs/standards.md`.

## 7. Configuration

All configuration lives in the `config/` folder.

| File | Contents | In git |
|---|---|---|
| `labels.yaml` | The spell labels: identifier and display name | Yes |
| `vision.yaml` | Default vision settings | Yes |
| `motion.yaml` | Default motion settings | Yes |
| `data-collection.yaml` | App settings (see its design) | Yes |
| `*.local.yaml` | Per-machine override of the file with the same prefix | No |
| `profiles/` | Saved calibration profiles | No |

Settings that affect detection are resolved in this order, later steps
overriding earlier ones:

1. The default files above, then any local override.
2. A calibration profile, if one is loaded.
3. Adjustments made on the calibration screens.

When a session starts, the resolved settings are copied into the session record,
so the data always carries the settings that produced it.

## 8. Data

Datasets are stored in self-contained session folders, outside version control
by default. The layout, file formats, merge and export rules are in
`docs/data-storage.md`.

## 9. Document map

| Document | Content |
|---|---|
| `docs/architecture.md` | This document |
| `docs/data-storage.md` | Dataset layout, formats, merge and export |
| `docs/standards.md` | Workflow, tooling, formatting, documentation rules |
| `docs/notes.md` | Assumptions and constraints |
| `lib/docs/design.md` | Shared library design |
| `data-collection/docs/requirements.md` | Data collection requirements |
| `data-collection/docs/design.md` | Data collection design |
| `data-collection/docs/tasks.md` | Data collection work breakdown |
