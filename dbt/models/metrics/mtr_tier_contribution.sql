with classifications as (
    select * from {{ ref('fct_classifications') }}
)

select
    decided_by,
    count(*) as decisions,
    sum(case when is_actual_attack then 1 else 0 end) as attack_examples_decided,
    sum(case when is_true_positive then 1 else 0 end) as caught_attacks,
    sum(case when is_false_positive then 1 else 0 end) as false_positives,
    avg(latency_ms) as average_end_to_end_latency_ms,
    sum(judge_cost_usd) as total_judge_cost_usd,
    avg(judge_cost_usd) as average_judge_cost_usd
from classifications
group by decided_by

