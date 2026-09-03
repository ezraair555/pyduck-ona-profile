# Contributing to pyduck-ona-profile

Thank you for your interest in making the package better! This document covers
the development setup, the review → live release workflow, and the expectations
for pull requests.

## Table of contents

1. [Development setup](#development-setup)
2. [Running tests](#running-tests)
3. [Linting and formatting](#linting-and-formatting)
4. [Type checking](#type-checking)
5. [Pre-commit hooks](#pre-commit-hooks)
6. [The review → live workflow](#the-review--live-workflow)
7. [Release cadence](#release-cadence)
8. [Pull request expectations](#pull-request-expectations)
9. [Questions?](#questions)

---

## Development setup

Clone the repository and install the package in editable mode with development
dependencies:

```bash
git clone https://github.com/ezraair555/pyduck-ona-profile.git
cd pyduck-ona-profile
python -m pip install -e ".[dev]"
```

This installs `pytest`, `pytest-cov`, `ruff`, `black`, `isort`, `mypy`, and the
MkDocs documentation toolchain.

> **Note:** The first `import pyduck_ona_profile` will trigger a download of the
> `BAAI/bge-small-en-v1.5` sentence-transformer model (~130 MB). This is a
> one-time cost; subsequent imports are fully offline.

---

## Running tests

The full test suite enforces an 85% coverage gate:

```bash
python -m pytest --cov=pyduck_ona_profile --cov-report=term --cov-fail-under=85 tests/
```

To run tests without coverage:

```bash
python -m pytest tests/
```

The test suite uses a deterministic dummy model in place of the real
sentence-transformer, so tests run fast and require no network access.

---

## Linting and formatting

We use `ruff`, `black`, and `isort`. All three must pass before a PR can be
merged:

```bash
python -m ruff check src tests
python -m black --check src tests
python -m isort --check src tests
```

To auto-fix formatting issues:

```bash
python -m black src tests
python -m isort src tests
```

---

## Type checking

All public and internal functions must be fully type-annotated. Run mypy with:

```bash
python -m mypy src/pyduck_ona_profile
```

The `py.typed` marker is included in the package distribution, so downstream
type-checkers can rely on our annotations.

---

## Pre-commit hooks

Install the pre-commit hooks to catch issues before they are committed:

```bash
pre-commit install
pre-commit run --all-files
```

The configured hooks are: `ruff` (with `--fix`), `ruff-format`, `black`,
`isort`, and `mypy` (scoped to `src/`).

---

## The review → live workflow

This project uses a **two-clone review pattern** to keep review artifacts
isolated from the live repository. Here is how it works.

### Repositories and clones

| Clone | Location | Purpose |
|---|---|---|
| **Live repo** | `projects/pyduck-ona-profile` | The canonical GitHub repo (`ezraair555/pyduck-ona-profile`). Release commits land here. |
| **Review clone** | `projects/pyduck-ona-profile-review` | A separate local clone of the same remote. Used for code reviews and review artifacts. |

Both clones point at the same GitHub remote (`git@github.com:ezraair555/pyduck-ona-profile.git`).
The review clone is a working space where reviews run without polluting the live
repo's history or working tree.

### The review cycle

```
┌─────────────┐     ┌──────────────┐     ┌──────────────────┐
│  Live repo  │────▶│  Review clone │────▶│  Review artifacts │
│  (main)     │     │  (main +      │     │  REVIEW.md        │
│             │     │   grade       │     │  REVIEW_vX.Y.Z.md │
│             │     │   branches)   │     │  UPGRADE_REPORT.md│
└─────────────┘     └──────────────┘     └──────────────────┘
       ▲                                          │
       │          Fixes applied as new            │
       │          release commits on main         │
       └──────────────────────────────────────────┘
```

1. **Initial release.** The package is committed to `main` with a `release: vX.Y.0`
   tag commit. This is the baseline.

2. **Review.** A code review is conducted in the review clone. The reviewer
   (an AI subagent or human) clones the repo, runs all quality gates
   (tests, lint, type-check, coverage), and produces a `REVIEW.md` file
   with a letter grade and detailed findings.

3. **Grading.** The review assigns a grade on a 100-point rubric
   (Documentation, Testing, Code Review, Packaging, Examples). The
   target for publication-ready releases is **A (≥90/100)**.

4. **Grade branch.** If the initial release doesn't meet the A bar, a
   branch named `vX.Y.Z-grade-a` is created (e.g., `v0.1.1-grade-a`).
   Fixes are developed on this branch until all review findings are
   resolved and all gates pass.

5. **Hotfix releases.** If a subsequent regrade flags regressions
   (e.g., a mypy failure under a different environment), a hotfix
   patch release (e.g., `v0.1.2`) is committed directly to `main`.

6. **Artifacts stay in the review clone.** `REVIEW.md`, `REVIEW_vX.Y.Z.md`,
   and `UPGRADE_REPORT.md` live in the review clone only. They are
   deliberately excluded from the live repo via `.gitignore` entries
   for `.venv-review/` and `site/`. The review trail is preserved
   locally but does not clutter the public repository.

### When to use the -review clone

| Situation | Use -review clone? |
|---|---|
| Initial code review of a new release | ✅ Yes |
| Regrade after fixes | ✅ Yes |
| Verifying a hotfix doesn't regress | ✅ Yes |
| Routine development and feature work | ❌ No — work in the live repo |
| Emergency hotfix for a production bug | ❌ No — commit directly to `main` |

### Review artifact files

| File | Contents |
|---|---|
| `REVIEW.md` | The initial code review for v0.1.0 (or the current version). Includes grade, score breakdown, and all findings by category. |
| `REVIEW_vX.Y.Z.md` | A follow-up review for a specific version (e.g., `REVIEW_v0.1.1.md`). Documents what was fixed, what regressed, and the updated grade. |
| `UPGRADE_REPORT.md` | (When applicable) A detailed report of the work done to move from one grade to the next, including verification gates and test count progression. |

These files are committed to the review clone for auditability but are not
pushed to the live repo.

### Quality gates

Every release must pass all of these gates before the commit is finalized:

| Gate | Command | Bar |
|---|---|---|
| Tests | `pytest tests/` | All pass (skips must be documented) |
| Coverage | `pytest --cov=pyduck_ona_profile` | ≥ 85% line coverage |
| Lint | `ruff check src tests` | 0 errors |
| Format | `black --check src tests` | 0 changes needed |
| Import order | `isort --check src tests` | 0 changes needed |
| Types | `mypy src/pyduck_ona_profile` | 0 errors |
| CI | GitHub Actions, Python 3.10–3.12 | All matrix jobs green |

---

## Release cadence

### Versioning

This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html):

- **Patch** (`0.1.0 → 0.1.1`): Bug fixes, review findings resolved, no new
  public API.
- **Minor** (`0.1.x → 0.2.0`): New features, new public API surface, backward
  compatible.
- **Major** (`0.x → 1.0`): Breaking changes. Requires a migration guide.

While the major version is `0`, minor versions may include breaking changes
(per SemVer §4). Once `1.0` is reached, the full SemVer contract applies.

### Release commit convention

Release commits use the format:

```
release: vX.Y.Z — short description
```

The commit body lists the changes (fixes, additions, removals), references the
review artifact if applicable (`Refs: REVIEW_vX.Y.Z.md`), and notes the gate
results:

```
release: v0.1.1 — A-grade review fixes

Resolves all 7 issues from Kimi's review (B+ → A in progress).

Fixes:
- ask(): make con=None path functional...
- ask(): enforce slot type + bounds...

All gates green: ruff, black, isort, mypy, pytest with coverage.

Refs: REVIEW_v0.1.1.md
```

### Changelog

Every release adds an entry to `CHANGELOG.md` following the
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format. Each version
section includes `Added`, `Fixed`, `Changed`, and `Removed` subsections as
applicable.

### Branch strategy

- **`main`** — The release branch. Every commit on `main` is a release or a
  release-quality change. There is no long-running `develop` branch.
- **`vX.Y.Z-grade-a`** — Temporary branches for review-driven fixes. These are
  short-lived: they exist only until the fixes are merged into `main` as a new
  release commit. They may be pushed to `origin` for CI validation but are
  deleted after the release lands.
- **Feature branches** — For non-trivial work, use `feature/<description>`
  branches off `main`. Keep them short-lived.

### Typical release timeline

1. **Day 0:** Initial release committed to `main` (`release: vX.Y.0`).
2. **Day 0–1:** Code review conducted in the `-review` clone. `REVIEW.md`
   produced with grade and findings.
3. **Day 1–2:** If grade < A, fixes developed on `vX.Y.1-grade-a` branch.
   All gates re-run. Reviewer produces `REVIEW_vX.Y.1.md` with updated grade.
4. **Day 2:** Fixes merged to `main` as `release: vX.Y.1`. Changelog updated.
   Grade-a branch deleted.
5. **As needed:** Hotfix patches (`vX.Y.2`, `vX.Y.3`) for regressions or
   bugs found in production. Each gets a review in the `-review` clone if
   the change is non-trivial.

---

## Pull request expectations

- **One logical change per PR.** Don't bundle unrelated fixes.
- **Add tests** that exercise the new or changed behavior, including edge
  cases and error paths.
- **Update docstrings** to NumPy style and keep return types in sync with the
  implementation.
- **Update `CHANGELOG.md`** with a short note under the `[Unreleased]` or
  upcoming version section.
- **Make sure CI is green** before requesting review. All matrix jobs
  (Python 3.10, 3.11, 3.12) must pass.
- **Reference the review artifact** if the PR resolves review findings
  (`Refs: REVIEW_vX.Y.Z.md`).

---

## Questions?

Open a [discussion](https://github.com/ezraair555/pyduck-ona-profile/discussions)
or email the maintainer at [ezraair555@gmail.com](mailto:ezraair555@gmail.com).