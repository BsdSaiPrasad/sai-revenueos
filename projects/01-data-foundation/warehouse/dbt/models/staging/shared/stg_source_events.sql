with raw_events as (
    select *
    from {{ source('revenueos_raw', 'source_event') }}
),

typed as (
    select
        event_id,
        contract_version,
        lower(source_system) as source_system,
        source_tenant,
        source_object_type,
        source_object_id,
        lower(event_type) as event_type,
        source_updated_at as source_updated_at_raw,
        try_to_timestamp_tz(source_updated_at) as source_updated_at,
        observed_at as observed_at_raw,
        try_to_timestamp_tz(observed_at) as observed_at,
        trace_id,
        extraction_id,
        stream_name,
        checkpoint_cursor,
        checkpoint_high_watermark_at as checkpoint_high_watermark_at_raw,
        try_to_timestamp_tz(checkpoint_high_watermark_at) as checkpoint_high_watermark_at,
        raw_payload_json,
        payload_sha256,
        envelope_sha256,
        processing_status,
        processing_attempts,
        last_error_type,
        last_error_message,
        source_record_id,
        became_current,
        received_at as received_at_raw,
        try_to_timestamp_tz(received_at) as received_at,
        processed_at as processed_at_raw,
        try_to_timestamp_tz(processed_at) as processed_at,
        load_batch_id,
        loaded_at,
        event_type = 'delete' as is_deleted,
        source_updated_at is not null and try_to_timestamp_tz(source_updated_at) is not null
            as is_source_updated_at_valid,
        observed_at is not null and try_to_timestamp_tz(observed_at) is not null
            as is_observed_at_valid
    from raw_events
),

versioned as (
    select
        *,
        row_number() over (
            partition by source_system, source_tenant, source_object_type, source_object_id
            order by source_updated_at desc nulls last,
                     observed_at desc nulls last,
                     received_at desc nulls last,
                     event_id desc
        ) = 1 as is_latest_source_version,
        coalesce(
            source_updated_at < max(source_updated_at) over (
                partition by source_system, source_tenant, source_object_type, source_object_id
                order by received_at, event_id
                rows between unbounded preceding and 1 preceding
            ),
            false
        ) as is_late_arriving
    from typed
)

select * from versioned
