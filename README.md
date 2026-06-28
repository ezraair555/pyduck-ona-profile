# pyduck-ona-profile

Subject-centric, time-aware people analytics on top of [pyduck-ona](https://github.com/ezraair555/pyduck-ona).

This package adds four layers on top of the analytical core:

1. **Schema registry** — maps loaded `DuckONA` tables to concepts (identity, position, compensation, mobility, attendance, engagement, skills).
2. **Subject** — a per-employee view that joins every loaded table on `employee_id` and returns a typed record per concept, with PII redaction via `with_role()`.
3. **Timeline** — a per-employee event log derived from current-state tables via event detectors (`manager_change`, `comp_change`, `promotion`, `absence_streak`). Supports `as_of(date)` snapshots and `between(start, end)` windows.
4. **Query** — a sentence-transformer-based natural-language layer. Match a question against a pattern bank, extract slots via regex, compile to DuckDB SQL, execute. **No LLM required.**

## Why sentence transformers, not an LLM?

The query layer is fundamentally a **retrieval problem**, not a generation problem. You have a fixed catalog of ~30-50 HR question archetypes. Each one has a known SQL template. You don't need the model to write SQL — you need it to **match the user's question to the closest pattern**.

| | LLM (e.g. Kimi) | Sentence transformer (`BAAI/bge-small-en-v1.5`) |
|---|---|---|
| Latency | 500ms–2s per query | **5-20ms per query** |
| Cost | $0.0001–0.001 per query | **$0 — runs locally** |
| Determinism | Temperature-dependent | **Bit-identical embeddings** |
| Privacy | PII leaves the box | **Stays on disk** |
| For this task | Overkill | **Purpose-built** |

## Install

```bash
pip install pyduck-ona-profile[all]
```

The first run will download the `BAAI/bge-small-en-v1.5` model (~130MB). After that it's fully offline.

## Quickstart

```python
import pandas as pd
from pyduck_ona import DuckONA
from pyduck_ona_profile import Subject, Timeline, ask, attach

# Load your HR data (typically from a Vertica function returning DataFrames)
ona = DuckONA()
ona.load_hris(hris_df) \
   .load_compensation(comp_df) \
   .load_turnover(turnover_df) \
   .load_promotions(promo_df) \
   .load_skills(skills_df) \
   .load_attendance(attendance_df)

# 1. Per-employee view — joins every table on employee_id
alice = Subject("E0042", ona)
print(alice.profile().to_dict())
# {
#   "identity":     {"employee_id": "E0042", "name": "...", "department": "...",
#                    "level": "L4", "hire_date": "2020-03-04", ...},
#   "position":     {"manager_id": "E0011", "direct_reports": 7, ...},
#   "compensation": {"salary": 142000, "snapshot_date": "..."},
#   "mobility":     {"old_title": "...", "new_title": "...", "promotion_date": "..."},
#   ...
# }

# 2. PII gating
alice.with_role("hrbp")             # full view
alice.with_role("manager")          # hides compensation, engagement, tenure
alice.with_role("self")             # hides compensation, manager_id

# 3. Time travel — every event for one employee
tl = Timeline(alice)
tl.all()                            # every event, newest first
tl.manager_changes()                # only manager changes
tl.comp_history()                   # only compensation changes
tl.between("2024-01-01", "2024-12-31")
tl.as_of("2024-06-01")              # snapshot at a point in time

# 4. Natural-language queries (no LLM)
reg = attach(ona)
# Pass `data=` so the in-memory DuckDB connection knows about your tables.
# You can also pass a pre-built `con=` DuckDB connection instead.
data = {
    "hris": hris_df,
    "compensation": comp_df,
    "turnover": turnover_df,
    "manager_changes": manager_changes_df,   # if you've computed this
    "promotions": promotions_df,             # if you've computed this
}
result = ask(
    "employees with the most managers in the last 24 months",
    reg, data=data,
)
print(result.result)                # DataFrame (or None on error)
print(result.sql)                   # DuckDB SQL that produced it
print(result.matched_pattern)       # which pattern fired
print(result.similarity_score)      # 0.0–1.0 confidence
print(result.error)                 # if matched but query failed
```

## How the query layer works

```
   "who has had the most managers in 24 months?"
                    │
                    ▼
   ┌──────────────────────────────────┐
   │  sentence-transformer             │   ~5-20ms
   │  BAAI/bge-small-en-v1.5          │
   │  cosine similarity vs centroids   │
   └────────────────┬─────────────────┘
                    │ matches 0.92 → "mgr_change_frequency"
                    ▼
   ┌──────────────────────────────────┐
   │  PatternBank                     │
   │  10-15 seed patterns with SQL     │
   │  template + slot phrasings        │
   └────────────────┬─────────────────┘
                    │ compile(sql_template, **{window_months: 24})
                    ▼
   ┌──────────────────────────────────┐
   │  DuckDB SQL                      │
   │  ... INTERVAL '24 months' ...    │
   └──────────────────────────────────┘
```

When a question doesn't match any pattern, `ask()` returns `matched_pattern=None` and an error message. Use this as a signal to grow the catalog — add the question as an example to an existing pattern with `PatternMatcher.add_example`, or write a new `QueryPattern`.

## Architecture

```
src/pyduck_ona_profile/
├── __init__.py        # Subject, Timeline, ask public exports
├── schema.py          # SchemaRegistry: table → concept mapping
├── subject.py         # Subject class + profile() + with_role() (PII gating)
├── timeline.py        # Timeline + as_of / between / event queries
├── events.py          # ManagerChangeDetector, CompChangeDetector, ...
├── snapshots.py       # SCD2 helpers + at_timestamp()
└── query/
    ├── __init__.py
    ├── patterns.py    # 10-15 seed QueryPattern entries with SQL templates
    ├── matcher.py     # sentence-transformer PatternMatcher (~150 LOC)
    └── ask.py         # ask() entrypoint that ties it all together
```

## Companion packages

- [pyduck-ona](https://github.com/ezraair555/pyduck-ona) — DuckDB-native people analytics (the analytical core)
- [pyduck-ona-viz](https://github.com/ezraair555/pyduck-ona-viz) — publication-quality visualizations

## License

MIT
