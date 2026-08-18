select
    event_id,
    ts as event_ts,
    prompt_hash,
    text as prompt_text
from {{ source('evalgauge_raw', 'events') }}

