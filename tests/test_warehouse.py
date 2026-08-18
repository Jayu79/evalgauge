from dataclasses import replace
from datetime import datetime

import duckdb
import pytest

from evalgauge.detect import Band, Detection
from evalgauge.generate import Family, Label, LabeledPrompt
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


def test_round_trip_preserves_provenance_and_measurement_fields():
    event, truth, detection = records()
    with Warehouse() as warehouse:
        warehouse.ingest_run([event], [truth], [detection])
        row = warehouse.joined_results()[0]

    assert row.event_id == event.event_id
    assert row.ts == event.ts
    assert row.source == truth.source
    assert row.is_synthetic is True
    assert row.tier1_band == "clear_benign"
    assert row.latency_ms == 1.25
    assert row.judge_cost_usd == 0.0


def test_identical_duplicates_are_noops_but_conflicts_fail():
    event, truth, detection = records()
    with Warehouse() as warehouse:
        warehouse.ingest_run([event], [truth], [detection])
        warehouse.ingest_run([event], [truth], [detection])
        assert warehouse.counts()["joined_results"] == 1
        with pytest.raises(ConflictError, match="conflicting events"):
            warehouse.ingest_event(replace(event, text="changed"))


@pytest.mark.parametrize("kind", ["truth", "detection"])
def test_orphan_references_are_rejected(kind):
    _, truth, detection = records("missing")
    with Warehouse() as warehouse, pytest.raises(duckdb.ConstraintException):
        if kind == "truth":
            warehouse.ingest_ground_truth(truth)
        else:
            warehouse.ingest_detection(detection)


def test_complete_join_rejects_missing_reference_side():
    event, _, _ = records()
    with Warehouse() as warehouse:
        warehouse.ingest_event(event)
        assert warehouse.joined_results(require_complete=False) == []
        with pytest.raises(ValueError, match="missing ground truth or detection"):
            warehouse.joined_results()


def test_failed_atomic_run_leaves_no_partial_rows():
    event, truth, detection = records()
    with Warehouse() as warehouse:
        with pytest.raises(duckdb.ConstraintException):
            warehouse.ingest_run([event], [], [replace(detection, tier1_score=2.0)])
        assert warehouse.counts()["events"] == 0

