select
    event_id,
    family as evaluation_family,
    label as ground_truth_label,
    is_synthetic,
    source,
    objective
from {{ source('evalgauge_raw', 'ground_truth') }}

