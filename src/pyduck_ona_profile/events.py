"""Event detectors: derive a per-person event log from raw HR tables.

Each detector is a small function that takes a DuckDB relation (or a
pandas DataFrame) and returns a DataFrame of events with columns::

    [employee_id, event_type, event_date, before_value, after_value,
     source_table, confidence]

Event detectors are the bridge between **current-state tables** (HRIS,
compensation snapshots) and the **Timeline** layer that lets you query
"what changed and when?".

Available detectors:

- ``detect_manager_changes`` — manager/supervisor changes between snapshots
- ``detect_comp_changes`` — salary band or compa-ratio changes
- ``detect_promotions`` — title/level changes that look like promotions
- ``detect_absence_streaks`` — long unbroken absence periods (attendance)
"""

from __future__ import annotations

from typing import Any

import pandas as pd

# Event type constants — used in event_type column and for filtering
MGR_CHANGE = "manager_change"
COMP_CHANGE = "comp_change"
PROMOTION = "promotion"
ABSENCE_STREAK = "absence_streak"
HIRE = "hire"
TERMINATION = "termination"


def detect_manager_changes(
    relation: Any,
    *,
    employee_col: str = "employee_id",
    manager_col: str = "supervisor_id",
    snapshot_col: str = "snapshot_date",
    min_confidence: float = 0.5,
) -> pd.DataFrame:
    """Find every employee whose manager changed between snapshots.

    Parameters
    ----------
    relation:
        A DuckDB relation OR pandas DataFrame with columns
        (employee_col, manager_col, snapshot_col). Each row is one
        employee's manager at one point in time.
    """
    df = _to_df(relation)
    if df.empty or snapshot_col not in df.columns:
        return _empty_events(employee_col)
    df = df.sort_values([employee_col, snapshot_col])
    df["_prev_manager"] = df.groupby(employee_col)[manager_col].shift(1)
    changes = df[df[manager_col] != df["_prev_manager"]].copy()
    changes = changes[changes["_prev_manager"].notna()]  # skip first snapshot
    out = pd.DataFrame(
        {
            "employee_id": changes[employee_col].values,
            "event_type": MGR_CHANGE,
            "event_date": changes[snapshot_col].values,
            "before_value": changes["_prev_manager"].values,
            "after_value": changes[manager_col].values,
            "source_table": "hris_snapshots",
            "confidence": min_confidence,
        }
    )
    return out.reset_index(drop=True)


def detect_comp_changes(
    relation: Any,
    *,
    employee_col: str = "employee_id",
    salary_col: str = "salary",
    snapshot_col: str = "snapshot_date",
    min_pct_change: float = 0.01,
) -> pd.DataFrame:
    """Find compensation changes above ``min_pct_change`` between snapshots."""
    df = _to_df(relation)
    if df.empty or snapshot_col not in df.columns:
        return _empty_events(employee_col)
    df = df.sort_values([employee_col, snapshot_col])
    df["_prev_salary"] = df.groupby(employee_col)[salary_col].shift(1)
    df["_pct_change"] = (df[salary_col] - df["_prev_salary"]) / df["_prev_salary"]
    changes = df[df["_pct_change"].abs() >= min_pct_change].copy()
    changes = changes[changes["_prev_salary"].notna()]
    out = pd.DataFrame(
        {
            "employee_id": changes[employee_col].values,
            "event_type": COMP_CHANGE,
            "event_date": changes[snapshot_col].values,
            "before_value": changes["_prev_salary"].round(2).values,
            "after_value": changes[salary_col].round(2).values,
            "source_table": "compensation_snapshots",
            "confidence": 0.9,
        }
    )
    return out.reset_index(drop=True)


def detect_promotions(
    relation: Any,
    *,
    employee_col: str = "employee_id",
    title_col: str = "title",
    level_col: str = "level",
    snapshot_col: str = "snapshot_date",
) -> pd.DataFrame:
    """Find events where title or level changed (promotion heuristic).

    A promotion is inferred when *either* the title changes (and the level
    stays the same) *or* the level increases. Title-only changes that look
    like lateral moves are tagged with confidence=0.4; level increases are
    tagged with confidence=0.8.
    """
    df = _to_df(relation)
    if df.empty or snapshot_col not in df.columns:
        return _empty_events(employee_col)
    df = df.sort_values([employee_col, snapshot_col])
    df["_prev_title"] = df.groupby(employee_col)[title_col].shift(1)
    df["_prev_level"] = df.groupby(employee_col)[level_col].shift(1)
    df["_title_changed"] = df[title_col] != df["_prev_title"]
    df["_level_increased"] = _safe_numeric(df[level_col]) > _safe_numeric(
        df["_prev_level"]
    )
    candidates = df[df["_title_changed"] | df["_level_increased"]].copy()
    candidates = candidates[candidates["_prev_title"].notna()]
    confidence = np.where(candidates["_level_increased"], 0.8, 0.4)
    out = pd.DataFrame(
        {
            "employee_id": candidates[employee_col].values,
            "event_type": PROMOTION,
            "event_date": candidates[snapshot_col].values,
            "before_value": candidates["_prev_title"].astype(str).values,
            "after_value": candidates[title_col].astype(str).values,
            "source_table": "hris_snapshots",
            "confidence": confidence,
        }
    )
    return out.reset_index(drop=True)


def detect_absence_streaks(
    relation: Any,
    *,
    employee_col: str = "employee_id",
    date_col: str = "date",
    absent_col: str = "was_absent",
    min_days: int = 5,
) -> pd.DataFrame:
    """Find consecutive absence runs of ``min_days`` or longer."""
    df = _to_df(relation)
    if df.empty:
        return _empty_events(employee_col)
    df = df.sort_values([employee_col, date_col])
    df[absent_col] = df[absent_col].astype(bool)

    events = []
    for emp_id, group in df.groupby(employee_col):
        absent = group[group[absent_col]]
        if absent.empty:
            continue
        # Find consecutive date runs
        dates = pd.to_datetime(absent[date_col]).reset_index(drop=True)
        gaps = dates.diff().dt.days.fillna(1)
        # New streak starts when gap > 1 day
        streak_id = (gaps > 1).cumsum()
        for _sid, run in absent.groupby(streak_id):
            run_dates = pd.to_datetime(run[date_col]).reset_index(drop=True)
            days = (run_dates.max() - run_dates.min()).days + 1
            if days >= min_days:
                events.append(
                    {
                        "employee_id": emp_id,
                        "event_type": ABSENCE_STREAK,
                        "event_date": run_dates.min(),
                        "before_value": None,
                        "after_value": f"{days} consecutive days absent",
                        "source_table": "attendance",
                        "confidence": 0.85,
                    }
                )
    if not events:
        return _empty_events(employee_col)
    return pd.DataFrame(events)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_df(relation: Any) -> pd.DataFrame:
    """Accept either a DuckDB relation or a pandas DataFrame."""
    if isinstance(relation, pd.DataFrame):
        return relation.copy()
    try:
        return relation.df()  # DuckDBPyRelation has .df()
    except AttributeError:
        # Try arrow for zero-copy
        try:
            return relation.arrow().to_pandas()
        except Exception:
            raise TypeError(f"unsupported relation type: {type(relation)}") from None


def _empty_events(employee_col: str = "employee_id") -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            employee_col,
            "event_type",
            "event_date",
            "before_value",
            "after_value",
            "source_table",
            "confidence",
        ]
    )


def _safe_numeric(s: pd.Series) -> pd.Series:
    """Convert a series to numeric, coercing errors to NaN."""
    return pd.to_numeric(s, errors="coerce")


# Imported here to avoid a circular dependency; numpy is a hard dep.
import numpy as np  # noqa: E402

# mypy: disable-error-code=no-any-return
