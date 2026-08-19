from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import duckdb
import pytest

from evalgauge.detect import Band, Detection
from evalgauge.generate import Family, Label, LabeledPrompt
from evalgauge.runs import EvalRun, RunStatus
from evalgauge.stream import Event, GroundTruth, split
from evalgauge.warehouse import ConflictError, Warehouse


def records(event_id: str = "evt-1"):
    prompt = LabeledPrompt(
        text="ordinary prompt",
        family=Family.BENIGN,
        label=Label.BENIGN,
        is_synthetic=True,
        source="synthetic:test.v1",
        objective="test",
    )
    event, truth = split(prompt, event_id=event_id, ts=datetime(2026, 1, 1))
    detection = Detection(
        event_id=event_id,
        tier1_score=0.1,
        tier1_band=Band.CLEAR_BENIGN,
        tier1_flag=False,
        escalated_to_judge=False,
        judge_verdict=None,
        final_flag=False,
        decided_by="fast",
        latency_ms=1.25,
        judge_cost_usd=0.0,
    )
    return event, truth, detection


def manifest(run_id: str = "run-1", baseline_run_id: str | None = None):
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return EvalRun(
        run_id=run_id,
        status=RunStatus.COMPLETED,
        started_at=started,
        completed_at=started,
        dataset_name="test-dataset",
        dataset_version="v1",
        dataset_hash="sha256:test",
        detector_version="detector.v1",
        judge_model="stub",
        policy_version="policy.v1",
        seed=1,
        low_threshold=0.5,
        high_threshold=0.85,
        git_sha="abc123",
        baseline_run_id=baseline_run_id,
    )


def test_round_trip_preserves_provenance_and_measurement_fields():
    event, truth, detection = records()
    run = manifest()
    with Warehouse() as warehouse:
        warehouse.ingest_run(run, [event], [truth], [detection])
        row = warehouse.joined_results(run.run_id)[0]

    assert row.run_id == run.run_id
    assert row.event_id == event.event_id
    assert row.ts == event.ts
    assert row.source == truth.source
    assert row.is_synthetic is True
    assert row.tier1_band == "clear_benign"
    assert row.latency_ms == 1.25
    assert row.judge_cost_usd == 0.0


def test_identical_duplicates_are_noops_but_conflicts_fail():
    event, truth, detection = records()
    run = manifest()
    with Warehouse() as warehouse:
        warehouse.ingest_run(run, [event], [truth], [detection])
        warehouse.ingest_run(run, [event], [truth], [detection])
        assert warehouse.counts(run.run_id)["joined_results"] == 1
        with pytest.raises(ConflictError, match="conflicting events"):
            warehouse.ingest_event(run.run_id, replace(event, text="changed"))

        with pytest.raises(ConflictError, match="conflicting runs"):
            warehouse.ingest_manifest(replace(run, detector_version="detector.v2"))


@pytest.mark.parametrize("kind", ["truth", "detection"])
def test_orphan_references_are_rejected(kind):
    _, truth, detection = records("missing")
    run = manifest()
    with Warehouse() as warehouse, pytest.raises(duckdb.ConstraintException):
        warehouse.ingest_manifest(run)
        if kind == "truth":
            warehouse.ingest_ground_truth(run.run_id, truth)
        else:
            warehouse.ingest_detection(run.run_id, detection)


def test_complete_join_rejects_missing_reference_side():
    event, _, _ = records()
    run = manifest()
    with Warehouse() as warehouse:
        warehouse.ingest_manifest(run)
        warehouse.ingest_event(run.run_id, event)
        assert warehouse.joined_results(run.run_id, require_complete=False) == []
        with pytest.raises(ValueError, match="missing ground truth or detection"):
            warehouse.joined_results(run.run_id)


def test_failed_atomic_run_leaves_no_partial_rows():
    event, truth, detection = records()
    run = manifest()
    with Warehouse() as warehouse:
        with pytest.raises(duckdb.ConstraintException):
            warehouse.ingest_run(
                run, [event], [], [replace(detection, tier1_score=2.0)]
            )
        assert warehouse.counts()["runs"] == 0
        assert warehouse.counts()["events"] == 0


def test_same_event_id_is_isolated_across_runs():
    event, truth, detection = records()
    baseline = manifest("run-baseline")
    candidate = manifest("run-candidate", baseline_run_id=baseline.run_id)

    with Warehouse() as warehouse:
        warehouse.ingest_run(baseline, [event], [truth], [detection])
        warehouse.ingest_run(
            candidate,
            [event],
            [truth],
            [
                replace(
                    detection,
                    tier1_score=0.9,
                    tier1_band=Band.CLEAR_ATTACK,
                    tier1_flag=True,
                    final_flag=True,
                )
            ],
        )

        assert warehouse.counts()["runs"] == 2
        assert warehouse.counts()["events"] == 2
        assert warehouse.joined_results(baseline.run_id)[0].final_flag is False
        assert warehouse.joined_results(candidate.run_id)[0].final_flag is True
        assert warehouse.manifest(candidate.run_id).baseline_run_id == baseline.run_id
        stored_hashes = warehouse.connection.execute(
            "select distinct configuration_hash from runs"
        ).fetchall()
        assert stored_hashes == [(baseline.configuration_hash,)]


def test_join_never_combines_missing_sides_from_different_runs():
    event, truth, detection = records()
    first = manifest("run-first")
    second = manifest("run-second")

    with Warehouse() as warehouse:
        warehouse.ingest_manifest(first)
        warehouse.ingest_event(first.run_id, event)
        warehouse.ingest_ground_truth(first.run_id, truth)
        warehouse.ingest_manifest(second)
        warehouse.ingest_event(second.run_id, event)
        warehouse.ingest_detection(second.run_id, detection)

        assert warehouse.joined_results(require_complete=False) == []
        with pytest.raises(ValueError, match="run-first/evt-1"):
            warehouse.joined_results()


def test_missing_baseline_run_is_rejected_atomically():
    event, truth, detection = records()
    candidate = manifest("run-candidate", baseline_run_id="missing-run")

    with Warehouse() as warehouse, pytest.raises(duckdb.ConstraintException):
        warehouse.ingest_run(candidate, [event], [truth], [detection])


def test_legacy_single_run_database_requires_explicit_rebuild(tmp_path):
    path = tmp_path / "legacy.duckdb"
    with duckdb.connect(str(path)) as connection:
        connection.execute("create table events (event_id varchar primary key)")

    with pytest.raises(RuntimeError, match="legacy v0.1.0 warehouse.*--replace"):
        Warehouse(path)
