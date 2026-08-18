select event_id
from {{ ref('fct_classifications') }}
where cast(is_true_positive as integer)
    + cast(is_false_positive as integer)
    + cast(is_true_negative as integer)
    + cast(is_false_negative as integer) <> 1

