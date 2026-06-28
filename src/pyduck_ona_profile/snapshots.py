"""SCD2 (slowly-changing-dimension type 2) helpers for temporal queries.

Most HR sources deliver **current-state** tables — one row per employee,
no history. To support ``Timeline.as_of()`` and event detection on
current-state data, we synthesize an SCD2-style history by *sorting* on
whatever date column the user has (hire_date, last_updated, etc.) and
treating each row's "effective_from" as the change date.

If your source already has explicit history (Workday job history tables,
custom change-event tables), skip this module and feed the change events
directly to the timeline layer.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SCD2Config:
    """Configuration for synthesizing SCD2 history from a current-state table."""

    effective_from_col: str  # column that holds the change/effective date
    effective_to_col: str | None  # column that holds the prior-change date (if any)
    employee_col: str = "employee_id"
    # If effective_to_col is None, we treat the next row's effective_from_col
    # as the current row's effective_to (i.e., last row is "still active").
