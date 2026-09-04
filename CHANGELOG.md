# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Fixed
- The documented manager-change natural-language query now consumes the
  event detector's actual `event_type`, `event_date`, and `after_value`
  columns.
- `ask(data=...)` now registers literal auxiliary tables referenced by query
  patterns, including `manager_changes` and `centrality_scores`.

## [0.1.3] - 2026-09-03

### Added
- **Ecosystem alignment with the flagship.** README "Companion packages"
  section restructured into a proper ecosystem section reflecting the
  current package family: `pyduck-ona` (flagship — analysis + the
  integrated `pyduck_ona.viz` subpackage), `pyduck-janitor` (cleaning),
  and `broom-sm` (stats). The standalone `pyduck-ona-viz` package is
  deprecated (frozen at v0.1.1) and replaced by the flagship's built-in
  `pyduck_ona.viz`.
- Committed previously untracked files: `CONTRIBUTING.md` and
  `tests/property_schema_heuristics.py` (18 Hypothesis property tests,
  now green).

### Changed
- Dependency floor raised: `pyduck-ona>=0.3.0` (tested against flagship
  0.3.0 with the integrated viz subpackage: 55 passed, 1 skipped).
- PyPI build/twine checks pass for sdist + wheel.

### Fixed
- Package-data glob referenced a non-existent `query/patterns/*.yaml`
  (patterns live in `query/patterns.py`); corrected to `py.typed` only.
- Classifier typo (`Typired :: Typed` → `Typing :: Typed`) and removed
  the Python 3.13 classifier (not currently tested in CI).

### Fixed
- CHANGELOG gap: the v0.1.2 hotfix (defensive type annotations in
  `matcher.py` for ndarray and the lazy-loaded SentenceTransformer slot;
  mypy strict clean on supported numpy/mypy combinations) had no
  changelog entry — documented here for completeness.

## [0.1.2] - 2026-06-27

### Fixed
- `matcher.py`: defensive type annotations for ndarray and the
  lazy-loaded SentenceTransformer slot. mypy strict passes on all
  supported numpy/mypy combinations (previously only on the dev
  machine's versions).

## [0.1.1] - 2026-06-27

### Fixed
- **`ask()` with `con=None` is now functional.** Pass `data={table_name: df, ...}`
  and an in-memory DuckDB connection is created with the supplied DataFrames
  registered. Previously the registration loop body was empty, so the README
  quickstart did not work.
- **Slot substitution now enforces type + bounds.** Numeric slots are
  required to be in `[1, 1200]`. Pathological values like `999999999 months`
  are rejected with a clear `AskResult.error` instead of producing an
  expensive DuckDB query.
- **Unresolved SQL placeholders** (e.g. `{schema_table_mobility}` when the
  promotions table isn't loaded) now return `AskResult.error` with a clear
  message instead of a DuckDB parse error.
- **`isort` config is now valid for isort 8.x.** Removed `multi_line_single`
  and `single_line_exclusions`, which were removed in isort 8 and caused
  `isort --check` to crash.

### Added
- `Subject.with_role("executive")` redaction coverage (was already in
  `REDACTION_BY_ROLE` but untested).
- `tests/test_query_security.py` — 7 adversarial tests covering SQL
  injection via slot values, pathological slot bounds, unresolved
  placeholders, missing-pattern behavior, and the `data=` registration path.
- `examples/full_demo.py` now builds auxiliary tables (`manager_changes`,
  `promotions`, `centrality_scores`) and passes them via `data=` so every
  `ask()` call returns a real DataFrame.
- MkDocs nav now references the changelog page; api pages have full
  mkdocstrings handler config.

### Changed
- Bumped to 0.1.1.
- Added Python 3.13 to classifiers.

## [0.1.0] - 2026-06-27

### Added
- Initial release.
- `Subject` class with `profile()` and `with_role()` for PII-gated per-employee views.
- `Timeline` class with event detection (manager changes, comp changes, promotions) and `as_of()` / `between()` queries.
- `SchemaRegistry` for mapping loaded DuckONA tables to concepts (identity, compensation, mobility, attendance, engagement, skills).
- Sentence-transformer pattern matcher (`BAAI/bge-small-en-v1.5`) with 10-15 seed HR question patterns.
- `ask()` entrypoint that translates natural-language HR questions to DuckDB SQL.
- Event detectors: `detect_manager_changes`, `detect_comp_changes`, `detect_promotions`, `detect_absence_streaks`.
- Synthetic 30-employee test fixture.
- Full test suite (schema, subject, timeline, events, query layers).
- CI matrix on Python 3.10-3.12 with ruff, black, isort, mypy, pytest.
- MkDocs documentation site.
