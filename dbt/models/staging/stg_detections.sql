select
    run_id,
    event_id,
    tier1_score,
    tier1_band,
    tier1_flag,
    escalated_to_judge,
    judge_verdict,
    final_flag,
    decided_by,
    latency_ms,
    judge_cost_usd,
    judge_rationale,
    judge_model
from {{ source('evalgauge_raw', 'detections') }}
