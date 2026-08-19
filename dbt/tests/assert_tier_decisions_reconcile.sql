with totals as (
    select run_id, count(*) as fact_rows
    from {{ ref('fct_classifications') }}
    group by run_id
),

tier_totals as (
    select run_id, sum(decisions) as tier_rows
    from {{ ref('mtr_tier_contribution') }}
    group by run_id
)

select run_id, fact_rows, tier_rows
from totals
inner join tier_totals using (run_id)
where fact_rows <> tier_rows
