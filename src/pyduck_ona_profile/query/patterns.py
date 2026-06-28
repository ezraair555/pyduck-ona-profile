"""Seed pattern bank for HR analytics queries.

Each ``QueryPattern`` is a small, hand-written SQL template with a few
example phrasings used for embedding similarity. To grow the bank, use
``PatternMatcher.add_example`` (see ``matcher.py``) or write new
``QueryPattern`` entries here.

The SQL templates use ``{schema_table_<concept>}`` placeholders so the
``ask()`` helper can resolve them against a real ``SchemaRegistry`` at
query time. This keeps patterns decoupled from the actual table names
the user happens to have loaded.
"""

from pyduck_ona_profile.query.matcher import QueryPattern

# A pattern's SQL can reference tables via {schema_table_<concept>}.
# Example: {schema_table_identity} resolves to the identity table name.


MANAGER_CHANGE_FREQUENCY = QueryPattern(
    pattern_id="mgr_change_frequency",
    examples=(
        "employees with the most managers in the last 24 months",
        "people who changed managers the most",
        "most reorged employees",
        "employees with the highest manager turnover",
        "who has had the most bosses lately",
        "frequent manager changes",
        "reorg victims",
        "employees whose manager changed many times",
    ),
    slot_phrasings={
        "window_months": (
            "24 months",
            "2 years",
            "1 year",
            "12 months",
            "6 months",
            "18 months",
        ),
    },
    sql_template="""
        SELECT m.employee_id, COUNT(DISTINCT m.new_manager_id) AS manager_changes
        FROM manager_changes m
        WHERE m.change_date >= CURRENT_DATE - INTERVAL '{window_months} months'
        GROUP BY m.employee_id
        ORDER BY manager_changes DESC
        LIMIT 50
    """,
)


HIGH_SPAN_OF_CONTROL = QueryPattern(
    pattern_id="high_span_of_control",
    examples=(
        "managers with the most direct reports",
        "who has the biggest team",
        "highest span of control managers",
        "managers overseeing the most people",
        "largest team managers",
        "managers with too many direct reports",
    ),
    slot_phrasings={},
    sql_template="""
        SELECT supervisor_id, COUNT(*) AS direct_reports
        FROM {schema_table_identity}
        WHERE supervisor_id IS NOT NULL
        GROUP BY supervisor_id
        ORDER BY direct_reports DESC
        LIMIT 25
    """,
)


FLIGHT_RISK_HIGH_TENURE = QueryPattern(
    pattern_id="flight_risk_high_tenure",
    examples=(
        "high-tenure employees at flight risk",
        "long-tenured employees likely to leave",
        "experienced employees showing attrition signals",
        "tenured people who might quit",
        "flight risks among senior employees",
    ),
    slot_phrasings={},
    sql_template="""
        SELECT i.employee_id, i.tenure_years, t.termination_date IS NOT NULL AS termed
        FROM {schema_table_identity} i
        LEFT JOIN {schema_table_turnover} t USING (employee_id)
        WHERE i.tenure_years >= 5
        ORDER BY i.tenure_years DESC
        LIMIT 100
    """,
)


COMPENSATION_OUTLIERS = QueryPattern(
    pattern_id="compensation_outliers",
    examples=(
        "compensation outliers vs peers",
        "who is overpaid or underpaid",
        "salary outliers within level",
        "compensation anomalies",
        "pay outside normal range for level",
    ),
    slot_phrasings={},
    sql_template="""
        WITH peer_stats AS (
            SELECT i.level, AVG(c.salary) AS mean_salary, STDDEV(c.salary) AS std_salary
            FROM {schema_table_compensation} c
            JOIN {schema_table_identity} i ON i.employee_id = c.employee_id
            GROUP BY i.level
        )
        SELECT c.employee_id, i.level, c.salary, p.mean_salary, p.std_salary,
               (c.salary - p.mean_salary) / NULLIF(p.std_salary, 0) AS z_score
        FROM {schema_table_compensation} c
        JOIN {schema_table_identity} i ON i.employee_id = c.employee_id
        JOIN peer_stats p ON p.level = i.level
        WHERE ABS((c.salary - p.mean_salary) / NULLIF(p.std_salary, 0)) > 2.0
        ORDER BY ABS((c.salary - p.mean_salary) / NULLIF(p.std_salary, 0)) DESC
        LIMIT 50
    """,
)


PROMOTION_RECENT = QueryPattern(
    pattern_id="promotion_recent",
    examples=(
        "employees promoted recently",
        "recent promotions",
        "who got promoted this year",
        "latest promotions",
        "promotions in the last 12 months",
    ),
    slot_phrasings={
        "window_months": ("12 months", "1 year", "6 months", "24 months", "2 years"),
    },
    sql_template="""
        SELECT employee_id, old_title, new_title, promotion_date
        FROM {schema_table_mobility}
        WHERE promotion_date >= CURRENT_DATE - INTERVAL '{window_months} months'
        ORDER BY promotion_date DESC
        LIMIT 100
    """,
)


DEPARTMENT_HEADCOUNT = QueryPattern(
    pattern_id="department_headcount",
    examples=(
        "headcount by department",
        "how many people in each department",
        "department sizes",
        "team sizes by department",
    ),
    slot_phrasings={},
    sql_template="""
        SELECT department, COUNT(*) AS headcount
        FROM {schema_table_identity}
        WHERE termination_date IS NULL
        GROUP BY department
        ORDER BY headcount DESC
    """,
)


CENTRALITY_LEADERS = QueryPattern(
    pattern_id="centrality_leaders",
    examples=(
        "most central people in the network",
        "who has the highest betweenness",
        "top influencers by pagerank",
        "key connectors in the org chart",
        "most central employees",
    ),
    slot_phrasings={},
    sql_template="""
        SELECT employee_id, betweenness, pagerank
        FROM centrality_scores
        ORDER BY betweenness DESC, pagerank DESC
        LIMIT 25
    """,
)


LOW_ENGAGEMENT_TEAMS = QueryPattern(
    pattern_id="low_engagement_teams",
    examples=(
        "teams with low engagement",
        "managers whose teams are disengaged",
        "low survey scores by manager",
        "where is engagement dropping",
    ),
    slot_phrasings={},
    sql_template="""
        SELECT i.supervisor_id AS manager_id, AVG(s.score) AS avg_score, COUNT(*) AS responses
        FROM {schema_table_identity} i
        JOIN {schema_table_engagement} s USING (employee_id)
        WHERE i.termination_date IS NULL
        GROUP BY i.supervisor_id
        HAVING COUNT(*) >= 3 AND AVG(s.score) < 3.5
        ORDER BY avg_score ASC
        LIMIT 25
    """,
)


NEW_HIRES_RECENT = QueryPattern(
    pattern_id="new_hires_recent",
    examples=(
        "recent hires",
        "new employees this quarter",
        "who started recently",
        "latest hires",
    ),
    slot_phrasings={
        "window_months": ("3 months", "6 months", "12 months", "1 year"),
    },
    sql_template="""
        SELECT employee_id, name, department, hire_date
        FROM {schema_table_identity}
        WHERE hire_date >= CURRENT_DATE - INTERVAL '{window_months} months'
        ORDER BY hire_date DESC
        LIMIT 100
    """,
)


ATTRITION_RATE_RECENT = QueryPattern(
    pattern_id="attrition_rate_recent",
    examples=(
        "recent attrition rate",
        "how many people left recently",
        "turnover rate last quarter",
        "recent terminations",
    ),
    slot_phrasings={
        "window_months": (
            "12 months",
            "1 year",
            "6 months",
            "3 months",
            "24 months",
            "2 years",
        ),
    },
    sql_template="""
        SELECT
            COUNT(*) AS terminations,
            (SELECT COUNT(*) FROM {schema_table_identity}
             WHERE termination_date IS NULL OR termination_date >= CURRENT_DATE - INTERVAL '{window_months} months') AS active_population,
            CAST(COUNT(*) AS DOUBLE) / NULLIF(
                (SELECT COUNT(*) FROM {schema_table_identity}), 0
            ) AS attrition_rate
        FROM {schema_table_turnover}
        WHERE termination_date >= CURRENT_DATE - INTERVAL '{window_months} months'
    """,
)


SEED_PATTERNS = (
    MANAGER_CHANGE_FREQUENCY,
    HIGH_SPAN_OF_CONTROL,
    FLIGHT_RISK_HIGH_TENURE,
    COMPENSATION_OUTLIERS,
    PROMOTION_RECENT,
    DEPARTMENT_HEADCOUNT,
    CENTRALITY_LEADERS,
    LOW_ENGAGEMENT_TEAMS,
    NEW_HIRES_RECENT,
    ATTRITION_RATE_RECENT,
)
