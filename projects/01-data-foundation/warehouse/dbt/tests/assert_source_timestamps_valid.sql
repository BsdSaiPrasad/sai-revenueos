select event_id, source_updated_at_raw, observed_at_raw
from {{ ref('stg_source_events') }}
where not is_source_updated_at_valid
   or not is_observed_at_valid
   or checkpoint_high_watermark_at is null
   or received_at is null
