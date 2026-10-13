select
    event_id,
    source_record_id,
    source_system,
    source_tenant,
    source_object_type,
    source_object_id,
    nullif(trim(raw_payload_json:id::string), '') as payload_source_object_id,
    nullif(trim(raw_payload_json:properties:dealname::string), '') as name,
    nullif(trim(raw_payload_json:properties:dealstage::string), '') as stage,
    try_to_decimal(raw_payload_json:properties:amount::string, 38, 2) as amount,
    raw_payload_json:properties:amount is null
        or is_null_value(raw_payload_json:properties:amount)
        or try_to_decimal(raw_payload_json:properties:amount::string, 38, 2) is not null as is_amount_valid,
    try_to_date(raw_payload_json:properties:closedate::string) as close_date,
    raw_payload_json:properties:closedate is null
        or is_null_value(raw_payload_json:properties:closedate)
        or try_to_date(raw_payload_json:properties:closedate::string) is not null as is_close_date_valid,
    nullif(trim(raw_payload_json:properties:hubspot_owner_id::string), '') as owner_id,
    event_type,
    is_deleted,
    source_updated_at,
    observed_at,
    received_at,
    is_latest_source_version,
    is_late_arriving,
    trace_id,
    extraction_id,
    checkpoint_cursor,
    payload_sha256,
    envelope_sha256,
    raw_payload_json,
    loaded_at
from {{ ref('stg_source_events') }}
where source_system = 'hubspot' and source_object_type = 'Deal'
