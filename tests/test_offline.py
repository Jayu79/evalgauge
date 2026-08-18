from evalgauge.generate.corpus import DEFAULT_SPEC
import duckdb

from evalgauge.offline import run_pipeline


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
    counts = run_pipeline(db_path, seed=7)

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
