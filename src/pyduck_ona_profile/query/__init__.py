"""Query layer: pattern bank + sentence-transformer matcher.

The ``ask()`` entrypoint lives in ``pyduck_ona_profile.query.ask``. It uses
the sentence-transformer-based PatternMatcher to find the closest registered
QueryPattern to a natural-language question, extracts slot values via simple
regex, and compiles the pattern + slots into DuckDB SQL.

Why not an LLM? See the README section "Why sentence transformers, not an
LLM". TL;DR: deterministic, local, fast, and you don't need generation —
you need retrieval against a fixed pattern catalog.
"""
