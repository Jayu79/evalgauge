from evalgauge.generate.corpus import DEFAULT_SPEC
import duckdb
import pytest

from evalgauge.gates import GateStatus, evaluate_gate
from evalgauge.offline import build_models, run, run_pipeline


def test_offline_run_is_complete_and_detector_input_is_blind(tmp_path, monkeypatch):
    seen_types = []

    from evalgauge.detect.detector import TwoTierDetector

    original = TwoTierDetector.detect

    def recording_detect(self, event):
        seen_types.append(type(event))
        assert not hasattr(event, "label")
        assert not hasattr(event, "family")
        return original(self, event)

    monkeypatch.setattr(TwoTierDetector, "detect", recording_detect)
    db_path = tmp_path / "run.duckdb"
    counts = run_pipeline(db_path, seed=7, run_id="test-run")

    assert counts["runs"] == 1
    assert counts["events"] == sum(DEFAULT_SPEC.values())
    assert counts["events"] == counts["ground_truth"] == counts["detections"]
    assert counts["events"] == counts["joined_results"]
    assert seen_types and all(t.__name__ == "Event" for t in seen_types)

    with duckdb.connect(str(db_path)) as connection:
        assert connection.execute(
            "select count(*) from main_marts.fct_classifications"
        ).fetchone()[0] == counts["events"]
        assert connection.execute(
            "select count(*) from main_metrics.mtr_performance_by_family"
        ).fetchone()[0] == 6


def test_offline_runs_append_and_dbt_metrics_stay_run_scoped(tmp_path):
    db_path = tmp_path / "runs.duckdb"
    first = run_pipeline(db_path, seed=11, run_id="baseline")
    second = run_pipeline(
        db_path, seed=11, run_id="candidate", baseline_run_id="baseline"
    )

    assert first["events"] == second["events"] == sum(DEFAULT_SPEC.values())

    with duckdb.connect(str(db_path)) as connection:
        assert connection.execute("select count(*) from runs").fetchone()[0] == 2
        assert connection.execute("select count(*) from events").fetchone()[0] == 3600
        assert connection.execute(
            "select count(distinct configuration_hash) from runs"
        ).fetchone()[0] == 1
        assert connection.execute(
            "select count(*) from main_marts.fct_classifications"
        ).fetchone()[0] == 3600
        assert connection.execute(
            """
            select run_id, count(*)
            from main_metrics.mtr_performance_by_family
            group by run_id
            order by run_id
            """
        ).fetchall() == [("baseline", 6), ("candidate", 6)]
        assert connection.execute(
            "select count(*) from main_marts.fct_case_comparisons"
        ).fetchone()[0] == 1800
        assert connection.execute(
            "select count(*) from main_metrics.mtr_run_comparisons"
        ).fetchone()[0] == 6

    assert evaluate_gate(db_path, "candidate").status is GateStatus.PASS


def test_dbt_rejects_comparison_across_different_datasets(tmp_path):
    db_path = tmp_path / "incompatible.duckdb"
    run(db_path, seed=21, run_id="baseline")
    run(
        db_path,
        seed=22,
        run_id="candidate",
        baseline_run_id="baseline",
    )

    with pytest.raises(RuntimeError, match="dbt build failed"):
        build_models(db_path)
    with pytest.raises(ValueError, match="not case-compatible"):
        evaluate_gate(db_path, "candidate")
