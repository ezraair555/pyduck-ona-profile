# pyduck-ona-profile

Subject-centric, time-aware people analytics on top of [pyduck-ona](https://github.com/ezraair555/pyduck-ona).

## Quick links

- [API reference](api/index.md)
- [GitHub repository](https://github.com/ezraair555/pyduck-ona-profile)
- [Companion package: pyduck-ona](https://github.com/ezraair555/pyduck-ona)

## What this package adds

`pyduck-ona` provides the analytical core: DuckDB-native relational API, recursive CTEs for hierarchy queries, ONA centrality metrics, statistical model integration (broom). This package sits on top and adds:

1. **Subject view** — point at an `employee_id`, get a typed record per concept.
2. **Timeline** — derive an event log from current-state tables; time-travel with `as_of()` and `between()`.
3. **Schema registry** — automatic mapping of loaded tables to concepts.
4. **Natural-language queries** — sentence-transformer pattern matcher, no LLM required.

## Quickstart

```python
from pyduck_ona import DuckONA
from pyduck_ona_profile import Subject, Timeline, ask, attach

ona = DuckONA()
ona.load_hris(hris_df).load_compensation(comp_df).load_turnover(turnover_df)

alice = Subject("E0042", ona)
print(alice.profile().to_dict())

tl = Timeline(alice)
print(tl.manager_changes())
print(tl.as_of("2024-06-01"))

reg = attach(ona)
result = ask("employees with the most managers in the last 24 months", reg)
print(result.result)
```
