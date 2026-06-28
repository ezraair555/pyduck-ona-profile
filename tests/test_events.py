"""Tests for event detectors."""

from __future__ import annotations

import pandas as pd

from pyduck_ona_profile.events import (
    ABSENCE_STREAK,
    COMP_CHANGE,
    MGR_CHANGE,
    PROMOTION,
    detect_absence_streaks,
    detect_comp_changes,
    detect_manager_changes,
    detect_promotions,
)


def test_detect_manager_changes(synthetic_hris):
    """Two snapshots with 3 manager changes should yield 3 events."""
    events = detect_manager_changes(synthetic_hris)
    assert not events.empty
    # synthetic fixture moves employees[5:8] (E0006, E0007, E0008) to the CEO
    affected = set(events[events["event_type"] == MGR_CHANGE]["employee_id"])
    assert {"E0006", "E0007", "E0008"}.issubset(affected)
    assert all(events["event_type"] == MGR_CHANGE)
    assert all(events["source_table"] == "hris_snapshots")


def test_detect_manager_changes_empty_input():
    events = detect_manager_changes(pd.DataFrame())
    assert events.empty
    assert "employee_id" in events.columns


def test_detect_manager_changes_single_snapshot():
    df = pd.DataFrame(
        {
            "employee_id": ["E1", "E2"],
            "supervisor_id": ["E0", "E0"],
            "snapshot_date": pd.to_datetime(["2024-01-01", "2024-01-01"]),
        }
    )
    events = detect_manager_changes(df)
    # First snapshot produces no change events (only one per employee)
    assert events.empty


def test_detect_comp_changes(tiny_ona):
    events = detect_comp_changes(tiny_ona.compensation)
    # E0006 had a 15% raise, must be detected
    assert not events.empty
    emp_6 = events[
        (events["employee_id"] == "E0006") & (events["event_type"] == COMP_CHANGE)
    ]
    assert not emp_6.empty, "E0006's 15% raise should be detected"


def test_detect_comp_changes_ignores_tiny_changes(tiny_ona):
    events = detect_comp_changes(tiny_ona.compensation, min_pct_change=0.5)
    # 50% threshold should filter everything out (max raise in fixture is 15%)
    assert events.empty


def test_detect_promotions(synthetic_hris):
    events = detect_promotions(synthetic_hris)
    # E0006 was promoted from Manager → Senior Manager + L5 → L3 in snap2
    emp_6 = events[
        (events["employee_id"] == "E0006") & (events["event_type"] == PROMOTION)
    ]
    assert not emp_6.empty


def test_detect_absence_streaks_basic():
    df = pd.DataFrame(
        {
            "employee_id": ["E1"] * 7 + ["E1", "E1"],
            "date": pd.to_datetime(
                [
                    "2024-01-01",
                    "2024-01-02",
                    "2024-01-03",
                    "2024-01-04",
                    "2024-01-05",
                    "2024-01-06",
                    "2024-01-07",
                    "2024-01-15",
                    "2024-01-16",
                ]
            ),
            "was_absent": [True] * 7 + [True, True],
        }
    )
    events = detect_absence_streaks(df, min_days=5)
    # Two streaks: 7 consecutive (Jan 1-7) and 2 consecutive (Jan 15-16, below threshold)
    long_streaks = events[events["event_type"] == ABSENCE_STREAK]
    assert len(long_streaks) == 1
    assert "7 consecutive days" in long_streaks.iloc[0]["after_value"]


def test_detect_absence_streaks_empty():
    events = detect_absence_streaks(pd.DataFrame())
    assert events.empty


def test_detect_absence_streaks_below_threshold():
    df = pd.DataFrame(
        {
            "employee_id": ["E1", "E1"],
            "date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
            "was_absent": [True, True],
        }
    )
    events = detect_absence_streaks(df, min_days=5)
    assert events.empty
