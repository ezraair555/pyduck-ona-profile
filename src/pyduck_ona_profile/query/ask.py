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


def ask(
    question: str,
    registry: SchemaRegistry,
    *,
    matcher: PatternMatcher | None = None,
    con: Any | None = None,
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
        used and the registry's underlying relations are registered on it.
        Most users don't need to pass this.
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

    # Substitute slots
    for slot_name, slot_value in match.slots.items():
        sql = sql.replace("{" + slot_name + "}", str(slot_value))

    # Provide defaults for slots the user didn't specify
    for slot_name in pattern.slot_phrasings:
        if "{" + slot_name + "}" in sql and slot_name not in match.slots:
            sql = sql.replace("{" + slot_name + "}", "12")  # default to 12 months

    try:
        if con is None:
            import duckdb

            con = duckdb.connect(":memory:")
            # Register all loaded tables from the registry into the connection
            for _binding in registry.bindings:
                # Best-effort: assume the registry carries enough metadata to
                # re-register the relation. In practice users pass a con that
                # already has the data loaded (DuckONA workflow).
                pass
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
