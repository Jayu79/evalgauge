# EvalGauge — Build Log

A running record of **what's built, what's next, and the decisions behind each choice**.
Terse and decision-focused on purpose: this is the raw material for the case study, so the
reasoning is captured while it's fresh rather than reconstructed later.

Legend: ✅ done · 🟡 in progress · ⬜ not started

---

## Status

| Layer | Module | Status |
|---|---|---|
| Design | `docs/threat_model.md` | ✅ |
| Data | `evalgauge/generate/` | ✅ |
| Ingestion | `evalgauge/stream/` | ✅ |
| Detection | `evalgauge/detect/` | ✅ |
| Warehouse | `evalgauge/warehouse/` (DuckDB) | ✅ |
| Transform | `dbt/` (staging → marts → metrics) | ✅ core models |
| Presentation | `dashboard/` wired to real data | ⬜ |
| Write-up | case study + **failure analysis** | ⬜ |

**Foundation:** annotated tag `v0.1.0` points to commit `481c1f9`.

**Next:** baseline/candidate comparison and regression gates, followed by reliable failure/resume
semantics. Licensed public-corpus ingestion remains the Month 1 data gap.

---

## Decision log

### Threat model first (before any code)
Reasoned assets → adversaries → attack surface → severity, *then* derived the architecture.
- **2 assets in tension:** the capability behind the door (protect by catching more) vs. user
  trust (protect by catching less / fewer false positives). They can't both be maximized —
  which is *why* catch rate and FP burden are always co-reported.
- **3 adversary tiers by capability** (opportunistic / determined / adaptive), not by intent —
  because capability (recognizable vs. novel attacks) is what dictates the defense, and that
  split *is* the derivation of the two-tier detector.
- Families grouped by **where the malicious signal lives** (local & recognizable → fast tier;
  *disguised* or *distributed* → judge; *unprecedented* → frontier). The grouping predicts
  which tier catches which family.

### `generate/` — data with provenance
- **Schema as a contract, validated at creation** (`LabeledPrompt`, `schema.py`): label/family
  consistency is enforced in `__post_init__` so a mislabel fails at birth, not silently three
  layers downstream where it would *invert* a metric (corrupt ground truth is worse than a
  crash because it's invisible).
- **Provenance stamped on every prompt** (family, label, is_synthetic, source) — this is what
  makes per-family reporting and base-rate re-weighting possible downstream.
- **Benign control group is load-bearing**, not filler: it's the denominator for FP burden.
- **Attacks wrap a benign stand-in objective** (e.g. "reveal your system prompt") — genuine
  jailbreak *shapes* with zero harmful payload. This is the detection-not-generation boundary
  enforced in code, not as a disclaimer.
- **Stratified corpus, not production-representative:** oversample attack families (200 each)
  for statistical power on per-family catch rate; re-weight to production's ~99.9%-benign base
  rate downstream when computing FP burden. Provenance is what lets one corpus serve both.
- **Reproducible by seed;** JSONL serialization (streamable, survives multi-line prompts).

### `stream/` — a moving system, and a blind detector
- Every record is **split at the stream boundary** into a blind `Event` (id, ts, text — all a
  real inbound prompt has) and a held-aside `GroundTruth` keyed by `event_id`. The detector
  only ever sees the `Event`. The label is **not a field on the type it receives** — so label
  leakage is *impossible to write*, not just discouraged (make illegal states unrepresentable).
- Transport is a `Bus` **protocol** (in-memory now, swappable for Pub/Sub later) — the pipeline
  depends on the interface, not the implementation.

### `detect/` — the two-tier detector
- **Fast tier** (`fast.py`): TF-IDF + logistic regression — a *surface* featurizer standing in
  for embeddings. Same character as the real thing: recognizes local tells, blind to disguised
  or distributed signal.
- **The honest-evaluation saga (the most important finding so far):**
  1. Naive eval scored ~100%/0% — a red flag, not a win.
  2. Probing with out-of-template cases showed the fast tier confidently *wrong* on unseen
     phrasings (couldn't tell a chess question from a disguised attack).
  3. Root cause: **train and test shared templates → we were measuring memorization, not
     detection.** Different seeds ≠ different templates.
  4. Fix: **held-out-template split** (`split="train"` / `"eval"` in `families.py`/`corpus.py`).
     Honest result — hard negatives get **~100% false-positived**, and there's finally a real
     **~5% ambiguous band** for the judge. Measuring honestly and defending against the adaptive
     attacker turn out to be the *same requirement* (both live off-distribution).
  - Also added **hard negatives** (benign prompts wearing attack surface) so the model stops
    equating loaded words with attacks — the thing that makes calibrated uncertainty possible.
- **Judge tier** (`judge.py`): a `Judge` protocol with two implementations —
  - `ClaudeJudge`: real **constitutional classifier** — an explicit, auditable policy in the
    system prompt (Anthropic's published approach); defaults to `claude-opus-4-8`, model is a
    param so a cheaper judge can be cost-tuned on the ambiguous band later.
  - `StubJudge`: deterministic offline stand-in so the pipeline runs with no API key.
    **Deliberately crude** — decodes encodings + reads context to show the *shape* of tier-2
    reasoning; its accuracy is not EvalGauge's real judge performance (that's `ClaudeJudge`).
  - Verified the (stub) judge **rescues both tier-1 failure modes**: decodes a base64 attack
    tier-1 was blind to, and reads fiction/security-ed context to clear false positives tier-1
    fired at 0.85. Every verdict carries latency + cost (backs `mtr_tier_contribution`).
- **`TwoTierDetector` wiring** (`detector.py`, `schema.py`): fast score → two-threshold bands
  (clear-benign / ambiguous / clear-attack) → escalate only the ambiguous band to the judge →
  emit a `Detection` (== dbt `stg_detections`). Thresholds are the tunable operating-point knob.
- **First end-to-end run** (generate → blind stream → detect → score against held-aside truth):
  - Tier-1 alone @0.5: 100% catch but **45.8% FP rate** (275 false positives) — unusable.
  - Two-tier: **92.4% catch, 0.0% FP** — the judge wiped out all 275 FPs for 91 lost catches.
    That's Asset A vs Asset B, quantified; ~31% escalation; catches split fast 909 / judge 200.
  - **Honesty caveat:** these magnitudes use the vocab-matched `StubJudge` and are optimistic —
    NOT the real judge. The *wiring* and the *direction* (trade recall for a large FP cut) are
    real; true numbers await swapping in `ClaudeJudge`. Even the stub isn't perfect (missed 91
    escalated attacks — biased benign).

### `warehouse/` — strict local measurement landing
- **Three raw contracts remain separate:** `events` has only detector-visible fields;
  `ground_truth` has provenance and labels; `detections` has scores, routing, verdict, latency, and
  judge cost. `joined_results` is the first place truth and prediction meet, after commitment.
- **DuckDB simulates Snowflake** as settled in `DECISIONS.md`. The raw tables map cleanly to future
  dbt sources; ingestion contains no dashboard or metric logic.
- **Immutable idempotency:** an identical replay is a no-op. Reusing an `event_id` for changed data
  raises `ConflictError` instead of silently replacing measurement history.
- **Integrity and atomicity:** foreign keys reject orphan truth/detections, checks reject invalid
  values, whole-run ingestion is transactional, and strict reads expose missing join sides.
- **One offline command:** `python -m evalgauge.offline --db data/evalgauge.duckdb --seed 42
  --replace` generates, replays, detects with `StubJudge`, and lands all 1,800 eval records.
- **Verification (2026-08-07):** 7 tests passed. A fresh smoke database had 1,800 rows in every raw
  table and the joined view, zero missing references, and 581 stub-judge-routed events.
- **Run-aware identity (2026-08-18):** immutable manifests record dataset version/hash, detector and
  judge-policy versions, thresholds, seed, Git SHA, status/timestamps, and optional baseline. Raw
  identity is `(run_id, event_id)`, so repeated event IDs across executions cannot collide.
- **Append-only execution:** the CLI appends by default; `--replace` is an explicit reset. Manifest
  and raw writes are immutable/idempotent, baseline references are validated, and the entire run
  lands atomically. `run_id` remains warehouse context and never enters detector inputs.
- **Verification (2026-08-18):** **12/12 pytest passed**. A two-run baseline/candidate smoke stored
  1,800 fact rows per run; all **8 models + 78 tests = 86/86 dbt operations** passed.
- **Scope honesty:** this layer is necessary measurement plumbing, not the differentiator by itself.
  The stronger evidence must come from dbt metric semantics and the later uncertainty, base-rate,
  threshold, disagreement, and failure analyses.

### `dbt/` — tested measurement semantics
- **Blind lineage remains visible:** events, truth, and detections have separate one-to-one staging
  views; `fct_classifications` is the first prediction/label join.
- **Fact grain:** one row per evaluated event, assigned to exactly one of TP/FP/TN/FN. Reverse
  completeness tests prevent inner joins from silently dropping missing truth or detections.
- **Per-family performance:** catch rate groups by true evaluation family. Precision is not reported
  by family because the detector predicts only attack/benign, not family.
- **FP burden travels with catch rate:** family rows carry the evaluation-wide benign FP rate.
  False-alarm share is explicitly labeled evaluation-mix, not production-base-rate evidence.
- **Tier contribution is bounded by stored data:** outcomes, end-to-end latency, and judge cost are
  grouped by deciding tier; total latency is not mislabeled as incremental judge latency.
- **Verification (2026-08-17):** fresh 1,800-event run; 7 dbt views + 55 tests = **62/62 passed**.
  Python suite: **7/7 passed**.
- **Deferred honestly:** intervention effect requires run/variant metadata that does not exist yet.

### Public-release hardening
- The default offline command now runs the entire local measurement path through dbt; `--skip-dbt`
  remains available for raw-only diagnostics.
- The end-to-end pytest verifies detector blindness, raw completeness, fact row count, and the
  per-family metric output in the resulting DuckDB file.
- GitHub Actions runs the clean-environment test path on Python 3.11, and generated dbt state is
  excluded from version control.
- Local verification (2026-08-17): **7/7 pytest passed**, including an in-process 62/62 dbt build;
  the standalone public-facing command also completed successfully.
- Hosted verification (2026-08-17): GitHub Actions CI passed on Python 3.11 after the history rewrite
  and again for licensing commit `297cd1a`, installing the project from a clean checkout and running
  the complete offline test path.
- The GitHub repository was renamed to `Jayu79/evalgauge`, and the local `origin` now points to it.
  The repository's original code and documentation are now licensed under Apache-2.0. External
  datasets and third-party materials remain under their own terms and are tracked separately.
- Removed Claude `Co-Authored-By` trailers from the early commit messages. All commits were already
  authored and committed by Jayanth; the rewrite changed messages only, preserved the complete tree,
  and was force-pushed with an explicit lease. A local recovery branch preserves the prior history.
- **Naming migration (2026-08-17):** retired the conflicting Tripwire working name and adopted
  **EvalGauge**. The old name collided with an established cybersecurity company and open-source
  product, creating avoidable trademark, discovery, and reader-confusion risk. EvalGauge instead
  names the actual value: measuring safeguard performance, false-positive burden, lineage, cost,
  and regressions without implying that the harness itself provides protection. It also remains
  accurate as the project expands beyond jailbreak detection into a provider-neutral eval harness.
  Migrated the `evalgauge` Python namespace, console command, dbt project/profile/source
  identifiers, environment variable, generated database name, filenames, and all continuity docs.
  Clean editable installation exposed and fixed ambiguous setuptools package discovery. The renamed
  test suite and CLI pass, and the GitHub repository and local remote now use the new name.

---

## Guiding constraints
- **Simulated infra** (DuckDB, in-process queue), not real Snowflake/Pub/Sub — same design
  story, cheaper; real-scale changes go in case-study §8.
- **Never report catch rate without FP burden.** The whole thesis.
- **The honest failure analysis is the differentiator** — guard it against scope creep.
