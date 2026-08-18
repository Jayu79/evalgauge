# EvalGauge: building the data layer for jailbreak detection

> Outline / working draft. Each section below is a placeholder with the argument it needs to make. Prose gets written as the corresponding module lands, so the writing stays honest to what was actually built.

---

## 0. The hook (≤150 words)
Open on the real problem, not the project. A safety team ships a new safeguard. The dashboard says accuracy is up. Two weeks later a new jailbreak family is quietly walking through the front door, and legitimate users are getting blocked on false positives nobody measured. Accuracy told them nothing. This is a walkthrough of a pipeline built to answer the question accuracy hides.

*Job of this section: make a Safeguards engineer keep reading. No spectacle — a real problem, stated plainly.*

## 1. Threat model
- The jailbreak families in scope, and why each matters.
- What an attacker does once they know a detector exists (adaptive pressure).
- Explicit scope boundary: this is detection and measurement, not attack generation.

*Job: prove I understand the problem before I show any solution. This section is the seniority signal.*

## 2. Why aggregate accuracy is the wrong metric
- Walk through a concrete case where 94% accuracy hides a fully-missed family.
- Introduce the two metrics EvalGauge actually reports: catch-rate-by-family, and false-positive burden on benign traffic.
- Tie the FP metric to mission: over-blocking real users is a trust failure, not a rounding error.

## 3. The data: real + synthetic, with provenance
- Public corpora for external credibility and recognizable attacks.
- Synthetic generator for volume, labeled variants, and novel families.
- Provenance metadata on every prompt → per-family reporting is possible downstream.
- The scope boundary again, concretely: what the generator does and does not produce.

## 4. Streaming ingestion
- Why a stream and not a batch: the production reality is a live prompt firehose.
- Pub/Sub replay design; each event a timestamped inbound prompt.
- What this buys: a dashboard that reflects a moving system, and the honest latency question in the next section.

## 5. The two-tier detector
- Tier 1: cheap fast classifier (embeddings + lightweight model).
- Tier 2: Claude-as-judge on the ambiguous middle band only.
- The real point: running an LLM judge on every event doesn't scale on cost or latency. The two-tier design *is* the production insight. Report both tiers' contribution.

## 6. Warehouse + dbt: where measurement happens
- Detections land in Snowflake; dbt turns them into the metrics.
- Lineage as a first-class feature — dbt DAG doubles as the legibility story.
- The intervention model: simulate a mitigation switching on, measure the before/after effect on catch rate *and* FP burden together.

## 7. Honest failure analysis
- The confusion matrix, unvarnished.
- **What EvalGauge misses, and why.** Name the families it's weak on. Name where the fast tier over-triggers. Name where the judge disagrees with ground truth and who's right.
- This section is non-negotiable and gets equal weight to everything else. It's the difference between a demo and an artifact.

## 8. What I'd build next with real infrastructure
- What changes at Anthropic's scale that a portfolio project can't simulate.
- Where the design would bend and why.

*Job: show I know the edges of my own work.*

---

### Distribution
- Front door for cold outreach: section 0 + the one-line tagline.
- Cross-post: Substack/Medium → LinkedIn, one thread per section that stands alone (threat model, the accuracy argument, the two-tier insight, the failure analysis).
- Repo linked throughout; dashboard embedded at section 6.
