# EvalGauge

**A data pipeline that catches jailbreak attempts and measures what your safeguards actually stop.**

EvalGauge treats adversarial-prompt detection as a production **data-engineering and measurement**
problem, not an ML demo. It ingests a stream of inbound prompts, classifies jailbreak attempts
through a two-tier detector, lands the results in a warehouse, and models them into the metrics a
safety team actually needs: *is this safeguard working, and what is it costing legitimate users?*

The interesting part is not the classifier. It's the lineage, the measurement, and the honesty
about what the system misses.

> **Status: active build.** The local measurement path now runs end-to-end through DuckDB. See [`BUILDLOG.md`](BUILDLOG.md) for the running decision log and
> [`docs/threat_model.md`](docs/threat_model.md) for the reasoning that drives every design choice.
> The approved expansion into a complete, provider-neutral safeguard-eval harness is defined in
> [`docs/eval_harness_scope.md`](docs/eval_harness_scope.md).

---

## Why this exists

Most jailbreak-detection projects stop at *"we got 94% accuracy on a held-out set."* That number is
close to meaningless to a team running safeguards in production, because it hides the two things
that matter:

1. **Which attack families slip through** — an aggregate score averages over a threat model instead
   of exposing it. 94% can mean 99% on five easy families and near-0% on the one that matters.
2. **The false-positive burden on real users** — over-blocking benign traffic is itself a safety and
   trust failure, not a rounding error.

EvalGauge surfaces both, with per-family breakdowns, a benign-traffic control group, and a
before/after view that simulates switching a mitigation on and measures its real effect.

**The one rule:** never report catch rate without false-positive burden beside it.

---

## The measurement thesis (a worked example)

A concrete result from the build — the reason FP burden is co-reported everywhere:

Take a perfectly ordinary detector: **80% catch rate, 5% false-positive rate.** On a balanced test
it looks fine. But production traffic is ~99.9% benign, so re-weighting to real base rates:

| Metric | On a balanced corpus | At production base rates |
|---|---|---|
| Catch rate | 80% | 80% |
| FP rate | 5% | 5% |
| **Share of blocked traffic that was a false alarm** | **5.9%** | **98.4%** |

Same detector. The 5% false-positive rate, multiplied across a million benign prompts, buries the
true catches — **98 of every 100 blocks are innocent users.** That number is invisible unless you
compute it at production weights, and it's exactly what a single accuracy figure launders away.

---

## Architecture

```
  public corpora ─┐
                  ├─►  event stream  ─►  two-tier detector  ─►  warehouse  ─►  dbt models  ─►  dashboard
 synthetic gen  ─┘   (replay producer)  (fast pass + judge)    (DuckDB)     (metrics/lineage)  (live view)
```

| Layer | Tech | Job |
|-------|------|-----|
| Data | synthetic generator (+ public corpora) | labeled prompts with full provenance |
| Ingestion | replay producer over a pub/sub-style bus | timestamped, **detector-blind** event stream |
| Detection | TF-IDF + logistic regression, then provider-neutral LLM judge | two-tier classification with cost/latency awareness; Claude built, OpenAI planned |
| Warehouse | DuckDB (simulating Snowflake) | raw detections + provenance |
| Transform | dbt | catch rate by family, FP burden, tier contribution |
| Presentation | dashboard | live stream, catch rate, FP rate, intervention toggle |

---

## Build status

| Layer | Module | Status |
|---|---|---|
| Design | `docs/threat_model.md` | ✅ done |
| Data | `evalgauge/generate/` | ✅ done |
| Ingestion | `evalgauge/stream/` | ✅ done |
| Detection | `evalgauge/detect/` | ✅ two-tier detector wired; offline stub + real judge adapter |
| Warehouse | `evalgauge/warehouse/` | ✅ DuckDB raw tables + strict post-detection join |
| Transform | `dbt/` | ✅ staging, classification fact, family/FP/tier metrics |
| Presentation | `dashboard/` (wired to real data) | ⬜ planned |
| Write-up | case study + failure analysis | ⬜ planned |

Full detail and rationale: [`BUILDLOG.md`](BUILDLOG.md).

---

## What's built so far — and what it honestly shows

- **Threat model that derives the architecture.** Two assets in tension (the capability behind the
  door vs. user trust), three adversary tiers ranked by *capability* (recognizable vs. novel
  attacks) — which is what makes the two-tier design a derivation, not a fashion. See
  [`docs/threat_model.md`](docs/threat_model.md).
- **Synthetic data with provenance, stratified for measurement.** Attacks wrap a *benign stand-in*
  objective (genuine jailbreak shapes, zero harmful payload). The corpus deliberately over-samples
  attacks for statistical power, then re-weights to production base rates downstream — one dataset,
  two weightings.
- **A detector-blind stream.** Each prompt is split into a blind `Event` (what the detector sees)
  and a held-aside answer key (joined only later to score) — so label leakage is *unrepresentable
  in the type*, not merely discouraged.
- **An honestly-evaluated fast tier.** Naive evaluation scored ~100% — a red flag, not a win. It
  turned out we were measuring *memorization* (train and test shared templates). A held-out-template
  split exposed the real behavior: the fast tier false-positives on ~100% of *unseen* benign prompts
  that wear attack-flavored surface, and there's a genuine ambiguous middle band. Measuring honestly
  and defending against an adaptive attacker turn out to be the same requirement.
- **A constitutional judge for the ambiguous middle.** Tier 2 is Claude classifying against an
  explicit, auditable policy — verified to rescue both of tier 1's failure modes (it decodes a
  disguised attack tier 1 was blind to, *and* reads context to clear false positives tier 1 fired at
  0.85). Pluggable interface with an offline stub so the pipeline runs without an API key.
- **A strict DuckDB landing layer.** `events`, `ground_truth`, and `detections` stay separate until
  the post-detection `joined_results` view. Foreign keys reject orphan truth/predictions, immutable
  duplicate records are idempotent, conflicting duplicates fail loudly, and run ingestion is
  transactional. Provenance, arrival time, tier routing, scores, latency, and judge cost are kept.

## Reproducible offline run

From `EvalGauge/`:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m evalgauge.offline --db data/evalgauge.duckdb --seed 42 --replace
```

This generates disjoint-template train/eval corpora, replays 1,800 evaluation events through the
blind stream, runs both detector tiers with `StubJudge`, lands a complete DuckDB database, and runs
the tested dbt fact and metric models.
`--replace` explicitly permits rebuilding the output; without it, an existing database is preserved.
Stub results verify pipeline wiring, not real Claude evaluation quality.

The current database represents one rebuildable run: sequential event IDs are not namespaced by a
`run_id`, and runtime latency can vary between executions. Multi-run lineage and explicit dataset,
detector, and policy versioning are later work; this raw warehouse is intentionally foundational,
not the project's final analytical contribution.

---

## Scope: defensive measurement, not attack generation

EvalGauge **classifies and measures** adversarial prompts as data. It does **not** generate novel
working jailbreaks. The synthetic module produces *labeled examples for evaluation* whose "harmful"
slot is a benign stand-in (e.g. "reveal your system prompt") — a real jailbreak *technique* with no
dangerous payload. That boundary is enforced in the design, not just stated in a README.

---

## Repo layout

```
evalgauge/
  generate/    synthetic labeled-prompt generator (schema, families, corpus)
  stream/      blind event replay (event model, bus, producer)
  detect/      two-tier detector (fast classifier, constitutional judge)
  warehouse/   DuckDB schema, idempotent ingestion, post-detection join
  offline.py   reproducible local pipeline command
tests/         warehouse contracts and end-to-end blindness/coverage tests
docs/          threat model, case-study outline
dbt/           tested staging, classification fact, and measurement metrics
dashboard/     dashboard mock (to be wired to real data)
BUILDLOG.md    status + decision log
```

---

*Numbers shown in the dashboard mock are illustrative. This is a controlled measurement over
labeled data — explicitly not a claim about live, unlabeled production traffic.*
