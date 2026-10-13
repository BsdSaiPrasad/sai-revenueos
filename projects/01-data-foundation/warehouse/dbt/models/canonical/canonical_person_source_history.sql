select
    mapping.canonical_entity_id as person_id,
    mapping.external_identity_crosswalk_id,
    mapping.reviewed_by as identity_reviewed_by,
    mapping.reviewed_at as identity_reviewed_at,
    source.event_id,
    source.source_record_id,
    source.source_system,
    source.source_tenant,
    source.source_object_type,
    source.source_object_id,
    source.name as observed_display_name,
    source.email as observed_email,
    source.employer_source_object_id,
    source.employer_name,
    source.job_title,
    source.event_type,
    source.is_deleted,
    source.source_updated_at,
    source.observed_at,
    source.received_at,
    source.is_latest_source_version,
    source.is_late_arriving,
    source.trace_id,
    source.payload_sha256,
    source.raw_payload_json
from {{ ref('int_active_identity_mappings') }} mapping
inner join {{ ref('stg_crm_people') }} source
    on source.source_record_id = mapping.source_record_id
where mapping.canonical_entity_type = 'Person'
