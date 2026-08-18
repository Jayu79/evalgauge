"""Small, strict DuckDB landing layer that mirrors the eventual Snowflake boundary.

Raw records remain separate: detector-visible events, held-aside ground truth, and
blind detection outputs. They meet only in ``joined_results``, after the detector has
committed its decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import duckdb

from ..detect.schema import Detection
from ..stream.event import Event, GroundTruth


class ConflictError(ValueError):
    """An immutable ID was replayed with a different payload."""


@dataclass(frozen=True)
class JoinedResult:
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
CREATE TABLE IF NOT EXISTS events (
    event_id VARCHAR PRIMARY KEY,
    ts TIMESTAMP NOT NULL,
    prompt_hash VARCHAR NOT NULL,
    text VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS ground_truth (
    event_id VARCHAR PRIMARY KEY REFERENCES events(event_id),
    family VARCHAR NOT NULL,
    label VARCHAR NOT NULL CHECK (label IN ('attack', 'benign')),
    is_synthetic BOOLEAN NOT NULL,
    source VARCHAR NOT NULL,
    objective VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS detections (
    event_id VARCHAR PRIMARY KEY REFERENCES events(event_id),
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
    CHECK (
        (escalated_to_judge AND decided_by = 'judge' AND judge_verdict IS NOT NULL)
        OR
        (NOT escalated_to_judge AND decided_by = 'fast' AND judge_verdict IS NULL)
    )
);
CREATE OR REPLACE VIEW joined_results AS
SELECT
    e.event_id, e.ts, e.prompt_hash, e.text,
    g.family, g.label, g.is_synthetic, g.source, g.objective,
    d.tier1_score, d.tier1_band, d.tier1_flag, d.escalated_to_judge,
    d.judge_verdict, d.final_flag, d.decided_by, d.latency_ms,
    d.judge_cost_usd, d.judge_rationale, d.judge_model
FROM events e
JOIN ground_truth g USING (event_id)
JOIN detections d USING (event_id);
"""


class Warehouse:
    """Owns schema creation and immutable, idempotent raw-record ingestion."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self.connection = duckdb.connect(self.path)
        self.connection.execute(_DDL)

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "Warehouse":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _insert_immutable(
        self, table: str, columns: tuple[str, ...], values: tuple[Any, ...]
    ) -> bool:
        existing = self.connection.execute(
            f"SELECT {', '.join(columns)} FROM {table} WHERE event_id = ?",
            [values[0]],
        ).fetchone()
        if existing is not None:
            if tuple(existing) == values:
                return False
            raise ConflictError(f"conflicting {table} record for event_id={values[0]}")

        placeholders = ", ".join("?" for _ in columns)
        self.connection.execute(
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
            values,
        )
        return True

    def ingest_event(self, event: Event) -> bool:
        return self._insert_immutable(
            "events",
            ("event_id", "ts", "prompt_hash", "text"),
            (event.event_id, event.ts, event.prompt_hash, event.text),
        )

    def ingest_ground_truth(self, truth: GroundTruth) -> bool:
        return self._insert_immutable(
            "ground_truth",
            ("event_id", "family", "label", "is_synthetic", "source", "objective"),
            (
                truth.event_id,
                truth.family.value,
                truth.label.value,
                truth.is_synthetic,
                truth.source,
                truth.objective,
            ),
        )

    def ingest_detection(self, detection: Detection) -> bool:
        return self._insert_immutable(
            "detections",
            (
                "event_id", "tier1_score", "tier1_band", "tier1_flag",
                "escalated_to_judge", "judge_verdict", "final_flag", "decided_by",
                "latency_ms", "judge_cost_usd", "judge_rationale", "judge_model",
            ),
            (
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
        )

    def ingest_run(
        self,
        events: Iterable[Event],
        truths: Iterable[GroundTruth],
        detections: Iterable[Detection],
    ) -> None:
        """Atomically land a completed run, preserving foreign-key order."""
        self.connection.execute("BEGIN")
        try:
            for event in events:
                self.ingest_event(event)
            for truth in truths:
                self.ingest_ground_truth(truth)
            for detection in detections:
                self.ingest_detection(detection)
        except Exception:
            self.connection.execute("ROLLBACK")
            raise
        self.connection.execute("COMMIT")

    def joined_results(self, *, require_complete: bool = True) -> list[JoinedResult]:
        if require_complete:
            missing = self.connection.execute(
                """
                SELECT e.event_id
                FROM events e
                LEFT JOIN ground_truth g USING (event_id)
                LEFT JOIN detections d USING (event_id)
                WHERE g.event_id IS NULL OR d.event_id IS NULL
                ORDER BY e.event_id
                """
            ).fetchall()
            if missing:
                ids = ", ".join(row[0] for row in missing[:5])
                raise ValueError(f"events missing ground truth or detection: {ids}")
        rows = self.connection.execute(
            "SELECT * FROM joined_results ORDER BY event_id"
        ).fetchall()
        return [JoinedResult(*row) for row in rows]

    def counts(self) -> dict[str, int]:
        return {
            table: self.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("events", "ground_truth", "detections", "joined_results")
        }

