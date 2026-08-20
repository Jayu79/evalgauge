select candidate_run_id, event_id
from {{ ref('fct_case_comparisons') }}
group by candidate_run_id, event_id
having count(*) > 1

union all

select candidate_run_id, evaluation_family as event_id
from {{ ref('mtr_run_comparisons') }}
group by candidate_run_id, evaluation_family
having count(*) > 1
