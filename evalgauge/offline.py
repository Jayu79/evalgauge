"""Reproducible local pipeline: generate, detect blindly, land, and model."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from .detect import FastClassifier, StubJudge, TwoTierDetector
from .generate.corpus import build_corpus
from .stream import Event, InMemoryBus, replay
from .warehouse import Warehouse


def run(db_path: str | Path, *, seed: int = 42) -> dict[str, int]:
    train = build_corpus(seed=seed, split="train")
    evaluation = build_corpus(seed=seed + 1, split="eval")
    detector = TwoTierDetector(FastClassifier().fit(train), StubJudge())

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

    with Warehouse(db_path) as warehouse:
        warehouse.ingest_run(events, truths, detections)
        warehouse.joined_results(require_complete=True)
        return warehouse.counts()


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


def run_pipeline(db_path: str | Path, *, seed: int = 42) -> dict[str, int]:
    """Run raw generation/detection/landing, then build tested measurement models."""
    counts = run(db_path, seed=seed)
    build_models(db_path)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/evalgauge.duckdb", type=Path)
    parser.add_argument("--seed", default=42, type=int)
    parser.add_argument(
        "--replace", action="store_true", help="replace an existing reproducible database"
    )
    parser.add_argument(
        "--skip-dbt", action="store_true", help="land raw rows without building dbt models"
    )
    args = parser.parse_args()
    args.db.parent.mkdir(parents=True, exist_ok=True)
    if args.db.exists():
        if not args.replace:
            parser.error(f"{args.db} exists; pass --replace to rebuild it")
        args.db.unlink()

    counts = (
        run(args.db, seed=args.seed)
        if args.skip_dbt
        else run_pipeline(args.db, seed=args.seed)
    )
    print(f"wrote {args.db}")
    print(" ".join(f"{name}={count}" for name, count in counts.items()))


if __name__ == "__main__":
    main()
