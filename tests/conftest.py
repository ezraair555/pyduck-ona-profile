"""Shared fixtures for pyduck_ona_profile tests.

Builds a synthetic 30-employee org with realistic HRIS + compensation
snapshots + turnover. Avoids any real PII.

The ``tiny_ona`` fixture is a stand-in for a ``DuckONA`` instance: just an
object with attributes that match what the SchemaRegistry looks for
(``_hris``, ``_compensation``, ``_turnover``, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import pytest


@dataclass
class TinyONA:
    """A DuckONA stand-in for tests.

    Each attribute is either a pandas DataFrame or a DuckDB relation-like
    with a ``.df()`` method. The SchemaRegistry only calls ``.df()`` if it
    exists; otherwise it returns the DataFrame directly.
    """

    hris: pd.DataFrame = field(default_factory=pd.DataFrame)
    compensation: pd.DataFrame = field(default_factory=pd.DataFrame)
    turnover: pd.DataFrame = field(default_factory=pd.DataFrame)
    promotions: pd.DataFrame = field(default_factory=pd.DataFrame)
    retirement: pd.DataFrame = field(default_factory=pd.DataFrame)
    skills: pd.DataFrame = field(default_factory=pd.DataFrame)
    attendance: pd.DataFrame = field(default_factory=pd.DataFrame)
    survey: pd.DataFrame = field(default_factory=pd.DataFrame)

    # Aliases used by SchemaRegistry fallback path
    _hris: pd.DataFrame = field(default_factory=pd.DataFrame)
    _compensation: pd.DataFrame = field(default_factory=pd.DataFrame)
    _turnover: pd.DataFrame = field(default_factory=pd.DataFrame)

    def __post_init__(self) -> None:
        self._hris = self.hris
        self._compensation = self.compensation
        self._turnover = self.turnover


def build_synthetic_hris(n: int = 30, seed: int = 7) -> pd.DataFrame:
    """Build a synthetic HRIS table with two snapshots so events can be detected."""
    rng = np.random.default_rng(seed)
    rows = []
    employees = [f"E{i:04d}" for i in range(1, n + 1)]
    # Level 1: 1 CEO; Level 2: 3 VPs; Level 3+: rest
    for i, eid in enumerate(employees):
        if i == 0:
            supervisor = None
            level = "L1"
        elif i < 4:
            supervisor = employees[0]
            level = "L2"
        else:
            supervisor = employees[(i - 4) % 3 + 1]
            level = rng.choice(["L3", "L4", "L5"])
        rows.append(
            {
                "employee_id": eid,
                "supervisor_id": supervisor,
                "name": f"Person-{eid}",
                "department": rng.choice(
                    ["Engineering", "Sales", "Marketing", "Finance"]
                ),
                "title": "Manager" if supervisor is not None else "CEO",
                "level": level,
                "hire_date": pd.Timestamp("2020-01-01")
                + pd.Timedelta(days=int(rng.integers(0, 1500))),
            }
        )
    df = pd.DataFrame(rows)

    # Second snapshot with some manager shuffles and one promotion
    snap2 = df.copy()
    snap2["snapshot_date"] = pd.Timestamp("2024-01-01")
    snap1 = df.copy()
    snap1["snapshot_date"] = pd.Timestamp("2023-01-01")
    # Manager changes: move employees[5:8] (E0006, E0007, E0008) from their
    # original manager to E0000 (the CEO). In the base frame these report
    # to employees[1:4] (the VPs), so this is a real change.
    snap2.loc[snap2["employee_id"].isin(employees[5:8]), "supervisor_id"] = employees[0]
    # One promotion
    snap2.loc[snap2["employee_id"] == employees[5], "title"] = "Senior Manager"
    snap2.loc[snap2["employee_id"] == employees[5], "level"] = "L3"

    return pd.concat([snap1, snap2], ignore_index=True)


def build_synthetic_compensation(hris: pd.DataFrame, seed: int = 7) -> pd.DataFrame:
    """Two compensation snapshots with a meaningful raise for one employee."""
    rng = np.random.default_rng(seed + 1)
    employees = hris["employee_id"].drop_duplicates().tolist()
    rows = []
    for snap_date, base in [("2023-01-01", 90000), ("2024-01-01", 95000)]:
        for eid in employees:
            salary = base + int(rng.integers(-10000, 30000))
            rows.append(
                {
                    "employee_id": eid,
                    "salary": salary,
                    "snapshot_date": pd.Timestamp(snap_date),
                }
            )
    # Give E0006 a notable 15% raise between snapshots
    df = pd.DataFrame(rows)
    mask_old = (df["employee_id"] == "E0006") & (
        df["snapshot_date"] == pd.Timestamp("2023-01-01")
    )
    mask_new = (df["employee_id"] == "E0006") & (
        df["snapshot_date"] == pd.Timestamp("2024-01-01")
    )
    df.loc[mask_new, "salary"] = (
        (df.loc[mask_old, "salary"] * 1.15).round().astype(int).values[0]
    )
    return df


def build_synthetic_turnover(hris: pd.DataFrame) -> pd.DataFrame:
    """Two terminations."""
    return pd.DataFrame(
        [
            {"employee_id": "E0007", "termination_date": pd.Timestamp("2023-06-15")},
            {"employee_id": "E0010", "termination_date": pd.Timestamp("2023-11-01")},
        ]
    )


@pytest.fixture
def tiny_ona() -> TinyONA:
    hris = build_synthetic_hris()
    return TinyONA(
        hris=hris,
        compensation=build_synthetic_compensation(hris),
        turnover=build_synthetic_turnover(hris),
    )


@pytest.fixture
def synthetic_hris() -> pd.DataFrame:
    return build_synthetic_hris()
