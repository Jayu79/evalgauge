with events as (
    select * from {{ ref('stg_events') }}
),

ground_truth as (
    select * from {{ ref('stg_ground_truth') }}
),

detections as (
    select * from {{ ref('stg_detections') }}
),

joined as (
    select
        e.event_id,
        e.event_ts,
        e.prompt_hash,
        e.prompt_text,
        g.source,
        g.is_synthetic,
        g.objective,
        g.evaluation_family,
        g.ground_truth_label,
        d.tier1_score,
        d.tier1_band,
        d.tier1_flag,
        d.escalated_to_judge,
        d.judge_verdict,
        d.final_flag,
        d.decided_by,
        d.latency_ms,
        d.judge_cost_usd,
        d.judge_rationale,
        d.judge_model
    from events e
    inner join ground_truth g using (event_id)
    inner join detections d using (event_id)
)

select
    *,
    ground_truth_label = 'attack' as is_actual_attack,
    ground_truth_label = 'attack' and final_flag as is_true_positive,
    ground_truth_label = 'benign' and final_flag as is_false_positive,
    ground_truth_label = 'benign' and not final_flag as is_true_negative,
    ground_truth_label = 'attack' and not final_flag as is_false_negative
from joined

