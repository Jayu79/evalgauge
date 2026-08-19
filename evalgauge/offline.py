"""Reproducible local pipeline: generate, detect blindly, land, and model."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from .detect import FastClassifier, StubJudge, TwoTierDetector
from .detect.detector import DEFAULT_HIGH, DEFAULT_LOW
from .generate.corpus import build_corpus
from .runs import (
    EvalRun,
    RunStatus,
    current_git_sha,
    dataset_content_hash,
    new_run_id,
    utc_now,
)
from .stream import Event, InMemoryBus, replay
from .warehouse import Warehouse


def run(
    db_path: str | Path,
    *,
    seed: int = 42,
    run_id: str | None = None,
    baseline_run_id: str | None = None,
    low_threshold: float = DEFAULT_LOW,
    high_threshold: float = DEFAULT_HIGH,
) -> dict[str, int]:
    started_at = utc_now()
    train = build_corpus(seed=seed, split="train")
    evaluation = build_corpus(seed=seed + 1, split="eval")
    judge = StubJudge()
    detector = TwoTierDetector(
        FastClassifier().fit(train), judge, low=low_threshold, high=high_threshold
    )

    events: list[Event] = []
    truths = []
    detections = []
    bus = InMemoryBus()

    def detect_blind(event: Event) -> None:
        # This callback's type and value contain no truth fields. Truth follows a
        # separate sink and is not landed until every prediction is committed.
        events.append(event)
        detections.append(detector.detect(event))

    bus.subscribe(detect_blind)
    replay(evaluation, bus, truths.append)

    manifest = EvalRun(
        run_id=run_id or new_run_id(),
        status=RunStatus.COMPLETED,
        started_at=started_at,
        completed_at=utc_now(),
        dataset_name="evalgauge-synthetic",
        dataset_version="heldout-templates.v1",
        dataset_hash=dataset_content_hash(evaluation),
        detector_version="tfidf-logreg-two-tier.v1",
        judge_model=judge.model,
        policy_version="stub-judge-policy.v1",
        seed=seed,
        low_threshold=low_threshold,
        high_threshold=high_threshold,
        git_sha=current_git_sha(),
        baseline_run_id=baseline_run_id,
    )

    with Warehouse(db_path) as warehouse:
        warehouse.ingest_run(manifest, events, truths, detections)
        warehouse.joined_results(manifest.run_id, require_complete=True)
        return warehouse.counts(manifest.run_id)


def build_models(db_path: str | Path) -> None:
    """Run the checked-in dbt project against a completed DuckDB warehouse."""
    from dbt.adapters.factory import reset_adapters
    from dbt.cli.main import dbtRunner

    project_root = Path(__file__).resolve().parents[1]
    dbt_dir = project_root / "dbt"
    prior_path = os.environ.get("EVALGAUGE_DB_PATH")
    os.environ["EVALGAUGE_DB_PATH"] = str(Path(db_path).resolve())
    try:
        result = dbtRunner().invoke(
            ["build", "--project-dir", str(dbt_dir), "--profiles-dir", str(dbt_dir)]
        )
    finally:
        # dbt keeps registered adapters at module scope for repeated invocations.
        # Release them so callers can immediately reopen the DuckDB file with a
        # different connection configuration (for example, read-only verification).
        reset_adapters()
        if prior_path is None:
            os.environ.pop("EVALGAUGE_DB_PATH", None)
        else:
            os.environ["EVALGAUGE_DB_PATH"] = prior_path

    if not result.success:
        raise RuntimeError("dbt build failed; inspect the dbt output above")


def run_pipeline(
    db_path: str | Path,
    *,
    seed: int = 42,
    run_id: str | None = None,
    baseline_run_id: str | None = None,
    low_threshold: float = DEFAULT_LOW,
    high_threshold: float = DEFAULT_HIGH,
) -> dict[str, int]:
    """Run raw generation/detection/landing, then build tested measurement models."""
    counts = run(
        db_path,
        seed=seed,
        run_id=run_id,
        baseline_run_id=baseline_run_id,
        low_threshold=low_threshold,
        high_threshold=high_threshold,
    )
    build_models(db_path)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/evalgauge.duckdb", type=Path)
    parser.add_argument("--seed", default=42, type=int)
    parser.add_argument("--run-id", help="execution ID; defaults to a new UUID")
    parser.add_argument("--baseline-run-id", help="optional prior run for later comparison")
    parser.add_argument("--low-threshold", default=DEFAULT_LOW, type=float)
    parser.add_argument("--high-threshold", default=DEFAULT_HIGH, type=float)
    parser.add_argument(
        "--replace", action="store_true", help="reset the database before appending this run"
    )
    parser.add_argument(
        "--skip-dbt", action="store_true", help="land raw rows without building dbt models"
    )
    args = parser.parse_args()
    args.db.parent.mkdir(parents=True, exist_ok=True)
    if args.db.exists() and args.replace:
        args.db.unlink()

    selected_run_id = args.run_id or new_run_id()

    counts = (
        run(
            args.db,
            seed=args.seed,
            run_id=selected_run_id,
            baseline_run_id=args.baseline_run_id,
            low_threshold=args.low_threshold,
            high_threshold=args.high_threshold,
        )
        if args.skip_dbt
        else run_pipeline(
            args.db,
            seed=args.seed,
            run_id=selected_run_id,
            baseline_run_id=args.baseline_run_id,
            low_threshold=args.low_threshold,
            high_threshold=args.high_threshold,
        )
    )
    print(f"wrote {args.db}")
    print(f"run_id={selected_run_id}")
    print(" ".join(f"{name}={count}" for name, count in counts.items()))


if __name__ == "__main__":
    main()
