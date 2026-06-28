"""pyduck_ona_profile: subject-centric, time-aware people analytics.

Companion to ``pyduck-ona``. Adds three layers on top of the analytical core:

1. **Schema registry** — maps loaded DuckONA tables to concepts (identity,
   position, compensation, mobility, attendance, engagement, skills).
2. **Subject** — a per-employee view that joins every loaded table on
   ``employee_id`` and returns a typed record per concept, with PII
   redaction via ``with_role()``.
3. **Timeline** — a per-employee event log derived from current-state
   tables via event detectors (``manager_change``, ``comp_change``,
   ``promotion``, ``absence_streak``). Supports ``as_of(date)`` snapshots
   and ``between(start, end)`` windows.
4. **Query** — a sentence-transformer-based natural-language layer. Match
   a question against a pattern bank, extract slots via regex, compile
   to DuckDB SQL, execute. No LLM required.

Quickstart::

    from pyduck_ona import DuckONA
    from pyduck_ona_profile import Subject, Timeline, ask, attach

    ona = DuckONA()
    ona.load_hris(hris_df).load_compensation(comp_df).load_turnover(turnover_df)

    # Per-employee view
    alice = Subject("E0042", ona)
    print(alice.profile().to_dict())

    # Time travel
    tl = Timeline(alice)
    print(tl.manager_changes())
    print(tl.as_of("2024-06-01"))

    # Natural-language queries (no LLM)
    reg = attach(ona)
    result = ask("employees with the most managers in the last 24 months", reg)
    print(result.result)
"""

from pyduck_ona_profile.query.ask import AskResult, ask, get_matcher, reset_matcher
from pyduck_ona_profile.schema import (
    ConceptBinding,
    SchemaRegistry,
    attach,
    normalize_field,
)
from pyduck_ona_profile.subject import Profile, Subject
from pyduck_ona_profile.timeline import Timeline

__version__ = "0.1.0"

__all__ = [
    "AskResult",
    "ConceptBinding",
    "Profile",
    "SchemaRegistry",
    "Subject",
    "Timeline",
    "__version__",
    "ask",
    "attach",
    "get_matcher",
    "normalize_field",
    "reset_matcher",
]
