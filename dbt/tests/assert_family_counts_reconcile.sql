select run_id, evaluation_family
from {{ ref('mtr_performance_by_family') }}
where attack_examples <> caught_attacks + missed_attacks
