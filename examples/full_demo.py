"""End-to-end demo of pyduck-ona-profile.

Builds a synthetic 30-employee organization with realistic change history,
then exercises every public API:
- SchemaRegistry (built from a real DuckONA instance)
- Subject.profile() + Subject.with_role()
- Timeline (events, manager_changes, comp_history, between, as_of)
- ask() with the natural-language query layer (no LLM)

Run with:
    PYTHONPATH=src python3 examples/full_demo.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the package importable when running directly from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pandas as pd
from pyduck_ona import DuckONA
from pyduck_ona_profile import Subject, Timeline, ask, attach


# ---------------------------------------------------------------------------
# Synthetic data builders
# ---------------------------------------------------------------------------

DEPARTMENTS = ["Engineering", "Sales", "Marketing", "Finance"]
LEVELS = ["L1", "L2", "L3", "L4", "L5"]


def build_hris() -> pd.DataFrame:
    """Synthetic HRIS with two snapshots so events are detectable.

    Includes every column Subject expects (department, level, title,
    termination_date, hire_date, supervisor_id).
    """
    rows = []
    for i in range(30):
        eid = f"E{i:04d}"
        if i == 0:
            sup = None
            title = "CEO"
            level = "L1"
            dept = "Executive"
        elif i < 4:
            sup = "E0000"
            title = "VP"
            level = "L2"
            dept = DEPARTMENTS[i % 4]
        else:
            sup = f"E{(i % 3) + 1:04d}"
            title = "Senior Manager" if i % 5 == 0 else "Manager" if i % 3 == 0 else "IC"
            level = ["L3", "L4", "L5"][i % 3]
            dept = DEPARTMENTS[i % 4]
        rows.append({
            "employee_id": eid,
            "supervisor_id": sup,
            "name": f"Person-{eid}",
            "department": dept,
            "title": title,
            "level": level,
            "hire_date": pd.Timestamp("2018-01-01") + pd.Timedelta(days=i * 90),
            "tenure_years": round(7.0 - i * 0.1, 2),
            "termination_date": pd.NaT,
            "snapshot_date": pd.Timestamp("2023-01-01"),
        })

    snap2 = pd.DataFrame(rows)
    snap2["snapshot_date"] = pd.Timestamp("2024-01-01")
    snap1 = pd.DataFrame(rows)

    # Manager changes: move employees[5:8] to report to the CEO instead
    # of their original VP. This produces 3 manager_change events.
    snap2.loc[snap2["employee_id"].isin(["E0006", "E0007", "E0008"]), "supervisor_id"] = "E0000"

    # One promotion: E0005 gets a title and level bump
    snap2.loc[snap2["employee_id"] == "E0005", "title"] = "Senior Manager"
    snap2.loc[snap2["employee_id"] == "E0005", "level"] = "L3"

    # Two terminations in the 2023 snapshot
    snap1.loc[snap1["employee_id"] == "E0007", "termination_date"] = pd.Timestamp("2023-06-15")
    snap1.loc[snap1["employee_id"] == "E0010", "termination_date"] = pd.Timestamp("2023-11-01")

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
    df = pd.DataFrame(rows)
    # Give E0006 a notable 15% raise
    df.loc[(df["employee_id"] == "E0006") & (df["snapshot_date"] == pd.Timestamp("2024-01-01")),
           "salary"] = (
        df.loc[(df["employee_id"] == "E0006") & (df["snapshot_date"] == pd.Timestamp("2023-01-01")),
               "salary"].iloc[0] * 1.15
    ).round().astype(int)
    return df


def build_turnover() -> pd.DataFrame:
    return pd.DataFrame([
        {"employee_id": "E0007", "termination_date": pd.Timestamp("2023-06-15")},
        {"employee_id": "E0010", "termination_date": pd.Timestamp("2023-11-01")},
    ])


# ---------------------------------------------------------------------------
# Auxiliary tables needed by some seed patterns. These are computed from
# the HRIS data so the demo is fully self-contained.
# ---------------------------------------------------------------------------


def build_manager_changes(hris: pd.DataFrame) -> pd.DataFrame:
    """Per-employee manager-change event log (matches MANAGER_CHANGE_FREQUENCY pattern)."""
    snap1 = hris[hris["snapshot_date"] == hris["snapshot_date"].min()].sort_values("employee_id")
    snap2 = hris[hris["snapshot_date"] == hris["snapshot_date"].max()].sort_values("employee_id")
    merged = snap1[["employee_id", "supervisor_id"]].merge(
        snap2[["employee_id", "supervisor_id"]], on="employee_id", suffixes=("_old", "_new"),
    )
    changes = merged[merged["supervisor_id_old"] != merged["supervisor_id_new"]]
    return pd.DataFrame({
        "employee_id": changes["employee_id"].values,
        "new_manager_id": changes["supervisor_id_new"].values,
        "change_date": pd.Timestamp("2024-01-01"),
    })


def build_promotions(hris: pd.DataFrame) -> pd.DataFrame:
    """Promotion event log (matches PROMOTION_RECENT pattern)."""
    snap1 = hris[hris["snapshot_date"] == hris["snapshot_date"].min()].sort_values("employee_id")
    snap2 = hris[hris["snapshot_date"] == hris["snapshot_date"].max()].sort_values("employee_id")
    merged = snap1[["employee_id", "title"]].merge(
        snap2[["employee_id", "title"]], on="employee_id", suffixes=("_old", "_new"),
    )
    promotions = merged[merged["title_old"] != merged["title_new"]]
    return pd.DataFrame({
        "employee_id": promotions["employee_id"].values,
        "old_title": promotions["title_old"].values,
        "new_title": promotions["title_new"].values,
        "promotion_date": pd.Timestamp("2024-01-01"),
    })


def build_centrality(hris: pd.DataFrame) -> pd.DataFrame:
    """Toy centrality scores (matches CENTRALITY_LEADERS pattern)."""
    employees = hris[hris["snapshot_date"] == hris["snapshot_date"].max()]["employee_id"].tolist()
    rng = pd.Series(range(len(employees))).sample(frac=1, random_state=42).values / len(employees)
    return pd.DataFrame({
        "employee_id": employees,
        "betweenness": rng.tolist(),
        "pagerank": (rng / rng.sum()).tolist(),
    })


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("Building synthetic organization ...")
    hris = build_hris()
    comp = build_compensation()
    turnover = build_turnover()
    manager_changes = build_manager_changes(hris)
    promotions = build_promotions(hris)
    centrality = build_centrality(hris)

    ona = DuckONA()
    ona.load_hris(hris)
    ona.load_compensation(comp)
    ona.load_turnover(turnover)

    # 1. Subject view — E0006 has manager change + comp change + promotion
    print("\n[1/4] Subject.profile() for E0006")
    alice = Subject("E0006", ona)
    profile = alice.profile()
    for concept, record in profile.to_dict().items():
        if record:
            print(f"  {concept}: {record}")

    # 2. PII gating
    print("\n[2/4] PII gating: with_role('manager')")
    gated = alice.with_role("manager")
    print(f"  compensation (manager view): {gated.compensation}")
    print(f"  identity (manager view):     {gated.identity}")

    # 3. Timeline — E0006 has manager change + comp change + promotion
    print("\n[3/4] Timeline for E0006")
    bob = Subject("E0006", ona)
    tl = Timeline(bob)
    print(f"  events: {len(tl.all())}")
    print(f"  manager_changes: {len(tl.manager_changes())}")
    print(f"  comp_history:    {len(tl.comp_history())}")
    print(f"  promotions:      {len(tl.promotions())}")
    snap = tl.as_of("2024-06-01")
    print(f"  as_of('2024-06-01'): {snap}")

    # 4. ask() — pass data= so the in-memory DuckDB connection has the
    # auxiliary tables (manager_changes, promotions, centrality_scores)
    # the seed patterns reference.
    print("\n[4/4] ask() — natural-language queries (no LLM)")
    reg = attach(ona)
    data = {
        "hris": hris,
        "compensation": comp,
        "turnover": turnover,
        "manager_changes": manager_changes,
        "promotions": promotions,
        "centrality_scores": centrality,
    }
    questions = [
        "employees with the most managers in the last 24 months",
        "recent promotions in the last 12 months",
        "headcount by department",
        "salary outliers within level",
        "recent hires in the last 12 months",
    ]
    for q in questions:
        print(f"\n  Q: {q}")
        result = ask(q, reg, data=data)
        if result.matched_pattern and result.result is not None and not result.result.empty:
            print(f"  matched: {result.matched_pattern} (sim={result.similarity_score:.3f})")
            print(f"  rows:    {len(result.result)}")
            print(f"  result:  {result.result.head(3).to_dict('records')}")
        elif result.matched_pattern:
            print(f"  matched: {result.matched_pattern} (sim={result.similarity_score:.3f})")
            print(f"  empty result (acceptable for tiny synthetic data)")
        elif result.error:
            print(f"  error: {result.error}")


if __name__ == "__main__":
    main()
