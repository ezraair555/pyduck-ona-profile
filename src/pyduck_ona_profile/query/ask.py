"""``ask()`` — the natural-language query entrypoint.

Translates a question into a DuckDB SQL query by:
1. Matching against the registered pattern bank via sentence-transformer.
2. Extracting slot values (time windows, etc.) via regex.
3. Resolving {schema_table_<concept>} placeholders against the schema registry.
4. Compiling and executing the SQL.

If no pattern matches, returns a "no_match" result so the caller can grow
the catalog by adding the question as an example to an existing pattern.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from pyduck_ona_profile.query.matcher import PatternMatcher
from pyduck_ona_profile.query.patterns import SEED_PATTERNS
from pyduck_ona_profile.schema import SchemaRegistry


@dataclass
class AskResult:
    """The outcome of an ``ask()`` call."""

    question: str
    matched_pattern: str | None
    similarity_score: float
    slots: dict[str, Any]
    sql: str | None
    result: pd.DataFrame | None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "matched_pattern": self.matched_pattern,
            "similarity_score": self.similarity_score,
            "slots": self.slots,
            "sql": self.sql,
            "result": self.result,
            "error": self.error,
        }


# Module-level matcher; lazily initialized on first ask() call.
_MATCHER: PatternMatcher | None = None


def get_matcher(model_name: str = PatternMatcher.DEFAULT_MODEL) -> PatternMatcher:
    """Return the process-wide pattern matcher, building the index if needed."""
    global _MATCHER
    if _MATCHER is None:
        _MATCHER = PatternMatcher(SEED_PATTERNS, model_name=model_name)
        _MATCHER.build_index()
    return _MATCHER


def reset_matcher() -> None:
    """Clear the module-level matcher (used by tests and after pattern edits)."""
    global _MATCHER
    _MATCHER = None


def _resolve_table_placeholders(template: str, registry: SchemaRegistry) -> str:
    """Replace {schema_table_<concept>} with the actual table name from the registry."""
    out = template
    for concept in registry.concepts():
        binding = registry.table_for(concept)
        if binding is None:
            continue
        placeholder = "{schema_table_" + concept + "}"
        out = out.replace(placeholder, binding.table)
    return out


def _looks_like_relevant_table(name: str, registry: SchemaRegistry) -> bool:
    """Heuristic: is this table name likely referenced by a pattern?

    Some patterns reference tables that the schema registry doesn't bind
    (e.g., ``centrality_scores``, ``manager_changes``). We accept any
    table whose name appears in the registered pattern SQL templates so
    the user can supply these auxiliary tables via ``data=``.
    """
    from pyduck_ona_profile.query.patterns import SEED_PATTERNS

    relevant = set()
    for p in SEED_PATTERNS:
        # Pull out {schema_table_X} placeholders
        i = 0
        while True:
            j = p.sql_template.find("{schema_table_", i)
            if j < 0:
                break
            k = p.sql_template.find("}", j)
            if k < 0:
                break
            concept = p.sql_template[j + len("{schema_table_") : k]
            binding = registry.table_for(concept)
            if binding is not None:
                relevant.add(binding.table)
            i = k + 1
    # Also accept names that match concept names directly (e.g. "centrality_scores")
    return name in relevant or name in {b.table for b in registry.bindings}


def ask(
    question: str,
    registry: SchemaRegistry,
    *,
    matcher: PatternMatcher | None = None,
    con: Any | None = None,
    data: dict[str, Any] | None = None,
    threshold: float = 0.45,
) -> AskResult:
    """Run a natural-language HR question against the loaded data.

    Parameters
    ----------
    question:
        The user's natural-language question.
    registry:
        A ``SchemaRegistry`` produced via ``attach(ona)``.
    matcher:
        Optional pre-built matcher (used by tests). If omitted, uses the
        process-wide matcher initialized lazily.
    con:
        Optional DuckDB connection. If omitted, an in-memory connection is
        used. The connection is populated from ``data`` (see below) and the
        registry's table names.
    data:
        Optional dict mapping table names to pandas DataFrames (or anything
        DuckDB can register via ``con.register(name, obj)``). Required if
        ``con`` is not provided. Each key must match a table name known to
        the registry. Extra keys are ignored.
    threshold:
        Minimum similarity for a match. Below this, returns matched_pattern=None
        so the caller can grow the catalog.
    """
    m = matcher or get_matcher()
    if threshold != m.threshold:
        m.threshold = threshold

    match = m.match(question)
    if match is None:
        return AskResult(
            question=question,
            matched_pattern=None,
            similarity_score=0.0,
            slots={},
            sql=None,
            result=None,
            error="no pattern matched; add this question as an example to grow the catalog",
        )

    pattern = next(p for p in m.patterns if p.pattern_id == match.pattern_id)
    sql = _resolve_table_placeholders(pattern.sql_template, registry)

    # Validate slot substitution: only allow integer types within a sane
    # range, and only substitute placeholders that are known to the
    # matched pattern. This is the second line of defense against SQL
    # injection: even if a future pattern author adds a non-numeric slot,
    # we refuse to substitute a non-int here.
    max_slot_int = 1200  # upper bound on window-style slots (months/quarters/etc.)

    for slot_name, slot_value in match.slots.items():
        placeholder = "{" + slot_name + "}"
        if placeholder not in sql:
            continue
        if not isinstance(slot_value, int) or not (1 <= slot_value <= max_slot_int):
            return AskResult(
                question=question,
                matched_pattern=match.pattern_id,
                similarity_score=match.similarity,
                slots=match.slots,
                sql=None,
                result=None,
                error=(
                    f"slot {slot_name!r} value {slot_value!r} rejected: "
                    f"must be int in [1, {max_slot_int}]"
                ),
            )
        sql = sql.replace(placeholder, str(slot_value))

    # Provide defaults for slots the user didn't specify
    for slot_name in pattern.slot_phrasings:
        placeholder = "{" + slot_name + "}"
        if placeholder in sql and slot_name not in match.slots:
            # Default to 12 (months). Safe: int in valid range.
            sql = sql.replace(placeholder, "12")

    # Catch any unresolved {schema_table_X} or other placeholders BEFORE
    # handing SQL to DuckDB. Return a clean error instead of a parse error.
    import re

    leftover = re.findall(r"\{[a-z_]+\}", sql)
    if leftover:
        return AskResult(
            question=question,
            matched_pattern=match.pattern_id,
            similarity_score=match.similarity,
            slots=match.slots,
            sql=sql,
            result=None,
            error=(
                f"unresolved placeholders in SQL: {leftover}. "
                f"Load the corresponding tables or add them to `data=`."
            ),
        )

    try:
        if con is None:
            if not data:
                return AskResult(
                    question=question,
                    matched_pattern=match.pattern_id,
                    similarity_score=match.similarity,
                    slots=match.slots,
                    sql=sql,
                    result=None,
                    error=(
                        "no DuckDB connection provided and no `data` dict "
                        "supplied; pass either `con=` or `data=`"
                    ),
                )
            import duckdb

            con = duckdb.connect(":memory:")
            # Register every table in `data` whose name matches a known
            # registry binding. Unknown tables are registered too — users
            # may legitimately have extra context tables.
            known_tables = {b.table for b in registry.bindings}
            for name, frame in data.items():
                if name in known_tables or _looks_like_relevant_table(name, registry):
                    try:
                        con.register(name, frame)
                    except Exception as e:
                        # Register failures are non-fatal — the query may
                        # still work without the optional table.
                        import logging

                        logging.getLogger("pyduck_ona_profile").debug(
                            "could not register %s: %s", name, e
                        )
        result_df = con.execute(sql).fetch_df()
    except Exception as e:
        return AskResult(
            question=question,
            matched_pattern=match.pattern_id,
            similarity_score=match.similarity,
            slots=match.slots,
            sql=sql,
            result=None,
            error=f"{type(e).__name__}: {e}",
        )

    return AskResult(
        question=question,
        matched_pattern=match.pattern_id,
        similarity_score=match.similarity,
        slots=match.slots,
        sql=sql,
        result=result_df,
    )
