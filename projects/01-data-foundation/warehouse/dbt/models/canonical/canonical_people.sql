with person_ids as (
    select
        canonical_entity_id as person_id,
        min(valid_from) as created_at,
        max(reviewed_at) as identity_reviewed_at,
        count(distinct source_record_id) as resolved_source_count
    from {{ ref('int_active_identity_mappings') }}
    where canonical_entity_type = 'Person'
    group by canonical_entity_id
)
select
    person_id,
    cast(null as varchar) as display_name,
    cast(null as varchar) as primary_email_normalized,
    'active' as identity_status,
    created_at,
    identity_reviewed_at as updated_at,
    resolved_source_count
from person_ids
