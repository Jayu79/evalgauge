"""Evaluate a stored candidate run against its declared baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .gates import GateStatus, RegressionPolicy, evaluate_gate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--candidate-run-id", required=True)
    parser.add_argument("--warn-catch-drop", default=0.01, type=float)
    parser.add_argument("--fail-catch-drop", default=0.05, type=float)
    parser.add_argument("--warn-fp-increase", default=0.001, type=float)
    parser.add_argument("--fail-fp-increase", default=0.01, type=float)
    args = parser.parse_args()

    result = evaluate_gate(
        args.db,
        args.candidate_run_id,
        RegressionPolicy(
            warn_family_catch_rate_drop=args.warn_catch_drop,
            fail_family_catch_rate_drop=args.fail_catch_drop,
            warn_false_positive_rate_increase=args.warn_fp_increase,
            fail_false_positive_rate_increase=args.fail_fp_increase,
        ),
    )
    print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    if result.status is GateStatus.FAIL:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
