with duplicate_keys as (
    select 'performance_by_family' as relation_name, run_id, evaluation_family as dimension
    from {{ ref('mtr_performance_by_family') }}
    group by run_id, evaluation_family
    having count(*) > 1

    union all

    select 'tier_contribution' as relation_name, run_id, decided_by as dimension
    from {{ ref('mtr_tier_contribution') }}
    group by run_id, decided_by
    having count(*) > 1
)

select * from duplicate_keys
