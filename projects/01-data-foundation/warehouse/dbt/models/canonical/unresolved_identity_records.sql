with current_records as (
    select
        'Account' as expected_entity_type,
        event_id,
        source_record_id,
        source_system,
        source_tenant,
        source_object_type,
        source_object_id,
        name as observed_name,
        domain as observed_domain,
        cast(null as varchar) as observed_email,
        source_updated_at,
        observed_at,
        trace_id,
        payload_sha256
    from {{ ref('stg_crm_companies') }}
    where is_latest_source_version and event_type = 'upsert' and not is_deleted

    union all

    select
        'Person' as expected_entity_type,
        event_id,
        source_record_id,
        source_system,
        source_tenant,
        source_object_type,
        source_object_id,
        name as observed_name,
        cast(null as varchar) as observed_domain,
        email as observed_email,
        source_updated_at,
        observed_at,
        trace_id,
        payload_sha256
    from {{ ref('stg_crm_people') }}
    where is_latest_source_version and event_type = 'upsert' and not is_deleted
)
select
    source.*,
    'unresolved' as identity_resolution_status
from current_records source
left join {{ ref('int_active_identity_mappings') }} mapping
    on mapping.source_record_id = source.source_record_id
where mapping.source_record_id is null
