"""Sentence-transformer pattern matcher.

The matcher pre-embeds a fixed catalog of ``QueryPattern`` examples. At query
time it embeds the user's question and finds the pattern whose centroid is
closest in cosine similarity. If similarity is below ``threshold`` it returns
``None`` so the caller can grow the catalog.

This is intentionally simple — a small catalog of 30-50 patterns does not
need approximate nearest neighbors, just a brute-force centroid comparison.
The whole match step takes ~5-20ms on CPU with all-MiniLM-L6-v2.
"""

from __future__ import annotations

import re
from typing import Any
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Match:
    """The result of matching a question to the pattern bank."""

    pattern_id: str
    similarity: float
    slots: dict[str, object]


@dataclass(frozen=True)
class QueryPattern:
    """A retrievable query template.

    Parameters
    ----------
    pattern_id:
        Stable identifier; used in logs and to add new examples later.
    examples:
        5-10 example phrasings. The matcher embeds each and uses their
        centroid for similarity comparison.
    slot_phrasings:
        Mapping from slot name to a small list of canonical phrasings the
        user might use, e.g. ``{"window_months": ["24 months", "2 years"]}``.
    compile:
        Callable that takes (schema, **slots) and returns DuckDB SQL.
        The schema is a SchemaRegistry so the SQL can reference the right
        table names.
    """

    pattern_id: str
    examples: Sequence[str]
    slot_phrasings: dict[str, Sequence[str]]
    # Use a string for the SQL template with {schema_table_X} placeholders so
    # we don't import duckdb at module import time. The ask() helper resolves
    # {schema_table_<concept>} into actual table names before compiling.
    sql_template: str


_SLOT_NUMERIC_PATTERN = re.compile(
    r"(\d+)\s*(months?|years?|yrs?|quarters?|q[1-4])",
    re.IGNORECASE,
)


def _parse_numeric_slot(text: str) -> int | None:
    """Parse phrasings like '24 months' / '2 years' / 'Q3' into a number."""
    text = text.strip().lower()
    m = _SLOT_NUMERIC_PATTERN.search(text)
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2).lower()
    if unit.startswith("year") or unit.startswith("yr"):
        return n * 12
    if unit.startswith("q"):
        return n * 3
    return n  # months


class PatternMatcher:
    """Embed pattern examples once, then match questions on demand.

    Parameters
    ----------
    patterns:
        All registered query patterns.
    model_name:
        Sentence-transformer model id. Defaults to ``BAAI/bge-small-en-v1.5``
        (130MB, strong English retrieval). Pass ``all-MiniLM-L6-v2`` (80MB,
        slightly lower quality) if disk is tight.
    threshold:
        Minimum cosine similarity for a match. Below this, ``match`` returns
        ``None`` so the caller can grow the catalog.
    """

    DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"

    def __init__(
        self,
        patterns: Sequence[QueryPattern],
        model_name: str = DEFAULT_MODEL,
        threshold: float = 0.45,
    ) -> None:
        self.patterns = list(patterns)
        self.threshold = threshold
        self._model_name = model_name
        self._model = None  # lazy-loaded
        self._centroids: dict[str, np.ndarray] = {}

    def _ensure_model(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model

    def build_index(self) -> None:
        """Pre-embed all pattern examples. Call once at startup."""
        model = self._ensure_model()
        self._centroids = {}
        for p in self.patterns:
            if not p.examples:
                continue
            embeddings = model.encode(
                list(p.examples), convert_to_numpy=True, show_progress_bar=False
            )
            centroid = embeddings.mean(axis=0)
            # Normalize so cosine similarity == dot product
            norm = float(np.linalg.norm(centroid))
            if norm > 0:
                centroid = centroid / norm
            self._centroids[p.pattern_id] = centroid

    def match(self, question: str) -> Match | None:
        """Return the best-matching pattern, or None if similarity is too low."""
        if not self._centroids:
            self.build_index()
        model = self._ensure_model()
        q_vec = model.encode(
            [question], convert_to_numpy=True, show_progress_bar=False
        )[0]
        norm = float(np.linalg.norm(q_vec))
        if norm > 0:
            q_vec = q_vec / norm

        best_id: str | None = None
        best_score = -1.0
        for pid, centroid in self._centroids.items():
            score = float(np.dot(q_vec, centroid))
            if score > best_score:
                best_score = score
                best_id = pid

        if best_id is None or best_score < self.threshold:
            return None

        pattern = next(p for p in self.patterns if p.pattern_id == best_id)
        slots = self._extract_slots(question, pattern)
        return Match(pattern_id=best_id, similarity=best_score, slots=slots)

    def _extract_slots(self, question: str, pattern: QueryPattern) -> dict[str, object]:
        """Find slot values in the question by matching against canonical phrasings."""
        q = question.lower()
        slots: dict[str, object] = {}
        for slot_name, phrasings in pattern.slot_phrasings.items():
            for ph in phrasings:
                if ph.lower() in q:
                    parsed = _parse_numeric_slot(ph)
                    if parsed is not None:
                        slots[slot_name] = parsed
                        break
        return slots


def add_example(matcher: PatternMatcher, pattern_id: str, example: str) -> None:
    """Add an example phrasing to an existing pattern and rebuild its centroid.

    This is the catalog-growth primitive: when an unmatched question arrives,
    you decide which existing pattern it should map to, then call this. The
    next match for a similar phrasing will be more accurate.

    Raises ``KeyError`` if ``pattern_id`` is not registered.
    """
    pattern = next((p for p in matcher.patterns if p.pattern_id == pattern_id), None)
    if pattern is None:
        raise KeyError(f"unknown pattern_id: {pattern_id}")
    new_examples = [*list(pattern.examples), example]
    object.__setattr__(pattern, "examples", tuple(new_examples))
    # Recompute that one centroid
    model = matcher._ensure_model()
    embeddings = model.encode(
        list(pattern.examples), convert_to_numpy=True, show_progress_bar=False
    )
    centroid = embeddings.mean(axis=0)
    norm = float(np.linalg.norm(centroid))
    if norm > 0:
        centroid = centroid / norm
    matcher._centroids[pattern_id] = centroid
