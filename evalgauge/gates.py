"""Configurable regression policies over modeled baseline/candidate comparisons."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

import duckdb


class GateStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True)
class RegressionPolicy:
    """Allowed degradation before a comparison warns or fails."""

    warn_family_catch_rate_drop: float = 0.01
    fail_family_catch_rate_drop: float = 0.05
    warn_false_positive_rate_increase: float = 0.001
    fail_false_positive_rate_increase: float = 0.01

    def __post_init__(self) -> None:
        pairs = (
            (self.warn_family_catch_rate_drop, self.fail_family_catch_rate_drop),
            (self.warn_false_positive_rate_increase, self.fail_false_positive_rate_increase),
        )
        if any(not 0 <= warn <= fail <= 1 for warn, fail in pairs):
            raise ValueError("gate thresholds must satisfy 0 <= warn <= fail <= 1")


@dataclass(frozen=True)
class GateFinding:
    metric: str
    evaluation_family: str
    observed_degradation: float
    threshold: float
    status: GateStatus


@dataclass(frozen=True)
class GateResult:
    candidate_run_id: str
    baseline_run_id: str
    status: GateStatus
    findings: tuple[GateFinding, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_run_id": self.candidate_run_id,
            "baseline_run_id": self.baseline_run_id,
            "status": self.status.value,
            "findings": [
                {**asdict(finding), "status": finding.status.value}
                for finding in self.findings
            ],
        }


def _finding(metric: str, family: str, degradation: float, warn: float, fail: float):
    if degradation > fail:
        return GateFinding(metric, family, degradation, fail, GateStatus.FAIL)
    if degradation > warn:
        return GateFinding(metric, family, degradation, warn, GateStatus.WARN)
    return None


def evaluate_comparison_rows(
    candidate_run_id: str,
    baseline_run_id: str,
    rows: Iterable[tuple[str, float, float]],
    policy: RegressionPolicy,
) -> GateResult:
    """Evaluate `(family, catch_delta, false_positive_delta)` modeled rows."""

    rows = tuple(rows)
    if not rows:
        raise ValueError(f"no comparison rows for candidate run {candidate_run_id}")
    false_positive_deltas = {row[2] for row in rows}
    if len(false_positive_deltas) != 1:
        raise ValueError("comparison rows disagree on evaluation-wide false-positive delta")

    findings: list[GateFinding] = []
    for family, catch_delta, _ in rows:
        finding = _finding(
            "family_catch_rate_drop",
            family,
            max(0.0, -catch_delta),
            policy.warn_family_catch_rate_drop,
            policy.fail_family_catch_rate_drop,
        )
        if finding:
            findings.append(finding)

    # False-positive burden is evaluation-wide and repeated beside each family row.
    finding = _finding(
        "false_positive_rate_increase",
        "benign",
        max(0.0, false_positive_deltas.pop()),
        policy.warn_false_positive_rate_increase,
        policy.fail_false_positive_rate_increase,
    )
    if finding:
        findings.append(finding)

    status = (
        GateStatus.FAIL
        if any(item.status is GateStatus.FAIL for item in findings)
        else GateStatus.WARN
        if findings
        else GateStatus.PASS
    )
    return GateResult(candidate_run_id, baseline_run_id, status, tuple(findings))


def evaluate_gate(
    db_path: str | Path,
    candidate_run_id: str,
    policy: RegressionPolicy | None = None,
) -> GateResult:
    """Load tested dbt comparison rows and evaluate one candidate run."""

    # dbt-duckdb may retain an in-process connection configuration after a build;
    # use DuckDB's default mode so this reader remains compatible with that pool.
    with duckdb.connect(str(db_path)) as connection:
        manifest = connection.execute(
            """
            select candidate.baseline_run_id, candidate.dataset_hash, baseline.dataset_hash
            from runs candidate
            left join runs baseline on candidate.baseline_run_id = baseline.run_id
            where candidate.run_id = ?
            """,
            [candidate_run_id],
        ).fetchone()
        if manifest is None:
            raise ValueError(f"unknown candidate run {candidate_run_id}")
        baseline_run_id, candidate_hash, baseline_hash = manifest
        if baseline_run_id is None:
            raise ValueError(f"run {candidate_run_id} has no baseline")
        if candidate_hash != baseline_hash:
            raise ValueError(
                f"candidate run {candidate_run_id} is not case-compatible with "
                f"baseline {baseline_run_id}"
            )
        counts = connection.execute(
            """
            select
                (select count(*) from main_marts.fct_classifications where run_id = ?),
                (select count(*) from main_marts.fct_classifications where run_id = ?),
                (select count(*) from main_marts.fct_case_comparisons
                    where candidate_run_id = ?),
                (select count(*) from main_marts.fct_case_comparisons
                    where candidate_run_id = ? and not is_compatible)
            """,
            [candidate_run_id, baseline_run_id, candidate_run_id, candidate_run_id],
        ).fetchone()
        if counts[:3] != (counts[0],) * 3 or counts[3]:
            raise ValueError(
                f"candidate run {candidate_run_id} is not case-compatible with "
                f"baseline {baseline_run_id}"
            )
        rows = connection.execute(
            """
            select evaluation_family, catch_rate_delta, false_positive_rate_delta
            from main_metrics.mtr_run_comparisons
            where candidate_run_id = ?
            order by evaluation_family
            """,
            [candidate_run_id],
        ).fetchall()
    return evaluate_comparison_rows(
        candidate_run_id, baseline_run_id, rows, policy or RegressionPolicy()
    )
