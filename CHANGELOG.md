# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
