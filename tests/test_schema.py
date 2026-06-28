"""Tests for the schema registry."""

from __future__ import annotations

from pyduck_ona_profile.schema import SchemaRegistry, attach, normalize_field


def test_normalize_field_canonical():
    assert normalize_field("salary") == "salary"
    assert normalize_field("base_salary") == "salary"
    assert normalize_field("AnnualComp") == "salary"
    assert normalize_field("supervisor_id") == "manager_id"
    assert normalize_field("DEPARTMENT") == "department"
    assert normalize_field("custom_field") == "custom_field"


def test_schema_registry_from_duckona(tiny_ona):
    reg = SchemaRegistry.from_duckona(tiny_ona)
    concepts = reg.concepts()
    # All the default-loaded concepts should be present
    assert "identity" in concepts
    assert "compensation" in concepts
    assert "turnover" in concepts


def test_schema_registry_table_for(tiny_ona):
    reg = SchemaRegistry.from_duckona(tiny_ona)
    binding = reg.table_for("compensation")
    assert binding is not None
    assert binding.table == "compensation"
    assert "salary" in binding.fields


def test_schema_registry_concepts_dedup(tiny_ona):
    reg = SchemaRegistry.from_duckona(tiny_ona)
    seen = reg.concepts()
    assert len(seen) == len(set(seen)), "concepts should be deduplicated"


def test_schema_registry_is_loaded(tiny_ona):
    reg = SchemaRegistry.from_duckona(tiny_ona)
    assert reg.is_loaded("identity") is True
    assert reg.is_loaded("nonexistent_concept") is False


def test_attach_is_convenience_wrapper(tiny_ona):
    reg = attach(tiny_ona)
    assert isinstance(reg, SchemaRegistry)
    assert reg.is_loaded("identity")


def test_schema_registry_employee_column_fallback(tiny_ona):
    """If the table has no employee_id column, fall back to the registry default."""
    reg = SchemaRegistry.from_duckona(tiny_ona)
    binding = reg.table_for("identity")
    assert binding is not None
    assert binding.employee_col == "employee_id"
