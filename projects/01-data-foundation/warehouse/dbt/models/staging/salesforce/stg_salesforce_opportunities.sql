select
    event_id,
    source_record_id,
    source_system,
    source_tenant,
    source_object_type,
    source_object_id,
    nullif(trim(raw_payload_json:Id::string), '') as payload_source_object_id,
    nullif(trim(raw_payload_json:Name::string), '') as name,
    nullif(trim(raw_payload_json:AccountId::string), '') as account_source_object_id,
    nullif(trim(raw_payload_json:StageName::string), '') as stage,
    try_to_decimal(raw_payload_json:Amount::string, 38, 2) as amount,
    raw_payload_json:Amount is null
        or is_null_value(raw_payload_json:Amount)
        or try_to_decimal(raw_payload_json:Amount::string, 38, 2) is not null as is_amount_valid,
    nullif(trim(raw_payload_json:CurrencyIsoCode::string), '') as currency_code,
    try_to_date(raw_payload_json:CloseDate::string) as close_date,
    raw_payload_json:CloseDate is null
        or is_null_value(raw_payload_json:CloseDate)
        or try_to_date(raw_payload_json:CloseDate::string) is not null as is_close_date_valid,
    try_to_boolean(raw_payload_json:IsClosed::string) as is_closed,
    try_to_boolean(raw_payload_json:IsWon::string) as is_won,
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
where source_system = 'salesforce' and source_object_type = 'Opportunity'
