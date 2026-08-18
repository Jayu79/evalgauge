with totals as (
    select count(*) as fact_rows
    from {{ ref('fct_classifications') }}
),

tier_totals as (
    select sum(decisions) as tier_rows
    from {{ ref('mtr_tier_contribution') }}
)

select fact_rows, tier_rows
from totals
cross join tier_totals
where fact_rows <> tier_rows

