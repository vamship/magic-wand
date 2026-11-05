# Magic Wand

A system that recognizes wand gestures from a camera and triggers an action, in
the style of the magic wands in the Harry Potter area of Universal Studios. It
is the term project for EECE5644 (Machine Learning and Pattern Recognition).

A user waves a wand (a brightly colored ping pong ball on a stick) in front of
a camera. The system tracks the ball, cuts its motion into gestures, classifies
each gesture as a spell, and performs the action for that spell.

## Running the data collection application

The project uses [uv](https://docs.astral.sh/uv/) for Python environments
and dependencies. From the repository root:

```text
uv sync                    # install everything (Python 3.11 or later)
uv run wand-collect serve  # start the application
```

Then open http://127.0.0.1:8000/ in a browser. The application listens only
on this computer by default. If no camera can be opened, it still starts,
without a live view. On macOS the terminal needs permission to use the
camera (System Settings, Privacy & Security, Camera).

Settings are in `config/`. To change them for this machine only, put
the changed keys in a `*.local.yaml` file beside the original (for example
`config/data-collection.local.yaml`), which is not committed. Options:

```text
uv run wand-collect serve --config <folder> --data-folder <folder>
```

Recorded datasets are stored in `data/` by default (not in git).

To check the code: `uv run ruff format --check`, `uv run ruff check` and
`uv run pytest`.

## Documentation

| Document | Content |
|---|---|
| `docs/architecture.md` | System overview, flows, subsystems, conventions |
| `docs/data-handling.md` | Dataset rules, layout, formats, operations |
| `docs/glossary.md` | Terms shared across the project |
| `docs/standards.md` | Workflow, tooling, formatting, documentation rules |
| `docs/notes.md` | Assumptions and constraints |
| `lib/docs/design.md` | Shared library design |
| `data-collection/docs/requirements.md` | Data collection requirements |
| `data-collection/docs/design.md` | Data collection design |
| `data-collection/docs/tasks.md` | Data collection work breakdown |
| `data-collection/docs/manual-tests.md` | Checklist for real-camera testing |

Start with `docs/architecture.md`.
