with case_comparisons as (
    select * from {{ ref('fct_case_comparisons') }}
),

attack_performance as (
    select
        candidate_run_id,
        baseline_run_id,
        evaluation_family,
        count(*) as attack_examples,
        sum(cast(baseline_final_flag as integer)) as baseline_caught_attacks,
        sum(cast(candidate_final_flag as integer)) as candidate_caught_attacks,
        sum(cast(is_fixed as integer)) as fixed_attacks,
        sum(cast(is_regressed as integer)) as regressed_attacks
    from case_comparisons
    where ground_truth_label = 'attack'
    group by candidate_run_id, baseline_run_id, evaluation_family
),

burden as (
    select
        candidate.run_id as candidate_run_id,
        candidate_run.baseline_run_id,
        baseline.false_positive_rate as baseline_false_positive_rate,
        candidate.false_positive_rate as candidate_false_positive_rate,
        candidate.false_positive_rate - baseline.false_positive_rate
            as false_positive_rate_delta
    from {{ ref('stg_runs') }} candidate_run
    inner join {{ ref('mtr_false_positive_burden') }} candidate
        on candidate_run.run_id = candidate.run_id
    inner join {{ ref('mtr_false_positive_burden') }} baseline
        on candidate_run.baseline_run_id = baseline.run_id
    where candidate_run.baseline_run_id is not null
)

select
    a.candidate_run_id,
    a.baseline_run_id,
    a.evaluation_family,
    a.attack_examples,
    a.baseline_caught_attacks,
    a.candidate_caught_attacks,
    a.fixed_attacks,
    a.regressed_attacks,
    a.baseline_caught_attacks::double / a.attack_examples as baseline_catch_rate,
    a.candidate_caught_attacks::double / a.attack_examples as candidate_catch_rate,
    (a.candidate_caught_attacks - a.baseline_caught_attacks)::double / a.attack_examples
        as catch_rate_delta,
    b.baseline_false_positive_rate,
    b.candidate_false_positive_rate,
    b.false_positive_rate_delta
from attack_performance a
inner join burden b using (candidate_run_id, baseline_run_id)
