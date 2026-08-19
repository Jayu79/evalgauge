select
    run_id,
    status as run_status,
    started_at,
    completed_at,
    dataset_name,
    dataset_version,
    dataset_hash,
    detector_version,
    judge_model,
    policy_version,
    configuration_hash,
    seed,
    low_threshold,
    high_threshold,
    git_sha,
    baseline_run_id
from {{ source('evalgauge_raw', 'runs') }}
