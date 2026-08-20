with candidate_runs as (
    select
        candidate.run_id as candidate_run_id,
        candidate.baseline_run_id,
        candidate.dataset_hash as candidate_dataset_hash,
        baseline.dataset_hash as baseline_dataset_hash
    from {{ ref('stg_runs') }} candidate
    inner join {{ ref('stg_runs') }} baseline
        on candidate.baseline_run_id = baseline.run_id
),

case_mismatches as (
    select
        runs.candidate_run_id,
        runs.baseline_run_id,
        candidate.event_id
    from candidate_runs runs
    inner join {{ ref('fct_classifications') }} candidate
        on runs.candidate_run_id = candidate.run_id
    left join {{ ref('fct_classifications') }} baseline
        on runs.baseline_run_id = baseline.run_id
        and candidate.event_id = baseline.event_id
    where baseline.event_id is null
        or candidate.prompt_hash <> baseline.prompt_hash
        or candidate.ground_truth_label <> baseline.ground_truth_label
        or candidate.evaluation_family <> baseline.evaluation_family

    union all

    select
        runs.candidate_run_id,
        runs.baseline_run_id,
        baseline.event_id
    from candidate_runs runs
    inner join {{ ref('fct_classifications') }} baseline
        on runs.baseline_run_id = baseline.run_id
    left join {{ ref('fct_classifications') }} candidate
        on runs.candidate_run_id = candidate.run_id
        and baseline.event_id = candidate.event_id
    where candidate.event_id is null
),

hash_mismatches as (
    select candidate_run_id, baseline_run_id, null as event_id
    from candidate_runs
    where candidate_dataset_hash <> baseline_dataset_hash
)

select * from case_mismatches
union all
select * from hash_mismatches
