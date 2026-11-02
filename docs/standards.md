# Standards

> **Version** 2 | **Updated** 2026-11-01 | **Approved**

## Overview

This document defines how work is done in every component of the repository:
what a task looks like, how branches and commits are named, what makes a task
done, the Python tooling, code and text formatting, naming, and the rules for
writing documentation. After reading it you will know what is required of any
change and of any document. The root `CLAUDE.md` points here; this file is the
single source for the rules.

## 1. Workflow

### 1.1 Tasks

Work is organized as tasks in the component's `tasks.md`. A task has:

- an **ID** and a **title**. The ID is a letter for the task's group followed
  by a number: `D` documentation, `F` foundation, `S` spike, `L` library, `A`
  application, `U` Web UI, `V` verification. IDs are unique within the file.
- a **Type**: the conventional commit type of the work (section 1.3), such as
  `feat`, `fix`, `docs`, `refactor`, `test`, `build` or `chore`. It names the
  branch (section 1.2).
- a **Status**: `Not started`, `In progress` or `Completed`.
- **Depends on**: the tasks that must be complete first.
- **Requirements** and **Design**: the requirement IDs it implements and the
  design sections that define it.
- a **Description**: what to build and how it behaves, written so that someone
  who has not seen the rest of the project can build it, with references for
  exact definitions.
- **Acceptance criteria**: a checklist. Each item can be verified by a test or
  an inspection.
- **Implementation notes**: suggestions on structure, libraries and pitfalls.
  The description and the acceptance criteria are binding; the notes are not.

A task is sized to fit one branch.

**A task must be written with enough information for an independent agent to
implement it successfully.** The agent has only the task and the documents the
task references. It must not have to ask questions or guess, so the task states
the behavior to build, the names and shapes of what it exchanges with other
parts, how each acceptance criterion is checked, and which documents define the
rest. A task that leaves such a gap is incomplete and is fixed before work
starts.

### 1.2 Branches

- All development takes place in a branch, with one branch per task. Never
  commit directly to `main`.
- A branch is named `<type>/<task id>-<short name>`. The type is the task's
  type, the id is lowercase, and the short name is the task title in lowercase
  words joined by hyphens. Task L2, "Tracker", of type `feat` gives
  `feat/l2-tracker`. Task F1, "Workspace and tooling", of type `chore` gives
  `chore/f1-workspace-and-tooling`.
- Work that is not a task, such as a change to a document, uses
  `<type>/<short name>`, for example `docs/glossary`.
- Create the branch from an up-to-date `main`.
- After review, merge the branch into `main` with a merge commit, so the branch
  stays visible in the history.

### 1.3 Commits

Commit messages follow Conventional Commits
(https://www.conventionalcommits.org):

```text
<type>(<scope>): <summary>

<body>

<footer>
```

- **Type**: `feat` (new behavior), `fix` (a bug fix), `docs`, `refactor`,
  `perf`, `test`, `build` (dependencies and tooling), `chore` (anything else
  that changes no behavior) or `revert`.
- **Scope** (optional): the lowercase ID of the task being worked on, for
  example `feat(l2): handle hues that wrap around`.
- **Summary**: imperative mood ("add", not "added"), no trailing period, at
  most 72 characters.
- **Body** (optional): what changed and why, wrapped at 80 columns.
- **Footer** (optional): a breaking change is marked with `!` after the type
  (or scope) and described in a `BREAKING CHANGE:` footer.
- Make each commit one small, logical change, and leave the tests passing.

### 1.4 Definition of done

A task is complete only when:

- `uv run ruff format` and `uv run ruff check` report nothing to fix;
- the task's tests pass with `uv run pytest`, and they need no camera;
- every new dependency is declared in the relevant `pyproject.toml`, and
  `uv.lock` is up to date;
- lines in code and text are within 80 columns, and names follow section 4;
- the behavior matches the approved design. A needed change to an approved
  document is made on a branch of its own first and reviewed;
- every acceptance criterion of the task is met;
- the branch has been reviewed and merged into `main`.

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
| Data handling | Dataset rules, layout, formats, operations | `docs/` |
| Standards | These rules | `docs/` |
| Glossary | Terms shared across documents | `docs/` |
| Notes | Assumptions and constraints that need no action | `docs/` |
| Requirements | What a component must do | `<component>/docs/` |
| Design | How a component does it | `<component>/docs/` |
| Tasks | Work breakdown in the format of section 1.1 | `<component>/docs/` |

The shared library is a component and keeps its own design in `lib/docs/`.

### 5.2 Rules for all documents

Every document starts, after its title, with a one-line header in this
format. The blockquote and bold make it render as a distinct header block:

```text
> **Version** 1 | **Updated** 2026-11-01 | **Draft**
```

- **Version**: a whole number, starting at 1. Increase it when the document is
  revised after a review.
- **Updated**: the date of the latest change, as `YYYY-MM-DD`. Change it
  whenever the document changes.
- **Status**: `Draft` or `Approved`, shown last.

Next comes an **Overview** section. It states what the document contains and
what the reader will learn from it.

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
