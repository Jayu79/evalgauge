# EvalGauge dbt models

The local measurement layer. Raw records land in DuckDB (standing in for Snowflake); dbt turns
them into tested classification facts and safeguard metrics.

## Layers

### staging/
One-to-one cleaned views over raw landed data. No joins or business logic.

- `stg_events` — detector-visible inbound events only; no labels or provenance proxies
- `stg_ground_truth` — held-aside labels, evaluation family, and provenance
- `stg_detections` — blind detector output, routing, verdict, latency, and cost

### marts/
Detections joined to ground truth — the analysis-ready fact table.

- `fct_classifications` — one row per evaluated event. This is the first truth/prediction join and
  classifies every complete row into exactly one of TP, FP, TN, or FN.

### metrics/
The numbers the dashboard and case study consume. Each is a deliberate answer to a question aggregate accuracy can't answer.

- `mtr_performance_by_family` — catch rate by true attack family, paired with the evaluation-wide
  benign FP rate. The detector does not predict family, so "precision by family" is not reported.
- `mtr_false_positive_burden` — benign FP rate and false alarms as a share of blocks. The latter is
  explicitly labeled `evaluation_mix_*` because the corpus is deliberately stratified.
- `mtr_tier_contribution` — outcomes by deciding tier, end-to-end latency, and judge cost. Stored
  latency cannot isolate incremental judge latency, so the model does not claim it.
- `mtr_intervention_effect` — **deferred.** No intervention/run/variant field exists in the raw
  contracts yet; creating a before/after model now would invent lineage that does not exist.

## Design notes
- `ground_truth_label` only exists because the data is labeled (public + synthetic). The case study is explicit that this is a controlled measurement setup, not a claim about live unlabeled traffic.
- Every metric model reports FP burden alongside catch rate wherever both apply. Never report catch rate alone — that's the whole thesis.
- The DAG is intentionally legible: staging → marts → metrics, no shortcuts. The lineage graph is part of the deliverable.

## Run locally

From `EvalGauge/`, after generating the warehouse:

```bash
EVALGAUGE_DB_PATH=data/evalgauge.duckdb \
  .venv/bin/dbt build --project-dir dbt --profiles-dir dbt
```

The build checks source contracts, references, evaluation completeness, one-row-per-event grain,
exhaustive outcomes, bounded rates, family count reconciliation, and tier count reconciliation.

These are controlled, stub-backed evaluation metrics. False-alarm share reflects the evaluation
mix, not production prevalence. Production-base-rate weighting, uncertainty, run comparison, and
real-judge measurement remain later work.
