with runs as (
    select * from {{ ref('stg_runs') }}
),

classifications as (
    select * from {{ ref('fct_classifications') }}
),

paired as (
    select
        candidate.run_id as candidate_run_id,
        candidate.baseline_run_id,
        c.event_id,
        b.prompt_hash as baseline_prompt_hash,
        c.prompt_hash as candidate_prompt_hash,
        b.evaluation_family as baseline_evaluation_family,
        c.evaluation_family as evaluation_family,
        b.ground_truth_label as baseline_ground_truth_label,
        c.ground_truth_label as ground_truth_label,
        b.final_flag as baseline_final_flag,
        c.final_flag as candidate_final_flag,
        b.decided_by as baseline_decided_by,
        c.decided_by as candidate_decided_by,
        b.latency_ms as baseline_latency_ms,
        c.latency_ms as candidate_latency_ms,
        b.judge_cost_usd as baseline_judge_cost_usd,
        c.judge_cost_usd as candidate_judge_cost_usd,
        (b.final_flag = b.is_actual_attack) as baseline_correct,
        (c.final_flag = c.is_actual_attack) as candidate_correct,
        b.prompt_hash = c.prompt_hash
            and b.evaluation_family = c.evaluation_family
            and b.ground_truth_label = c.ground_truth_label as is_compatible
    from runs candidate
    inner join classifications c
        on candidate.run_id = c.run_id
    inner join classifications b
        on candidate.baseline_run_id = b.run_id
        and c.event_id = b.event_id
    where candidate.baseline_run_id is not null
)

select
    *,
    not baseline_correct and candidate_correct as is_fixed,
    baseline_correct and not candidate_correct as is_regressed,
    ground_truth_label = 'benign'
        and not baseline_final_flag
        and candidate_final_flag as is_new_false_positive,
    candidate_latency_ms - baseline_latency_ms as latency_delta_ms,
    candidate_judge_cost_usd - baseline_judge_cost_usd as judge_cost_delta_usd
from paired
