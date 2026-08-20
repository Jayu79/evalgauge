# EvalGauge

[![CI](https://github.com/Jayu79/evalgauge/actions/workflows/ci.yml/badge.svg)](https://github.com/Jayu79/evalgauge/actions/workflows/ci.yml)
[![Foundation tag](https://img.shields.io/badge/tag-v0.1.0-2563eb)](https://github.com/Jayu79/evalgauge/tree/v0.1.0)
[![License](https://img.shields.io/badge/license-Apache--2.0-0f766e)](LICENSE)

**A reproducible evaluation pipeline for measuring jailbreak safeguards, including what they miss
and what they cost legitimate users.**

EvalGauge treats adversarial-prompt detection as a production data-engineering and measurement
problem—not a classifier demo and not a runtime security product. It replays labeled prompts through
a detector-blind event path, commits two-tier predictions, preserves provenance and execution
metadata in DuckDB, and models the results with dbt.

The central rule is simple:

> **Never report catch rate without false-positive burden beside it.**

## Status

`v0.1.0` is the published measurement-backbone release. It includes:

- reproducible synthetic train/evaluation corpora with held-out templates;
- a detector-blind replay stream;
- a TF-IDF/logistic-regression fast tier and an ambiguous-band judge protocol;
- `StubJudge` for deterministic offline execution and a `ClaudeJudge` adapter;
- strict DuckDB ingestion for events, held-aside ground truth, and detections;
- dbt staging, classification facts, and per-family, false-positive, and tier metrics;
- Python and dbt tests running in GitHub Actions; and
- Apache-2.0 licensing with explicit third-party-material tracking.

The reproducible release path uses **`StubJudge`**. The Claude adapter exists, but the project does
not yet claim real Claude or OpenAI evaluation quality.

## Quickstart

Requires Python 3.9 or newer.

```bash
git clone https://github.com/Jayu79/evalgauge.git
cd evalgauge
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m evalgauge.offline \
  --db data/evalgauge.duckdb \
  --seed 42 \
  --replace
```

The command generates disjoint-template corpora, replays 1,800 evaluation events, runs both detector
tiers with `StubJudge`, lands the raw records in DuckDB, and builds and tests the dbt models.

Expected terminal summary:

```text
runs=1 events=1800 ground_truth=1800 detections=1800 joined_results=1800
```

Subsequent commands append immutable runs by default. Use `--run-id` for a stable name and
`--baseline-run-id` to record comparison lineage; `--replace` intentionally resets the database.

Compare a candidate with its declared baseline and apply configurable regression limits:

```bash
.venv/bin/evalgauge-compare \
  --db data/evalgauge.duckdb \
  --candidate-run-id candidate-run
```

The command emits machine-readable JSON and exits with status 2 when a failure limit is exceeded.
Its default warning/failure limits exercise the policy mechanism; they are not validated production
tolerances and should be configured for the decision being made.

Run the complete test suite separately with:

```bash
.venv/bin/python -m pytest -q
```

The current suite contains 19 Python tests. The end-to-end path runs 10 dbt models and 91 dbt data
tests: 101 dbt operations in total.

## Current architecture

```text
synthetic corpus
      |
      v
detector-blind replay
      |
      v
two-tier detector
(fast tier + StubJudge)
      |
      v
immutable run manifest + DuckDB raw contracts
(runs | events | ground_truth | detections)
      |
      v
dbt staging -> classification fact -> measurement metrics
```

| Layer | Current implementation | Responsibility |
|---|---|---|
| Data | Reproducible synthetic generator | Labeled prompts, held-out templates, full provenance |
| Ingestion | In-memory bus and replay producer | Timestamped events with labels structurally removed |
| Detection | TF-IDF + logistic regression, then judge protocol | Fast decisions, ambiguous-band escalation, latency and cost capture |
| Run lineage | Immutable `EvalRun` manifest | Dataset/config hashes, artifact versions, thresholds, Git SHA, and baseline identity |
| Warehouse | DuckDB | Run-aware raw contracts, constraints, immutable/idempotent ingestion |
| Transform | dbt | Classification outcomes, family catch rate, FP burden, tier contribution, paired run deltas |
| Policy | Configurable regression gate | Per-family catch degradation and evaluation-wide FP increase |
| Presentation | React mock only | Illustrative design; not connected to measured outputs |

Public-corpus ingestion, a wired dashboard, and paid real-judge evaluation are planned—not part of
`v0.1.0`. Append-only multi-run storage, paired comparison, and regression gates were added after
that foundation release.

## Why this exists

A single aggregate accuracy score hides the two questions a safeguard owner needs answered:

1. **Which attack families slip through?** Aggregate performance can average away a catastrophic
   family-level failure.
2. **How many legitimate users are blocked?** Over-blocking benign traffic is itself a safety and
   trust failure.

EvalGauge therefore reports attack performance by true evaluation family and carries the
evaluation-wide benign false-positive rate beside it.

### Why base rates matter

Consider an illustrative detector with 80% catch rate and 5% false-positive rate:

| Metric | Balanced corpus | 0.1% attack prevalence |
|---|---:|---:|
| Catch rate | 80% | 80% |
| False-positive rate | 5% | 5% |
| Share of blocked traffic that is benign | 5.9% | 98.4% |

The detector has not changed. The traffic mix has. At the production-like base rate, approximately
98 of every 100 blocked prompts are false alarms. This is why catch rate and false-positive burden
must travel together.

This table is an analytical example, not a claim about observed production traffic. Production
base-rate weighting is not implemented in `v0.1.0`.

## Measurement integrity

### Detector-blind execution

Each labeled prompt is split into two different types:

- `Event`: event ID, timestamp, prompt hash, and prompt text;
- `GroundTruth`: family, label, synthetic/source provenance, and objective.

Only `Event` reaches the detector. Ground truth is held aside and joins the prediction only after the
detector has committed a `Detection`. Tests assert that detector inputs have no label or family
attributes.

### Strict warehouse contracts

The raw DuckDB tables preserve:

- event identity, arrival time, prompt hash, and text;
- label, attack family, provenance, and synthetic/source metadata;
- tier-1 score, band, flag, and escalation decision;
- judge verdict, model, rationale, latency, and cost where available; and
- final flag and the tier that made the decision.

Within a run, identical replays are no-ops and changed content under the same event ID raises a
conflict. The same event ID may safely recur in another run. Foreign keys reject orphan truth or
detections, invalid values fail constraints, baseline references must exist, and whole-run
ingestion is transactional.

### Honest evaluation split

An early random split produced nearly perfect fast-tier performance because train and evaluation
records shared generation templates. That measured memorization, not generalization. `v0.1.0` splits
by template, forcing evaluation prompts to use structures unseen during training.

That failure—and the correction—is more important than the naive score. See
[BUILDLOG.md](BUILDLOG.md) for the full decision history.

## Verified release behavior

The offline release run verifies the shape and integrity of the system:

- 1,800 events, 1,800 truth records, 1,800 detections, and 1,800 joined results;
- no missing event references;
- 1,219 fast-tier decisions and 581 stub-judge decisions;
- 19/19 Python tests passing;
- 101/101 dbt models and tests passing; and
- the same test path passing from a clean GitHub Actions environment.

These numbers validate pipeline wiring and the deterministic stub's behavior. They are not evidence
of real LLM-judge quality or live production safeguard performance.

## Known limitations

- The included corpus is synthetic; no external public dataset is redistributed yet.
- Run manifests currently record completed executions; failed/partial lifecycle transitions and
  resumable execution are not implemented.
- Runtime latency can vary between executions.
- `StubJudge` is deliberately crude and must not be treated as a model-quality result.
- `ClaudeJudge` has not been used to produce the published release measurements.
- There is no OpenAI judge adapter yet.
- Production-base-rate weighting, uncertainty, calibration, threshold sweeps, and judge
  disagreement analysis remain future work.
- The dashboard is an unwired mock with illustrative numbers.

## Next milestone

The next milestone is reliable execution and stronger statistics:

1. add failure accounting, bounded retries, budgets, and resume semantics;
2. add uncertainty estimates so gates can distinguish signal from sampling noise;
3. add one properly licensed public corpus; and
4. define a small deterministic CI regression suite.

Dashboard wiring and paid real-judge evaluation remain deferred until their outputs can be
reproduced and compared.

The approved longer-term scope is documented in
[docs/eval_harness_scope.md](docs/eval_harness_scope.md). The threat-model derivation is in
[docs/threat_model.md](docs/threat_model.md).

## Repository layout

```text
evalgauge/
  generate/    synthetic labeled-prompt generator
  stream/      blind event replay and bus protocol
  detect/      fast classifier, judge protocol, and two-tier routing
  warehouse/   DuckDB schema, ingestion, and post-detection join
  offline.py   reproducible local pipeline command
tests/         warehouse contracts and end-to-end tests
dbt/           staging, classification fact, metrics, and data tests
docs/          threat model, eval-harness scope, and case-study outline
dashboard/     unwired React mock
```

## License

Copyright 2026 Jayanth Veeramachaneni.

EvalGauge's original code and documentation are licensed under the
[Apache License 2.0](LICENSE).

External datasets and third-party materials are not automatically covered by EvalGauge's license.
They retain their original licenses and attribution requirements, recorded in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). No external dataset is currently redistributed
with this repository.
