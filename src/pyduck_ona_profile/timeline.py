"""Timeline: per-employee event log + as_of() snapshots.

The Timeline is built on top of the event detectors in ``events.py``. Given
a ``Subject``, you can ask:

- ``Timeline(subject).events()`` — every event for this employee, newest first
- ``Timeline(subject).manager_changes()`` — only manager changes
- ``Timeline(subject).comp_history()`` — only compensation changes
- ``Timeline(subject).between(d1, d2)`` — events in a window
- ``Timeline(subject).as_of(date)`` — what did the profile look like on that date

If your source already provides explicit event/history tables, pass them
directly to the constructor via ``events=`` and skip the detector step.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import pandas as pd

from pyduck_ona_profile.events import (
    COMP_CHANGE,
    MGR_CHANGE,
    PROMOTION,
    detect_comp_changes,
    detect_manager_changes,
    detect_promotions,
)
from pyduck_ona_profile.subject import Subject


@dataclass
class Timeline:
    """A per-employee event timeline.

    Build via ``Timeline(subject)`` to auto-detect events from the loaded
    data, or pass an explicit ``events`` DataFrame if your source already
    has a history table.
    """

    subject: Subject
    events: pd.DataFrame = field(default_factory=pd.DataFrame)

    def __post_init__(self) -> None:
        if self.events.empty:
            self.events = self._auto_detect()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def all(self) -> pd.DataFrame:
        """Every event for this employee, newest first."""
        return self._for_employee().sort_values("event_date", ascending=False)

    def manager_changes(self) -> pd.DataFrame:
        return self._filter_type(MGR_CHANGE)

    def comp_history(self) -> pd.DataFrame:
        return self._filter_type(COMP_CHANGE)

    def promotions(self) -> pd.DataFrame:
        return self._filter_type(PROMOTION)

    def between(
        self, start: str | date | datetime, end: str | date | datetime
    ) -> pd.DataFrame:
        """Events whose ``event_date`` falls between ``start`` and ``end`` (inclusive)."""
        s = pd.to_datetime(start)
        e = pd.to_datetime(end)
        df = self._for_employee()
        if df.empty:
            return df
        in_window = (pd.to_datetime(df["event_date"]) >= s) & (
            pd.to_datetime(df["event_date"]) <= e
        )
        return (
            df[in_window]
            .sort_values("event_date", ascending=False)
            .reset_index(drop=True)
        )

    def as_of(self, when: str | date | datetime) -> dict[str, Any]:
        """Return a snapshot of the subject's profile as of ``when``.

        For current-state source tables, this is best-effort: it returns
        the events that had occurred on or before ``when`` and the most
        recent values for each concept. For sources with explicit SCD2
        history, this would issue a real temporal query.
        """
        when_dt = pd.to_datetime(when)
        events_so_far = self._for_employee()
        if not events_so_far.empty:
            in_window = pd.to_datetime(events_so_far["event_date"]) <= when_dt
            events_so_far = events_so_far[in_window]
        # Build a snapshot: take the most recent before_value / after_value per concept
        snapshot = {"as_of": str(when_dt)}
        if not events_so_far.empty:
            for concept in ("manager", "comp", "promotion"):
                type_col = (
                    MGR_CHANGE
                    if concept == "manager"
                    else COMP_CHANGE if concept == "comp" else PROMOTION
                )
                concept_events = events_so_far[events_so_far["event_type"] == type_col]
                if not concept_events.empty:
                    latest = concept_events.sort_values("event_date").iloc[-1]
                    snapshot[concept + "_at_as_of"] = {  # type: ignore[assignment]
                        "value": latest["after_value"],
                        "since": str(latest["event_date"]),
                    }
        return snapshot

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _for_employee(self) -> pd.DataFrame:
        if self.events.empty:
            return self.events
        return self.events[self.events["employee_id"] == self.subject.employee_id]

    def _filter_type(self, event_type: str) -> pd.DataFrame:
        df = self._for_employee()
        if df.empty:
            return df
        return (
            df[df["event_type"] == event_type]
            .sort_values("event_date", ascending=False)
            .reset_index(drop=True)
        )

    def _auto_detect(self) -> pd.DataFrame:
        """Run the built-in event detectors against the loaded data.

        Best-effort: silently skips tables that don't have the columns the
        detector expects. Users with richer source data can override by
        passing their own ``events`` DataFrame.
        """
        ona = self.subject._ona
        frames: list[pd.DataFrame] = []
        import contextlib

        hris = _try_get_relation(ona, ("hris", "_hris", "_register_hris"))
        comp = _try_get_relation(ona, ("compensation", "_compensation"))
        with contextlib.suppress(Exception):
            if hris is not None:
                frames.append(detect_manager_changes(hris))
        with contextlib.suppress(Exception):
            if comp is not None:
                frames.append(detect_comp_changes(comp))
        with contextlib.suppress(Exception):
            if hris is not None:
                frames.append(detect_promotions(hris))
        if not frames:
            return pd.DataFrame(
                columns=[
                    "employee_id",
                    "event_type",
                    "event_date",
                    "before_value",
                    "after_value",
                    "source_table",
                    "confidence",
                ]
            )
        return pd.concat(frames, ignore_index=True)


def _try_get_relation(ona: Any, names: Iterable[str]) -> Any:
    for n in names:
        rel = getattr(ona, n, None)
        if rel is not None:
            return rel
    return None


# mypy: disable-error-code=no-any-return
