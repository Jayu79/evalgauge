# Tripwire — Build Log

A running record of **what's built, what's next, and the decisions behind each choice**.
Terse and decision-focused on purpose: this is the raw material for the case study, so the
reasoning is captured while it's fresh rather than reconstructed later.

Legend: ✅ done · 🟡 in progress · ⬜ not started

---

## Status

| Layer | Module | Status |
|---|---|---|
| Design | `docs/threat_model.md` | ✅ |
| Data | `tripwire/generate/` | ✅ |
| Ingestion | `tripwire/stream/` | ✅ |
| Detection | `tripwire/detect/` | 🟡 fast tier + judge built; two-tier wiring remains |
| Warehouse | `tripwire/warehouse/` (DuckDB) | ⬜ |
| Transform | `dbt/` (staging → marts → metrics) | ⬜ |
| Presentation | `dashboard/` wired to real data | ⬜ |
| Write-up | case study + **failure analysis** | ⬜ |

**Next:** `TwoTierDetector` wiring — fast score → threshold bands → escalate ambiguous to
the judge → emit a `Detection` record (maps to dbt `stg_detections`).

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
    reasoning; its accuracy is not Tripwire's real judge performance (that's `ClaudeJudge`).
  - Verified the (stub) judge **rescues both tier-1 failure modes**: decodes a base64 attack
    tier-1 was blind to, and reads fiction/security-ed context to clear false positives tier-1
    fired at 0.85. Every verdict carries latency + cost (backs `mtr_tier_contribution`).

---

## Guiding constraints
- **Simulated infra** (DuckDB, in-process queue), not real Snowflake/Pub/Sub — same design
  story, cheaper; real-scale changes go in case-study §8.
- **Never report catch rate without FP burden.** The whole thesis.
- **The honest failure analysis is the differentiator** — guard it against scope creep.
