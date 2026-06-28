"""Subject: a per-employee view that joins every loaded table on employee_id.

The Subject class is the answer to "give me everything we know about this
person". Internally it joins the loaded relations in the DuckONA instance on
the registered employee column and returns a typed record per concept
(identity, position, compensation, etc.).

For PII gating, ``Subject.with_role()`` returns a view that redacts fields
the role shouldn't see (e.g., a manager doesn't see their reports' salaries).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from pyduck_ona_profile.schema import ConceptBinding, SchemaRegistry

# Fields redacted for each non-HR role. HR roles (hrbp, hr_business_partner,
# compensation_analyst) see the full record.
REDACTION_BY_ROLE: dict[str, set[str]] = {
    "manager": {"salary", "compensation_history", "engagement_score", "tenure_years"},
    "executive": {"engagement_score"},
    "self": {"salary", "manager_id"},  # employees don't see comp or skip-level
}


@dataclass
class Profile:
    """A typed per-concept view of one employee."""

    identity: dict[str, Any] | None
    position: dict[str, Any] | None
    compensation: dict[str, Any] | None
    mobility: dict[str, Any] | None
    attendance: dict[str, Any] | None
    engagement: dict[str, Any] | None
    skills: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "position": self.position,
            "compensation": self.compensation,
            "mobility": self.mobility,
            "attendance": self.attendance,
            "engagement": self.engagement,
            "skills": self.skills,
        }


class Subject:
    """A single employee viewed through every loaded concept."""

    def __init__(
        self,
        employee_id: str,
        ona: Any,
        *,
        registry: SchemaRegistry | None = None,
    ) -> None:
        self.employee_id = employee_id
        self._ona = ona
        self._registry = registry or SchemaRegistry.from_duckona(ona)

    def profile(self) -> Profile:
        """Return a typed per-concept view of this employee."""
        return Profile(
            identity=self._concept_record("identity")
            or {"employee_id": self.employee_id},
            position=self._position_view(),
            compensation=self._concept_record("compensation"),
            mobility=self._concept_record("mobility"),
            attendance=self._concept_record("attendance"),
            engagement=self._concept_record("engagement"),
            skills=self._concept_record("skills"),
        )

    def with_role(self, role: str) -> Profile:
        """Return a profile with fields redacted according to the role.

        Supported roles: ``hrbp`` (full view), ``manager``, ``executive``,
        ``self``. Unknown roles behave like ``hrbp`` (full view).
        """
        full = self.profile()
        redacted_fields = REDACTION_BY_ROLE.get(role, set())
        if not redacted_fields:
            return full
        return Profile(
            identity=_redact(full.identity, redacted_fields),
            position=_redact(full.position, redacted_fields),
            compensation=(
                _redact(full.compensation, redacted_fields)
                if full.compensation
                else None
            ),
            mobility=_redact(full.mobility, redacted_fields) if full.mobility else None,
            attendance=(
                _redact(full.attendance, redacted_fields) if full.attendance else None
            ),
            engagement=(
                _redact(full.engagement, redacted_fields) if full.engagement else None
            ),
            skills=_redact(full.skills, redacted_fields) if full.skills else None,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _concept_record(self, concept: str) -> dict[str, Any] | None:
        """Pull a single row from the table bound to ``concept``."""
        binding = self._registry.table_for(concept)
        if binding is None:
            return None
        df = self._relation_to_df(binding)
        if df is None or df.empty:
            return None
        row = df[df[binding.employee_col] == self.employee_id]
        if row.empty:
            return None
        return row.iloc[0].to_dict()

    def _position_view(self) -> dict[str, Any]:
        """Derive a position view (manager, level, span) from the identity table."""
        ident = self._concept_record("identity") or {}
        # Span of control: count employees with supervisor_id == this id
        binding = self._registry.table_for("identity")
        span = 0
        if binding is not None:
            df = self._relation_to_df(binding)
            if df is not None and not df.empty and "supervisor_id" in df.columns:
                span = int((df["supervisor_id"] == self.employee_id).sum())
        return {
            "employee_id": self.employee_id,
            "manager_id": ident.get("supervisor_id") or ident.get("manager_id"),
            "level": ident.get("level") or ident.get("job_level"),
            "department": ident.get("department"),
            "title": ident.get("title") or ident.get("job_title"),
            "direct_reports": span,
        }

    def _relation_to_df(self, binding: ConceptBinding) -> pd.DataFrame | None:
        """Best-effort fetch of the underlying relation as a DataFrame."""
        # NB: pandas DataFrames raise on truthiness, so we can't use `or`.
        rel = getattr(self._ona, binding.table, None)
        if rel is None:
            rel = getattr(self._ona, "_" + binding.table, None)
        if rel is None:
            return None
        try:
            if isinstance(rel, pd.DataFrame):
                return rel
            if hasattr(rel, "df"):
                return rel.df()
            if hasattr(rel, "arrow"):
                return rel.arrow().to_pandas()
        except Exception:
            return None
        return None


def _redact(d: dict[str, Any] | None, fields: set[str]) -> dict[str, Any] | None:
    """Return a copy of ``d`` with values for ``fields`` replaced by None."""
    if d is None:
        return None
    return {k: (None if k in fields else v) for k, v in d.items()}


# mypy: disable-error-code=no-any-return
