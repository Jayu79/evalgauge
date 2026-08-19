with duplicate_keys as (
    select 'events' as relation_name, run_id, event_id
    from {{ ref('stg_events') }}
    group by run_id, event_id
    having count(*) > 1

    union all

    select 'ground_truth' as relation_name, run_id, event_id
    from {{ ref('stg_ground_truth') }}
    group by run_id, event_id
    having count(*) > 1

    union all

    select 'detections' as relation_name, run_id, event_id
    from {{ ref('stg_detections') }}
    group by run_id, event_id
    having count(*) > 1

    union all

    select 'classifications' as relation_name, run_id, event_id
    from {{ ref('fct_classifications') }}
    group by run_id, event_id
    having count(*) > 1
)

select * from duplicate_keys
