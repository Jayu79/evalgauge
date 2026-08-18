# EvalGauge Eval-Harness Scope

**Status:** approved scope, implementation in progress  
**Last updated:** 2026-08-10

## 1. Positioning

EvalGauge will become a **complete safeguard-evaluation harness**, specialized for measuring
jailbreak detectors. It will not become a universal framework for every LLM, RAG, multimodal, or
agent evaluation.

The intended description is:

> EvalGauge is a safeguard-evaluation and measurement system built on eval-harness primitives:
> controlled datasets, blind execution, versioned runs, scoring, lineage, statistical comparison,
> regression gates, and per-slice failure analysis.

The specialization is deliberate. A complete vertical system with a real threat model and honest
failure analysis is a stronger artifact than a broad framework with shallow integrations.

## 2. Current foundation

EvalGauge already has several harness primitives:

- reproducible labeled synthetic cases with provenance;
- a held-out-template train/eval split;
- detector-blind event replay with truth held aside until prediction;
- a two-tier detector behind clean interfaces;
- case-level predictions with confidence, routing, latency, judge cost, and rationale;
- strict DuckDB landing with separate event, truth, and detection contracts;
- an offline end-to-end command and integrity tests.

The current system is a reproducible single-run evaluation pipeline. It is not yet a complete
experiment system because it lacks multi-run identity, artifact versioning, durable comparison,
statistical analysis, regression gates, and reliable real-model execution.

## 3. Core eval contracts

The following concepts become explicit contracts:

- `EvalCase`: input, expected label, family, severity, provenance, and metadata;
- `Dataset`: immutable case collection with an ID, manifest, and content hash;
- `Target`: the safeguard or detector being evaluated;
- `Scorer`: compares a committed target result with an oracle;
- `EvalRun`: executes one target/configuration over one dataset;
- `CaseResult`: output, score, trace, latency, cost, token use, and errors for one case;
- `RunResult`: run metadata, aggregates, slices, comparison results, and status.

The first real target remains the two-tier jailbreak detector. Extensibility is demonstrated through
the contracts; multiple artificial target integrations are not required.

## 4. Provider-neutral LLM judge

EvalGauge will keep the existing `Judge` protocol and support multiple provider adapters:

```text
Judge protocol
├── StubJudge       # deterministic infrastructure tests only
├── OpenAIJudge     # planned
│   ├── cost-sensitive/high-volume model for development and sweeps
│   ├── balanced model for the default real tier-2 candidate
│   └── frontier model for difficult-case adjudication
└── ClaudeJudge     # built; retained for comparison and Anthropic relevance
```

Current OpenAI planning defaults are `gpt-5.6-luna` for inexpensive iteration,
`gpt-5.6-terra` for the balanced tier-2 candidate, and `gpt-5.6-sol` for a small difficult-case
sample. Model identifiers and prices are runtime configuration and run metadata, not permanent
business logic.

The final artifact should include a controlled OpenAI-versus-Claude comparison on the same
ambiguous-case subset. Compare per-family quality, false positives, latency, escalation behavior,
and cost; do not declare a winner from one aggregate accuracy number.

Every provider result must retain:

- provider and exact model identifier;
- reasoning configuration;
- policy-prompt hash;
- input, cached-input, output, and reasoning-token usage where available;
- latency and calculated cost;
- parsing/schema-validation status;
- raw response or a controlled response hash.

Use provider-supported structured output when available. Content-addressed response caching should
be implemented before large threshold, model, or policy sweeps.

## 5. Target, oracle, and evaluator independence

An LLM used in tier 2 is part of the **target being evaluated**. It is not independent ground truth.
Held-aside labels remain the primary oracle.

Disputed cases follow this evidence order:

1. human-authored ground truth and annotation policy;
2. human adjudication;
3. a cross-provider judge as supporting evidence;
4. a same-family model judge as a diagnostic signal.

EvalGauge may support deterministic label scorers, independent LLM scorers, and human-review imports,
but an LLM scorer must never silently rewrite the answer key. Disagreements enter a review queue and
are reported as disagreements.

## 6. In scope

### Run identity and lineage

- multi-run warehouse rather than `--replace` single-run storage;
- immutable `run_id` and run manifest;
- dataset ID/version/hash;
- detector, training-data, threshold, judge-policy, scorer, and code versions;
- seed, environment, timestamps, baseline/parent run, and run status;
- explicit partial, failed, resumed, and completed states.

### Reliable execution

- deterministic replay and configurable targets/scorers;
- concurrency, timeouts, bounded retries, rate limiting, and error accounting;
- response caching keyed by all behavior-relevant inputs;
- resume after interruption;
- cost budgets and complete-case accounting;
- no silent removal of failures from metric denominators.

### Dataset management

- appropriately licensed public data alongside synthetic data;
- immutable dataset snapshots and manifests;
- schema checks, exact/near-duplicate checks, and contamination checks;
- enforced held-out-template separation;
- family, severity, source, and synthetic/public slices;
- annotation guidance and quarantine for disputed labels;
- permanent regression cases derived from confirmed failures.

### Measurement and statistics

- catch rate, precision, false-positive rate, and production-weighted false-discovery burden;
- per-family, severity, source, and benign-subtype reporting;
- tier contribution, escalation rate, judge override rate, and failure rate;
- latency percentiles, token use, cost per case, and cost per true catch;
- threshold sweeps and precision-recall trade-offs;
- calibration, reliability, and an explicit calibration score;
- bootstrap confidence intervals and paired run differences;
- judge/ground-truth disagreement and small-slice uncertainty;
- intervention effect on catch rate and false-positive burden together;
- visible denominators beside every metric.

### Comparison and regression gates

- candidate-versus-baseline comparison;
- cases fixed, cases regressed, and newly introduced false positives;
- per-family, cost, latency, and escalation deltas;
- configurable pass/warn/fail policies;
- CI execution for a small deterministic offline regression suite;
- larger and paid evaluations run manually or on a schedule.

### Reporting and auditability

- machine-readable JSONL or Parquet results;
- DuckDB/dbt analytical models with case-level lineage;
- human-readable dashboard or static report;
- run selection and side-by-side comparison;
- metric-to-case drill-down for failure analysis;
- controlled prompt redaction/hashing where needed;
- sufficient traces to explain every prediction, score, retry, and failure.

## 7. Explicitly out of scope

- a hosted multi-tenant SaaS product;
- a universal replacement for Inspect, promptfoo, Braintrust, or similar platforms;
- arbitrary agent-trajectory and tool-use evaluation;
- RAG, citation, image, audio, and video evaluation suites;
- dozens of provider integrations;
- automated live-target jailbreak optimization or attack breeding;
- production request blocking or claims about live unlabeled catch rate;
- real Snowflake/Pub/Sub infrastructure solely for portfolio optics;
- extracting a standalone `core/` package before genuine reuse appears.

## 8. Implementation sequence

### Phase A — harness foundation

1. Define the core eval contracts and configuration.
2. Add multi-run storage and immutable run manifests.
3. Add dataset, target, policy, scorer, and code versioning.
4. Make the runner resumable with complete failure accounting.
5. Add the OpenAI provider adapter and structured verdict schema.

### Phase B — defensible measurement

1. Build dbt staging, fact, metric, and comparison models.
2. Integrate licensed public data and dataset quality checks.
3. Add base-rate weighting, threshold sweeps, uncertainty, and calibration.
4. Run controlled real-model samples with OpenAI and Claude.
5. Add disagreement review and rigorous failure analysis.

### Phase C — experiment operations

1. Add baseline/candidate comparison and regression policies.
2. Add CI regression execution and machine-readable reports.
3. Add caching, concurrency, retries, rate limits, and cost budgets.
4. Wire the dashboard to measured multi-run outputs.

### Phase D — selective extraction

Extract reusable contracts or runner components into `core/` only after EvalGauge demonstrates a
second genuine consumer or meaningful internal duplication. Extraction does not gate publication.

## 9. Planning envelope

Starting from the current repository, the complete specialized harness is expected to require
approximately **140–200 focused engineering hours**, with **10–12 weeks at 15–20 hours per week** as
the working calendar. The incremental cash budget is approximately **$60–180**, with **$200** as a
safe cap for real-model evaluation, optional hosting/domain costs, and contingency.

Use the stub for wiring tests, inexpensive models for development and sweeps, provider caching for
unchanged cases, and frontier models only for final samples and difficult-case adjudication.

## 10. Definition of complete

EvalGauge can be called a complete safeguard-eval harness when one reproducible workflow can:

1. select an immutable dataset;
2. select and configure a target detector and judge provider;
3. execute every case with reliable failure accounting;
4. score committed predictions without leaking truth into the target;
5. store an immutable, versioned, multi-run result;
6. compute sliced metrics with uncertainty, latency, and cost;
7. compare the candidate with a baseline;
8. produce human- and machine-readable reports;
9. pass or fail configurable regression policies; and
10. reproduce or explain every recorded result.

