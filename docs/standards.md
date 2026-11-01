# Standards

## Overview

This document defines how work is done in every component of the repository:
the branching workflow, Python tooling, code and text formatting, and the
rules for writing documentation. After reading it you will know what is
required of any change and of any document. The root `CLAUDE.md` points
here; this file is the single source for the rules.

## 1. Workflow

- All development takes place in a branch, with one branch per task. Never
  commit directly to `main`.
- Branch names are `<kind>/<short-name>`, where kind is `docs`, `feat`, `fix`
  or `chore` (for example `docs/requirements` or `feat/tracker`).
- Each task in a component's `tasks.md` is sized to fit one branch and names
  that branch.

## 2. Python tooling

- Use **uv** for all Python development: environments, dependencies, running
  scripts, tests and tools. Do not use `pip` or `venv` directly.
- The repository is a single uv workspace. The root `pyproject.toml` lists the
  member packages, and one `uv.lock` at the root is committed. Every package
  therefore resolves to the same version of each shared dependency.
- Every dependency is declared in the `pyproject.toml` of the package that uses
  it, with a version constraint. The exact resolved version is recorded in
  `uv.lock`. Each package declares its supported Python version. Tools used
  only in development belong in the development dependency group. Never
  install packages ad hoc.
- Run everything through `uv run` (for example `uv run pytest`,
  `uv run ruff format` and `uv run ruff check`). Applications declare a
  command so they start with `uv run <command>`.
- Use **ruff** for formatting and linting. It is configured once, in the root
  `pyproject.toml`, with a line length of 80 and the line-length lint rule
  enabled. Run both ruff commands before committing.
- Tests use pytest and live in each package's `tests` directory. Code that is
  shared between components must be testable without a camera or a UI.

## 3. Code and text formatting

- Wrap all text at 80 columns: code, markdown, configuration and
  documentation alike.
- Python is formatted and checked by ruff.
- JavaScript and CSS have no tooling. Whoever writes them, including the
  agent, wraps lines at 80 columns by hand.
- HTML files are exempt from the 80-column rule.
- Vendored third-party files are exempt. JavaScript libraries cannot be
  tracked in `pyproject.toml`, so each vendored directory has a `VERSIONS.md`
  recording every file's name, version and source URL. Updating a vendored
  file is a task with its own branch.

## 4. Naming

- Python variable names are lowercase snake case (`tip_position`).
- Python constants are uppercase snake case (`MAX_DURATION_S`).
- Do not use single-letter variable names, except for loop counters. Use a
  descriptive name instead: prefer `features` over `f` or `X`.
- JSON and YAML keys are camel case (`formatVersion`). When Python reads a JSON
  or YAML file, it converts the keys to the equivalent snake case variable
  names (`format_version`). When Python writes a JSON or YAML file, it converts
  snake case variable names to the equivalent camel case keys. Only keys are
  converted; string values, such as `too_long`, may be snake case.

## 5. Documentation

### 5.1 Document types and locations

| Document | Purpose | Location |
|---|---|---|
| Architecture | System-wide components, flows, conventions | `docs/` |
| Data storage | How datasets are laid out on disk | `docs/` |
| Standards | These rules | `docs/` |
| Notes | Assumptions and constraints that need no action | `docs/` |
| Requirements | What a component must do | `<component>/docs/` |
| Design | How a component does it | `<component>/docs/` |
| Tasks | Work breakdown, status, links to requirements | `<component>/docs/` |

The shared library is a component and keeps its own design in `lib/docs/`.

### 5.2 Rules for all documents

Every document has an **Overview** section at the start. It states what the
document contains and what the reader will learn from it.

### 5.3 Rules for design documents

1. **Independent of source code.** Code is generated from the design, so the
   design describes the system rather than the code. Do not name files,
   modules, classes, functions or library calls. Interface specifications are
   allowed because they define behavior: file formats, configuration keys,
   HTTP endpoints, command-line commands and event names.
2. **Lucid.** A reader should understand what challenge the design faces and
   how the design addresses it, without being buried in words.
3. **No chain of thought.** State the decision and a brief reason. Do not
   narrate deliberation or walk through alternatives. A short
   decision-and-reason table is fine.
4. **Define before use.** Introduce each component and term, and its
   responsibility, before describing how components interact.
5. **Show the system flow.** Every design shows how the system works: the
   components involved, what each is responsible for, and how they interact.
6. **High level first.** When a system is complex, describe the components and
   their interactions at a high level before the detail of any one component.
   Split into architecture and design documents when that reads better.
7. **No open questions in finished documents.** Resolve them, turn them into
   tasks, or record them as notes in `docs/notes.md`. A document that cannot
   be finished yet lists what is missing in a final To Do section.

### 5.4 Writing style

Do not write sentences that comment on the text instead of stating something.
They are typical of AI-generated text and carry no information. Example of
what to avoid: "Three things make this hard, and the architecture is shaped by
them." Name the three things and say how each is handled.

Avoid in particular:

- sentences that announce or summarize structure ("The following sections
  describe...", "In summary...");
- sentences that claim importance or promise a payoff ("This is a key
  design decision", "This makes the system robust");
- filler transitions and framing ("It is worth noting that...").

State facts, behavior and reasons directly. If a sentence can be deleted
without losing information, delete it.

### 5.5 Formatting

Diagrams are plain-text blocks that fit in 80 columns. Tables must also fit,
so keep cell text short.
