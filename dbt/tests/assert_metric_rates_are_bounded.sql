select 'family_catch_rate' as metric
from {{ ref('mtr_performance_by_family') }}
where catch_rate not between 0 and 1

union all

select 'false_positive_rate' as metric
from {{ ref('mtr_false_positive_burden') }}
where false_positive_rate not between 0 and 1

union all

select 'evaluation_mix_false_alarm_share_of_blocks' as metric
from {{ ref('mtr_false_positive_burden') }}
where evaluation_mix_false_alarm_share_of_blocks not between 0 and 1

