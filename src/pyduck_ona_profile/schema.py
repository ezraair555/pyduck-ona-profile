"""Schema registry: maps loaded DuckONA tables to concepts.

The registry is built automatically when you load DataFrames into a
``DuckONA`` instance via ``pyduck-ona-profile.attach(ona)``. You can also
inspect or override it manually for non-standard schemas.

A *concept* is a logical bucket like "identity", "position", "compensation",
"mobility", "attendance", "engagement". Each concept is associated with one
or more loaded tables and the column(s) that link them on ``employee_id``.

The schema registry is the substrate for everything else in this package:
Subject.profile(), Timeline, and the ask() pattern matcher all consult it.
"""

from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ConceptBinding:
    """A mapping from a logical concept to the table+column that supplies it."""

    concept: str  # e.g. "compensation"
    table: str  # e.g. "compensation"
    employee_col: str  # e.g. "employee_id"
    fields: tuple[str, ...]  # canonical fields exposed by this binding


# Built-in heuristics: given a table name, what concept does it likely hold?
# These are intentionally conservative — the user can override at any time.
_TABLE_HEURISTICS: dict[str, str] = {
    "hris": "identity",
    "compensation": "compensation",
    "turnover": "turnover",
    "promotions": "mobility",
    "retirement": "retirement",
    "skills": "skills",
    "attendance": "attendance",
    "survey": "engagement",
}


# Field normalization: maps noisy input column names to a canonical key.
# Example: "salary" / "base_salary" / "annual_comp" all → "salary".
_FIELD_ALIASES: dict[str, set[str]] = {
    "salary": {
        "salary",
        "base_salary",
        "annual_salary",
        "annual_comp",
        "current_salary",
        "comp",
        "pay",
    },
    "manager_id": {"manager_id", "supervisor_id", "reports_to"},
    "department": {"department", "dept", "org", "business_unit"},
    "level": {"level", "job_level", "grade", "band"},
    "title": {"title", "job_title", "position", "role"},
    "hire_date": {"hire_date", "start_date", "hired_on"},
    "termination_date": {"termination_date", "term_date", "end_date", "left_on"},
}


def normalize_field(col: str) -> str:
    """Map a column name to its canonical key, or return the input unchanged.

    Aliases are matched case-insensitively after stripping non-alphanumeric
    characters. If no alias matches, the original column name is returned
    unchanged so user-defined fields are preserved.
    """

    stripped = re.sub(r"[^a-z0-9]", "", col.strip().lower())
    for canonical, aliases in _FIELD_ALIASES.items():
        norm_aliases = {re.sub(r"[^a-z0-9]", "", a.lower()) for a in aliases}
        if stripped in norm_aliases:
            return canonical
    return col  # preserve original column name when no alias matches


@dataclass
class SchemaRegistry:
    """The catalog of concepts → tables for a loaded DuckONA instance.

    Built once via ``SchemaRegistry.from_duckona(ona)``. Read-mostly after
    construction: Subject/Timeline/ask() never mutate it; they only read.
    """

    bindings: list[ConceptBinding] = field(default_factory=list)
    employee_column: str = "employee_id"
    # Extra concept → table overrides the user has applied.
    overrides: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_duckona(cls, ona: Any) -> SchemaRegistry:
        """Inspect a DuckONA instance and produce a registry of its loaded tables."""
        reg = cls()
        loaded = getattr(ona, "_loaded_tables", None)
        if not loaded:
            # DuckONA (>=0.1.5) exposes _table_names: set[str] and .con.
            # Build {name: relation} by querying each known name.
            table_names = getattr(ona, "_table_names", None)
            con = getattr(ona, "con", None)
            if table_names and con is not None:
                loaded = {}
                with contextlib.suppress(Exception):
                    for name in table_names:
                        loaded[name] = con.sql(f"SELECT * FROM {name}")
        if not loaded:
            # Fall back to a generic guess based on what attributes the DuckONA
            # instance exposes; this is best-effort and intended for tests.
            loaded = {
                name: getattr(ona, name)
                for name in (
                    "hris",
                    "compensation",
                    "turnover",
                    "promotions",
                    "skills",
                    "attendance",
                    "survey",
                    "retirement",
                )
                if hasattr(ona, name)
            }

        for table, relation in loaded.items():
            concept = _TABLE_HEURISTICS.get(table)
            if not concept:
                continue
            try:
                columns = tuple(relation.columns)
            except Exception:
                columns = ()
            employee_col = next(
                (
                    c
                    for c in ("employee_id", "emp_id", "worker_id")
                    if c in [col.lower() for col in columns]
                ),
                reg.employee_column,
            )
            normalized = tuple({normalize_field(c) for c in columns})
            reg.bindings.append(
                ConceptBinding(
                    concept=concept,
                    table=table,
                    employee_col=employee_col,
                    fields=normalized,
                )
            )
        return reg

    def tables_for(self, concept: str) -> list[ConceptBinding]:
        """Return all bindings for a given concept (e.g. 'compensation')."""
        return [b for b in self.bindings if b.concept == concept]

    def table_for(self, concept: str) -> ConceptBinding | None:
        """Return the first binding for a given concept, or None if absent."""
        bindings = self.tables_for(concept)
        return bindings[0] if bindings else None

    def concepts(self) -> list[str]:
        """Return the set of concepts currently loaded, in registration order."""
        seen: set[str] = set()
        out: list[str] = []
        for b in self.bindings:
            if b.concept not in seen:
                seen.add(b.concept)
                out.append(b.concept)
        return out

    def is_loaded(self, concept: str) -> bool:
        return self.table_for(concept) is not None


def attach(ona: Any) -> SchemaRegistry:
    """Build a SchemaRegistry from a DuckONA instance.

    Convenience wrapper so callers can write::

        from pyduck_ona_profile import attach
        reg = attach(ona)
        # reg.concepts(), reg.table_for("compensation"), ...

    Equivalent to ``SchemaRegistry.from_duckona(ona)``.
    """
    return SchemaRegistry.from_duckona(ona)
