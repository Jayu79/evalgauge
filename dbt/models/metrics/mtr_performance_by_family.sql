with classifications as (
    select * from {{ ref('fct_classifications') }}
),

family_performance as (
    select
        run_id,
        evaluation_family,
        count(*) as attack_examples,
        sum(case when is_true_positive then 1 else 0 end) as caught_attacks,
        sum(case when is_false_negative then 1 else 0 end) as missed_attacks
    from classifications
    where ground_truth_label = 'attack'
    group by run_id, evaluation_family
),

benign_burden as (
    select * from {{ ref('mtr_false_positive_burden') }}
)

select
    f.run_id,
    f.evaluation_family,
    f.attack_examples,
    f.caught_attacks,
    f.missed_attacks,
    case
        when f.attack_examples = 0 then null
        else f.caught_attacks::double / f.attack_examples
    end as catch_rate,
    b.benign_examples,
    b.false_positives,
    b.false_positive_rate,
    b.evaluation_mix_false_alarm_share_of_blocks
from family_performance f
inner join benign_burden b using (run_id)
