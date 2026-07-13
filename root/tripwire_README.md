# Tripwire

**A data pipeline that catches jailbreak attempts and measures what your safeguards actually stop.**

Tripwire treats adversarial-prompt detection as a production data-engineering problem, not an ML demo. It ingests a stream of inbound prompts, classifies jailbreak attempts through a two-tier detector, lands the results in a warehouse, and models them into metrics that answer the question a safety team actually asks: *is this safeguard working, and what is it costing legitimate users?*

The interesting part is not the classifier. It is the lineage, the measurement, and the honesty about what the system misses.

---

## Why this exists

Most jailbreak-detection projects stop at "we got 94% accuracy on a held-out set." That number is close to meaningless for a team running safeguards in production, because it hides the two things that matter:

1. **Which attack families slip through** — an aggregate score averages over a threat model instead of exposing it.
2. **The false-positive burden on real users** — over-blocking benign traffic is itself a safety and trust failure, not a rounding error.

Tripwire is built to surface both, with per-family breakdowns, a benign-traffic control group, and a before/after view that simulates switching a mitigation on and measures its real effect.

## What this is *not*

Tripwire is a **defensive measurement** system. It classifies and measures adversarial prompts as data. It does **not** generate novel working jailbreaks, and the synthetic data module produces *labeled examples for training and evaluation* — not attacks designed to defeat production systems. That boundary is deliberate and enforced in the design.

---

## Architecture

```
  public corpora ─┐
                  ├─►  event stream  ─►  two-tier detector  ─►  warehouse  ─►  dbt models  ─►  dashboard
 synthetic gen  ─┘   (Pub/Sub replay)   (fast pass + judge)    (Snowflake)   (metrics/lineage)   (live view)
```

| Layer | Tech | Job |
|-------|------|-----|
| Data | public jailbreak corpora + synthetic generator | labeled prompts with full provenance |
| Ingestion | Pub/Sub replay producer | timestamped inbound-prompt event stream |
| Detection | embeddings + lightweight classifier, then Claude-as-judge | two-tier classification with cost/latency awareness |
| Warehouse | Snowflake | raw detections + provenance |
| Transform | dbt | precision/recall by family, FP burden, intervention effect |
| Presentation | dashboard | live stream, catch rate, FP rate, intervention toggle |

## Repo layout

```
tripwire/
  generate/    synthetic labeled-prompt generator (extends the eval-harness dataset module)
  stream/      Pub/Sub producer + consumer
  detect/      two-tier detector: fast classifier + Claude-as-judge
  warehouse/   Snowflake loaders
dbt/
  models/
    staging/   cleaned events + detections
    marts/     detection results joined to ground truth
    metrics/   precision/recall by family, FP burden, intervention before/after
dashboard/     live dashboard
docs/          case study, threat model, failure analysis
```

## Status

Active build. See [`docs/CASE_STUDY.md`](docs/CASE_STUDY.md) for the written walkthrough — the threat model, the metric choices, and the honest failure analysis are there, not here.
