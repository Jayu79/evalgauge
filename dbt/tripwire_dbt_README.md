# Tripwire dbt models

The measurement layer. Raw detections come in from Snowflake; these models turn them into the metrics the case study argues for.

## Layers

### staging/
One-to-one cleaned views over raw landed data. No business logic.

- `stg_events` — inbound prompt events from the stream (event_id, ts, prompt_hash, source, family, is_synthetic, ground_truth_label)
- `stg_detections` — detector output (event_id, tier1_score, tier1_flag, escalated_to_judge, judge_verdict, final_flag, latency_ms, judge_cost_usd)

### marts/
Detections joined to ground truth — the analysis-ready fact table.

- `fct_classifications` — one row per event: predicted vs. actual, which tier decided it, latency, cost. Everything downstream reads from here.

### metrics/
The numbers the dashboard and case study consume. Each is a deliberate answer to a question aggregate accuracy can't answer.

- `mtr_performance_by_family` — precision / recall / catch-rate per attack family. **The anti-aggregate metric.** Exposes the family that a global score would hide.
- `mtr_false_positive_burden` — FP rate on benign traffic, in absolute terms and as a share of blocked traffic. The trust-cost metric.
- `mtr_tier_contribution` — how much each tier caught, and the cost/latency each tier added. Backs the two-tier production argument.
- `mtr_intervention_effect` — before/after a simulated mitigation toggle: change in catch-rate AND in FP burden, side by side. The intervention-effectiveness module.

## Design notes
- `ground_truth_label` only exists because the data is labeled (public + synthetic). The case study is explicit that this is a controlled measurement setup, not a claim about live unlabeled traffic.
- Every metric model reports FP burden alongside catch rate wherever both apply. Never report catch rate alone — that's the whole thesis.
- The DAG is intentionally legible: staging → marts → metrics, no shortcuts. The lineage graph is part of the deliverable.
