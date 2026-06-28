"""Tests for the Subject per-employee view."""

from __future__ import annotations

import pytest

from pyduck_ona_profile.schema import SchemaRegistry
from pyduck_ona_profile.subject import REDACTION_BY_ROLE, Profile, Subject


def test_subject_profile_returns_identity(tiny_ona):
    s = Subject("E0006", tiny_ona)
    p = s.profile()
    assert isinstance(p, Profile)
    assert p.identity["employee_id"] == "E0006"
    assert p.identity.get("department") in {
        "Engineering",
        "Sales",
        "Marketing",
        "Finance",
    }


def test_subject_profile_position_includes_direct_reports(tiny_ona):
    s = Subject("E0001", tiny_ona)  # a VP, has direct reports
    p = s.profile()
    assert p.position["employee_id"] == "E0001"
    assert p.position["direct_reports"] >= 0


def test_subject_unknown_employee_returns_minimal_record(tiny_ona):
    s = Subject("E9999", tiny_ona)
    p = s.profile()
    assert p.identity == {"employee_id": "E9999"}
    assert p.compensation is None
    assert p.mobility is None


def test_subject_with_role_manager_redacts_salary(tiny_ona):
    s = Subject("E0006", tiny_ona)
    full = s.profile()
    if full.compensation is None or "salary" not in full.compensation:
        pytest.skip("synthetic fixture didn't include salary for E0006")
    redacted = s.with_role("manager")
    assert redacted.compensation is not None
    assert redacted.compensation.get("salary") is None
    # Identity should still be intact
    assert redacted.identity["employee_id"] == "E0006"


def test_subject_with_role_self_redacts_salary(tiny_ona):
    s = Subject("E0006", tiny_ona)
    full = s.profile()
    if full.compensation is None or "salary" not in full.compensation:
        pytest.skip("synthetic fixture didn't include salary for E0006")
    redacted = s.with_role("self")
    assert redacted.compensation.get("salary") is None


def test_subject_with_role_hrbp_shows_full(tiny_ona):
    """HR business partner / unknown role sees the full record."""
    s = Subject("E0006", tiny_ona)
    full = s.profile()
    redacted = s.with_role("hrbp")
    assert redacted.compensation == full.compensation


def test_subject_with_role_unknown_role_shows_full(tiny_ona):
    s = Subject("E0006", tiny_ona)
    full = s.profile()
    redacted = s.with_role("nonexistent_role")
    assert redacted.compensation == full.compensation


def test_subject_profile_to_dict(tiny_ona):
    s = Subject("E0006", tiny_ona)
    d = s.profile().to_dict()
    assert "identity" in d
    assert "position" in d
    assert "compensation" in d
    assert "mobility" in d


def test_subject_with_explicit_registry(tiny_ona):
    reg = SchemaRegistry.from_duckona(tiny_ona)
    s = Subject("E0006", tiny_ona, registry=reg)
    p = s.profile()
    assert p.identity["employee_id"] == "E0006"


def test_redaction_table_basic():
    """Sanity check: every non-hrbp role in REDACTION_BY_ROLE has at least one field."""
    for role, fields in REDACTION_BY_ROLE.items():
        assert isinstance(fields, set)
        assert len(fields) > 0, f"role {role!r} has no redaction fields"
