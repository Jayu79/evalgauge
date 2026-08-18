with classifications as (
    select * from {{ ref('fct_classifications') }}
),

summary as (
    select
        sum(case when ground_truth_label = 'benign' then 1 else 0 end) as benign_examples,
        sum(case when is_false_positive then 1 else 0 end) as false_positives,
        sum(case when is_true_negative then 1 else 0 end) as true_negatives,
        sum(case when is_true_positive then 1 else 0 end) as true_positive_blocks,
        sum(case when final_flag then 1 else 0 end) as total_blocks
    from classifications
)

select
    benign_examples,
    false_positives,
    true_negatives,
    true_positive_blocks,
    total_blocks,
    case
        when benign_examples = 0 then null
        else false_positives::double / benign_examples
    end as false_positive_rate,
    case
        when total_blocks = 0 then null
        else false_positives::double / total_blocks
    end as evaluation_mix_false_alarm_share_of_blocks
from summary

