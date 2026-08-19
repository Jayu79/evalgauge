"""DuckDB landing layer for versioned runs, blind events, truth, and detections."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from ..detect.schema import Detection
from ..runs import EvalRun, RunStatus
from ..stream.event import Event, GroundTruth


class ConflictError(ValueError):
    """An immutable ID was replayed with a different payload."""


@dataclass(frozen=True)
class JoinedResult:
    run_id: str
    event_id: str
    ts: Any
    prompt_hash: str
    text: str
    family: str
    label: str
    is_synthetic: bool
    source: str
    objective: str
    tier1_score: float
    tier1_band: str
    tier1_flag: bool
    escalated_to_judge: bool
    judge_verdict: bool | None
    final_flag: bool
    decided_by: str
    latency_ms: float
    judge_cost_usd: float
    judge_rationale: str | None
    judge_model: str | None


_DDL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id VARCHAR PRIMARY KEY,
    status VARCHAR NOT NULL CHECK (status IN ('completed', 'failed')),
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL,
    dataset_name VARCHAR NOT NULL,
    dataset_version VARCHAR NOT NULL,
    dataset_hash VARCHAR NOT NULL,
    detector_version VARCHAR NOT NULL,
    judge_model VARCHAR NOT NULL,
    policy_version VARCHAR NOT NULL,
    configuration_hash VARCHAR NOT NULL,
    seed BIGINT NOT NULL,
    low_threshold DOUBLE NOT NULL CHECK (low_threshold BETWEEN 0 AND 1),
    high_threshold DOUBLE NOT NULL CHECK (high_threshold BETWEEN 0 AND 1),
    git_sha VARCHAR NOT NULL,
    baseline_run_id VARCHAR REFERENCES runs(run_id),
    CHECK (completed_at >= started_at),
    CHECK (low_threshold <= high_threshold),
    CHECK (baseline_run_id IS NULL OR baseline_run_id <> run_id)
);
CREATE TABLE IF NOT EXISTS events (
    run_id VARCHAR NOT NULL REFERENCES runs(run_id),
    event_id VARCHAR NOT NULL,
    ts TIMESTAMP NOT NULL,
    prompt_hash VARCHAR NOT NULL,
    text VARCHAR NOT NULL,
    PRIMARY KEY (run_id, event_id)
);
CREATE TABLE IF NOT EXISTS ground_truth (
    run_id VARCHAR NOT NULL,
    event_id VARCHAR NOT NULL,
    family VARCHAR NOT NULL,
    label VARCHAR NOT NULL CHECK (label IN ('attack', 'benign')),
    is_synthetic BOOLEAN NOT NULL,
    source VARCHAR NOT NULL,
    objective VARCHAR NOT NULL,
    PRIMARY KEY (run_id, event_id),
    FOREIGN KEY (run_id, event_id) REFERENCES events(run_id, event_id)
);
CREATE TABLE IF NOT EXISTS detections (
    run_id VARCHAR NOT NULL,
    event_id VARCHAR NOT NULL,
    tier1_score DOUBLE NOT NULL CHECK (tier1_score BETWEEN 0 AND 1),
    tier1_band VARCHAR NOT NULL CHECK (
        tier1_band IN ('clear_benign', 'ambiguous', 'clear_attack')
    ),
    tier1_flag BOOLEAN NOT NULL,
    escalated_to_judge BOOLEAN NOT NULL,
    judge_verdict BOOLEAN,
    final_flag BOOLEAN NOT NULL,
    decided_by VARCHAR NOT NULL CHECK (decided_by IN ('fast', 'judge')),
    latency_ms DOUBLE NOT NULL CHECK (latency_ms >= 0),
    judge_cost_usd DOUBLE NOT NULL CHECK (judge_cost_usd >= 0),
    judge_rationale VARCHAR,
    judge_model VARCHAR,
    PRIMARY KEY (run_id, event_id),
    FOREIGN KEY (run_id, event_id) REFERENCES events(run_id, event_id),
    CHECK (
        (escalated_to_judge AND decided_by = 'judge' AND judge_verdict IS NOT NULL)
        OR
        (NOT escalated_to_judge AND decided_by = 'fast' AND judge_verdict IS NULL)
    )
);
CREATE OR REPLACE VIEW joined_results AS
SELECT
    e.run_id, e.event_id, e.ts, e.prompt_hash, e.text,
    g.family, g.label, g.is_synthetic, g.source, g.objective,
    d.tier1_score, d.tier1_band, d.tier1_flag, d.escalated_to_judge,
    d.judge_verdict, d.final_flag, d.decided_by, d.latency_ms,
    d.judge_cost_usd, d.judge_rationale, d.judge_model
FROM events e
JOIN ground_truth g
    ON e.run_id = g.run_id AND e.event_id = g.event_id
JOIN detections d
    ON e.run_id = d.run_id AND e.event_id = d.event_id;
"""


_RUN_COLUMNS = (
    "run_id", "status", "started_at", "completed_at", "dataset_name",
    "dataset_version", "dataset_hash", "detector_version", "judge_model",
    "policy_version", "seed", "low_threshold", "high_threshold", "git_sha",
    "baseline_run_id",
)

_RUN_STORAGE_COLUMNS = _RUN_COLUMNS[:10] + ("configuration_hash",) + _RUN_COLUMNS[10:]


class Warehouse:
    """Owns run-aware schema creation and immutable, idempotent ingestion."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self.connection = duckdb.connect(self.path)
        event_columns = {
            row[0]
            for row in self.connection.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'main' AND table_name = 'events'
                """
            ).fetchall()
        }
        if event_columns and "run_id" not in event_columns:
            self.connection.close()
            raise RuntimeError(
                "legacy v0.1.0 warehouse detected; rebuild it with --replace "
                "before using run-aware storage"
            )
        self.connection.execute(_DDL)

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "Warehouse":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _insert_immutable(
        self,
        table: str,
        columns: tuple[str, ...],
        values: tuple[Any, ...],
        *,
        key_columns: tuple[str, ...],
    ) -> bool:
        key_values = values[: len(key_columns)]
        where = " AND ".join(f"{column} = ?" for column in key_columns)
        existing = self.connection.execute(
            f"SELECT {', '.join(columns)} FROM {table} WHERE {where}",
            key_values,
        ).fetchone()
        if existing is not None:
            if tuple(existing) == values:
                return False
            rendered_key = ", ".join(
                f"{column}={value}" for column, value in zip(key_columns, key_values)
            )
            raise ConflictError(f"conflicting {table} record for {rendered_key}")

        placeholders = ", ".join("?" for _ in columns)
        self.connection.execute(
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
            values,
        )
        return True

    def ingest_manifest(self, run: EvalRun) -> bool:
        return self._insert_immutable(
            "runs",
            _RUN_STORAGE_COLUMNS,
            (
                run.run_id,
                run.status.value,
                run.started_at,
                run.completed_at,
                run.dataset_name,
                run.dataset_version,
                run.dataset_hash,
                run.detector_version,
                run.judge_model,
                run.policy_version,
                run.configuration_hash,
                run.seed,
                run.low_threshold,
                run.high_threshold,
                run.git_sha,
                run.baseline_run_id,
            ),
            key_columns=("run_id",),
        )

    def ingest_event(self, run_id: str, event: Event) -> bool:
        return self._insert_immutable(
            "events",
            ("run_id", "event_id", "ts", "prompt_hash", "text"),
            (run_id, event.event_id, event.ts, event.prompt_hash, event.text),
            key_columns=("run_id", "event_id"),
        )

    def ingest_ground_truth(self, run_id: str, truth: GroundTruth) -> bool:
        return self._insert_immutable(
            "ground_truth",
            (
                "run_id", "event_id", "family", "label", "is_synthetic",
                "source", "objective",
            ),
            (
                run_id,
                truth.event_id,
                truth.family.value,
                truth.label.value,
                truth.is_synthetic,
                truth.source,
                truth.objective,
            ),
            key_columns=("run_id", "event_id"),
        )

    def ingest_detection(self, run_id: str, detection: Detection) -> bool:
        return self._insert_immutable(
            "detections",
            (
                "run_id", "event_id", "tier1_score", "tier1_band", "tier1_flag",
                "escalated_to_judge", "judge_verdict", "final_flag", "decided_by",
                "latency_ms", "judge_cost_usd", "judge_rationale", "judge_model",
            ),
            (
                run_id,
                detection.event_id,
                detection.tier1_score,
                detection.tier1_band.value,
                detection.tier1_flag,
                detection.escalated_to_judge,
                detection.judge_verdict,
                detection.final_flag,
                detection.decided_by,
                detection.latency_ms,
                detection.judge_cost_usd,
                detection.judge_rationale,
                detection.judge_model,
            ),
            key_columns=("run_id", "event_id"),
        )

    def ingest_run(
        self,
        run: EvalRun,
        events: Iterable[Event],
        truths: Iterable[GroundTruth],
        detections: Iterable[Detection],
    ) -> None:
        """Atomically append one manifested run, preserving foreign-key order."""
        self.connection.execute("BEGIN")
        try:
            self.ingest_manifest(run)
            for event in events:
                self.ingest_event(run.run_id, event)
            for truth in truths:
                self.ingest_ground_truth(run.run_id, truth)
            for detection in detections:
                self.ingest_detection(run.run_id, detection)
        except Exception:
            self.connection.execute("ROLLBACK")
            raise
        self.connection.execute("COMMIT")

    def manifest(self, run_id: str) -> EvalRun:
        row = self.connection.execute(
            f"SELECT {', '.join(_RUN_COLUMNS)} FROM runs WHERE run_id = ?",
            [run_id],
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown run_id={run_id}")
        values = list(row)
        values[1] = RunStatus(values[1])
        return EvalRun(*values)

    def joined_results(
        self, run_id: str | None = None, *, require_complete: bool = True
    ) -> list[JoinedResult]:
        run_filter = "AND e.run_id = ?" if run_id is not None else ""
        parameters = [run_id] if run_id is not None else []
        if require_complete:
            missing = self.connection.execute(
                f"""
                SELECT e.run_id, e.event_id
                FROM events e
                LEFT JOIN ground_truth g
                    ON e.run_id = g.run_id AND e.event_id = g.event_id
                LEFT JOIN detections d
                    ON e.run_id = d.run_id AND e.event_id = d.event_id
                WHERE (g.event_id IS NULL OR d.event_id IS NULL)
                {run_filter}
                ORDER BY e.run_id, e.event_id
                """,
                parameters,
            ).fetchall()
            if missing:
                ids = ", ".join(f"{row[0]}/{row[1]}" for row in missing[:5])
                raise ValueError(f"events missing ground truth or detection: {ids}")

        where = "WHERE run_id = ?" if run_id is not None else ""
        rows = self.connection.execute(
            f"SELECT * FROM joined_results {where} ORDER BY run_id, event_id",
            parameters,
        ).fetchall()
        return [JoinedResult(*row) for row in rows]

    def counts(self, run_id: str | None = None) -> dict[str, int]:
        counts: dict[str, int] = {}
        for table in ("runs", "events", "ground_truth", "detections", "joined_results"):
            where = " WHERE run_id = ?" if run_id is not None else ""
            parameters = [run_id] if run_id is not None else []
            counts[table] = self.connection.execute(
                f"SELECT count(*) FROM {table}{where}", parameters
            ).fetchone()[0]
        return counts
