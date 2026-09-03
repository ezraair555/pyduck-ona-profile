"""
Property-based tests for pyduck-ona-profile _TABLE_HEURISTICS.

Uses Hypothesis to verify:
1. Every table name in _TABLE_HEURISTICS maps to a valid, non-empty concept.
2. The heuristic mapping is total — no table name maps to None or empty string.
3. Every concept value is a recognized people-analytics concept.
4. Adding new table→concept pairs preserves consistency.
5. SchemaRegistry.from_duckona correctly applies heuristics for all known tables.

Run:  pytest tests/property_schema_heuristics.py -v
"""

from __future__ import annotations

import re
import string
from types import SimpleNamespace
from unittest.mock import MagicMock

import duckdb
import pandas as pd
import pytest
from hypothesis import given, settings, strategies as st

from pyduck_ona_profile.schema import (
    ConceptBinding,
    SchemaRegistry,
    _TABLE_HEURISTICS,
    normalize_field,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# The set of valid people-analytics concepts that _TABLE_HEURISTICS may use.
# This is derived from the module's own documentation and existing values.
VALID_CONCEPTS = frozenset({
    "identity",
    "compensation",
    "turnover",
    "mobility",
    "retirement",
    "skills",
    "attendance",
    "engagement",
})


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy for valid concept strings
concept_strategy = st.sampled_from(sorted(VALID_CONCEPTS))

# Strategy for plausible table names (lowercase, alphanumeric + underscore)
table_name_strategy = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789_",
    min_size=1,
    max_size=30,
).filter(lambda s: not s.startswith("_") and not s.endswith("_") and s != "_")

# Strategy for table names from the existing heuristics
known_table_strategy = st.sampled_from(sorted(_TABLE_HEURISTICS.keys()))


# ---------------------------------------------------------------------------
# Property 1: Every existing heuristic maps to a valid concept
# ---------------------------------------------------------------------------

class TestHeuristicMappingsValid:
    """Every table→concept in _TABLE_HEURISTICS is valid."""

    def test_all_table_names_map_to_nonempty_concept(self):
        """No table name maps to None or empty string."""
        for table, concept in _TABLE_HEURISTICS.items():
            assert concept is not None, f"Table '{table}' maps to None"
            assert isinstance(concept, str), f"Table '{table}' maps to non-string"
            assert concept != "", f"Table '{table}' maps to empty string"
            assert concept.strip() == concept, f"Table '{table}' concept has whitespace"

    def test_all_concepts_are_recognized(self):
        """Every concept in _TABLE_HEURISTICS is in the recognized set."""
        for table, concept in _TABLE_HEURISTICS.items():
            assert concept in VALID_CONCEPTS, (
                f"Table '{table}' maps to unknown concept '{concept}'. "
                f"Valid concepts: {sorted(VALID_CONCEPTS)}"
            )

    def test_no_duplicate_table_names(self):
        """Keys in _TABLE_HEURISTICS are unique (dicts guarantee this, but verify)."""
        tables = list(_TABLE_HEURISTICS.keys())
        assert len(tables) == len(set(tables)), "Duplicate table names in heuristics"

    def test_heuristics_cover_all_documented_concepts(self):
        """Every documented concept has at least one table mapping to it."""
        mapped_concepts = set(_TABLE_HEURISTICS.values())
        missing = VALID_CONCEPTS - mapped_concepts
        assert not missing, f"Concepts with no heuristic table: {sorted(missing)}"


# ---------------------------------------------------------------------------
# Property 2: Heuristic lookup is total for known tables
# ---------------------------------------------------------------------------

class TestHeuristicLookupTotal:
    """_TABLE_HEURISTICS.get() always returns a value for known keys."""

    @given(table=known_table_strategy)
    @settings(max_examples=100, deadline=None)
    def test_known_table_returns_concept(self, table):
        concept = _TABLE_HEURISTICS.get(table)
        assert concept is not None
        assert concept in VALID_CONCEPTS

    @given(table=known_table_strategy)
    @settings(max_examples=100, deadline=None)
    def test_known_table_returns_consistent_concept(self, table):
        """Repeated lookups return the same value (dict is deterministic)."""
        c1 = _TABLE_HEURISTICS.get(table)
        c2 = _TABLE_HEURISTICS.get(table)
        assert c1 == c2


# ---------------------------------------------------------------------------
# Property 3: Unknown table names return None (not a wrong concept)
# ---------------------------------------------------------------------------

class TestUnknownTableReturnsNone:
    """Tables not in _TABLE_HEURISTICS return None, not a guessed concept."""

    @given(table=table_name_strategy.filter(lambda t: t not in _TABLE_HEURISTICS))
    @settings(max_examples=100, deadline=None)
    def test_unknown_table_returns_none(self, table):
        assert _TABLE_HEURISTICS.get(table) is None


# ---------------------------------------------------------------------------
# Property 4: SchemaRegistry.from_duckona binds all heuristic tables correctly
# ---------------------------------------------------------------------------

class TestSchemaRegistryBindsHeuristics:
    """from_duckona creates correct ConceptBindings for every heuristic table."""

    @pytest.fixture
    def mock_ona(self):
        """Build a mock DuckONA with one table per heuristic entry."""
        loaded = {}
        for table_name in _TABLE_HEURISTICS:
            df = pd.DataFrame({
                "employee_id": ["E001", "E002", "E003"],
                "value": [100, 200, 300],
            })
            loaded[table_name] = SimpleNamespace(columns=list(df.columns))
        # Build a mock object that has _loaded_tables attribute
        mock = MagicMock()
        mock._loaded_tables = loaded
        return mock

    def test_all_heuristic_tables_get_bindings(self, mock_ona):
        """Every table in _TABLE_HEURISTICS gets a ConceptBinding."""
        reg = SchemaRegistry.from_duckona(mock_ona)
        bound_tables = {b.table for b in reg.bindings}
        for table in _TABLE_HEURISTICS:
            assert table in bound_tables, f"Table '{table}' has no binding"

    def test_binding_concepts_match_heuristics(self, mock_ona):
        """ConceptBinding.concept matches _TABLE_HEURISTICS for each table."""
        reg = SchemaRegistry.from_duckona(mock_ona)
        for binding in reg.bindings:
            expected_concept = _TABLE_HEURISTICS[binding.table]
            assert binding.concept == expected_concept, (
                f"Table '{binding.table}': expected concept '{expected_concept}', "
                f"got '{binding.concept}'"
            )

    def test_every_binding_has_valid_concept(self, mock_ona):
        """Every binding's concept is in the recognized set."""
        reg = SchemaRegistry.from_duckona(mock_ona)
        for binding in reg.bindings:
            assert binding.concept in VALID_CONCEPTS, (
                f"Binding for '{binding.table}' has invalid concept '{binding.concept}'"
            )

    def test_every_binding_has_employee_col(self, mock_ona):
        """Every binding has a non-empty employee_col."""
        reg = SchemaRegistry.from_duckona(mock_ona)
        for binding in reg.bindings:
            assert binding.employee_col, (
                f"Binding for '{binding.table}' has empty employee_col"
            )

    def test_every_binding_has_fields(self, mock_ona):
        """Every binding has a non-empty fields tuple."""
        reg = SchemaRegistry.from_duckona(mock_ona)
        for binding in reg.bindings:
            assert isinstance(binding.fields, tuple), (
                f"Binding for '{binding.table}' fields is not a tuple"
            )
            assert len(binding.fields) > 0, (
                f"Binding for '{binding.table}' has empty fields"
            )


# ---------------------------------------------------------------------------
# Property 5: Concept distribution is well-formed
# ---------------------------------------------------------------------------

class TestConceptDistribution:
    """The heuristic mapping has sensible structural properties."""

    def test_at_least_one_table_per_concept(self):
        """Each valid concept has ≥1 table mapping to it."""
        for concept in VALID_CONCEPTS:
            tables = [t for t, c in _TABLE_HEURISTICS.items() if c == concept]
            assert len(tables) >= 1, (
                f"Concept '{concept}' has no tables mapping to it"
            )

    def test_concepts_are_mutually_exclusive(self):
        """Each table maps to exactly one concept (dict values are single strings)."""
        # This is guaranteed by dict structure, but we verify the invariant
        for table, concept in _TABLE_HEURISTICS.items():
            assert isinstance(concept, str), (
                f"Table '{table}' maps to non-string: {type(concept)}"
            )
            # Single string = single concept, no overlap possible
            assert " " not in concept, (
                f"Concept '{concept}' for table '{table}' contains spaces"
            )

    @given(
        extra_table=table_name_strategy.filter(lambda t: t not in _TABLE_HEURISTICS),
        extra_concept=concept_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_adding_pair_preserves_validity(self, extra_table, extra_concept):
        """Adding a new table→concept pair doesn't break existing mappings."""
        # Work on a copy
        extended = dict(_TABLE_HEURISTICS)
        extended[extra_table] = extra_concept

        # All original mappings still intact
        for t, c in _TABLE_HEURISTICS.items():
            assert extended[t] == c

        # New mapping is valid
        assert extended[extra_table] == extra_concept
        assert extra_concept in VALID_CONCEPTS


# ---------------------------------------------------------------------------
# Property 6: normalize_field is consistent with heuristic schema usage
# ---------------------------------------------------------------------------

class TestNormalizeFieldConsistency:
    """normalize_field produces canonical keys that bindings use correctly."""

    @given(
        col=st.text(alphabet=string.ascii_letters + "_0123456789", min_size=1, max_size=30)
    )
    @settings(max_examples=100, deadline=None)
    def test_normalize_returns_nonempty_string(self, col):
        result = normalize_field(col)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_employee_id_normalizes_to_itself(self):
        """The canonical employee_id column should normalize to itself."""
        assert normalize_field("employee_id") == "employee_id"

    def test_known_aliases_normalize_correctly(self):
        """Known aliases from _FIELD_ALIASES normalize to their canonical key."""
        from pyduck_ona_profile.schema import _FIELD_ALIASES
        for canonical, aliases in _FIELD_ALIASES.items():
            for alias in aliases:
                assert normalize_field(alias) == canonical, (
                    f"Alias '{alias}' should normalize to '{canonical}', "
                    f"got '{normalize_field(alias)}'"
                )