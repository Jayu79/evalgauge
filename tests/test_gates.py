import pytest

from evalgauge.gates import GateStatus, RegressionPolicy, evaluate_comparison_rows


def evaluate(rows):
    return evaluate_comparison_rows("candidate", "baseline", rows, RegressionPolicy())


def test_gate_passes_without_material_degradation():
    result = evaluate([("encoding", 0.01, 0.0), ("role_play", 0.0, 0.0)])
    assert result.status is GateStatus.PASS
    assert result.findings == ()


def test_gate_warns_before_failure_threshold():
    result = evaluate([("encoding", -0.02, 0.002)])
    assert result.status is GateStatus.WARN
    assert {finding.metric for finding in result.findings} == {
        "family_catch_rate_drop", "false_positive_rate_increase"
    }


def test_any_failed_rule_fails_the_gate():
    result = evaluate([("encoding", -0.06, 0.0)])
    assert result.status is GateStatus.FAIL
    assert result.findings[0].evaluation_family == "encoding"


def test_policy_rejects_inverted_thresholds():
    with pytest.raises(ValueError, match="0 <= warn <= fail <= 1"):
        RegressionPolicy(
            warn_family_catch_rate_drop=0.2,
            fail_family_catch_rate_drop=0.1,
        )


def test_gate_rejects_empty_comparison():
    with pytest.raises(ValueError, match="no comparison rows"):
        evaluate([])


def test_gate_rejects_inconsistent_global_false_positive_delta():
    with pytest.raises(ValueError, match="disagree on evaluation-wide"):
        evaluate([("encoding", 0.0, 0.0), ("role_play", 0.0, 0.1)])
