select e.run_id, e.event_id
from {{ ref('stg_events') }} e
left join {{ ref('stg_ground_truth') }} g
    on e.run_id = g.run_id and e.event_id = g.event_id
left join {{ ref('stg_detections') }} d
    on e.run_id = d.run_id and e.event_id = d.event_id
where g.event_id is null or d.event_id is null
