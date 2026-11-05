# Data Handling

> **Version** 5 | **Updated** 2026-11-05 | **Approved**

## 1. Overview

This document defines how recorded gesture data is organized on disk: the
rules for handling datasets, the data folder layout, identifiers, file
formats, write safety, and the export, merge and check operations. After
reading it you will know where each piece of data lives, what the session
and sample records contain, and what every tool must do when it reads or
writes a dataset. Data collection writes this layout; the classifier and
tools read it.

Goals:

- Be organized and documented, with a clear place for everything.
- Let sessions recorded in parallel, by different people on different machines,
  be combined without collisions.
- Be directly loadable by the classifier.
- Never leave a half-written file behind, even after a crash.

## 2. Rules

- Datasets are not stored in git. The default location, `data/`, is excluded
  from version control. A dataset can be placed in any folder on the local
  machine by setting the data folder in `config/data-collection.yaml`.
- A session folder is self-contained and is the unit of exchange. Datasets are
  combined by merging session folders; merging never modifies a session or its
  inputs.
- Samples store positions, never derived vectors.
- Rejected samples stay in the dataset with status `rejected`; training uses
  accepted samples.
- A sample can be deleted. Deleting is permanent: it removes the sample record
  and its video clip from the dataset.
- A whole session can be deleted. Deleting is permanent: it removes the session
  folder with its record, its samples and its clips. A session that is loaded
  cannot be deleted.
- Video clips are optional. A clip may never have been recorded, may have
  failed to encode, or may have been removed later to save space. A missing
  clip is never an error: every tool treats it as "no clip".
- Labels are defined in the shared configuration, not in the dataset. Samples
  refer to labels by identifier.
- Every session records the settings and camera mode used to capture it.
- Handedness is recorded, and positions are never mirrored when stored.
- Writes are crash-safe (section 6), and the format carries a version number.
- Derived data such as thumbnails is cached outside the dataset and can be
  deleted.

## 3. The data folder

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
      samples.jsonl            one line per recorded gesture
      videos/
        <sample id>.mp4        video clip for the sample (may be absent)
```

- `dataset.json`: format version of the folder, created with the folder.
- `sessions/`: one subfolder per session; nothing else is stored here.
- `session.json`: session metadata and the exact settings used.
- `samples.jsonl`: the session's samples, accepted or rejected, in capture
  order, one JSON record per line.
- `videos/`: one video clip per sample, named after the sample.

Not stored in the data folder:

- **Labels** are shared project configuration (`config/labels.yaml`), so every
  teammate uses the same identifiers.
- **Calibration profiles** are per machine (`config/profiles/`).
- **Caches** (thumbnails and similar derived files) are created on demand in
  the operating system's user cache location. They can be deleted at any time.
  Keeping them out of the data folder keeps copies of it clean.

## 4. Identifiers

- **Session id**: a random UUID (version 4) in lowercase with hyphens, for
  example `3f8c1d2e-9a4b-4c7e-8f10-5b6d7e8f9a0b`. It names the session folder.
  It carries no author or time information; those are in `session.json`.
- **Session name**: free text chosen by the author when starting the session,
  so teammates can refer to a session by name. It is stored in `session.json`,
  need not be unique, and is never used as an identifier or folder name.
- **Sample id**: `<session id>-<number>`, for example
  `3f8c1d2e-9a4b-4c7e-8f10-5b6d7e8f9a0b-0042`. The number is a sequence that
  starts at 0001 in capture order, with more digits if a session exceeds 9999
  samples. Because the session id is unique, the sample id is unique across all
  datasets.
- A session stays open until the user ends it; closing the application does
  not end it. Samples are added only while a session is open, so an ended
  session never receives new samples. An open session can be resumed later and
  continues in the same session folder.
- The session records the highest sample number it has used. The next sample
  takes the number after the larger of that value and the highest number in
  the samples file. Numbers are therefore never reused, not after a sample is
  deleted and not after a resume.
- Identifiers never change. Merging keeps them.
- **Label id**: a lowercase slug (letters, digits, underscore).

## 5. File formats

`session.json` and `dataset.json` are UTF-8 JSON. `samples.jsonl` is UTF-8 JSON
Lines: one complete JSON object per line, each line ending in a newline. JSON
keys are camel case, as required by `docs/standards.md`. Both `dataset.json` and
`session.json` carry an integer `formatVersion`.

### 5.1 `session.json`

```json
{
  "formatVersion": 1,
  "sessionId": "3f8c1d2e-9a4b-4c7e-8f10-5b6d7e8f9a0b",
  "name": "Vamshi evening desk",
  "author": "vamshi",
  "handedness": "right",
  "startedAt": "2026-11-01T14:15:02-04:00",
  "endedAt": "2026-11-01T14:58:40-04:00",
  "notes": "desk lamp, white wall",
  "camera": {
    "device": "FaceTime HD Camera",
    "index": 0,
    "requested": {"width": 640, "height": 480, "fps": 30},
    "actual": {"width": 640, "height": 480, "fps": 29.8}
  },
  "visionSettings": {"...": "see the library design"},
  "motionSettings": {"...": "see the library design"},
  "clipPadding": {"preS": 2.0, "postS": 2.0},
  "highestSampleNumber": 42,
  "profile": "desk-evening"
}
```

`endedAt` is null while the session is open, including when the application
was closed without ending it. `highestSampleNumber` is the highest sample
number used so far, and is updated each time a sample is saved. `profile` is
null if none was loaded. `name` and `notes` are optional free text; they
can be edited at any time, also after the session has ended, and are the only
fields a user can change in a session.

### 5.2 `samples.jsonl`

Each line is one sample record. The example is spread over several lines for
reading; in the file it is a single line.

```json
{
  "sampleId": "3f8c1d2e-9a4b-4c7e-8f10-5b6d7e8f9a0b-0042",
  "sessionId": "3f8c1d2e-9a4b-4c7e-8f10-5b6d7e8f9a0b",
  "capturedAt": "2026-11-01T14:15:30-04:00",
  "updatedAt": "2026-11-01T14:15:30-04:00",
  "label": "circle",
  "status": "accepted",
  "handedness": "right",
  "frameSize": [640, 480],
  "positions": {
    "timeS": [0.0, 0.033, 0.066],
    "horizontal": [0.41, 0.42, 0.44],
    "vertical": [0.52, 0.50, 0.47]
  },
  "video": {
    "file": "videos/3f8c1d2e-9a4b-4c7e-8f10-5b6d7e8f9a0b-0042.mp4",
    "gestureStartS": 2.0
  }
}
```

- `status` is `accepted` or `rejected`. Samples are accepted when captured and
  can be rejected during or after the session.
- `label` is a label id and is always set for recorded samples. Changing it
  later updates `updatedAt`.
- `positions` are the tip positions as defined in `docs/architecture.md`,
  stored column by column: `timeS` in seconds from the first position,
  `horizontal` and `vertical` as fractions of the frame. Frames where the tip
  was not found are absent; the times show the gaps. Derived vectors are never
  stored.
- `video.file` is relative to the session folder. `video.gestureStartS` is
  where the gesture begins within the clip. `video` is null if no clip was
  recorded. If the referenced file is absent, the sample has no clip, exactly
  as if `video` were null.

JSON is used because samples are small (tens to a few hundred points) and the
files stay readable. One line per sample keeps a session in a single file and
lets a set of samples be combined by concatenating lines.

## 6. Writing safely

Every write follows one of three routines, so a reader never sees a damaged
file:

- **Replace** (used for `session.json`, `dataset.json` and any edit or delete
  in `samples.jsonl`): write the complete new content to a temporary file in
  the same folder, flush it to disk, atomically rename it over the final name,
  then flush the folder.
- **Append** (used when a new sample is saved): write the video clip first,
  using the replace routine. Then write the sample's line, including its
  newline, to the end of `samples.jsonl` in one write and flush it to disk.
  Then update `highestSampleNumber` in `session.json` using the replace
  routine.
- **Delete** (used when a sample is deleted): rewrite `samples.jsonl` without
  the sample using the replace routine, then remove the video clip.
- **Delete session** (used when a session is deleted): rename the session
  folder to a temporary name outside `sessions/`, then remove it. A crash
  leaves the session whole or gone, never half deleted, and opening the data
  folder removes a leftover temporary folder.

A crash during an append can leave an incomplete last line. Readers ignore a
last line that lacks its newline or is not valid JSON. Opening a data folder
removes it, and removes leftover temporary files. At most the sample being
written is lost. If a crash falls between the append and the update of
`highestSampleNumber`, the next sample number is still correct because it also
considers the highest number in the samples file.

## 7. Operations

### 7.1 Consistency check

Reports, without changing anything: temporary files, incomplete last lines in
sample files, video clips with no sample, samples whose clip is missing,
samples with an unknown label id, and files with an unsupported format
version. Samples whose clip is missing are listed as information, not as
errors.

### 7.2 Export

Writes one consolidated file in JSON Lines format. Each line is one sample
record with its session record embedded under `session`. The export can be
filtered (for example, accepted samples only) and can read several data
folders at once. It contains positions and metadata, not video. The classifier
can load either a data folder or an export file.

### 7.3 Merge

Combines one or more source data folders into a target data folder:

- Sources are only read and are never changed. Only the target is written.
- Session folders that the target does not have are copied in whole. Session
  ids and sample ids are kept as they are; they are already unique, so nothing
  is renumbered.
- A session present in both with identical content is skipped.
- A session present in both with different content is a conflict. It is
  reported and left unchanged unless the user chooses to replace the target's
  copy with the source's.
- Video clips are copied with their sessions, so everything travels together
  and the target never depends on the source. Because clips are optional, the
  user can choose to skip them when only positions are needed.
- Sessions are never modified or split, so merging cannot interleave data from
  different sessions.

Merging does not need a camera or a running application.

## 8. Size

At the default 640x480 and 30 fps, a clip with 2 seconds of padding on each
side of a 2-second gesture is about 6 seconds, roughly 1 to 2 MB. At 1,000
samples per gesture that is about 1 to 2 GB per gesture. The padding is
configurable in `config/data-collection.yaml`. Clips can be deleted at any
time without affecting the rest of the dataset.

## 9. Versioning

`formatVersion` increases when a change is not backward compatible. Readers
reject versions they do not know rather than guessing.
