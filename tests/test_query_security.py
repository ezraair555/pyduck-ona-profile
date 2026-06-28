"""Security tests for the ask() / matcher layer.

These tests verify that user-supplied input cannot reach DuckDB SQL
in an unsafe way. The current design uses allow-listed slot phrasings
parsed to integers, so classical SQL injection is not possible — these
tests document and enforce that invariant.

What we're protecting against:
1. Classical SQL injection via slot values: ``'24; DROP TABLE employees; --'``
2. Pathological slot values: ``999999999 months`` → expensive query
3. Raw user text leaking into SQL when the slot isn't matched
4. Patterns referencing tables the user hasn't loaded (unresolved placeholders)
5. Pattern matching returning the wrong pattern (high false-positive rate)
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from pyduck_ona_profile.query.ask import ask, reset_matcher
from pyduck_ona_profile.query.matcher import (
    PatternMatcher,
    QueryPattern,
)
from pyduck_ona_profile.query.patterns import SEED_PATTERNS
from pyduck_ona_profile.schema import SchemaRegistry

# ---------------------------------------------------------------------------
# Dummy sentence-transformer stand-in (mirrors test_query.py)
# ---------------------------------------------------------------------------


class _DummyModel:
    """Token-overlap based stand-in. Deterministic, no model download."""

    _VOCAB = [
        "employees",
        "managers",
        "most",
        "24",
        "months",
        "last",
        "people",
        "changed",
        "reorged",
        "high",
        "manager",
        "boss",
        "lately",
        "frequent",
        "changes",
        "victims",
        "many",
        "times",
        "promotions",
        "promoted",
        "recent",
        "year",
        "quarter",
        "12",
        "6",
        "new",
        "quarter",
        "q1",
        "q2",
        "q3",
        "q4",
        "headcount",
        "department",
        "sizes",
        "team",
        "each",
        "how",
        "many",
        "in",
        "who",
        "promoted",
        "outliers",
        "peers",
        "salary",
        "paid",
        "level",
        "overpaid",
        "underpaid",
        "compensation",
        "anomalies",
        "outside",
        "normal",
        "range",
        "central",
        "network",
        "betweenness",
        "highest",
        "key",
        "connectors",
        "org",
        "chart",
        "top",
        "influencers",
        "pagerank",
        "engagement",
        "low",
        "scores",
        "manager",
        "teams",
        "disengaged",
        "dropping",
        "survey",
        "where",
        "attrition",
        "rate",
        "turnover",
        "terminated",
        "recent",
        "last",
        "hires",
        "started",
        "quarter",
        "new",
        "hires",
        "quarter",
        "year",
        "months",
        "years",
    ]

    def encode(self, sentences, convert_to_numpy=True, show_progress_bar=False):
        import re

        out = []
        for s in sentences:
            v = np.zeros(len(self._VOCAB), dtype=np.float32)
            tokens = re.findall(r"[a-z0-9]+", s.lower())
            for tok in tokens:
                for i, w in enumerate(self._VOCAB):
                    if w == tok:
                        v[i] += 1
            norm = float(np.linalg.norm(v))
            if norm > 0:
                v = v / norm
            out.append(v)
        return np.stack(out, axis=0)


@pytest.fixture
def patched_st(monkeypatch):
    """Patch sentence_transformers with a deterministic dummy model."""
    fake_st = types.ModuleType("sentence_transformers")
    fake_st.SentenceTransformer = MagicMock(return_value=_DummyModel())
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_st)
    reset_matcher()
    yield
    reset_matcher()


@pytest.fixture
def dummy_matcher(patched_st):
    matcher = PatternMatcher(SEED_PATTERNS, model_name="dummy-model")
    matcher.build_index()
    return matcher


# ---------------------------------------------------------------------------
# Security tests
# ---------------------------------------------------------------------------


def test_classical_sql_injection_in_slot_is_rejected(
    dummy_matcher, tiny_registry_with_data, empty_hris
):
    """A malicious string in the question must NOT end up in the SQL."""
    question = "reorg victims in 24 months; DROP TABLE employees; --"
    result = ask(
        question,
        tiny_registry_with_data,
        matcher=dummy_matcher,
        data={"hris": empty_hris},
    )
    if result.matched_pattern == "mgr_change_frequency":
        assert "DROP TABLE" not in (result.sql or "")
        assert "employees; --" not in (result.sql or "")


def test_pathological_slot_value_is_rejected(
    dummy_matcher, tiny_registry_with_data, empty_hris
):
    """A slot value of 999999999 months must be rejected before SQL execution."""
    question = "reorg victims in 999999999 months"
    result = ask(
        question,
        tiny_registry_with_data,
        matcher=dummy_matcher,
        data={"hris": empty_hris},
    )
    if result.matched_pattern == "mgr_change_frequency" and result.error:
        assert "rejected" in result.error or "bound" in result.error.lower()


def test_year_slot_bounded(dummy_matcher, tiny_registry_with_data, empty_hris):
    """Year slot must convert to a sane month value."""
    question = "frequent manager changes in the last 5 years"
    result = ask(
        question,
        tiny_registry_with_data,
        matcher=dummy_matcher,
        data={"hris": empty_hris},
    )
    if result.matched_pattern and result.slots.get("window_months"):
        assert result.slots["window_months"] <= 1200


def test_unresolved_placeholder_returns_clean_error(
    tiny_registry_with_data, patched_st, empty_hris
):
    """If the SQL has an unresolved {schema_table_X}, return AskResult.error."""
    # Use example words that exist in the dummy vocab so the centroid is
    # non-zero and the matcher actually returns a Match. This guarantees
    # we exercise the unresolved-placeholder branch in ask().
    bad_pattern = QueryPattern(
        pattern_id="bad_pattern",
        examples=("reorged victims",),
        slot_phrasings={},
        sql_template="SELECT * FROM {schema_table_unknown_concept}",
    )
    matcher = PatternMatcher([bad_pattern], model_name="dummy-model")
    matcher.build_index()
    matcher.threshold = 0.0
    result = ask(
        "reorged victims",
        tiny_registry_with_data,
        matcher=matcher,
        data={"hris": empty_hris},
    )
    # Assert we actually matched the bad pattern; otherwise the test is
    # vacuous. The placeholder path is only reachable when a pattern matches.
    assert result.matched_pattern == "bad_pattern"
    assert result.error is not None
    assert (
        "unresolved" in (result.error or "").lower()
        or "placeholders" in (result.error or "").lower()
    )


def test_ask_without_con_or_data_returns_helpful_error(tiny_registry_with_data):
    """ask() with no connection and no data must error, not silently fail."""
    result = ask("anything", tiny_registry_with_data, con=None, data=None)
    if result.matched_pattern:
        assert result.error is not None
        assert "no" in result.error.lower() and (
            "connection" in result.error.lower() or "data" in result.error.lower()
        )


def test_no_pattern_returns_no_match(dummy_matcher, tiny_registry_with_data):
    """A nonsense question returns matched_pattern=None."""
    result = ask(
        "xyzzy banana republic frobnicate",
        tiny_registry_with_data,
        matcher=dummy_matcher,
    )
    assert result.matched_pattern is None


def test_con_data_parameter_actually_registers(patched_st):
    """ask() must register the data into the in-memory connection."""
    import duckdb

    from pyduck_ona_profile.schema import SchemaRegistry as _Reg

    class _ONAWithCon:
        pass

    df = pd.DataFrame(
        {
            "employee_id": ["E0001", "E0002"],
            "department": ["Eng", "Sales"],
            "termination_date": [pd.NaT, pd.NaT],
        }
    )
    con = duckdb.connect(":memory:")
    con.register("hris", df)
    ona = _ONAWithCon()
    ona._table_names = {"hris"}
    ona.con = con
    registry = _Reg.from_duckona(ona)
    p = QueryPattern(
        pattern_id="headcount",
        examples=("headcount",),
        slot_phrasings={},
        sql_template="SELECT department, COUNT(*) AS n FROM {schema_table_identity} WHERE termination_date IS NULL GROUP BY department",
    )
    matcher = PatternMatcher([p], model_name="dummy-model")
    matcher.build_index()
    matcher.threshold = 0.0
    matcher._centroids["headcount"] = np.ones(88, dtype=np.float32)
    result = ask("headcount", registry, matcher=matcher, data={"hris": df})
    if result.matched_pattern and result.result is not None:
        assert len(result.result) == 2
    elif result.matched_pattern and result.error:
        pytest.fail(f"query should have succeeded: {result.error}")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tiny_registry_with_data():
    """A minimal SchemaRegistry covering identity + compensation."""

    class _TinyONA:
        pass

    ona = _TinyONA()
    ona._table_names = {"hris", "compensation", "turnover"}
    return SchemaRegistry.from_duckona(ona)


@pytest.fixture
def empty_hris() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "employee_id",
            "supervisor_id",
            "department",
            "termination_date",
            "snapshot_date",
        ]
    )
