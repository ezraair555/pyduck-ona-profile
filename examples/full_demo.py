"""End-to-end demo of pyduck-ona-profile.

Builds a synthetic 30-employee organization with realistic change history,
then exercises every public API:
- SchemaRegistry
- Subject.profile() + Subject.with_role()
- Timeline (events, manager_changes, comp_history, between, as_of)
- ask() with the natural-language query layer

Run with:
    python examples/full_demo.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the package importable when running directly from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pandas as pd
from pyduck_ona import DuckONA
from pyduck_ona_profile import Subject, Timeline, ask, attach


def build_hris() -> pd.DataFrame:
    """Synthetic HRIS with two snapshots so events are detectable."""
    rng = pd.Series(range(30)).sample(frac=1, random_state=7).index
    rows = []
    for i in range(30):
        eid = f"E{i:04d}"
        if i == 0:
            sup = None
            title = "CEO"
            level = "L1"
        elif i < 4:
            sup = "E0000"
            title = "VP"
            level = "L2"
        else:
            sup = f"E{(i % 3) + 1:04d}"
            title = "Manager" if i % 5 == 0 else "IC"
            level = "L4"
        rows.append({
            "employee_id": eid,
            "supervisor_id": sup,
            "name": f"Person-{eid}",
            "department": ["Engineering", "Sales", "Marketing", "Finance"][i % 4],
            "title": title,
            "level": level,
            "hire_date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=int(rng[i] * 50)),
            "snapshot_date": pd.Timestamp("2023-01-01"),
        })

    snap2 = pd.DataFrame(rows)
    snap2["snapshot_date"] = pd.Timestamp("2024-01-01")
    # Some manager shuffles
    snap2.loc[snap2["employee_id"].isin(["E0001", "E0002", "E0003"]), "supervisor_id"] = "E0000"
    # One promotion
    snap2.loc[snap2["employee_id"] == "E0005", "title"] = "Senior Manager"
    snap2.loc[snap2["employee_id"] == "E0005", "level"] = "L3"

    snap1 = pd.DataFrame(rows)
    return pd.concat([snap1, snap2], ignore_index=True)


def build_compensation() -> pd.DataFrame:
    """Two compensation snapshots; E0006 gets a 15% raise."""
    employees = [f"E{i:04d}" for i in range(30)]
    rows = []
    for snap_date, base in [("2023-01-01", 100000), ("2024-01-01", 105000)]:
        for eid in employees:
            rows.append({
                "employee_id": eid,
                "salary": base + (hash(eid) % 30000) - 15000,
                "snapshot_date": pd.Timestamp(snap_date),
            })
    return pd.DataFrame(rows)


def build_turnover() -> pd.DataFrame:
    return pd.DataFrame([
        {"employee_id": "E0007", "termination_date": pd.Timestamp("2023-06-15")},
        {"employee_id": "E0010", "termination_date": pd.Timestamp("2023-11-01")},
    ])


def main() -> None:
    print("Building synthetic organization ...")
    hris = build_hris()
    comp = build_compensation()
    turnover = build_turnover()

    ona = DuckONA()
    ona.load_hris(hris)
    ona.load_compensation(comp)
    ona.load_turnover(turnover)

    # 1. Subject view — use E0005 since E0006 has the full event history
    print("\n[1/4] Subject.profile() for E0005")
    alice = Subject("E0005", ona)
    profile = alice.profile()
    for concept, record in profile.to_dict().items():
        if record:
            print(f"  {concept}: {record}")

    # 2. PII gating
    print("\n[2/4] PII gating: with_role('manager')")
    gated = alice.with_role("manager")
    print(f"  compensation (manager view): {gated.compensation}")
    print(f"  identity (manager view):     {gated.identity}")

    # 3. Timeline — E0005 has a manager change and a promotion in the demo
    print("\n[3/4] Timeline for E0005")
    bob = Subject("E0005", ona)
    tl = Timeline(bob)
    print(f"  events: {len(tl.all())}")
    print(f"  manager_changes: {len(tl.manager_changes())}")
    print(f"  comp_history:    {len(tl.comp_history())}")
    print(f"  promotions:      {len(tl.promotions())}")
    snap = tl.as_of("2024-06-01")
    print(f"  as_of('2024-06-01'): {snap}")

    # 4. ask()
    print("\n[4/4] ask() — natural-language queries (no LLM)")
    reg = attach(ona)
    questions = [
        "employees with the most managers in the last 24 months",
        "recent promotions in the last 12 months",
        "headcount by department",
    ]
    for q in questions:
        print(f"\n  Q: {q}")
        result = ask(q, reg)
        if result.matched_pattern:
            print(f"  matched: {result.matched_pattern} (sim={result.similarity_score:.3f})")
            print(f"  sql: {result.sql[:120]}...")
        else:
            print(f"  no pattern matched — add this question to grow the catalog")


if __name__ == "__main__":
    main()
