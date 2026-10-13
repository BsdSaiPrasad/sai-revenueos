with current_sources as (
    select *
    from {{ ref('canonical_account_source_history') }}
    where is_latest_source_version and event_type = 'upsert' and not is_deleted
),
authoritative as (
    select account_id, observed_lifecycle_status as authoritative_value
    from current_sources
    where source_system = 'salesforce' and observed_lifecycle_status is not null
    qualify row_number() over (
        partition by account_id
        order by source_updated_at desc, observed_at desc, event_id desc
    ) = 1
)
select
    sha2(
        source.account_id || '|lifecycle_status|' || source.source_record_id || '|' || source.event_id,
        256
    ) as conflict_evidence_id,
    'Account' as canonical_entity_type,
    source.account_id as canonical_entity_id,
    'lifecycle_status' as field_name,
    authoritative.authoritative_value,
    source.observed_lifecycle_status as competing_value,
    'salesforce' as authoritative_source_system,
    source.source_system as competing_source_system,
    source.source_record_id as competing_source_record_id,
    source.event_id as competing_event_id,
    source.source_updated_at as observed_at,
    'open_evidence' as review_status
from current_sources source
inner join authoritative using (account_id)
where source.source_system <> 'salesforce'
  and source.observed_lifecycle_status is not null
  and source.observed_lifecycle_status <> authoritative.authoritative_value
