select e.event_id
from {{ ref('stg_events') }} e
left join {{ ref('stg_ground_truth') }} g using (event_id)
left join {{ ref('stg_detections') }} d using (event_id)
where g.event_id is null or d.event_id is null

