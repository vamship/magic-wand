# Data Storage

Status: Draft v1. Defines how recorded data is organized on disk. Data
collection writes this layout; the classifier and tools read it.

## 1. Goals

- Be organized and documented, with a clear place for everything.
- Let sessions recorded in parallel, by different people on different machines,
  be combined without collisions.
- Be directly loadable by the classifier.
- Never leave a half-written file behind, even after a crash.

## 2. The data folder

A dataset lives in one **data folder**. The default is `data/` at the repository
root, which is not under version control (recorded video makes datasets too
large). The location is set in `config/data-collection.yaml`.

The unit of storage and exchange is the **session folder**. It holds everything
about one session, so a session can be copied, zipped, or sent to a teammate as
a whole.

```text
<data folder>/
  dataset.json                 format version and creation time
  sessions/
    <session id>/
      session.json             who, when, camera, settings used
      samples/
        <sample id>.json       one file per recorded gesture
      videos/
        <sample id>.mp4        video clip for the sample (may be absent)
```

- `dataset.json`: format version of the folder, created with the folder.
- `sessions/`: one subfolder per session; nothing else is stored here.
- `session.json`: session metadata and the exact settings used.
- `samples/`: one JSON file per sample, accepted or rejected.
- `videos/`: one video clip per sample, named after the sample.

Not stored in the data folder:

- **Labels** are shared project configuration (`config/labels.yaml`), so every
  teammate uses the same identifiers.
- **Calibration profiles** are per machine (`config/profiles/`).
- **Caches** (thumbnails and similar derived files) are created on demand in
  the operating system's user cache location. They can be deleted at any time.
  Keeping them out of the data folder keeps copies of it clean.

## 3. Identifiers

- **Session id**: `YYYYMMDDTHHMMSS-<author>-<4 hex>`, for example
  `20261101T141502-vamshi-a3f1`. The author part is a lowercase slug.
- **Sample id**: `YYYYMMDDTHHMMSS-<4 hex>`, unique within its session.
- A sample is identified globally by its session id and sample id together.
- Identifiers are never reused or changed.
- **Label id**: a lowercase slug (letters, digits, underscore).

## 4. File formats

All files are UTF-8 JSON. Every file has an integer `format_version`.

### 4.1 `session.json`

```json
{
  "format_version": 1,
  "session_id": "20261101T141502-vamshi-a3f1",
  "author": "vamshi",
  "handedness": "right",
  "started_at": "2026-11-01T14:15:02-04:00",
  "ended_at": "2026-11-01T14:58:40-04:00",
  "notes": "desk lamp, white wall",
  "camera": {
    "device": "FaceTime HD Camera",
    "index": 0,
    "requested": {"width": 640, "height": 480, "fps": 30},
    "actual": {"width": 640, "height": 480, "fps": 29.8}
  },
  "vision_settings": {"...": "see the library design"},
  "motion_settings": {"...": "see the library design"},
  "clip_padding": {"pre_s": 2.0, "post_s": 2.0},
  "profile": "desk-evening"
}
```

`ended_at` is null while the session is open. `profile` is null if none was
loaded.

### 4.2 `<sample id>.json`

```json
{
  "format_version": 1,
  "sample_id": "20261101T141530-9c2e",
  "session_id": "20261101T141502-vamshi-a3f1",
  "captured_at": "2026-11-01T14:15:30-04:00",
  "updated_at": "2026-11-01T14:15:30-04:00",
  "label": "circle",
  "status": "accepted",
  "handedness": "right",
  "frame_size": [640, 480],
  "positions": {
    "t": [0.0, 0.033, 0.066],
    "x": [0.41, 0.42, 0.44],
    "y": [0.52, 0.50, 0.47]
  },
  "video": {"file": "videos/20261101T141530-9c2e.mp4", "gesture_start_s": 2.0}
}
```

- `status` is `accepted` or `rejected`. Samples are accepted when captured and
  can be rejected during or after the session.
- `label` is a label id and is always set for recorded samples. Changing it
  later updates `updated_at`.
- `positions` are the tip positions as defined in `docs/architecture.md`,
  stored column by column. Frames where the tip was not found are absent;
  timestamps show the gaps. Derived vectors are never stored.
- `video.gesture_start_s` is where the gesture begins within the clip. `video`
  is null if no clip exists.

JSON is used because samples are small (tens to a few hundred points), files
stay readable, and one file per sample makes safe edits simple.

## 5. Writing safely

Every write goes through one routine: write to a temporary file in the same
folder, flush it to disk, atomically rename it over the final name, then flush
the folder. A reader never sees a partial file. A video clip is completed
before the sample file that refers to it. Leftover temporary files are removed
when the data folder is opened.

## 6. Operations

### 6.1 Consistency check

Reports, without changing anything: temporary files, video clips with no
sample, samples whose clip is missing, samples with an unknown label id, and
files with an unsupported format version.

### 6.2 Export

Writes one consolidated file in JSON Lines format. Each line is one sample
record with its session record embedded under `session`. The export can be
filtered (for example, accepted samples only) and can read several data
folders at once. It contains positions and metadata, not video. The classifier
can load either a data folder or an export file.

### 6.3 Merge

Combines one or more source data folders into a target data folder:

- Session folders that the target does not have are copied in whole.
- A session present in both with identical content is skipped.
- A session present in both with different content is a conflict. It is
  reported and left unchanged unless the user chooses to replace the target's
  copy with the source's.
- Sessions are never modified or split, so merging cannot interleave data from
  different sessions.

Merging does not need a camera or a running application.

## 7. Size

At the default 640x480 and 30 fps, a clip with 2 seconds of padding on each
side of a 2-second gesture is about 6 seconds, roughly 1 to 2 MB. At 1,000
samples per gesture that is about 1 to 2 GB per gesture. The padding is
configurable in `config/data-collection.yaml`.

## 8. Versioning

`format_version` increases when a change is not backward compatible. Readers
reject versions they do not know rather than guessing.
