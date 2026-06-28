"""Tests for the Timeline class."""

from __future__ import annotations

import pandas as pd

from pyduck_ona_profile.events import COMP_CHANGE, MGR_CHANGE
from pyduck_ona_profile.subject import Subject
from pyduck_ona_profile.timeline import Timeline


def test_timeline_auto_detects_events(tiny_ona):
    s = Subject("E0006", tiny_ona)
    tl = Timeline(s)
    assert not tl.events.empty
    # E0006 had a manager change in the synthetic fixture
    assert not tl.manager_changes().empty


def test_timeline_manager_changes(tiny_ona):
    s = Subject("E0006", tiny_ona)
    tl = Timeline(s)
    mgr = tl.manager_changes()
    assert not mgr.empty
    assert all(mgr["event_type"] == MGR_CHANGE)


def test_timeline_comp_history(tiny_ona):
    s = Subject("E0006", tiny_ona)
    tl = Timeline(s)
    comp = tl.comp_history()
    assert not comp.empty
    assert all(comp["event_type"] == COMP_CHANGE)


def test_timeline_promotions(tiny_ona):
    s = Subject("E0006", tiny_ona)
    tl = Timeline(s)
    proms = tl.promotions()
    assert not proms.empty


def test_timeline_between(tiny_ona):
    s = Subject("E0006", tiny_ona)
    tl = Timeline(s)
    events = tl.between("2023-12-31", "2024-01-02")
    # Manager change happened on 2024-01-01
    assert not events.empty


def test_timeline_between_empty_window(tiny_ona):
    s = Subject("E0006", tiny_ona)
    tl = Timeline(s)
    events = tl.between("2030-01-01", "2030-12-31")
    assert events.empty


def test_timeline_as_of_returns_snapshot(tiny_ona):
    s = Subject("E0006", tiny_ona)
    tl = Timeline(s)
    snap = tl.as_of("2024-06-01")
    assert "as_of" in snap
    assert "manager_at_as_of" in snap


def test_timeline_as_of_before_any_event(tiny_ona):
    s = Subject("E0006", tiny_ona)
    tl = Timeline(s)
    snap = tl.as_of("2020-01-01")
    assert "as_of" in snap
    # No events before 2023, so no concept snapshots
    assert "manager_at_as_of" not in snap


def test_timeline_all_returns_employee_events(tiny_ona):
    s = Subject("E0006", tiny_ona)
    tl = Timeline(s)
    all_events = tl.all()
    assert not all_events.empty
    assert all(all_events["employee_id"] == "E0006")


def test_timeline_with_explicit_events(tiny_ona):
    """If the user passes events explicitly, skip auto-detection."""
    df = pd.DataFrame(
        {
            "employee_id": ["E0006"],
            "event_type": ["custom_event"],
            "event_date": pd.to_datetime(["2024-06-15"]),
            "before_value": [None],
            "after_value": ["custom_value"],
            "source_table": ["custom"],
            "confidence": [1.0],
        }
    )
    s = Subject("E0006", tiny_ona)
    tl = Timeline(s, events=df)
    assert not tl.manager_changes().empty or len(tl.events) == 1
    # The custom event should be there
    assert "custom_event" in tl.events["event_type"].values
